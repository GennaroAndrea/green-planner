"""Admin CLI for chat access (Q54): talks to a running server's /api/admin endpoints.
Short form: ./chat <command> (same commands).

    ./chat status
    ./chat codes 10 [--budget 0.30] [--expires "2026-10-01 23:59"] [--label giuria]
    ./chat sessions
    ./chat revoke <session-id>
    ./chat revoke-all [--yes]
    ./chat disable | enable

The admin secret is read from GREEN_PLANNER_ADMIN_SECRET (environment or the project's `.env`).
The server is the one scripts/demo.sh is running (http or https, any port: the launcher writes
its address to data/interim/demo_url), else http://127.0.0.1:8080; --url or GREEN_PLANNER_URL
point elsewhere. HTTPS certificates are verified against the system's CAs plus the project's
self-signed tls/cert.pem (Q55).
"""

import argparse
import os
import ssl
import sys
from datetime import datetime
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
URL_FILE = Path(__file__).resolve().parent.parent / "data" / "interim" / "demo_url"
LOCAL_CERT = Path(__file__).resolve().parent.parent / "tls" / "cert.pem"
DEFAULT_URL = "http://127.0.0.1:8080"


def load_env_file(path: Path = ENV_FILE) -> None:
    """KEY=VALUE lines from .env, without overriding variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def default_url() -> str:
    """GREEN_PLANNER_URL, else the server scripts/demo.sh is running (it writes its address to
    data/interim/demo_url, http or https), else http://127.0.0.1:8080."""
    if os.environ.get("GREEN_PLANNER_URL"):
        return os.environ["GREEN_PLANNER_URL"]
    if URL_FILE.is_file() and (url := URL_FILE.read_text().strip()):
        return url
    return DEFAULT_URL


def tls_context() -> ssl.SSLContext:
    """The system's trusted CAs (public URLs such as ngrok) plus our self-signed certificate
    (the backend served with --https), so verification always stays on."""
    ctx = ssl.create_default_context()
    if LOCAL_CERT.is_file():
        ctx.load_verify_locations(LOCAL_CERT)
    return ctx


def default_expiry() -> datetime:
    """End of today, local time."""
    return datetime.now().astimezone().replace(hour=23, minute=59, second=0, microsecond=0)


def parse_expiry(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()


def fmt_time(value: int | None) -> str:
    return datetime.fromtimestamp(value).strftime("%d/%m %H:%M") if value else "-"


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    p = argparse.ArgumentParser(prog="python -m backend.admin", description=__doc__.split("\n")[0])
    p.add_argument("--url", default=default_url(), help=f"server (default: {default_url()})")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="chat switch, code and session counts")
    c = sub.add_parser("create-codes", aliases=["codes"], help="new single-use access codes")
    c.add_argument("count", type=int)
    c.add_argument("--expires", type=parse_expiry, default=None,
                   help='"YYYY-MM-DD HH:MM", local time (default: today 23:59)')  # fmt: skip
    c.add_argument("--label", help="e.g. giuria, prova")
    c.add_argument("--budget", type=float, default=0.30,
                   help="API spending allowed per session, in USD (default 0.30)")  # fmt: skip
    sub.add_parser("sessions", help="all sessions with spending, budget and token usage")
    r = sub.add_parser("revoke", help="end one session")
    r.add_argument("session_id")
    ra = sub.add_parser("revoke-all", help="end every session and invalidate unused codes")
    ra.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    sub.add_parser("disable", help="switch the chat off (sessions are kept)")
    sub.add_parser("enable", help="switch the chat back on")
    args = p.parse_args(argv)

    secret = os.environ.get("GREEN_PLANNER_ADMIN_SECRET")
    if not secret:
        print("GREEN_PLANNER_ADMIN_SECRET is not set (environment or .env)", file=sys.stderr)
        return 2
    client = httpx.Client(
        base_url=args.url.rstrip("/"),
        headers={"Authorization": f"Bearer {secret}"},
        timeout=15,
        verify=tls_context(),
    )

    def call(method: str, path: str, **kw):
        try:
            resp = client.request(method, f"/api/admin{path}", **kw)
        except httpx.HTTPError as e:
            sys.exit(f"cannot reach {args.url}: {e}")
        if resp.status_code == 404 and path == "/status":
            sys.exit(f"{args.url}: chat access is not configured on this server")
        if resp.is_error:
            sys.exit(f"{resp.status_code}: {resp.text}")
        return resp.json()

    if args.cmd == "status":
        s = call("GET", "/status")
        codes = s["codes"]
        print(f"chat: {'ON' if s['enabled'] else 'OFF'}  ({args.url})")
        err = s.get("model_error")
        if not s.get("model_configured"):
            print("model: NOT CONFIGURED (no ANTHROPIC_API_KEY): the chat is hidden")
        elif err and err["kind"] == "credit_exhausted":
            print(f"model: ERROR, Anthropic credit exhausted since {err['at'][11:16]}: "
                  "add credits in the Claude Console (Billing)")  # fmt: skip
        elif err:
            print(
                f"model: ERROR, API key rejected since {err['at'][11:16]}: check ANTHROPIC_API_KEY"
            )
        else:
            print("model: ok")
        if s.get("test_mode"):
            print("test mode: ON (questions starting with /test get canned answers, no API call)")
        print(f"sessions: {s['sessions_active']} active / {s['sessions_total']} total, "
              f"${s['spent_usd']:.2f} spent in all")  # fmt: skip
        print(f"codes: {codes['unused']} unused, {codes['used']} used, "
              f"{codes['dead']} expired or revoked")  # fmt: skip
    elif args.cmd in ("create-codes", "codes"):
        expires = args.expires or default_expiry()
        body = {"count": args.count, "expires_at": expires.isoformat(), "label": args.label,
                "budget_usd": args.budget}  # fmt: skip
        res = call("POST", "/codes", json=body)
        print(f"{len(res['codes'])} codes, valid until {expires:%d/%m/%Y %H:%M}, "
              f"${res['budget_usd']:.2f} of API spending per session "
              "(each works once; they are not stored, keep this list):")  # fmt: skip
        for code in res["codes"]:
            print(f"  {code}")
    elif args.cmd == "sessions":
        rows = call("GET", "/sessions")
        if not rows:
            print("no sessions")
        print(f"{'id':<9}{'label':<12}{'state':<9}{'opened':<13}{'expires':<13}"
              f"{'spent / budget':>16}{'questions':>10}{'in tok':>9}{'out tok':>9}"
              f"{'cached':>9}")  # fmt: skip
        for s in rows:
            state = "active" if s["active"] else ("revoked" if s["revoked_at"] else "expired")
            label = (s["label"] or "-")[:11]
            print(f"{s['id']:<9}{label:<12}{state:<9}"
                  f"{fmt_time(s['created_at']):<13}{fmt_time(s['expires_at']):<13}"
                  f"{'$' + format(s['spent_usd'], '.3f'):>9} / ${s['budget_usd']:<4.2f}"
                  f"{s['questions']:>10}{s['input_tokens']:>9}{s['output_tokens']:>9}"
                  f"{s['cache_read_tokens']:>9}")  # fmt: skip
    elif args.cmd == "revoke":
        call("POST", f"/sessions/{args.session_id}/revoke")
        print(f"session {args.session_id} revoked")
    elif args.cmd == "revoke-all":
        if not args.yes and input("Revoke every session and unused code? [y/N] ").lower() != "y":
            return 1
        res = call("POST", "/revoke-all")
        print(f"revoked {res['sessions']} sessions and {res['codes']} unused codes")
    elif args.cmd in ("disable", "enable"):
        res = call("PUT", "/chat", json={"enabled": args.cmd == "enable"})
        print(f"chat: {'ON' if res['enabled'] else 'OFF'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

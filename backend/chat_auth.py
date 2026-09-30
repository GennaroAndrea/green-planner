"""Access control for the AI chat (Q54).

The server issues single-use access codes (admin API, `python -m backend.admin`). A visitor
redeems a code once and gets a session in an HttpOnly cookie. Codes and sessions expire at the
time set when the codes are created, and an admin can revoke one session, revoke everything, or
switch the chat off. Each session has a budget in US dollars (set per batch of codes, default
$0.30): the chat's API usage is priced (backend/chat_pricing.py) and added to the session, and a
session whose spending has reached its budget can't ask more questions.

Only the chat is gated: the map and every other /api endpoint stay public.

Configuration (environment, e.g. a local `.env` passed to uvicorn with `--env-file .env`):
- GREEN_PLANNER_ADMIN_SECRET: required. Without it the chat is unavailable and the admin API
  answers 404 (the Render deploy runs this way, Q54: chat on the laptop only).
- GREEN_PLANNER_CHAT_DB: SQLite file (default data/interim/chat_auth.sqlite, gitignored).

Stored secrets are never usable as-is: codes are kept as an HMAC keyed with the admin secret
(a leaked database can't be brute-forced without it), session tokens as a SHA-256 hash.
"""

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.chat_pricing import Usage, cost_usd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "interim" / "chat_auth.sqlite"
DEFAULT_BUDGET_USD = 0.30
MAX_BUDGET_USD = 5.0

COOKIE = "gp_chat"
COOKIE_PATH = "/api"
# Unambiguous on a phone keyboard: no 0/O, 1/I/L. 8 characters ≈ 40 bits.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8
MAX_CODES_PER_REQUEST = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS codes (
    code_hash   TEXT PRIMARY KEY,
    label       TEXT,
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    budget_usd  REAL NOT NULL,
    used_at     INTEGER,
    session_id  TEXT,
    revoked_at  INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
    id                 TEXT PRIMARY KEY,
    token_hash         TEXT NOT NULL UNIQUE,
    label              TEXT,
    created_at         INTEGER NOT NULL,
    expires_at         INTEGER NOT NULL,
    revoked_at         INTEGER,
    last_used_at       INTEGER,
    budget_usd         REAL NOT NULL,
    spent_usd          REAL NOT NULL DEFAULT 0,
    questions          INTEGER NOT NULL DEFAULT 0,
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def normalise_code(code: str) -> str:
    """Accept lowercase, spaces and dashes: 'k7qm-4rxp' → 'K7QM4RXP'."""
    return "".join(c for c in code.upper() if c.isalnum())


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


@dataclass(frozen=True)
class Session:
    id: str
    label: str | None
    expires_at: int
    budget_usd: float
    spent_usd: float

    @property
    def has_budget(self) -> bool:
        return self.spent_usd < self.budget_usd


class AuthStore:
    """SQLite-backed codes, sessions and the chat on/off switch. Thread-safe (one lock)."""

    def __init__(self, db_path: Path, secret: str):
        if not secret:
            raise ValueError("an admin secret is required")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._key = secret.encode()

    def is_admin(self, secret: str) -> bool:
        return hmac.compare_digest(secret.encode(), self._key)

    # --- hashing -------------------------------------------------------------------------
    def _code_hash(self, code: str) -> str:
        return hmac.new(self._key, normalise_code(code).encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    # --- switch --------------------------------------------------------------------------
    def enabled(self) -> bool:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = 'enabled'").fetchone()
        return row is None or row["value"] == "1"

    def set_enabled(self, on: bool) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO settings (key, value) VALUES ('enabled', ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                ("1" if on else "0",),
            )

    # --- codes ---------------------------------------------------------------------------
    def create_codes(
        self, count: int, expires_at: int, label: str | None = None,
        budget_usd: float = DEFAULT_BUDGET_USD,
    ) -> list[str]:  # fmt: skip
        """New single-use codes; the plain codes are returned once and never stored. Each
        code's session gets `budget_usd` of API spending."""
        now = int(time.time())
        codes = [
            "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH)) for _ in range(count)
        ]
        with self._lock:
            self._db.executemany(
                "INSERT INTO codes (code_hash, label, created_at, expires_at, budget_usd) "
                "VALUES (?, ?, ?, ?, ?)",
                [(self._code_hash(c), label, now, expires_at, budget_usd) for c in codes],
            )
        return [format_code(c) for c in codes]

    def redeem(self, code: str) -> tuple[str, Session] | None:
        """Single use: marks the code used and opens a session. None if invalid, used, expired
        or revoked (deliberately indistinguishable to the caller)."""
        now = int(time.time())
        code_hash = self._code_hash(code)
        session_id = secrets.token_hex(4)
        token = secrets.token_urlsafe(32)
        with self._lock:
            row = self._db.execute(
                "UPDATE codes SET used_at = ?, session_id = ? WHERE code_hash = ? "
                "AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ? "
                "RETURNING label, expires_at, budget_usd",
                (now, session_id, code_hash, now),
            ).fetchone()
            if row is None:
                return None
            self._db.execute(
                "INSERT INTO sessions (id, token_hash, label, created_at, expires_at, "
                "budget_usd) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, self._token_hash(token), row["label"], now, row["expires_at"],
                 row["budget_usd"]),
            )  # fmt: skip
        return token, Session(session_id, row["label"], row["expires_at"], row["budget_usd"], 0.0)

    # --- sessions ------------------------------------------------------------------------
    def session(self, token: str) -> Session | None:
        """The active session for a token, or None (unknown, expired or revoked)."""
        with self._lock:
            row = self._db.execute(
                "SELECT id, label, expires_at, budget_usd, spent_usd FROM sessions "
                "WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?",
                (self._token_hash(token), int(time.time())),
            ).fetchone()
        return Session(**dict(row)) if row else None

    def session_by_id(self, session_id: str) -> Session | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, label, expires_at, budget_usd, spent_usd FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return Session(**dict(row)) if row else None

    def start_question(self, session_id: str) -> bool:
        """Count a new question if the session still has budget; False once it is spent.
        The budget is checked before a question, so the last question may overshoot it by
        that question's cost."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE sessions SET questions = questions + 1, last_used_at = ? "
                "WHERE id = ? AND spent_usd < budget_usd",
                (int(time.time()), session_id),
            )
        return cur.rowcount == 1

    def record_usage(self, session_id: str, model: str, usage: Usage) -> float:
        """Price one API response and add it to the session; returns its cost in USD."""
        cost = cost_usd(model, usage)
        with self._lock:
            self._db.execute(
                "UPDATE sessions SET spent_usd = spent_usd + ?, input_tokens = input_tokens + ?, "
                "output_tokens = output_tokens + ?, cache_read_tokens = cache_read_tokens + ?, "
                "cache_write_tokens = cache_write_tokens + ? WHERE id = ?",
                (cost, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens,
                 usage.cache_write_5m_tokens + usage.cache_write_1h_tokens, session_id),
            )  # fmt: skip
        return cost

    def end_session(self, session_id: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (int(time.time()), session_id),
            )
        return cur.rowcount == 1

    def revoke_all(self) -> dict[str, int]:
        """Revoke every active session and every unused code."""
        now = int(time.time())
        with self._lock:
            s = self._db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL", (now,)
            ).rowcount
            c = self._db.execute(
                "UPDATE codes SET revoked_at = ? WHERE used_at IS NULL AND revoked_at IS NULL",
                (now,),
            ).rowcount
        return {"sessions": s, "codes": c}

    # --- listings (admin) ----------------------------------------------------------------
    def list_sessions(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM sessions ORDER BY created_at").fetchall()
        now = int(time.time())
        out = []
        for r in rows:
            d = dict(r)
            d.pop("token_hash")
            d["active"] = d["revoked_at"] is None and d["expires_at"] > now
            out.append(d)
        return out

    def code_counts(self) -> dict[str, int]:
        now = int(time.time())
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(used_at IS NOT NULL) AS used, "
                "SUM(used_at IS NULL AND revoked_at IS NULL AND expires_at > ?) AS unused, "
                "SUM(used_at IS NULL AND (revoked_at IS NOT NULL OR expires_at <= ?)) AS dead "
                "FROM codes",
                (now, now),
            ).fetchone()
        return {k: int(row[k] or 0) for k in ("total", "used", "unused", "dead")}


def auth_from_env() -> AuthStore | None:
    secret = os.environ.get("GREEN_PLANNER_ADMIN_SECRET", "")
    if not secret:
        return None
    db = Path(os.environ.get("GREEN_PLANNER_CHAT_DB", DEFAULT_DB))
    return AuthStore(db, secret)


# --- API --------------------------------------------------------------------------------


class ChatStatus(BaseModel):
    available: bool = Field(description="Chat configured on this server and switched on")
    authenticated: bool
    expires_at: datetime | None = None
    budget_usd: float | None = None
    spent_usd: float | None = None


class RedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class CodesRequest(BaseModel):
    count: int = Field(ge=1, le=MAX_CODES_PER_REQUEST)
    expires_at: datetime = Field(description="When the codes and their sessions stop working")
    label: str | None = Field(default=None, max_length=60)
    budget_usd: float = Field(
        default=DEFAULT_BUDGET_USD, gt=0, le=MAX_BUDGET_USD, description="API spending per session"
    )


class CodesResponse(BaseModel):
    codes: list[str]
    expires_at: datetime
    budget_usd: float


class SwitchRequest(BaseModel):
    enabled: bool


def get_auth(request: Request) -> AuthStore | None:
    return request.app.state.chat_auth


AuthDep = Annotated[AuthStore | None, Depends(get_auth)]


def _ts(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch).astimezone()


def _available(request: Request, auth: AuthStore | None) -> bool:
    """Access configured and switched on, and a model client (ANTHROPIC_API_KEY) present."""
    ready = getattr(request.app.state, "chat_client", None) is not None
    return auth is not None and ready and auth.enabled()


def _status(request: Request, auth: AuthStore | None, s: Session | None) -> ChatStatus:
    available = _available(request, auth)
    if not (available and s):
        return ChatStatus(available=available, authenticated=False)
    return ChatStatus(
        available=True,
        authenticated=True,
        expires_at=_ts(s.expires_at),
        budget_usd=s.budget_usd,
        spent_usd=round(s.spent_usd, 4),
    )


def _current(request: Request, auth: AuthStore | None) -> Session | None:
    token = request.cookies.get(COOKIE)
    return auth.session(token) if auth and token else None


def require_chat_session(request: Request, auth: AuthDep) -> Session:
    """Dependency for the chat endpoint: an active session on an available chat. It doesn't
    count the question or check the budget: call `AuthStore.start_question` (False → 402), then
    `AuthStore.record_usage` after each API response."""
    if not _available(request, auth):
        raise HTTPException(503, "chat unavailable")
    s = _current(request, auth)
    if s is None:
        raise HTTPException(401, "no active chat session")
    return s


def require_admin(request: Request, auth: AuthDep) -> AuthStore:
    if auth is None:  # not configured: the admin API doesn't exist on this server
        raise HTTPException(404)
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or not auth.is_admin(header.removeprefix("Bearer ")):
        raise HTTPException(401, "invalid admin secret")
    return auth


AdminDep = Annotated[AuthStore, Depends(require_admin)]

router = APIRouter(prefix="/api")


@router.get("/chat/status", response_model=ChatStatus, tags=["chat"])
def chat_status(request: Request, auth: AuthDep) -> ChatStatus:
    return _status(request, auth, _current(request, auth))


@router.post("/chat/session", response_model=ChatStatus, tags=["chat"])
def chat_login(body: RedeemRequest, request: Request, response: Response, auth: AuthDep):
    """Redeem a single-use access code; the session goes in an HttpOnly cookie."""
    if not _available(request, auth):
        raise HTTPException(503, "chat unavailable")
    redeemed = auth.redeem(body.code)
    if redeemed is None:
        raise HTTPException(401, "invalid code")
    token, s = redeemed
    response.set_cookie(
        COOKIE, token, max_age=max(0, s.expires_at - int(time.time())), path=COOKIE_PATH,
        httponly=True, secure=True, samesite="strict",
    )  # fmt: skip
    return _status(request, auth, s)


@router.delete("/chat/session", response_model=ChatStatus, tags=["chat"])
def chat_logout(request: Request, response: Response, auth: AuthDep) -> ChatStatus:
    s = _current(request, auth)
    if auth and s:
        auth.end_session(s.id)
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, secure=True, samesite="strict")
    return _status(request, auth, None)


@router.post("/admin/codes", response_model=CodesResponse, tags=["admin"])
def admin_create_codes(body: CodesRequest, auth: AdminDep) -> CodesResponse:
    expires = body.expires_at
    if expires.tzinfo is None:  # a naive time is read as the server's local time
        expires = expires.astimezone()
    epoch = int(expires.timestamp())
    if epoch <= time.time():
        raise HTTPException(422, "expires_at is in the past")
    codes = auth.create_codes(body.count, epoch, body.label, body.budget_usd)
    return CodesResponse(codes=codes, expires_at=expires, budget_usd=body.budget_usd)


@router.get("/admin/status", tags=["admin"])
def admin_status(request: Request, auth: AdminDep) -> dict:
    sessions = auth.list_sessions()
    state = request.app.state
    return {
        "enabled": auth.enabled(),
        "model_configured": getattr(state, "chat_client", None) is not None,
        "model_error": getattr(state, "chat_model_error", None),
        "test_mode": os.environ.get("GREEN_PLANNER_CHAT_TEST_MODE", "") == "1",
        "codes": auth.code_counts(),
        "spent_usd": round(sum(s["spent_usd"] for s in sessions), 4),
        "sessions_active": sum(s["active"] for s in sessions),
        "sessions_total": len(sessions),
    }


@router.get("/admin/sessions", tags=["admin"])
def admin_sessions(auth: AdminDep) -> list[dict]:
    return auth.list_sessions()


@router.post("/admin/sessions/{session_id}/revoke", tags=["admin"])
def admin_revoke(session_id: str, auth: AdminDep) -> dict:
    if not auth.end_session(session_id):
        raise HTTPException(404, "no active session with this id")
    return {"revoked": session_id}


@router.post("/admin/revoke-all", tags=["admin"])
def admin_revoke_all(auth: AdminDep) -> dict:
    return auth.revoke_all()


@router.put("/admin/chat", tags=["admin"])
def admin_switch(body: SwitchRequest, auth: AdminDep) -> dict:
    auth.set_enabled(body.enabled)
    return {"enabled": auth.enabled()}


def install(app: FastAPI, auth: AuthStore | None) -> None:
    app.state.chat_auth = auth
    app.include_router(router)

"""AI chat (FR-54, Q56): tools, streaming endpoint with a fake Claude client, number check.

The tools run on the committed data snapshot (deploy/data/); assertions check the format, not
exact results, so they survive a rebuild of the data.
"""

import json
import time
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient

from backend.chat import MAX_TOOL_ROUNDS, MODEL, ProjectTools, ToolError, it
from backend.chat_auth import AuthStore
from backend.chat_numbers import correct_results, unverified_numbers
from backend.main import PROJECT_ROOT, create_app
from backend.store import Store

SNAPSHOT = PROJECT_ROOT / "deploy" / "data"
SECRET = "chat-test-secret"
ADMIN = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture(scope="module")
def store():
    return Store(SNAPSHOT)


# --- tools ----------------------------------------------------------------------------------


def test_italian_numbers():
    assert it(1678, 0) == "1.678" and it(91.4655) == "91,5" and it(0.2222, 3) == "0,222"


def test_zone_lookup_is_forgiving(store):
    t = ProjectTools(store)
    assert t.zone_id("liberta") == t.zone_id("Libertà") == t.zone_id("LIBERTA'")
    assert t.zone_id("palese") == t.zone_id("Palese - Macchie")
    with pytest.raises(ToolError, match="Quartieri validi"):
        t.zone_id("Roma")


def test_zone_card_text(store):
    text = ProjectTools(store).zone("Libertà")
    for part in ("Quartiere Libertà: IPF", "classe", "su 16 quartieri", "Robustezza",
                 "Carenza di vegetazione: punteggio", "Alberi: stima", "residenti"):  # fmt: skip
        assert part in text
    assert "nan" not in text.lower() and "None" not in text


def test_ranking_text(store):
    t = ProjectTools(store)
    top = t.ranking("quartieri", 3, "highest_first").splitlines()
    assert top[0].startswith("Classifica IPF") and top[1].startswith("- 1° ")
    assert len(top) == 4
    bottom = t.ranking("quartieri", 1, "lowest_first").splitlines()
    assert bottom[1].startswith("- 16° ")
    cells = t.ranking("celle_250", 2, "highest_first")
    assert "cella 250-" in cells and "celle da 250 m" in cells
    assert len(t.ranking("quartieri", 999, "highest_first").splitlines()) == 17  # capped


def test_simulation_text(store):
    text = ProjectTools(store).simulate("Libertà", 1000)
    assert "1.000 nuovi alberi" in text and "- Prima:" in text and "- Dopo:" in text
    with pytest.raises(ToolError):
        ProjectTools(store).simulate("Libertà", -5)


# --- number check -----------------------------------------------------------------------------


SOURCE = ["IPF 91,5/100, 4° su 16. Vegetazione 3,0% (obiettivo 15%). Alberi 1.678. "
          "Carenza di vegetazione: punteggio 93,9 × peso 0,333 (33,3%)."]  # fmt: skip


@pytest.mark.parametrize(
    "answer, bad",
    [
        ("IPF 91,5, quarta su 16, 1.678 alberi, vegetazione del 3%.", []),  # rounding ok
        ("Peso 33% (0,33) e quota 0,03.", []),  # share ↔ percent
        ("0,333 × 93,9 = 31,3 punti; 0,33 x 93,9 = 31,0.", []),  # correct operations
        ("(0,333 × 93,9) + 60,2 = 91,5", ["60,2"]),  # the unsourced operand is flagged
        ("0,333 × 93,9 = 45,0", ["45,0"]),  # wrong result
        ("IPF 97,2 e 2.500 alberi; PM10 e NO2 non sono numeri.", ["97,2", "2.500"]),
        # LaTeX (Q59): same checks after translation to plain text
        (r"$0{,}333 \times 93{,}9 = 31{,}3$ e $$\text{IPF} = \sum_i w_i \cdot s_i$$", []),
        (r"$0,333 \cdot 93,9 = 31,3$ e $\frac{3}{9} = 0{,}333$", []),
        (r"$0{,}333 \times 93{,}9 = 45{,}0$", ["45,0"]),
        (r"IPF $= 97{,}2$", ["97,2"]),
    ],
)
def test_number_check(answer, bad):
    assert unverified_numbers(answer, SOURCE) == bad


def test_correct_results_percent_operand():
    assert correct_results("22% × 94 = 20,7") == {"20,7"}


# --- endpoint with a fake Claude client ---------------------------------------------------------


def _block(kind, **kw):
    return SimpleNamespace(type=kind, **kw)


def _usage(inp=1000, out=100):
    return SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0, cache_creation=None)  # fmt: skip


class FakeStream:
    def __init__(self, turn):
        self.turn = turn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for block in self.turn["content"]:
                if block.type == "text":
                    for word in block.text.split(" "):
                        yield SimpleNamespace(type="text", text=word + " ")

        return gen()

    async def get_final_message(self):
        return SimpleNamespace(content=self.turn["content"], stop_reason=self.turn["stop"],
                               usage=_usage())  # fmt: skip


class FakeClient:
    """Replays scripted turns and records the requests."""

    def __init__(self, turns):
        self.turns, self.calls = list(turns), []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: vars(o))))
        return FakeStream(self.turns.pop(0))


def _events(resp) -> list[tuple[str, dict]]:
    out = []
    for chunk in resp.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture
def setup(tmp_path):
    auth = AuthStore(tmp_path / "auth.sqlite", SECRET)

    def make(turns, budget=0.30):
        fake = FakeClient(turns)
        app = create_app(SNAPSHOT, chat_auth=auth, chat_client=fake)
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()  # run the lifespan: loads the store
        (code,) = auth.create_codes(1, int(time.time()) + 3600, "test", budget)
        assert client.post("/api/chat/session", json={"code": code}).status_code == 200
        return client, fake

    return make


def test_chat_stream_with_tool(setup, store):
    ipf = it(ProjectTools(store).store.levels["zones"].frame.loc[
        ProjectTools(store).zone_id("Libertà"), "ipf"])  # fmt: skip
    turns = [
        {
            "content": [
                _block("text", text="Controllo."),
                _block("tool_use", id="t1", name="get_zone", input={"name": "liberta"}),
            ],
            "stop": "tool_use",
        },  # fmt: skip
        {
            "content": [_block("text", text=f"Libertà ha IPF {ipf} e 1.234.567 abitanti.")],
            "stop": "end_turn",
        },  # fmt: skip
    ]
    client, fake = setup(turns)
    resp = client.post("/api/chat", json={"message": "Perché Libertà è prioritaria?"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    events = _events(resp)
    kinds = [e for e, _ in events]
    assert kinds[0] == "delta" and "status" in kinds and kinds[-1] == "done"
    assert dict(events)["status"]["text"] == "Consulto la scheda di liberta…"
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert ipf in text
    done = events[-1][1]
    assert done["unverified"] == ["1.234.567"]  # invented number flagged, answer kept
    # Two API calls priced: 2 × (1000 input × $1 + 100 output × $5) / 1M = $0.003
    assert done["spent_usd"] == pytest.approx(0.003) and done["budget_usd"] == 0.30
    # Request shape: Haiku, system with the methodology cached, strict tools, no thinking
    first = fake.calls[0]
    assert first["model"] == MODEL == "claude-haiku-4-5" and "thinking" not in first
    assert "<methodology>" in first["system"][1]["text"]
    assert first["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert {t["name"] for t in first["tools"]} == {"get_ranking", "get_zone", "simulate_zone"}
    assert all(t["strict"] for t in first["tools"])
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "Quartiere Libertà" in tool_result["content"]

    history = client.get("/api/chat/history").json()
    assert history[0]["question"] == "Perché Libertà è prioritaria?"
    assert history[0]["unverified"] == ["1.234.567"]


def test_memory_and_clear(setup):
    turns = [{"content": [_block("text", text=f"Risposta {i}.")], "stop": "end_turn"}
             for i in range(3)]  # fmt: skip
    client, fake = setup(turns)
    client.post("/api/chat", json={"message": "Prima domanda"})
    client.post("/api/chat", json={"message": "E poi?"})
    msgs = fake.calls[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "Prima domanda" and msgs[1]["content"] == "Risposta 0."
    client.delete("/api/chat/history")
    client.post("/api/chat", json={"message": "Nuova"})
    assert len(fake.calls[2]["messages"]) == 1


def test_tool_rounds_are_capped(setup):
    loop = {"content": [_block("tool_use", id="t", name="get_ranking",
                               input={"level": "quartieri", "limit": 3, "order": "highest_first"})],
            "stop": "tool_use"}  # fmt: skip
    client, fake = setup([loop] * (MAX_TOOL_ROUNDS - 1) + [
        {"content": [_block("text", text="Fine.")], "stop": "end_turn"}])  # fmt: skip
    kinds = [e for e, _ in _events(client.post("/api/chat", json={"message": "Classifica"}))]
    assert kinds[-1] == "done" and len(fake.calls) == MAX_TOOL_ROUNDS
    assert fake.calls[-1]["tool_choice"] == {"type": "none"}  # the last round must answer


def test_bad_tool_input_is_reported_to_the_model(setup):
    client, fake = setup([
        {"content": [_block("tool_use", id="t", name="get_zone", input={"name": "Roma"})],
         "stop": "tool_use"},
        {"content": [_block("text", text="Roma non è un quartiere di Bari.")], "stop": "end_turn"},
    ])  # fmt: skip
    _events(client.post("/api/chat", json={"message": "E Roma?"}))
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "Quartieri validi" in result["content"]


def test_budget_exhausted(setup):
    client, _ = setup([{"content": [_block("text", text="Ok.")], "stop": "end_turn"}],
                      budget=0.001)  # fmt: skip
    assert client.post("/api/chat", json={"message": "Domanda"}).status_code == 200
    # $0.0015 spent ≥ $0.001: no new question
    r = client.post("/api/chat", json={"message": "Altra"})
    assert r.status_code == 402 and "credito" in r.json()["detail"]


def test_requires_session_and_valid_message(setup, tmp_path):
    client, _ = setup([])
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 1001}).status_code == 422
    anon = TestClient(client.app, base_url="https://testserver")
    assert anon.post("/api/chat", json={"message": "Ciao"}).status_code == 401
    assert anon.get("/api/chat/history").status_code == 401


# --- test mode and model errors -----------------------------------------------------------------


def test_test_mode_canned_answers(setup, monkeypatch):
    from backend import chat_test

    monkeypatch.setenv("GREEN_PLANNER_CHAT_TEST_MODE", "1")
    monkeypatch.setattr(chat_test, "FIRST_TOKEN_DELAY_S", 0)
    monkeypatch.setattr(chat_test, "TOOL_DELAY_S", 0)
    monkeypatch.setattr(chat_test, "WORD_DELAY_S", 0)
    client, fake = setup([])  # the model must never be called
    seen = []
    for i in range(len(chat_test.TEST_SCRIPT) + 1):
        events = _events(client.post("/api/chat", json={"message": f"/test domanda {i}"}))
        text = "".join(d["text"] for e, d in events if e == "delta")
        seen.append(text)
        done = events[-1][1]
        assert events[-1][0] == "done"
        if i == 5:  # the answer with an invented number
            assert done["unverified"] == ["23.456"]
        else:
            assert done["unverified"] == [], (i, done["unverified"])
    assert fake.calls == []
    assert seen[-1] == seen[0]  # cycles
    assert "Madonnella" in seen[0] and "Japigia" in seen[1]
    # ~$0.006 charged per canned answer, like a real one
    assert done["spent_usd"] == pytest.approx(7 * 0.00595, abs=1e-4)  # rounded to 4 decimals
    history = client.get("/api/chat/history").json()
    assert len(history) == 7 and history[0]["question"] == "/test domanda 0"


def test_test_command_ignored_when_mode_off(setup, monkeypatch):
    monkeypatch.delenv("GREEN_PLANNER_CHAT_TEST_MODE", raising=False)
    client, fake = setup([{"content": [_block("text", text="Risposta vera.")], "stop": "end_turn"}])
    _events(client.post("/api/chat", json={"message": "/test ciao"}))
    assert len(fake.calls) == 1  # went to the model


class FailingClient:
    def __init__(self, exc):
        self.exc, self.messages = exc, self

    def stream(self, **kw):
        raise self.exc


def _api_error(cls, status, message):
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(status, request=req, headers={"request-id": "req_test"})
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    return cls(message, response=resp, body=body)


@pytest.mark.parametrize(
    "exc, kind, ui",
    [
        (lambda: _api_error(anthropic.BadRequestError, 400, "Your credit balance is too low to "
                            "access the Anthropic API."), "credit_exhausted", "unavailable"),
        (lambda: _api_error(anthropic.AuthenticationError, 401, "invalid x-api-key"),
         "key_rejected", "unavailable"),
        (lambda: _api_error(anthropic.BadRequestError, 400, "something else"), None, "generic"),
    ],
)  # fmt: skip
def test_model_errors(tmp_path, exc, kind, ui):
    from backend.chat import ERRORS

    auth = AuthStore(tmp_path / "auth.sqlite", SECRET)
    app = create_app(SNAPSHOT, chat_auth=auth, chat_client=FailingClient(exc()))
    with TestClient(app, base_url="https://testserver") as client:
        (code,) = auth.create_codes(1, int(time.time()) + 3600)
        client.post("/api/chat/session", json={"code": code})
        events = _events(client.post("/api/chat", json={"message": "Domanda"}))
        assert events == [("error", {"message": ERRORS[ui]})]
        status = client.get("/api/admin/status", headers=ADMIN).json()
        assert (status["model_error"] or {}).get("kind") == kind
        assert status["model_configured"] is True

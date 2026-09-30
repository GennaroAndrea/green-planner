"""Chat test mode: canned answers for trying the "Chiedi" UI without calling the Claude API.

Enabled with GREEN_PLANNER_CHAT_TEST_MODE=1. A question that starts with "/test" gets the next
answer of TEST_SCRIPT (cycling per session) through the same pipeline as a real one: a real tool
call (status line, sources for the number check), word-by-word streaming at about the model's
pace, the number check, the memory and a charge on the session budget (FAKE_USAGE, priced like a
real Haiku answer, so the credit bar moves). Other questions go to the real model as usual.

The numbers in the answers are the ones of the data at the time of writing (2026-09-30); after a
rebuild they may be flagged as unverified. Answer 6 contains an invented number on purpose.
"""

import asyncio
import os

from backend.chat_pricing import Usage

PREFIX = "/test"
# One reply ≈ 3.000 uncached + 12.000 cached input tokens and 350 output tokens: ~$0.006 on Haiku
FAKE_USAGE = Usage(input_tokens=3000, output_tokens=350, cache_read_tokens=12_000)
FIRST_TOKEN_DELAY_S = 0.8
TOOL_DELAY_S = 0.5
WORD_DELAY_S = 0.025


def enabled() -> bool:
    return os.environ.get("GREEN_PLANNER_CHAT_TEST_MODE", "") == "1"


def is_test(question: str) -> bool:
    return enabled() and question.lstrip().lower().startswith(PREFIX)


# (tool name, tool input or None, answer). Formatted the way Claude usually writes Markdown
# (headings, numbered lists, bold lead-ins, tables, code, quotes), to check how the UI renders it.
TEST_SCRIPT: list[tuple[str | None, dict | None, str]] = [
    (
        "get_zone",
        {"name": "Madonnella"},
        """## Perché Madonnella è al 1° posto

**Madonnella** ha l'IPF più alto di Bari: **97,0/100**, classe *Alta*, 1° su 16 quartieri. \
È anche una priorità **robusta**: resta 1° in tutte le 1000 simulazioni con i pesi variati di \
±5 punti.

Il punteggio nasce da tre fattori quasi al massimo:

1. **Carenza di vegetazione**: $92{,}7 \\times 0{,}333 = 30{,}9$ punti. Dal satellite, solo l'1,9% della \
superficie è vegetato, contro un obiettivo del 15%.
2. **Inquinamento**: $100{,}0 \\times 0{,}222 = 22{,}2$ punti. Le concentrazioni stimate sono in media al \
112,8% dei limiti UE 2030.
3. **Popolazione**: $99,5 \\times 0,222 = 22,1$ punti, con 21.875 abitanti/km².

### In sintesi
- Anche il **traffico** pesa: punteggio 98,1, circa 38.500 veicoli/giorno agli incroci vicini.
- Il modello stima **508 nuovi alberi** nelle celle abitate; per arrivare al 15% di \
vegetazione ne servirebbero 2.046.

> *Nota:* la priorità è relativa. Dice dove intervenire **prima**, non che il quartiere sia \
"cattivo" in assoluto.""",
    ),
    (
        "get_zone",
        {"name": "Japigia"},
        """**Japigia** è al 6° posto su 16, con un IPF di **85,5/100** (classe *Medio-alta*), \
anche qui con una priorità robusta.

Ecco il confronto con Madonnella:

| | Madonnella | Japigia |
|---|---:|---:|
| IPF | 97,0 | 85,5 |
| Posizione | 1° | 6° |
| Vegetazione (satellite) | 1,9% | 6,2% |
| Densità (ab./km²) | 21.875 | 4.070 |
| Alberi stimati | 508 | 4.639 |

La differenza principale è la **vegetazione**: a Japigia la carenza pesa 27,0 punti invece di \
30,9. Il quartiere però è molto più grande (7,29 km² in 125 celle), quindi servono più alberi: \
4.639 nelle celle abitate, più 807 in aree non residenziali.""",
    ),
    (
        "get_zone",
        {"name": "Libertà"},
        """## Come si calcola l'IPF

L'IPF è una **somma pesata** dei punteggi degli indicatori, ciascuno normalizzato da 0 a 100:

$$
\\text{IPF} = \\sum_{i} w_i \\cdot s_i \\qquad \\text{con} \\quad \\sum_{i} w_i = 1, \\quad s_i \\in [0, 100]
$$

### Esempio: Libertà

| Indicatore | Punteggio | Peso | Contributo |
|---|---:|---:|---:|
| Inquinamento | 79,3 | 0,222 | 17,6 |
| Carenza di vegetazione | 93,9 | 0,333 | 31,3 |
| Traffico | 92,3 | 0,222 | 20,5 |
| Popolazione | 99,2 | 0,222 | 22,0 |

Sommando i contributi: $17{,}6 + 31{,}3 + 20{,}5 + 22{,}0 = 91{,}4$. Con i valori non arrotondati si \
ottiene l'IPF di **91,5**, cioè il 4° posto su 16 in classe *Alta*.

**Perché questi pesi?** I pesi di partenza sono 20, 30, 20, 20 e 10 punti. L'indicatore \
`industry` è escluso per ora, quindi gli altri quattro vengono riscalati sul loro totale di 90: \
per esempio la carenza di vegetazione pesa $\\frac{30}{90} = 0{,}333$.""",
    ),
    (
        "simulate_zone",
        {"name": "Libertà", "trees": 2000},
        """Ho simulato **2.000 nuovi alberi a Libertà** (circa 60.000 m² di chioma, 30 m² per \
albero), distribuiti sulle celle abitate.

| | Prima | Dopo |
|---|---:|---:|
| Vegetazione | 3,0% | 6,4% |
| Punteggio carenza | 93,9 | 78,3 |
| IPF | 91,5 | 86,3 |
| Classe | Alta | Medio-alta |
| Posizione | 4° | 4° |

**Cosa significa:**
- l'indice scende di circa 5 punti e il quartiere passa alla classe *Medio-alta*;
- non basta però per l'obiettivo: per arrivare al 15% di vegetazione servirebbero **6.763 \
alberi** (la stima del modello per Libertà è 1.678).

> È una simulazione *indicativa*: gli altri quartieri restano invariati.""",
    ),
    (
        None,
        None,
        "Posso rispondere solo a domande sul progetto **Urban Green Planner** per Bari. Prova per "
        'esempio: *"Perché Libertà è al 4° posto?"*',
    ),
    (
        "get_ranking",
        {"level": "quartieri", "limit": 5, "order": "highest_first"},
        """### I 5 quartieri più prioritari

1. **Madonnella**: IPF 97,0 (*Alta*), 508 alberi stimati
2. **Murat**: IPF 95,9 (*Alta*), 1.397 alberi stimati
3. **San Nicola**: IPF 95,2 (*Alta*), 400 alberi stimati
4. **Libertà**: IPF 91,5 (*Alta*), 1.678 alberi stimati
5. **San Pasquale**: IPF 86,2 (*Medio-alta*), 1.952 alberi stimati

Tutte e cinque sono priorità **robuste**: la loro posizione non cambia variando i pesi di ±5 \
punti.

---

*Risposta di prova con un numero inventato, per vedere l'avviso:* in totale servirebbero \
**23.456 alberi**.""",
    ),
]


async def answer(tools, n: int):
    """The n-th canned answer as (kind, payload) steps: ("status", text), ("tool", text),
    ("delta", text)."""
    tool, args, text = TEST_SCRIPT[n % len(TEST_SCRIPT)]
    await asyncio.sleep(FIRST_TOKEN_DELAY_S)
    if tool:
        yield "status", f"[test] {tool}…"
        yield "tool", await asyncio.to_thread(tools.run, tool, args)
        await asyncio.sleep(TOOL_DELAY_S)
    words = text.split(" ")
    for i, word in enumerate(words):
        yield "delta", word + (" " if i < len(words) - 1 else "")
        await asyncio.sleep(WORD_DELAY_S)

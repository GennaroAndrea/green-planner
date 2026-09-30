"""Number check for chat answers (Q53, Q56).

A number in an answer passes when it matches a number in the sources (the turn's tool results,
the methodology, the question), allowing for rounding and for share ↔ percent conversion, or when
it is the correct result of an operation written in the answer (`0,33 × 94 = 31,3`). The chat
shows a warning under answers with numbers that pass neither test; it never blocks them.

LaTeX in the answer (Q59) is translated to plain text first (`delatex`): `0{,}333 \\times 93{,}9`
reads like `0,333 × 93,9`, `\\frac{30}{90}` like `(30)/(90)`.

Numbers are read in Italian format first (decimal comma, thousands dot) and English format
second, so `1.678` can be 1678 or 1.678 and either reading may match.
"""

import ast
import operator
import re

# A number not glued to letters (skips identifiers such as PM10, NO2, B04, Q49)
_NUM = r"(?<![A-Za-zÀ-ÿ\d])\d+(?:[.,]\d+)*"
NUMBER_RE = re.compile(_NUM + r"(?![A-Za-zÀ-ÿ\d])")
# "expression = result": numbers joined by operators, optional parentheses and % signs
_TERM = r"\(?\s*" + _NUM + r"\s*%?\s*\)?"
_OP = r"\s*(?:[×*·/÷+−–-]|\sx\s)\s*"
EQUATION_RE = re.compile(r"(" + _TERM + r"(?:" + _OP + _TERM + r")+)\s*(?:=|≈|≃)\s*(" + _NUM + r")")

ALWAYS_OK = set(range(11))  # list numbering, "1 su 3", small counts
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv}  # fmt: skip


def readings(token: str) -> set[tuple[float, int]]:
    """Possible (value, decimal places) of a written number, Italian and English conventions."""
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):  # 1.234,5 (Italian)
            dec = token.rsplit(",", 1)[1]
            return {(float(token.replace(".", "").replace(",", ".")), len(dec))}
        dec = token.rsplit(".", 1)[1]  # 1,234.5 (English)
        return {(float(token.replace(",", "")), len(dec))}
    for sep in (",", "."):
        if sep in token:
            parts = token.split(sep)
            out = set()
            if len(parts) == 2:
                out.add((float(parts[0] + "." + parts[1]), len(parts[1])))  # decimal
            if all(len(p) == 3 for p in parts[1:]):
                out.add((float("".join(parts)), 0))  # thousands groups
            return out or {(float("".join(parts)), 0)}
    return {(float(token), 0)}


def primary(token: str) -> float:
    """The most likely value in an Italian answer (used to evaluate operations)."""
    if "," in token:
        if token.rfind(",") > token.rfind("."):  # Italian decimal comma
            return float(token.replace(".", "").replace(",", "."))
        return float(token.replace(",", ""))
    if "." in token:
        head, _, tail = token.rpartition(".")
        if token.count(".") > 1 or (len(tail) == 3 and head not in ("0", "")):
            return float(token.replace(".", ""))
        return float(token)
    return float(token)


def decimals(token: str) -> int:
    """Decimal places as written (Italian comma, or a dot not used for thousands)."""
    if "," in token:
        return len(token.rsplit(",", 1)[1])
    if "." in token:
        head, _, tail = token.rpartition(".")
        if token.count(".") == 1 and not (len(tail) == 3 and head not in ("0", "")):
            return len(tail)
    return 0


def source_values(texts: list[str]) -> set[float]:
    """Every reading of every number in the sources, also ×100 and ÷100 (share ↔ percent)."""
    out: set[float] = set()
    for text in texts:
        for m in NUMBER_RE.finditer(text):
            for v, _ in readings(m.group()):
                out.update((v, v * 100, v / 100))
    return out


def _matches(token: str, allowed: set[float]) -> bool:
    """True if some reading of the token is a rounding of an allowed value (half a unit of
    that reading's last decimal)."""
    return any(abs(v - a) <= 0.5 * 10**-dec + 1e-9 for v, dec in readings(token) for a in allowed)


def _evaluate(expr: str) -> float | None:
    """Value of an operation like '0,33 × 94 + 22%' (None if it can't be read)."""
    numbers: list[float] = []

    def number(m: re.Match) -> str:
        value = primary(m.group(1))
        numbers.append(value / 100 if m.group(2) else value)
        return f" __n{len(numbers) - 1} "

    py = re.sub(r"(" + _NUM + r")\s*(%?)", number, expr)
    py = re.sub(r"\sx\s", " * ", f" {py} ")
    py = py.translate(str.maketrans({"×": "*", "·": "*", "÷": "/", "−": "-", "–": "-"}))
    try:
        tree = ast.parse(py.strip(), mode="eval")
    except SyntaxError:
        return None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Name) and node.id.startswith("__n"):
            return numbers[int(node.id[3:])]
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        raise ValueError

    try:
        return float(ev(tree))
    except (ValueError, ZeroDivisionError, IndexError):
        return None


def correct_results(answer: str) -> set[str]:
    """Results of the operations written in the answer that are right within rounding
    (half a unit of the last written decimal, or 1.5%, for rounded operands)."""
    ok = set()
    for m in EQUATION_RE.finditer(answer):
        value, result = _evaluate(m.group(1)), m.group(2)
        if value is None:
            continue
        target = primary(result)
        tol = max(0.5 * 10 ** -decimals(result), 0.015 * abs(target)) + 1e-9
        if abs(value - target) <= tol:
            ok.add(result)
    return ok


_LATEX_SYMBOLS = {
    r"\times": " × ", r"\cdot": " × ", r"\div": " ÷ ", r"\approx": " ≈ ", r"\simeq": " ≈ ",
    r"\%": "%", r"\left": "", r"\right": "", r"\,": " ", r"\;": " ", r"\!": "", r"\quad": " ",
    r"\qquad": " ",
}  # fmt: skip


def delatex(text: str) -> str:
    """LaTeX maths as plain text, so numbers and operations can be checked."""
    t = text.replace("{,}", ",")
    for _ in range(3):  # nested fractions
        t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\\(?:text|mathrm|mathbf|mathit|textbf|operatorname)\s*\{([^{}]*)\}", r"\1", t)
    for cmd, plain in _LATEX_SYMBOLS.items():
        t = t.replace(cmd, plain)
    t = re.sub(r"\\[A-Za-z]+", " ", t)  # other commands: \sum, \geq, \alpha…
    return t.replace("$", " ").replace("{", "").replace("}", "")


def unverified_numbers(answer: str, sources: list[str]) -> list[str]:
    """Numbers in the answer that no source supports and no correct operation produces."""
    answer = delatex(answer)
    allowed = source_values(sources) | {float(i) for i in ALWAYS_OK}
    computed = correct_results(answer)
    out: list[str] = []
    for m in NUMBER_RE.finditer(answer):
        token = m.group()
        if token in computed or _matches(token, allowed) or token in out:
            continue
        out.append(token)
    return out

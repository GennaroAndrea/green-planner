"""Claude API prices, for the per-session chat budget (Q54).

USD per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing
(checked 2026-09-30). Standard global routing, no batch or fast mode. Update this table if the
chat moves to another model or the prices change: an unknown model is an error, so a cost is
never silently counted as zero.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float
    output: float


PRICES: dict[str, Price] = {
    "claude-haiku-4-5": Price(1.00, 1.25, 2.00, 0.10, 5.00),
    "claude-sonnet-5-5": Price(2.00, 2.50, 4.00, 0.20, 10.00),
}


@dataclass(frozen=True)
class Usage:
    """Token counts of one API response (`response.usage`). `input_tokens` is the uncached
    remainder; cache writes are split by duration (`usage.cache_creation`)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0

    @classmethod
    def from_api(cls, usage) -> "Usage":
        """From the SDK's usage object. Without the per-duration split, all cache writes are
        counted at the 5-minute rate."""
        created = getattr(usage, "cache_creation", None)
        w5 = getattr(created, "ephemeral_5m_input_tokens", None) if created else None
        w1 = getattr(created, "ephemeral_1h_input_tokens", None) if created else None
        if w5 is None and w1 is None:
            w5, w1 = getattr(usage, "cache_creation_input_tokens", 0) or 0, 0
        return cls(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_5m_tokens=w5 or 0,
            cache_write_1h_tokens=w1 or 0,
        )


def cost_usd(model: str, u: Usage) -> float:
    try:
        p = PRICES[model]
    except KeyError:
        msg = f"no price for model {model!r}: add it to backend/chat_pricing.py"
        raise ValueError(msg) from None
    return (
        u.input_tokens * p.input
        + u.cache_write_5m_tokens * p.cache_write_5m
        + u.cache_write_1h_tokens * p.cache_write_1h
        + u.cache_read_tokens * p.cache_read
        + u.output_tokens * p.output
    ) / 1_000_000

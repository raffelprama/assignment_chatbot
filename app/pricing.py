"""Model prices (USD per 1M tokens) used for cost reporting.

Source: https://aistudio.google.com/docs/pricing (redirect target of ai.google.dev/gemini-api/docs/pricing),
read 2026-11-23, Standard (paid) tier. Thinking tokens are billed as output.
`verified=False` rows came from a summary of a truncated page read, not verbatim page text:
re-check them before quoting costs externally. The free tier was listed as "Free of charge" for
the models below, so a free-tier key pays nothing; these figures show what paid usage would cost.
"""

from dataclasses import dataclass

PRICE_TABLE_DATE = "2026-11-23"


@dataclass(frozen=True)
class Price:
    input_per_1m: float
    output_per_1m: float
    verified: bool


PRICES: dict[str, Price] = {
    "gemini-3.5-flash-lite": Price(0.30, 2.50, verified=True),
    "gemini-2.5-flash": Price(0.30, 2.50, verified=False),
    "gemini-2.5-flash-lite": Price(0.10, 0.40, verified=False),
    "gemini-embedding-001": Price(0.15, 0.0, verified=False),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price.input_per_1m + output_tokens * price.output_per_1m) / 1_000_000

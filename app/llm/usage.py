"""Token usage records, read from `AIMessage.usage_metadata` (never estimated)."""

from dataclasses import asdict, dataclass

from app.pricing import cost_usd


@dataclass
class Usage:
    node: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    latency_ms: float = 0.0

    @property
    def cost_usd(self) -> float | None:
        return cost_usd(self.model, self.input_tokens, self.output_tokens)

    def to_dict(self) -> dict:
        return {**asdict(self), "cost_usd": self.cost_usd}


def usage_from_message(message, node: str, model: str, latency_ms: float) -> Usage:
    meta = getattr(message, "usage_metadata", None) or {}
    details = meta.get("output_token_details") or {}
    return Usage(
        node=node,
        model=model,
        input_tokens=int(meta.get("input_tokens", 0)),
        output_tokens=int(meta.get("output_tokens", 0)),
        reasoning_tokens=int(details.get("reasoning", 0)),
        latency_ms=round(latency_ms, 1),
    )


def summarize(usages: list[Usage]) -> dict:
    priced = [u.cost_usd for u in usages if u.cost_usd is not None]
    return {
        "input_tokens": sum(u.input_tokens for u in usages),
        "output_tokens": sum(u.output_tokens for u in usages),
        "reasoning_tokens": sum(u.reasoning_tokens for u in usages),
        "llm_calls": len(usages),
        "cost_usd": round(sum(priced), 6),
        "unpriced_calls": len(usages) - len(priced),
        "models": sorted({u.model for u in usages}),
        "by_call": [u.to_dict() for u in usages],
    }

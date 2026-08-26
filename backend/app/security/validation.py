"""Security validation — prompt injection detection and tool argument guards.

The policy engine is the real defense (deterministic, outside the LLM).
This layer adds detection + audit evidence for the threat model.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts|rules)",
    r"ignore (your |the )?(system|policy|rules)",
    r"you are now",
    r"new system prompt",
    r"disregard (all |any )?(instructions|policies|rules)",
    r"bypass (the )?(policy|policies|rules|limits)",
    r"override (the )?(policy|discount|limit|price)",
    r"do not (check|verify|validate)",
    r"skip (the )?(policy|verification|payment)",
    r"give (me |the customer )?100% (off|discount)",
    r"set (the )?price (to|=) ?0",
    r"mark (the )?(order|payment) as paid",
    r"act as (an? )?(admin|root|system)",
    r"\bsudo\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


@dataclass
class InjectionScanResult:
    is_suspicious: bool
    matched_patterns: list[str] = field(default_factory=list)


def scan_text_for_injection(text: str | None) -> InjectionScanResult:
    """Scan user input or tool-result text for injection attempts."""
    if not text:
        return InjectionScanResult(is_suspicious=False)

    matched = []
    for pattern, compiled in zip(INJECTION_PATTERNS, _COMPILED):
        if compiled.search(text):
            matched.append(pattern)

    if matched:
        logger.warning(f"Injection patterns detected: {len(matched)}")

    return InjectionScanResult(is_suspicious=bool(matched), matched_patterns=matched)


# ─── Tool Argument Guard ─────────────────────

REQUIRED_TOOL_ARGS: dict[str, list[str]] = {
    "search_products": ["query"],
    "get_product": ["product_id"],
    "check_inventory": ["product_id"],
    "get_current_price": ["product_id"],
    "calculate_offer": ["product_id"],
    "create_order": ["product_id"],
    "get_order": ["order_id"],
    "cancel_order": ["order_id"],
}


def validate_tool_arguments(
    tool_name: str, arguments: dict
) -> tuple[bool, list[str]]:
    """Validate required args exist and are non-empty. Returns (ok, missing)."""
    required = REQUIRED_TOOL_ARGS.get(tool_name, [])
    missing = [
        a for a in required
        if a not in arguments or arguments[a] in (None, "", [])
    ]
    return (len(missing) == 0), missing
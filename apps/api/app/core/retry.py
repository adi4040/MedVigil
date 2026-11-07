import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class AuditEvaluationExhaustedError(RuntimeError):
    """Raised when all retry attempts (transient or validation) are exhausted."""
    pass


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 16.0
    jitter: bool = True


def calculate_backoff(attempt: int, config: RetryConfig) -> float:
    """Calculate exponential backoff with optional jitter.
    
    attempt: 0-indexed retry number (0 for 1st retry, 1 for 2nd retry, etc.)
    """
    delay = min(config.max_delay, config.base_delay * (2 ** attempt))
    if config.jitter:
        # Full/symmetric jitter: randomize between 80% and 120% of base calculation
        delay = delay * random.uniform(0.8, 1.2)
    return max(0.0, round(delay, 3))


def format_validation_feedback(errors: List[Dict[str, Any]], raw_response: Optional[str] = None) -> str:
    """Format Pydantic ValidationError dictionaries into an actionable correction prompt."""
    error_items = []
    for err in errors:
        loc_str = " -> ".join(str(item) for item in err.get("loc", [])) or "root"
        msg = err.get("msg", "Invalid value")
        error_items.append(f"- Field '{loc_str}': {msg}")

    error_summary = "\n".join(error_items)
    feedback = (
        f"Your previous response failed schema validation with the following error(s):\n"
        f"{error_summary}\n\n"
        f"Please correct the violations and output ONLY the valid JSON conforming strictly to the schema."
    )
    return feedback


def is_transient_error(exc: Exception) -> bool:
    """Determine if an exception is a transient network or server error eligible for backoff retry."""
    # Check status_code attribute (common across Google GenAI, OpenAI, httpx, requests)
    status_code = getattr(exc, "status_code", None)
    if status_code in (408, 429, 500, 502, 503, 504):
        return True

    # Check common exception names
    exc_type_name = type(exc).__name__
    transient_type_names = {
        "RateLimitError",
        "APIConnectionError",
        "InternalServerError",
        "APITimeoutError",
        "ServerError",
        "TimeoutException",
        "NetworkError",
        "ConnectTimeout",
        "ReadTimeout",
        "ConnectionError",
        "TimeoutError",
    }
    if exc_type_name in transient_type_names:
        return True

    # Check error message keywords
    msg = str(exc).lower()
    transient_keywords = [
        "429",
        "503",
        "502",
        "504",
        "rate limit",
        "resource exhausted",
        "overloaded",
        "temporarily unavailable",
        "connection reset",
        "connection timed out",
        "high demand",
    ]
    return any(keyword in msg for keyword in transient_keywords)

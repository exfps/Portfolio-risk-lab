"""Optional import of portfolio positions from a screenshot, using the user's own API key.

Nothing in the core library imports this package. See docs/architecture.md and SECURITY.md.
"""

from portfolio_risk.vision.extract import PROMPT, Extraction, extract_positions
from portfolio_risk.vision.media import MAX_IMAGE_BYTES, detect_media_type
from portfolio_risk.vision.providers import (
    PROVIDERS,
    ModelReply,
    Provider,
    VisionClient,
    import_disabled,
    provider_by_key,
)
from portfolio_risk.vision.schema import (
    ExtractedPosition,
    ParsedAnswer,
    parse_response,
    weights_from_positions,
)

__all__ = [
    "MAX_IMAGE_BYTES",
    "PROMPT",
    "PROVIDERS",
    "ExtractedPosition",
    "Extraction",
    "ModelReply",
    "ParsedAnswer",
    "Provider",
    "VisionClient",
    "detect_media_type",
    "extract_positions",
    "import_disabled",
    "parse_response",
    "provider_by_key",
    "weights_from_positions",
]

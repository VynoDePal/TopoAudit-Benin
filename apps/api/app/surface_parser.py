import re
import unicodedata


_SURFACE_TOKEN_PATTERN = re.compile(r"(?P<value>\d+)\s*(?P<unit>ha|ca|a)(?![a-z])")


def _normalize_surface_text(raw: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw).lower()
    normalized = normalized.replace("hectares", "ha").replace("hectare", "ha")
    normalized = normalized.replace("centiares", "ca").replace("centiare", "ca")
    normalized = normalized.replace("ares", "a").replace("are", "a")
    return normalized


def parse_surface_to_m2(raw: str) -> int | None:
    """Convert a French land-area string in ha/a/ca units to square meters."""
    if not raw or not raw.strip():
        return None

    units = {"ha": 10_000, "a": 100, "ca": 1}
    total = 0
    matched = False

    for match in _SURFACE_TOKEN_PATTERN.finditer(_normalize_surface_text(raw)):
        matched = True
        total += int(match.group("value")) * units[match.group("unit")]

    return total if matched else None

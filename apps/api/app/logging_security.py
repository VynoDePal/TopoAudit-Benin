import logging
import re
from collections.abc import Iterable
from typing import Any

_REDACTED = "[REDACTED]"
_SECRET_VALUES: set[str] = set()
_SECRET_FIELD_PATTERN = re.compile(r"(key|token|secret|password|credential|authorization)", re.IGNORECASE)
_KEY_VALUE_PATTERN = re.compile(
    r"(?P<prefix>\b[\w.-]*(?:api[_-]?key|subscription[_ -]?key|token|secret|password|credential|authorization)[\w.-]*\b"
    r"\s*[=:]\s*)"
    r"(?P<quote>['\"]?)"
    r"(?P<value>[^'\"\s,;&)}\]]+)",
    re.IGNORECASE,
)
_JSON_VALUE_PATTERN = re.compile(
    r"(?P<prefix>['\"](?:[^'\"]*(?:api[_-]?key|subscription[_ -]?key|token|secret|password|credential|authorization)[^'\"]*)['\"]"
    r"\s*:\s*)"
    r"(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\b(Bearer|Basic)\s+[^\s,;}\]]+", re.IGNORECASE)


def register_secret(value: Any) -> None:
    if value is None:
        return
    secret = str(value)
    if len(secret) >= 4:
        _SECRET_VALUES.add(secret)


def register_secrets(values: Iterable[Any]) -> None:
    for value in values:
        register_secret(value)


def is_secret_field(name: str) -> bool:
    return bool(_SECRET_FIELD_PATTERN.search(name))


def sanitize_for_logging(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {
            key: _REDACTED if is_secret_field(str(key)) else sanitize_for_logging(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(sanitize_for_logging(item) for item in value)
    if isinstance(value, list):
        return [sanitize_for_logging(item) for item in value]
    return value


def _sanitize_text(text: str) -> str:
    sanitized = text
    for secret in sorted(_SECRET_VALUES, key=len, reverse=True):
        sanitized = sanitized.replace(secret, _REDACTED)
    sanitized = _JSON_VALUE_PATTERN.sub(lambda match: f"{match.group('prefix')}{match.group('quote')}{_REDACTED}{match.group('quote')}", sanitized)
    sanitized = _KEY_VALUE_PATTERN.sub(lambda match: f"{match.group('prefix')}{match.group('quote')}{_REDACTED}", sanitized)
    sanitized = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)} {_REDACTED}", sanitized)
    return sanitized


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_for_logging(record.getMessage())
        record.args = ()
        return True


def install_sensitive_data_filter() -> SensitiveDataFilter:
    root_logger = logging.getLogger()
    for existing_filter in root_logger.filters:
        if isinstance(existing_filter, SensitiveDataFilter):
            return existing_filter

    sensitive_filter = SensitiveDataFilter()
    root_logger.addFilter(sensitive_filter)
    logging.setLogRecordFactory(_redacting_log_record_factory(logging.getLogRecordFactory()))
    return sensitive_filter


def _redacting_log_record_factory(factory: Any) -> Any:
    if getattr(factory, "_redacts_sensitive_data", False):
        return factory

    def create_record(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = factory(*args, **kwargs)
        SensitiveDataFilter().filter(record)
        return record

    create_record._redacts_sensitive_data = True
    return create_record

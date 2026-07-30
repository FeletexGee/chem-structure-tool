from collections.abc import Callable, Collection
from typing import Any


class RequestValidationError(ValueError):
    """Raised when an API request does not match the documented schema."""


def require_json_object(flask_request) -> dict:
    data = flask_request.get_json(silent=True)
    if not isinstance(data, dict):
        raise RequestValidationError("请求体必须是 JSON 对象")
    return data


def require_string(data: dict, key: str, *, max_length: int) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise RequestValidationError(f"'{key}' 必须是字符串")
    value = value.strip()
    if not value:
        raise RequestValidationError(f"'{key}' 不能为空")
    if len(value) > max_length:
        raise RequestValidationError(f"'{key}' 长度不能超过 {max_length}")
    return value


def optional_bool(data: dict, key: str, *, default: bool) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise RequestValidationError(f"'{key}' 必须是布尔值")
    return value


def optional_choice(
    data: dict,
    key: str,
    *,
    allowed: Collection[str],
    default: str,
    transform: Callable[[str], str] | None = None,
) -> str:
    value: Any = data.get(key, default)
    if not isinstance(value, str):
        raise RequestValidationError(f"'{key}' 必须是字符串")
    value = value.strip()
    if transform:
        value = transform(value)
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise RequestValidationError(f"'{key}' 必须是以下值之一: {choices}")
    return value

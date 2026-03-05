import json
import math
import pathlib
from dataclasses import dataclass
from typing import cast, ClassVar, NoReturn, Protocol, Self, TypeAlias, TypeVar

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonArray: TypeAlias = list["JsonValue"]
JsonValue: TypeAlias = JsonObject | JsonArray | JsonPrimitive

JsonValuePathToken: TypeAlias = str | int
JsonValuePath: TypeAlias = tuple[JsonValuePathToken, ...]

def _escape_json_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")

def _json_value_path_to_pointer(path: JsonValuePath) -> str:
    if not path:
        return ""

    tokens: list[str] = []

    for token in path:
        if isinstance(token, int) and (not isinstance(token, bool)):
            if token < 0:
                raise ValueError(f"Negative array index in JsonValuePath: {token}")

            tokens.append(str(token))
        elif isinstance(token, str):
            tokens.append(_escape_json_pointer_token(token))
        else:
            raise TypeError(f"Invalid JsonValuePathToken: {type(token).__name__}")

    return "/" + "/".join(tokens)

class JsonValueError(ValueError):
    def __init__(self, reason: str, path: JsonValuePath):
        super().__init__(reason)
        self.path: JsonValuePath = path

    def __str__(self) -> str:
        pointer: str = _json_value_path_to_pointer(self.path)
        at: str = pointer if pointer else "<root>"
        return f"{self.args[0]} at {at}"

def validate_json_primitive(x: object, *, path: JsonValuePath = ()) -> None:
    if x is None:
        return

    if isinstance(x, bool):
        return

    if isinstance(x, str):
        return

    if isinstance(x, int):
        return

    if isinstance(x, float):
        if math.isfinite(x):
            return

        raise JsonValueError(f"Non-finite float: {x!r}", path)

    raise JsonValueError(f"Invalid primitive: {type(x).__name__} value={x!r}", path)

@dataclass(frozen=True, slots=True)
class _StackItem:
    discard: bool
    oid: int
    value: object
    depth: int
    path: JsonValuePath

    DUMMY_OID: ClassVar[int] = -1
    DUMMY_VALUE: ClassVar[object] = object()

def validate_json_value(x: object, *, max_depth: int = 1000) -> None:
    active_oids: set[int] = set()
    stack: list[_StackItem] = [_StackItem(False, _StackItem.DUMMY_OID, x, 0, ())]

    while stack:
        item: _StackItem = stack.pop()

        if item.discard:
            active_oids.discard(item.oid)
            continue

        if item.depth > max_depth:
            raise JsonValueError(f"Max depth exceeded (depth={item.depth} > {max_depth})", item.path)

        if isinstance(item.value, dict):
            value: JsonObject = cast(JsonObject, item.value)

            oid = id(value)

            if oid in active_oids:
                raise JsonValueError("Cycle detected (object)", item.path)

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.depth, item.path))

            for k, v in value.items():
                if not isinstance(k, str):
                    raise JsonValueError(f"Non-string object key: {k!r} (type={type(k).__name__})", item.path)

                stack.append(_StackItem(False, _StackItem.DUMMY_OID, v, item.depth + 1, item.path + (k,)))
        elif isinstance(item.value, list):
            value: JsonArray = cast(JsonArray, item.value)

            oid = id(value)

            if oid in active_oids:
                raise JsonValueError("Cycle detected (array)", item.path)

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.depth, item.path))

            for i, j in enumerate(value):
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, j, item.depth + 1, item.path + (i,)))
        else:
            validate_json_primitive(item.value, path=item.path)

def validate_json_object(x: object, *, max_depth: int = 1000) -> None:
    if not isinstance(x, dict):
        raise JsonValueError(f"Expected JSON object, got {type(x).__name__}", ())

    validate_json_value(x, max_depth=max_depth)

def validate_json_array(x: object, *, max_depth: int = 1000) -> None:
    if not isinstance(x, list):
        raise JsonValueError(f"Expected JSON array, got {type(x).__name__}", ())

    validate_json_value(x, max_depth=max_depth)

class JsonObjectConvertible(Protocol):
    def to_json_object(self) -> JsonObject:
        ...

    @classmethod
    def from_json_object(cls: type[Self], json_object: JsonObject) -> Self:
        ...

def dump_json_object_convertible(convertible: JsonObjectConvertible, path: pathlib.Path) -> None:
    o: JsonObject = convertible.to_json_object()

    try:
        validate_json_object(o)
    except JsonValueError as e:
        raise TypeError(f"Invalid JSON produced by {type(convertible).__name__} when writing {path}: {e}") from e

    s: str = json.dumps(o, ensure_ascii=False, allow_nan=False, indent=4, sort_keys=True)
    path.write_text(s, encoding="utf-8")

def _parse_float(s: str) -> float:
    f: float = float(s)

    if not math.isfinite(f):
        raise ValueError(f"Non-finite float: {s}")

    return f

def _parse_constant(s: str) -> NoReturn:
    raise ValueError(f"Invalid JSON constant: {s}")

T = TypeVar("T", bound=JsonObjectConvertible)
def load_json_object_convertible(cls: type[T], path: pathlib.Path) -> T:
    s: str = path.read_text(encoding="utf-8")

    try:
        o = json.loads(s, parse_float=_parse_float, parse_constant=_parse_constant)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse JSON in {path}: {e}") from e

    try:
        validate_json_object(o)
    except JsonValueError as e:
        raise TypeError(f"Invalid JSON in {path}: {e}") from e

    return cls.from_json_object(cast(JsonObject, o))

def get_str_from_json_object(obj: JsonObject, key: str, *, default: str = "") -> str:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, str):
        return default

    return value

def get_int_from_json_object(obj: JsonObject, key: str, *, default: int = 0) -> int:
    value: JsonValue | None = obj.get(key)

    if isinstance(value, bool) or (not isinstance(value, int)):
        return default

    return value

def get_float_from_json_object(obj: JsonObject, key: str, *, default: float = 0.0) -> float:
    value: JsonValue | None = obj.get(key)

    if isinstance(value, bool):
        return default

    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            return default

    if isinstance(value, float):
        if not math.isfinite(value):
            return default

        return value

    return default

def get_bool_from_json_object(obj: JsonObject, key: str, *, default: bool = False) -> bool:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, bool):
        return default

    return value

T_co = TypeVar("T_co", covariant=True)
class Factory(Protocol[T_co]):
    def __call__(self) -> T_co:
        ...

def get_object_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonObject] = dict) -> JsonObject:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, dict):
        return default_factory()

    return cast(JsonObject, value)

def get_array_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonArray] = list) -> JsonArray:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, list):
        return default_factory()

    return cast(JsonArray, value)

T = TypeVar("T", bound=JsonObjectConvertible)
def get_convertible_from_json_object(obj: JsonObject, key: str, cls: type[T], *, default_factory: Factory[T] | None = None) -> T:
    value: JsonValue | None = obj.get(key)

    if isinstance(value, dict):
        try:
            return cls.from_json_object(cast(JsonObject, value))
        except Exception:
            pass

    if default_factory is None:
        return cls()
    else:
        return default_factory()

T = TypeVar("T", bound=JsonObjectConvertible)
def get_convertibles_from_json_object(obj: JsonObject, key: str, cls: type[T], *, default_factory: Factory[list[T]] = list) -> list[T]:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, list):
        return default_factory()

    convertibles: list[T] = []

    for item in value:
        if not isinstance(item, dict):
            return default_factory()

        try:
            convertibles.append(cls.from_json_object(cast(JsonObject, item)))
        except Exception:
            return default_factory()

    return convertibles

def _require_value_from_json_object(obj: JsonObject, key: str) -> JsonValue:
    if key not in obj:
        raise JsonValueError("Missing required key", (key,))

    return obj[key]

def require_str_from_json_object(obj: JsonObject, key: str) -> str:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if not isinstance(value, str):
        raise JsonValueError(f"Expected string, got {type(value).__name__}", (key,))

    return value

def require_int_from_json_object(obj: JsonObject, key: str) -> int:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if isinstance(value, bool) or (not isinstance(value, int)):
        raise JsonValueError(f"Expected integer, got {type(value).__name__}", (key,))

    return value

def require_float_from_json_object(obj: JsonObject, key: str) -> float:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if isinstance(value, bool):
        raise JsonValueError("Expected number, got bool", (key,))

    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            raise JsonValueError(f"Integer too large to convert to float: {value!r}", (key,))

    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonValueError(f"Non-finite float: {value!r}", (key,))

        return value

    raise JsonValueError(f"Expected number, got {type(value).__name__}", (key,))

def require_bool_from_json_object(obj: JsonObject, key: str) -> bool:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if not isinstance(value, bool):
        raise JsonValueError(f"Expected boolean, got {type(value).__name__}", (key,))

    return value

def require_object_from_json_object(obj: JsonObject, key: str) -> JsonObject:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if not isinstance(value, dict):
        raise JsonValueError(f"Expected JSON object, got {type(value).__name__}", (key,))

    return cast(JsonObject, value)

def require_array_from_json_object(obj: JsonObject, key: str) -> JsonArray:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if not isinstance(value, list):
        raise JsonValueError(f"Expected JSON array, got {type(value).__name__}", (key,))

    return cast(JsonArray, value)

T = TypeVar("T", bound=JsonObjectConvertible)
def require_convertible_from_json_object(obj: JsonObject, key: str, cls: type[T]) -> T:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if not isinstance(value, dict):
        raise JsonValueError(f"Expected JSON object for {cls.__name__}, got {type(value).__name__}", (key,))

    try:
        return cls.from_json_object(cast(JsonObject, value))
    except Exception as e:
        raise JsonValueError(f"Failed to decode {cls.__name__}: {e}", (key,)) from e

T = TypeVar("T", bound=JsonObjectConvertible)
def require_convertibles_from_json_object(obj: JsonObject, key: str, cls: type[T]) -> list[T]:
    value: JsonValue = _require_value_from_json_object(obj, key)

    if not isinstance(value, list):
        raise JsonValueError(f"Expected JSON array of {cls.__name__}, got {type(value).__name__}", (key,))

    convertibles: list[T] = []

    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise JsonValueError(f"Expected JSON object element for {cls.__name__}, got {type(item).__name__}", (key, i))

        try:
            convertibles.append(cls.from_json_object(cast(JsonObject, item)))
        except Exception as e:
            raise JsonValueError(f"Failed to decode {cls.__name__}: {e}", (key, i)) from e

    return convertibles

__all__ = [
    "JsonPrimitive",
    "JsonObject",
    "JsonArray",
    "JsonValue",
    "JsonValuePathToken",
    "JsonValuePath",
    "JsonValueError",
    "validate_json_primitive",
    "validate_json_value",
    "validate_json_object",
    "validate_json_array",
    "JsonObjectConvertible",
    "dump_json_object_convertible",
    "load_json_object_convertible",
    "get_str_from_json_object",
    "get_int_from_json_object",
    "get_float_from_json_object",
    "get_bool_from_json_object",
    "Factory",
    "get_object_from_json_object",
    "get_array_from_json_object",
    "get_convertible_from_json_object",
    "get_convertibles_from_json_object",
    "require_str_from_json_object",
    "require_int_from_json_object",
    "require_float_from_json_object",
    "require_bool_from_json_object",
    "require_object_from_json_object",
    "require_array_from_json_object",
    "require_convertible_from_json_object",
    "require_convertibles_from_json_object",
]

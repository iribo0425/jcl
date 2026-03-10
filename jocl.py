# SPDX-FileCopyrightText: 2026 Iribo
# SPDX-License-Identifier: MIT

import abc
import json
import logging
import math
import pathlib
from dataclasses import dataclass
from typing import cast, ClassVar, Iterable, NoReturn, Optional, Protocol, TypeVar, Union

def _is_strict_int(x: object) -> bool:
    return type(x) is int

JsonPrimitive = Union[str, int, float, bool, None]
JsonObject = dict[str, "JsonValue"]
JsonArray = list["JsonValue"]
JsonValue = Union[JsonObject, JsonArray, JsonPrimitive]

JsonValuePathPart = Union[str, int]
JsonValuePath = tuple[JsonValuePathPart, ...]

def default_json_primitive() -> JsonPrimitive:
    """Returns the default JSON primitive.

    Returns:
        The default JSON primitive, which is ``None``.
    """
    return None

def default_json_object() -> JsonObject:
    """Returns a new empty JSON object.

    Returns:
        A new empty JSON object.
    """
    return {}

def default_json_array() -> JsonArray:
    """Returns a new empty JSON array.

    Returns:
        A new empty JSON array.
    """
    return []

def default_json_value() -> JsonValue:
    """Returns the default JSON value.

    Returns:
        The default JSON value, which is ``None``.
    """
    return None

def default_json_value_path() -> JsonValuePath:
    """Returns the empty path for the JSON root.

    Returns:
        The empty path for the JSON root.
    """
    return ()

def _validate_json_value_path_part(x: object) -> None:
    if _is_strict_int(x):
        if cast(int, x) < 0:
            raise ValueError(f"JsonValuePathPart integer must be >= 0, got {x}")

        return

    if isinstance(x, str):
        return

    raise TypeError(f"Invalid JsonValuePathPart: {type(x).__name__}")

def _validate_json_value_path(x: object) -> None:
    if not isinstance(x, tuple):
        raise TypeError(f"JsonValuePath must be tuple, got {type(x).__name__}")

    for part in cast(tuple[object, ...], x):
        _validate_json_value_path_part(part)

def append_json_value_path_part(path: JsonValuePath, part: JsonValuePathPart) -> JsonValuePath:
    """Appends a part to a path.

    Args:
        path: Base path.
        part: Object key or array index to append.

    Returns:
        A new path with ``part`` appended.

    Raises:
        TypeError: Raised when ``path`` or ``part`` has an invalid type.
        ValueError: Raised when ``part`` is an invalid array index.
    """

    _validate_json_value_path(path)
    _validate_json_value_path_part(part)
    return path + (part,)

def _validate_max_depth(x: object) -> None:
    if not _is_strict_int(x):
        raise TypeError(f"max_depth must be int, got {type(x).__name__}")

    if cast(int, x) < 0:
        raise ValueError(f"max_depth must be >= 0, got {x}")

def _validate_logger(x: object) -> None:
    if x is None:
        return

    if not isinstance(x, logging.Logger):
        raise TypeError(f"logger must be logging.Logger, got {type(x).__name__}")

class JsonContext(object):
    """Stores path, maximum depth, and optional logging context for JSON handling."""

    def __init__(self, path: JsonValuePath = default_json_value_path(), max_depth: int = 1000, logger: Optional[logging.Logger] = None):
        """Initializes a JSON context.

        Args:
            path: Current JSON value path.
            max_depth: Maximum allowed nesting depth for JSON values.
            logger: Optional logger used for fallback diagnostics.

        Raises:
            TypeError: Raised when ``path``, ``max_depth``, or ``logger`` has an invalid type.
            ValueError: Raised when ``max_depth`` is negative or when ``path`` contains an invalid part.
        """
        super(JsonContext, self).__init__()

        _validate_json_value_path(path)
        _validate_max_depth(max_depth)
        _validate_logger(logger)

        self.__path: JsonValuePath = path
        self.__max_depth: int = max_depth
        self.__logger: Optional[logging.Logger] = logger

    def get_path(self) -> JsonValuePath:
        """Returns the current path.

        Returns:
            The current path.
        """
        return self.__path

    def get_max_depth(self) -> int:
        """Returns the maximum validation depth.

        Returns:
            The maximum validation depth.
        """
        return self.__max_depth

    def get_logger(self) -> Optional[logging.Logger]:
        """Returns the logger used for fallback read logging.

        Returns:
            The configured logger, or ``None`` if fallback reads are not logged.
        """
        return self.__logger

    def create_child(self, path_part: JsonValuePathPart) -> "JsonContext":
        """Creates a child context for a nested path part.

        The child context inherits the current maximum depth and logger.

        Args:
            path_part: Object key or array index to append to the current path.

        Returns:
            A new context for the child path.

        Raises:
            TypeError: Raised when ``path_part`` has an invalid type.
            ValueError: Raised when ``path_part`` is an invalid array index.
        """
        return JsonContext(
            path=append_json_value_path_part(self.get_path(), path_part),
            max_depth=self.get_max_depth(),
            logger=self.get_logger()
        )

_MISSING_LOG_VALUE: object = object()

def _format_json_location(path: JsonValuePath) -> str:
    pointer: str = _json_value_path_to_pointer(path)
    return pointer if pointer else "<root>"

def _get_exception_reason(exc: BaseException) -> str:
    if exc.args:
        try:
            return str(exc.args[0])
        except Exception:
            pass

    return exc.__class__.__name__

def _log_get_failure(ctx: JsonContext, reason: str, *, value: object = _MISSING_LOG_VALUE, exc: Optional[Exception] = None) -> None:
    logger: Optional[logging.Logger] = ctx.get_logger()

    if logger is None:
        return

    location: str = _format_json_location(ctx.get_path())

    if value is _MISSING_LOG_VALUE:
        if exc is None:
            logger.warning("JSON get fallback at %s: %s", location, reason)
        else:
            logger.warning("JSON get fallback at %s: %s; exc_type=%s; exc=%s", location, reason, type(exc).__name__, exc)
        return

    max_length: int = 200

    try:
        value_repr: str = repr(value)
    except Exception as e:
        value_repr = f"<unrepresentable value ({type(e).__name__}: {e})>"

    if len(value_repr) > max_length:
        value_repr = value_repr[:max_length - 3] + "..."

    value_type: str = type(value).__name__

    if exc is None:
        logger.warning(
            "JSON get fallback at %s: %s; value_type=%s; value=%s",
            location,
            reason,
            value_type,
            value_repr,
        )
    else:
        logger.warning(
            "JSON get fallback at %s: %s; value_type=%s; value=%s; exc_type=%s; exc=%s",
            location,
            reason,
            value_type,
            value_repr,
            type(exc).__name__,
            exc,
        )

T_JsonObjectConvertible = TypeVar("T_JsonObjectConvertible", bound="JsonObjectConvertible")
class JsonObjectConvertible(abc.ABC):
    """Abstract base class for types that convert to and from JSON objects."""

    @classmethod
    @abc.abstractmethod
    def from_json_object(cls: type[T_JsonObjectConvertible], ctx: JsonContext, json_object: JsonObject) -> T_JsonObjectConvertible:
        """Creates an instance from a JSON object.

        Args:
            ctx: Current JSON context, including the current path.
            json_object: Source JSON object.

        Returns:
            A newly constructed instance.

        Raises:
            JsonError: Raised when required JSON data is missing or when a JSON value is invalid.
            TypeError: Raised when deserialization encounters a type-related error.
            ValueError: Raised when deserialization encounters a value-related error.
        """
        ...

    @abc.abstractmethod
    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        """Converts this instance to a JSON object.

        Args:
            ctx: Current JSON context, including the current path.

        Returns:
            A JSON-compatible object representation of this instance.

        Raises:
            TypeError: Raised when serialization encounters a type-related error.
            ValueError: Raised when serialization encounters an invalid value.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def create_default(cls: type[T_JsonObjectConvertible]) -> T_JsonObjectConvertible:
        """Creates a default instance of this type.

        Returns:
            A newly created default instance.
        """
        ...

T_Convertible = TypeVar("T_Convertible", bound=JsonObjectConvertible)

def _escape_json_pointer_part(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")

def _json_value_path_to_pointer(path: JsonValuePath) -> str:
    if not path:
        return ""

    parts: list[str] = []

    for part in path:
        if _is_strict_int(part):
            if cast(int, part) < 0:
                raise ValueError(f"Negative array index in JsonValuePath: {part}")

            parts.append(str(part))
        elif isinstance(part, str):
            parts.append(_escape_json_pointer_part(part))
        else:
            raise TypeError(f"Invalid JsonValuePathPart: {type(part).__name__}")

    return "/" + "/".join(parts)

class JsonError(ValueError):
    """Raised when a JSON-related validation or access error occurs under this module's rules."""

    def __init__(self, reason: str, path: JsonValuePath):
        """Initializes the error with a reason and a path.

        Args:
            reason: Human-readable description of the failure.
            path: Path at which the failure occurred.

        Raises:
            TypeError: Raised when ``path`` has an invalid type.
            ValueError: Raised when ``path`` contains an invalid part.
        """
        _validate_json_value_path(path)

        super(JsonError, self).__init__(reason)

        self.__path: JsonValuePath = path

    def get_path(self) -> JsonValuePath:
        """Returns the path associated with the error.

        Returns:
            The stored path.
        """
        return self.__path

    def __str__(self) -> str:
        """Formats the error with its path.

        Returns:
            A message that includes both the failure reason and a JSON Pointer-like path.
        """
        reason: str = _get_exception_reason(self)

        try:
            at: str = _format_json_location(self.__path)
        except Exception as e:
            try:
                path_repr = repr(self.__path)
            except Exception:
                path_repr = "<unrepresentable path>"

            at = f"<invalid path ({type(e).__name__}: {e}); path={path_repr}>"

        return f"{reason} at {at}"

def validate_json_primitive(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON primitive.

    Accepted values are ``None``, ``bool``, ``str``, exact ``int`` objects, and finite ``float`` values.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON primitive under this module's rules.
    """
    if x is None:
        return

    if isinstance(x, bool):
        return

    if isinstance(x, str):
        return

    if _is_strict_int(x):
        return

    if isinstance(x, float):
        if math.isfinite(x):
            return

        raise JsonError(f"Non-finite float: {x!r}", ctx.get_path())

    raise JsonError(f"Expected JSON primitive, got {type(x).__name__}", ctx.get_path())

@dataclass(frozen=True)
class _StackItem:
    discard: bool
    oid: int
    value: object
    depth: int
    path: JsonValuePath

    DUMMY_OID: ClassVar[int] = -1
    DUMMY_VALUE: ClassVar[object] = object()

def validate_json_value(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON value.

    This validator traverses nested objects and arrays iteratively, enforces a maximum nesting depth, rejects non-string object keys, and detects cycles in container graphs.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON value.
    """
    active_oids: set[int] = set()
    stack: list[_StackItem] = [_StackItem(False, _StackItem.DUMMY_OID, x, 0, ctx.get_path())]

    while stack:
        item: _StackItem = stack.pop()

        if item.discard:
            active_oids.discard(item.oid)
            continue

        if item.depth > ctx.get_max_depth():
            raise JsonError(f"JSON max depth exceeded: depth={item.depth} > max_depth={ctx.get_max_depth()}", item.path)

        if isinstance(item.value, dict):
            # Pylance strict cannot infer the precise type here.
            # This cast is intentional; container contents are validated below at runtime.
            obj: dict = cast(dict, item.value)

            oid = id(obj)

            if oid in active_oids:
                raise JsonError("Cycle detected (object)", item.path)

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.depth, item.path))

            items: list[tuple[object, object]] = list(obj.items())

            for k, v in reversed(items):
                if not isinstance(k, str):
                    raise JsonError(f"Non-string object key: {k!r} (type={type(k).__name__})", item.path)

                child_path: JsonValuePath = append_json_value_path_part(item.path, k)
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, v, item.depth + 1, child_path))
        elif isinstance(item.value, list):
            # Pylance strict cannot infer the precise type here.
            # This cast is intentional; container contents are validated below at runtime.
            array: list = cast(list, item.value)

            oid = id(array)

            if oid in active_oids:
                raise JsonError("Cycle detected (array)", item.path)

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.depth, item.path))

            for i in range(len(array) - 1, -1, -1):
                child_path: JsonValuePath = append_json_value_path_part(item.path, i)
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, array[i], item.depth + 1, child_path))
        else:
            validate_json_primitive(
                JsonContext(item.path, ctx.get_max_depth(), ctx.get_logger()),
                item.value
            )

def validate_json_object(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON object.
    """
    if not isinstance(x, dict):
        raise JsonError(f"Expected JSON object, got {type(x).__name__}", ctx.get_path())

    # Pylance strict cannot infer the precise type here.
    # Container type is checked above; full validation is delegated to validate_json_value().
    validate_json_value(ctx, x)

def validate_json_array(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON array.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON array.
    """
    if not isinstance(x, list):
        raise JsonError(f"Expected JSON array, got {type(x).__name__}", ctx.get_path())

    # Pylance strict cannot infer the precise type here.
    # Container type is checked above; full validation is delegated to validate_json_value().
    validate_json_value(ctx, x)

def dump_convertible(ctx: JsonContext, convertible: JsonObjectConvertible, path: pathlib.Path) -> None:
    """Writes a convertible to a UTF-8 JSON file.

    The JSON object returned by ``to_json_object()`` is validated before writing so that invalid JSON objects are rejected early.
    Exceptions raised directly by ``to_json_object()`` are propagated unchanged.

    Args:
        ctx: Current JSON context, including the current path.
        convertible: Convertible to write.
        path: Destination file path.

    Returns:
        ``None``.

    Raises:
        TypeError: Raised when the JSON object returned by ``to_json_object()`` is invalid.
        OSError: Raised when writing the file fails.
    """
    o: JsonObject = convertible.to_json_object(ctx)

    try:
        validate_json_object(ctx, o)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object produced by {type(convertible).__name__} for {path}: {e}") from e

    s: str = json.dumps(o, ensure_ascii=False, allow_nan=False, indent=4, sort_keys=True)
    path.write_text(s, encoding="utf-8")

def _parse_float(s: str) -> float:
    f: float = float(s)

    if not math.isfinite(f):
        raise ValueError(f"Non-finite float: {s!r}")

    return f

def _parse_constant(s: str) -> NoReturn:
    raise ValueError(f"Invalid JSON constant: {s}")

T = TypeVar("T", bound=JsonObjectConvertible)
def load_convertible(ctx: JsonContext, cls: type[T], path: pathlib.Path) -> T:
    """Loads a convertible from a JSON file.

    Parsing rejects non-finite floats and invalid JSON constants before JSON object validation and deserialization begin.
    Deserialization errors are normalized to ``TypeError``.

    Args:
        ctx: Current JSON context, including the current path.
        cls: Target type to deserialize.
        path: Source file path.

    Returns:
        The deserialized convertible.

    Raises:
        ValueError: Raised when JSON parsing fails.
        TypeError: Raised when the parsed value is not a valid JSON object or when deserialization fails.
        OSError: Raised when reading the file fails.
    """
    s: str = path.read_text(encoding="utf-8")

    try:
        o = json.loads(s, parse_float=_parse_float, parse_constant=_parse_constant)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse JSON from {path}: {e}") from e

    try:
        validate_json_object(ctx, o)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object in {path}: {e}") from e

    try:
        return cls.from_json_object(ctx, cast(JsonObject, o))
    except (JsonError, TypeError, ValueError) as e:
        raise TypeError(f"Failed to deserialize {cls.__name__} from {path}: {e}") from e

def get_str(ctx: JsonContext, json_object: JsonObject, key: str, *, default: str = "") -> str:
    """Gets a string from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored string, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default

    value: object = json_object[key]

    if not isinstance(value, str):
        _log_get_failure(child_ctx, f"Expected string, got {type(value).__name__}", value=value)
        return default

    return value

def get_int(ctx: JsonContext, json_object: JsonObject, key: str, *, default: int = 0) -> int:
    """Gets an integer from a JSON object.

    Only exact ``int`` objects are accepted.
    ``bool`` and integer subclasses are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored integer, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default

    value: object = json_object[key]

    if not _is_strict_int(value):
        _log_get_failure(child_ctx, f"Expected integer, got {type(value).__name__}", value=value)
        return default

    return cast(int, value)

def get_float(ctx: JsonContext, json_object: JsonObject, key: str, *, default: float = 0.0) -> float:
    """Gets a finite number from a JSON object as ``float``.

    Integers are accepted and converted to ``float``.
    Booleans and non-finite floats are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored number converted to ``float``, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default

    value: object = json_object[key]

    if _is_strict_int(value):
        try:
            return float(cast(int, value))
        except OverflowError as e:
            _log_get_failure(child_ctx, "Integer too large to convert to float", value=value, exc=e)
            return default

    if isinstance(value, float):
        if math.isfinite(value):
            return value

        _log_get_failure(child_ctx, "Non-finite float", value=value)
        return default

    _log_get_failure(child_ctx, f"Expected number, got {type(value).__name__}", value=value)
    return default

def get_bool(ctx: JsonContext, json_object: JsonObject, key: str, *, default: bool = False) -> bool:
    """Gets a boolean from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored boolean, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default

    value: object = json_object[key]

    if not isinstance(value, bool):
        _log_get_failure(child_ctx, f"Expected boolean, got {type(value).__name__}", value=value)
        return default

    return value

def get_primitive(ctx: JsonContext, json_object: JsonObject, key: str, *, default: JsonPrimitive = default_json_primitive()) -> JsonPrimitive:
    """Gets a JSON primitive stored under a key.

    The stored value must satisfy this module's JSON primitive rules.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored JSON primitive, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default

    value: object = json_object[key]

    try:
        validate_json_primitive(child_ctx, value)
    except JsonError as e:
        _log_get_failure(child_ctx, _get_exception_reason(e), value=value, exc=e)
        return default

    return cast(JsonPrimitive, value)

def get_value(ctx: JsonContext, json_object: JsonObject, key: str, *, default: JsonValue = default_json_value()) -> JsonValue:
    """Gets a JSON value stored under a key.

    The stored value must satisfy this module's JSON value rules.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored JSON value, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default

    value: object = json_object[key]

    try:
        validate_json_value(child_ctx, value)
    except JsonError as e:
        _log_get_failure(child_ctx, _get_exception_reason(e), value=value, exc=e)
        return default

    return cast(JsonValue, value)

T_co = TypeVar("T_co", covariant=True)
class Factory(Protocol[T_co]):
    """Protocol for zero-argument factories that create default values."""

    def __call__(self) -> T_co:
        """Creates a default value.

        Returns:
            A newly created default value.
        """
        ...

def get_object(ctx: JsonContext, json_object: JsonObject, key: str, *, default_factory: Factory[JsonObject] = default_json_object) -> JsonObject:
    """Gets a JSON object stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default_factory: Factory used to create the default object.

    Returns:
        The stored JSON object, or a new default object if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default_factory()

    value: object = json_object[key]

    try:
        validate_json_object(child_ctx, value)
    except JsonError as e:
        _log_get_failure(child_ctx, _get_exception_reason(e), value=value, exc=e)
        return default_factory()

    return cast(JsonObject, value)

def get_array(ctx: JsonContext, json_object: JsonObject, key: str, *, default_factory: Factory[JsonArray] = default_json_array) -> JsonArray:
    """Gets a JSON array stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default_factory: Factory used to create the default array.

    Returns:
        The stored JSON array, or a new default array if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return default_factory()

    value: object = json_object[key]

    try:
        validate_json_array(child_ctx, value)
    except JsonError as e:
        _log_get_failure(child_ctx, _get_exception_reason(e), value=value, exc=e)
        return default_factory()

    return cast(JsonArray, value)

def get_convertible(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible], *, default_factory: Optional[Factory[T_Convertible]] = None) -> T_Convertible:
    """Gets a convertible from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type to deserialize.
        default_factory: Factory used to create the default value.
            If ``None``, ``cls.create_default`` is used.

    Returns:
        The deserialized convertible, or a new default value if the key is missing,
        if the value is not a valid JSON object, or if deserialization fails.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    factory: Factory[T_Convertible] = cls.create_default if default_factory is None else default_factory

    if key not in json_object:
        _log_get_failure(child_ctx, "Missing key")
        return factory()

    value: object = json_object[key]

    try:
        validate_json_object(child_ctx, value)
        return cls.from_json_object(child_ctx, cast(JsonObject, value))
    except (JsonError, TypeError, ValueError) as e:
        _log_get_failure(child_ctx, f"Failed to deserialize {cls.__name__}", value=value, exc=e)
        return factory()

def get_convertibles(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible], *, default_factory: Factory[list[T_Convertible]] = list) -> list[T_Convertible]:
    """Gets a list of convertibles from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type used to deserialize each element.
        default_factory: Factory used to create the default list.

    Returns:
        The deserialized convertibles, or a new default list if the key is missing, if the value is not a valid JSON array, if an element is not a valid JSON object, or if deserialization fails.
    """
    array_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _log_get_failure(array_ctx, "Missing key")
        return default_factory()

    value: object = json_object[key]

    try:
        validate_json_array(array_ctx, value)
    except JsonError as e:
        _log_get_failure(array_ctx, _get_exception_reason(e), value=value, exc=e)
        return default_factory()

    try:
        convertibles: list[T_Convertible] = []

        for i, item in enumerate(cast(JsonArray, value)):
            item_ctx: JsonContext = array_ctx.create_child(i)
            validate_json_object(item_ctx, item)
            convertibles.append(cls.from_json_object(item_ctx, cast(JsonObject, item)))

        return convertibles
    except (JsonError, TypeError, ValueError) as e:
        _log_get_failure(array_ctx, f"Failed to deserialize list[{cls.__name__}]", value=value, exc=e)
        return default_factory()

def _require_value(ctx: JsonContext, json_object: JsonObject, key: str) -> object:
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        raise JsonError("Missing required key", child_ctx.get_path())

    return json_object[key]

def require_str(ctx: JsonContext, json_object: JsonObject, key: str) -> str:
    """Gets a required string from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored string.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a string.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if not isinstance(value, str):
        raise JsonError(f"Expected string, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_int(ctx: JsonContext, json_object: JsonObject, key: str) -> int:
    """Gets a required integer from a JSON object.

    Only exact ``int`` objects are accepted.
    ``bool`` and integer subclasses are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored integer.

    Raises:
        JsonError: Raised when the key is missing or when the value is not an integer.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if not _is_strict_int(value):
        raise JsonError(f"Expected integer, got {type(value).__name__}", child_ctx.get_path())

    return cast(int, value)

def require_float(ctx: JsonContext, json_object: JsonObject, key: str) -> float:
    """Gets a required finite number from a JSON object as ``float``.

    Integers are accepted and converted to ``float``.
    Booleans and non-finite floats are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored number converted to ``float``.

    Raises:
        JsonError: Raised when the key is missing, when the value is not numeric, or when the value cannot be represented as a finite float.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if _is_strict_int(value):
        try:
            return float(cast(int, value))
        except OverflowError:
            raise JsonError(f"Integer too large to convert to float: {value!r}", child_ctx.get_path())

    if isinstance(value, float):
        if math.isfinite(value):
            return value
        else:
            raise JsonError(f"Non-finite float: {value!r}", child_ctx.get_path())

    raise JsonError(f"Expected number, got {type(value).__name__}", child_ctx.get_path())

def require_bool(ctx: JsonContext, json_object: JsonObject, key: str) -> bool:
    """Gets a required boolean from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored boolean.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a boolean.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if not isinstance(value, bool):
        raise JsonError(f"Expected boolean, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_primitive(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonPrimitive:
    """Gets a required JSON primitive stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON primitive.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON primitive.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_primitive(child_ctx, value)
    return cast(JsonPrimitive, value)

def require_value(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonValue:
    """Gets a required JSON value stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON value.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON value.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_value(child_ctx, value)
    return cast(JsonValue, value)

def require_object(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonObject:
    """Gets a required JSON object stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON object.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON object.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_object(child_ctx, value)
    return cast(JsonObject, value)

def require_array(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonArray:
    """Gets a required JSON array stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON array.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON array.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_array(child_ctx, value)
    return cast(JsonArray, value)

def require_convertible(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible]) -> T_Convertible:
    """Gets a required convertible from a JSON object.

    Deserialization errors are propagated as raised by ``cls.from_json_object()``.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type to deserialize.

    Returns:
        The deserialized convertible.

    Raises:
        JsonError: Raised when the key is missing or when the stored value is not a valid JSON object.
        TypeError: Raised when deserialization fails with a type-related error.
        ValueError: Raised when deserialization fails with a value-related error.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_object(child_ctx, value)
    return cls.from_json_object(child_ctx, cast(JsonObject, value))

def require_convertibles(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible]) -> list[T_Convertible]:
    """Gets a required list of convertibles from a JSON object.

    Element deserialization errors are propagated as raised by ``cls.from_json_object()``.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type used to deserialize each element.

    Returns:
        The deserialized convertibles.

    Raises:
        JsonError: Raised when the key is missing, when the stored value is not a valid JSON array, or when an element is not a valid JSON object.
        TypeError: Raised when element deserialization fails with a type-related error.
        ValueError: Raised when element deserialization fails with a value-related error.
    """
    value: object = _require_value(ctx, json_object, key)

    array_ctx: JsonContext = ctx.create_child(key)
    validate_json_array(array_ctx, value)

    convertibles: list[T_Convertible] = []

    for i, item in enumerate(cast(JsonArray, value)):
        item_ctx: JsonContext = array_ctx.create_child(i)
        validate_json_object(item_ctx, item)
        convertibles.append(cls.from_json_object(item_ctx, cast(JsonObject, item)))

    return convertibles

def convert_convertible_to_json_object(ctx: JsonContext, key: str, convertible: JsonObjectConvertible) -> JsonObject:
    """Converts a convertible to a validated JSON object.

    The object returned by ``to_json_object()`` is validated with ``key`` appended to ``ctx`` so that failures point to the correct location.
    Exceptions raised directly by ``to_json_object()`` are propagated unchanged.

    Args:
        ctx: Current JSON context, including the current path.
        key: Key associated with the convertible in the parent JSON object.
        convertible: Convertible to serialize.

    Returns:
        A validated JSON object.

    Raises:
        TypeError: Raised when the produced value is not a valid JSON object.
        ValueError: Raised when ``to_json_object()`` fails with an invalid value.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    json_object: JsonObject = convertible.to_json_object(child_ctx)

    try:
        validate_json_object(child_ctx, json_object)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object produced by {type(convertible).__name__} for key {key!r}: {e}") from e

    return json_object

def convert_convertibles_to_json_objects(ctx: JsonContext, key: str, convertibles: Iterable[JsonObjectConvertible]) -> list[JsonObject]:
    """Converts an iterable of convertibles to validated JSON objects.

    Each object returned by ``to_json_object()`` is validated with both ``key`` and the element index appended to ``ctx`` so that failures point to the offending element.
    Exceptions raised directly by ``to_json_object()`` are propagated unchanged.

    Args:
        ctx: Current JSON context, including the current path.
        key: Key associated with the convertible list in the parent JSON object.
        convertibles: Convertibles to serialize.

    Returns:
        A list of validated JSON objects.

    Raises:
        TypeError: Raised when any produced value is not a valid JSON object.
        ValueError: Raised when element serialization fails with an invalid value.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    json_objects: list[JsonObject] = []

    for i, convertible in enumerate(convertibles):
        item_ctx: JsonContext = child_ctx.create_child(i)
        json_object: JsonObject = convertible.to_json_object(item_ctx)

        try:
            validate_json_object(item_ctx, json_object)
        except JsonError as e:
            raise TypeError(f"Invalid JSON object produced by element {i} ({type(convertible).__name__}) for key {key!r}: {e}") from e

        json_objects.append(json_object)

    return json_objects

__all__ = [
    "JsonPrimitive",
    "JsonObject",
    "JsonArray",
    "JsonValue",
    "JsonValuePathPart",
    "JsonValuePath",
    "default_json_primitive",
    "default_json_object",
    "default_json_array",
    "default_json_value",
    "default_json_value_path",
    "JsonError",
    "validate_json_primitive",
    "validate_json_value",
    "validate_json_object",
    "validate_json_array",
    "JsonObjectConvertible",
    "dump_convertible",
    "load_convertible",
    "get_str",
    "get_int",
    "get_float",
    "get_bool",
    "get_primitive",
    "get_value",
    "Factory",
    "get_object",
    "get_array",
    "get_convertible",
    "get_convertibles",
    "require_str",
    "require_int",
    "require_float",
    "require_bool",
    "require_primitive",
    "require_value",
    "require_object",
    "require_array",
    "require_convertible",
    "require_convertibles",
    "convert_convertible_to_json_object",
    "convert_convertibles_to_json_objects",
    "append_json_value_path_part",
    "JsonContext",
]

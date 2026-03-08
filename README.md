# JCL (JSON Conversion Lib)

A small Python utility library that makes it easier to convert Python class instances to and from JSON objects.

With this library, you can:
- convert class instances into JSON-compatible dictionaries
- rebuild class instances from JSON objects
- validate JSON values before saving or loading
- read and write JSON files safely
- locate errors inside nested JSON data more easily

## Examples

### Minimal Example

This example shows the basic conversion flow in both directions.
`to_json_object()` converts a class instance into a JSON object, and `from_json_object()` builds a class instance from a JSON object.
```python
from dataclasses import dataclass
from jcl import JsonObject, JsonObjectConvertible

@dataclass
class User(JsonObjectConvertible):
    name: str
    age: int

    def to_json_object(self) -> JsonObject:
        return {
            "name": self.name,
            "age": self.age,
        }

    @classmethod
    def from_json_object(cls, json_object: JsonObject, *, ctx=None) -> "User":
        return cls(
            name=json_object["name"],
            age=json_object["age"],
        )

user = User(name="Alice", age=30)

json_object = user.to_json_object()
print(json_object)
# {'name': 'Alice', 'age': 30}

loaded_user = User.from_json_object(json_object)
print(loaded_user)
# User(name='Alice', age=30)
```

### Tolerant Deserialization

This example uses the `get_*` helpers to read values with defaults.
It is useful when missing or invalid values should fall back to safe default values instead of raising an error.
```python
from dataclasses import dataclass

from jcl import (
    JsonObject,
    JsonObjectConvertible,
    get_bool_from_json_object,
    get_int_from_json_object,
    get_str_from_json_object,
)

@dataclass
class UserSettings(JsonObjectConvertible):
    theme: str = "dark"
    max_item_count: int = 20
    show_tips: bool = True

    def to_json_object(self) -> JsonObject:
        return {
            "theme": self.theme,
            "max_item_count": self.max_item_count,
            "show_tips": self.show_tips,
        }

    @classmethod
    def from_json_object(cls, json_object: JsonObject, *, ctx=None) -> "UserSettings":
        return cls(
            theme=get_str_from_json_object(json_object, "theme", default="dark"),
            max_item_count=get_int_from_json_object(json_object, "max_item_count", default=20),
            show_tips=get_bool_from_json_object(json_object, "show_tips", default=True),
        )
```

### Strict Deserialization

This example uses the `require_*` helpers to read required values.
It is useful when input data must have the expected fields and types, and invalid input should immediately raise an error.
```python
from dataclasses import dataclass

from jcl import (
    JsonObject,
    JsonObjectConvertible,
    require_bool_from_json_object,
    require_int_from_json_object,
    require_str_from_json_object,
)

@dataclass
class User(JsonObjectConvertible):
    name: str
    age: int
    active: bool

    def to_json_object(self) -> JsonObject:
        return {
            "name": self.name,
            "age": self.age,
            "active": self.active,
        }

    @classmethod
    def from_json_object(cls, json_object: JsonObject, *, ctx=None) -> "User":
        return cls(
            name=require_str_from_json_object(json_object, "name", ctx=ctx),
            age=require_int_from_json_object(json_object, "age", ctx=ctx),
            active=require_bool_from_json_object(json_object, "active", ctx=ctx),
        )
```

### Nested Objects and Lists

This example shows how to deserialize nested objects and lists of objects.
It is useful when one class contains other `JsonObjectConvertible` objects, such as an address object or a list of tags.
```python
from dataclasses import dataclass, field

from jcl import (
    JsonObject,
    JsonObjectConvertible,
    convert_convertibles_to_json_objects,
    get_convertible_from_json_object,
    get_convertibles_from_json_object,
    get_str_from_json_object,
)

@dataclass
class Address(JsonObjectConvertible):
    city: str = ""
    country: str = ""

    def to_json_object(self) -> JsonObject:
        return {
            "city": self.city,
            "country": self.country,
        }

    @classmethod
    def from_json_object(cls, json_object: JsonObject, *, ctx=None) -> "Address":
        return cls(
            city=get_str_from_json_object(json_object, "city", default=""),
            country=get_str_from_json_object(json_object, "country", default=""),
        )

@dataclass
class Tag(JsonObjectConvertible):
    name: str = ""

    def to_json_object(self) -> JsonObject:
        return {
            "name": self.name,
        }

    @classmethod
    def from_json_object(cls, json_object: JsonObject, *, ctx=None) -> "Tag":
        return cls(
            name=get_str_from_json_object(json_object, "name", default=""),
        )

@dataclass
class User(JsonObjectConvertible):
    name: str = ""
    address: Address = field(default_factory=Address)
    tags: list[Tag] = field(default_factory=list)

    def to_json_object(self) -> JsonObject:
        return {
            "name": self.name,
            "address": self.address.to_json_object(),
            "tags": convert_convertibles_to_json_objects(self.tags),
        }

    @classmethod
    def from_json_object(cls, json_object: JsonObject, *, ctx=None) -> "User":
        return cls(
            name=get_str_from_json_object(json_object, "name", default=""),
            address=get_convertible_from_json_object(
                json_object,
                "address",
                Address,
                Address,
                ctx=ctx,
            ),
            tags=get_convertibles_from_json_object(
                json_object,
                "tags",
                Tag,
                ctx=ctx,
            ),
        )

user = User(
    name="Alice",
    address=Address(city="Tokyo", country="Japan"),
    tags=[Tag(name="admin"), Tag(name="developer")],
)

json_object = user.to_json_object()
print(json_object)
# {
#     'name': 'Alice',
#     'address': {'city': 'Tokyo', 'country': 'Japan'},
#     'tags': [{'name': 'admin'}, {'name': 'developer'}],
# }

loaded_user = User.from_json_object(json_object)
print(loaded_user)
# User(
#     name='Alice',
#     address=Address(city='Tokyo', country='Japan'),
#     tags=[Tag(name='admin'), Tag(name='developer')],
# )
```

## Installation

Copy `jcl.py` into your project and import what you need.

```python
from jcl import JsonObject, JsonObjectConvertible
```

## Requirements

- Python 3.9.7+

## License

This project is licensed under the MIT License.
See the `LICENSE` file for details.

# JOCL (JSON Object Conversion Lib)

A small utility library for converting Python class instances to and from JSON objects, with helpers for validation, issue collection, and file I/O.

With this library, you can:
- convert Python class instances to JSON objects
- deserialize Python class instances from JSON objects
- validate JSON values before saving or loading
- load and save JSON files safely
- locate issues in nested JSON data more easily

## Examples

### Basic Usage

This example shows the basic workflow: convert an instance to a JSON object, save it to a JSON file, and deserialize it back into a class instance.
It uses `get()` during deserialization so missing or invalid fields fall back to default values while issues are collected in `JsonContext`.

```python
from dataclasses import dataclass
from pathlib import Path
from jocl import (
    JsonContext,
    JsonObject,
    JsonObjectConvertible,
    dump_convertible,
    get,
    load_convertible,
)


@dataclass
class User(JsonObjectConvertible):
    name: str = ""
    age: int = 0

    @classmethod
    def can_convert_from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> bool:
        return True

    def can_convert_to_json_object(self, ctx: JsonContext) -> bool:
        return True

    @classmethod
    def from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> "User":
        return cls(
            name=get(ctx, obj, "name", str),
            age=get(ctx, obj, "age", int),
        )

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "name": self.name,
            "age": self.age,
        }

    @classmethod
    def create_default(cls) -> "User":
        return cls()


ctx = JsonContext()
user = User(name="Alice", age=30)
path = Path("user.json")

# Convert the instance to a JSON object.
obj = user.to_json_object(ctx)
print(obj)
# {'name': 'Alice', 'age': 30}

# Write the instance to a JSON file.
dump_convertible(ctx, user, path)

# Load the instance back from the JSON file.
loaded_user = load_convertible(ctx, User, path)
print(loaded_user)
# User(name='Alice', age=30)
```

If you want missing or invalid fields to raise immediately, use `require()` instead:

```python
from jocl import JsonContext, JsonObject, require


@classmethod
def from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> "User":
    return cls(
        name=require(ctx, obj, "name", str),
        age=require(ctx, obj, "age", int),
    )
```

### Nested Objects and Lists

This example builds on the basic usage example.
It shows how to deserialize more complex JSON structures with the same `get()`-based pattern.
Here, `address` is a nested object, `tags` is a list of nested objects, and `user_id` may be either an integer or a string depending on the data source.

```python
from dataclasses import dataclass, field
from typing import Union
from jocl import (
    ArrayOf,
    JsonContext,
    JsonObject,
    JsonObjectConvertible,
    from_convertible,
    from_convertibles,
    get,
)


@dataclass
class Address(JsonObjectConvertible):
    city: str = ""
    country: str = ""

    @classmethod
    def can_convert_from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> bool:
        return True

    def can_convert_to_json_object(self, ctx: JsonContext) -> bool:
        return True

    @classmethod
    def from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> "Address":
        return cls(
            city=get(ctx, obj, "city", str),
            country=get(ctx, obj, "country", str),
        )

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "city": self.city,
            "country": self.country,
        }

    @classmethod
    def create_default(cls) -> "Address":
        return cls()


@dataclass
class Tag(JsonObjectConvertible):
    name: str = ""

    @classmethod
    def can_convert_from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> bool:
        return True

    def can_convert_to_json_object(self, ctx: JsonContext) -> bool:
        return True

    @classmethod
    def from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> "Tag":
        return cls(
            name=get(ctx, obj, "name", str),
        )

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "name": self.name,
        }

    @classmethod
    def create_default(cls) -> "Tag":
        return cls()


@dataclass
class User(JsonObjectConvertible):
    user_id: Union[int, str] = 0
    name: str = ""
    address: Address = field(default_factory=Address.create_default)
    tags: list[Tag] = field(default_factory=list)

    @classmethod
    def can_convert_from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> bool:
        return True

    def can_convert_to_json_object(self, ctx: JsonContext) -> bool:
        return True

    @classmethod
    def from_json_object(cls, ctx: JsonContext, obj: JsonObject) -> "User":
        return cls(
            user_id=get(ctx, obj, "user_id", (int, str)),
            name=get(ctx, obj, "name", str),
            address=get(ctx, obj, "address", Address),
            tags=get(ctx, obj, "tags", ArrayOf(Tag)),
        )

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "address": from_convertible(ctx, "address", self.address),
            "tags": from_convertibles(ctx, "tags", self.tags),
        }

    @classmethod
    def create_default(cls) -> "User":
        return cls()


ctx = JsonContext()

obj1: JsonObject = {
    "user_id": 1001,
    "name": "Alice",
    "address": {"city": "Tokyo", "country": "Japan"},
    "tags": [{"name": "admin"}, {"name": "developer"}],
}

obj2: JsonObject = {
    "user_id": "A-1002",
    "name": "Bob",
    "address": {"city": "Osaka", "country": "Japan"},
    "tags": [{"name": "artist"}],
}

user1 = User.from_json_object(ctx, obj1)
user2 = User.from_json_object(ctx, obj2)

print(user1)
print(user2)
# User(
#     user_id=1001,
#     name='Alice',
#     address=Address(city='Tokyo', country='Japan'),
#     tags=[Tag(name='admin'), Tag(name='developer')],
# )
# User(
#     user_id='A-1002',
#     name='Bob',
#     address=Address(city='Osaka', country='Japan'),
#     tags=[Tag(name='artist')],
# )
```

### Collecting Issues

This example shows how `get()` collects non-fatal issues in `JsonContext`.
After accessing the fields, you can inspect the collected issues and print them.

```python
from jocl import JsonContext, JsonObject, get


obj: JsonObject = {
    "name": 123,
    # "age" is missing
}

ctx = JsonContext()

name = get(ctx, obj, "name", str, default="default name")
age = get(ctx, obj, "age", int, default=456)

print(name)
print(age)

for issue in ctx.get_issues():
    print(issue)

# default name
# 456
# JSON issue at /name: Expected string, got int; severity=WARNING; code=INVALID_TYPE; value_type=int; value=123
# JSON issue at /age: Missing key; severity=WARNING; code=MISSING_KEY
```

## Installation

Copy `jocl.py` into your project and import what you need.

```python
from jocl import JsonObject, JsonObjectConvertible
```

## Requirements

- Python 3.9+
- No third-party dependencies

## License

This project is licensed under the MIT License.
See the `LICENSE` file for details.

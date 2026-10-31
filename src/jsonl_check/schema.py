"""Schema definition and compilation for structural JSON/JSONL validation."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Iterator, List, Optional, Pattern, Set, Union

from .errors import ValidationError, format_path

_TYPE_MAP = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
    "object": (dict,),
    "array": (list,),
}


def _get_type_name(val: Any) -> str:
    """Return JSON-friendly type name of value."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, dict):
        return "object"
    if isinstance(val, list):
        return "array"
    return type(val).__name__


class Schema:
    """Compiled structural schema for JSON/JSONL validation."""

    def __init__(self, raw: Union[dict[str, Any], "Schema", str]) -> None:
        if isinstance(raw, Schema):
            # Clone or reuse
            self._init_from_dict(raw.raw_schema)
            self.raw_schema = raw.raw_schema
        elif isinstance(raw, str):
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError(f"Schema must be a JSON object, got {type(parsed).__name__}")
            self.raw_schema = parsed
            self._init_from_dict(parsed)
        elif isinstance(raw, dict):
            self.raw_schema = raw
            self._init_from_dict(raw)
        else:
            raise TypeError(f"Schema must be dict, str, or Schema; got {type(raw).__name__}")

    def _init_from_dict(self, d: dict[str, Any]) -> None:
        # Types
        raw_type = d.get("type")
        if raw_type is None:
            self.types: Optional[tuple[str, ...]] = None
        elif isinstance(raw_type, str):
            self.types = (raw_type.lower(),)
        elif isinstance(raw_type, (list, tuple)):
            self.types = tuple(str(t).lower() for t in raw_type)
        else:
            raise ValueError(f"'type' must be string or list of strings, got {type(raw_type).__name__}")

        # Required fields
        raw_required = d.get("required")
        if raw_required is not None:
            if not isinstance(raw_required, (list, tuple)):
                raise ValueError(f"'required' must be list of strings, got {type(raw_required).__name__}")
            self.required: tuple[str, ...] = tuple(str(k) for k in raw_required)
        else:
            self.required = ()

        # Properties
        raw_props = d.get("properties")
        if raw_props is not None:
            if not isinstance(raw_props, dict):
                raise ValueError(f"'properties' must be a dict, got {type(raw_props).__name__}")
            self.properties: dict[str, Schema] = {k: Schema(v) for k, v in raw_props.items()}
        else:
            self.properties = {}

        # additionalProperties
        raw_add_props = d.get("additionalProperties")
        if raw_add_props is None:
            self.additional_properties: Union[bool, Schema] = True
        elif isinstance(raw_add_props, bool):
            self.additional_properties = raw_add_props
        elif isinstance(raw_add_props, dict):
            self.additional_properties = Schema(raw_add_props)
        else:
            raise ValueError(
                f"'additionalProperties' must be boolean or dict schema, got {type(raw_add_props).__name__}"
            )

        # Items (for arrays)
        raw_items = d.get("items")
        if raw_items is None:
            self.items: Optional[Union[Schema, list[Schema]]] = None
        elif isinstance(raw_items, dict):
            self.items = Schema(raw_items)
        elif isinstance(raw_items, (list, tuple)):
            self.items = [Schema(sub) for sub in raw_items]
        else:
            raise ValueError(f"'items' must be dict or list of schemas, got {type(raw_items).__name__}")

        # Enum & Const
        self.enum: Optional[list[Any]] = d.get("enum")
        self.has_const: bool = "const" in d
        self.const: Any = d.get("const")

        # Numeric constraints
        self.minimum: Optional[Union[int, float]] = d.get("minimum")
        self.maximum: Optional[Union[int, float]] = d.get("maximum")
        self.exclusive_minimum: Optional[Union[int, float]] = d.get("exclusiveMinimum")
        self.exclusive_maximum: Optional[Union[int, float]] = d.get("exclusiveMaximum")
        self.multiple_of: Optional[Union[int, float]] = d.get("multipleOf")

        # String constraints
        self.min_length: Optional[int] = d.get("minLength")
        self.max_length: Optional[int] = d.get("maxLength")
        raw_pattern = d.get("pattern")
        if raw_pattern is not None:
            try:
                self.pattern: Optional[Pattern[str]] = re.compile(raw_pattern)
            except re.error as err:
                raise ValueError(f"Invalid regex in pattern {raw_pattern!r}: {err}") from err
        else:
            self.pattern = None

        # Array constraints
        self.min_items: Optional[int] = d.get("minItems")
        self.max_items: Optional[int] = d.get("maxItems")
        self.unique_items: bool = bool(d.get("uniqueItems", False))

        # Object constraints
        self.min_properties: Optional[int] = d.get("minProperties")
        self.max_properties: Optional[int] = d.get("maxProperties")

    @classmethod
    def from_file(cls, path: str) -> Schema:
        """Load and compile schema from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)

    def validate(
        self,
        value: Any,
        path: str = "$",
        line: int = 1,
        column: Optional[int] = None,
    ) -> Iterator[ValidationError]:
        """Validate a Python value against this schema.

        Yields ValidationError instances for any mismatch.
        """
        # 1. Type validation
        if self.types is not None and "any" not in self.types:
            matches_type = False
            for expected_type in self.types:
                if expected_type in _TYPE_MAP:
                    types_to_check = _TYPE_MAP[expected_type]
                    # Note: in Python, bool is a subclass of int. Handle strictly:
                    if expected_type == "integer":
                        if isinstance(value, int) and not isinstance(value, bool):
                            matches_type = True
                            break
                    elif expected_type == "number":
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            matches_type = True
                            break
                    elif isinstance(value, types_to_check):
                        matches_type = True
                        break

            if not matches_type:
                expected_str = ", ".join(self.types) if len(self.types) > 1 else self.types[0]
                actual_str = _get_type_name(value)
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="type_mismatch",
                    message=f"Expected type {expected_str}, got {actual_str}",
                    value=value,
                )
                # If basic type mismatch, skip nested property validations
                return

        # 2. Const & Enum validation
        if self.has_const and value != self.const:
            yield ValidationError(
                line=line,
                column=column,
                path=path,
                code="const_mismatch",
                message=f"Expected constant value {self.const!r}, got {value!r}",
                value=value,
            )

        if self.enum is not None:
            # Check equality against enum elements (handling bool != 1, 0)
            in_enum = False
            for allowed in self.enum:
                if type(allowed) is type(value) and allowed == value:
                    in_enum = True
                    break
                elif (
                    isinstance(allowed, (int, float))
                    and isinstance(value, (int, float))
                    and not isinstance(allowed, bool)
                    and not isinstance(value, bool)
                    and allowed == value
                ):
                    in_enum = True
                    break
            if not in_enum:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="enum_mismatch",
                    message=f"Value {value!r} is not in allowed enum {self.enum!r}",
                    value=value,
                )

        # 3. Numeric checks
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="minimum_error",
                    message=f"Value {value} is less than minimum {self.minimum}",
                    value=value,
                )
            if self.maximum is not None and value > self.maximum:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="maximum_error",
                    message=f"Value {value} is greater than maximum {self.maximum}",
                    value=value,
                )
            if self.exclusive_minimum is not None and value <= self.exclusive_minimum:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="exclusive_minimum_error",
                    message=f"Value {value} is not strictly greater than {self.exclusive_minimum}",
                    value=value,
                )
            if self.exclusive_maximum is not None and value >= self.exclusive_maximum:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="exclusive_maximum_error",
                    message=f"Value {value} is not strictly less than {self.exclusive_maximum}",
                    value=value,
                )
            if self.multiple_of is not None and self.multiple_of != 0:
                remainder = value % self.multiple_of
                if abs(remainder) > 1e-9 and abs(remainder - self.multiple_of) > 1e-9:
                    yield ValidationError(
                        line=line,
                        column=column,
                        path=path,
                        code="multiple_of_error",
                        message=f"Value {value} is not a multiple of {self.multiple_of}",
                        value=value,
                    )

        # 4. String checks
        if isinstance(value, str):
            if self.min_length is not None and len(value) < self.min_length:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="min_length_error",
                    message=f"String length {len(value)} is less than minLength {self.min_length}",
                    value=value,
                )
            if self.max_length is not None and len(value) > self.max_length:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="max_length_error",
                    message=f"String length {len(value)} is greater than maxLength {self.max_length}",
                    value=value,
                )
            if self.pattern is not None and not self.pattern.search(value):
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="pattern_mismatch",
                    message=f"String does not match pattern {self.pattern.pattern!r}",
                    value=value,
                )

        # 5. Object checks
        if isinstance(value, dict):
            if self.min_properties is not None and len(value) < self.min_properties:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="min_properties_error",
                    message=f"Object property count {len(value)} is less than minProperties {self.min_properties}",
                    value=len(value),
                )
            if self.max_properties is not None and len(value) > self.max_properties:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="max_properties_error",
                    message=f"Object property count {len(value)} is greater than maxProperties {self.max_properties}",
                    value=len(value),
                )

            # Check required fields
            for req in self.required:
                if req not in value:
                    field_path = format_path(path, req)
                    yield ValidationError(
                        line=line,
                        column=column,
                        path=field_path,
                        code="missing_required",
                        message=f"Missing required field '{req}'",
                        value=None,
                    )

            # Check properties
            for prop_name, prop_schema in self.properties.items():
                if prop_name in value:
                    sub_val = value[prop_name]
                    sub_path = format_path(path, prop_name)
                    yield from prop_schema.validate(sub_val, path=sub_path, line=line)

            # Check additionalProperties
            if self.additional_properties is False:
                for k, v in value.items():
                    if k not in self.properties:
                        sub_path = format_path(path, k)
                        yield ValidationError(
                            line=line,
                            column=column,
                            path=sub_path,
                            code="unexpected_property",
                            message=f"Unexpected property '{k}' not defined in schema",
                            value=v,
                        )
            elif isinstance(self.additional_properties, Schema):
                for k, v in value.items():
                    if k not in self.properties:
                        sub_path = format_path(path, k)
                        yield from self.additional_properties.validate(v, path=sub_path, line=line)

        # 6. Array checks
        if isinstance(value, list):
            if self.min_items is not None and len(value) < self.min_items:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="min_items_error",
                    message=f"Array length {len(value)} is less than minItems {self.min_items}",
                    value=len(value),
                )
            if self.max_items is not None and len(value) > self.max_items:
                yield ValidationError(
                    line=line,
                    column=column,
                    path=path,
                    code="max_items_error",
                    message=f"Array length {len(value)} is greater than maxItems {self.max_items}",
                    value=len(value),
                )
            if self.unique_items:
                # Check for duplicate items
                seen: list[Any] = []
                has_duplicate = False
                for item in value:
                    if item in seen:
                        has_duplicate = True
                        break
                    seen.append(item)
                if has_duplicate:
                    yield ValidationError(
                        line=line,
                        column=column,
                        path=path,
                        code="unique_items_error",
                        message="Array contains duplicate items",
                        value=value,
                    )

            # Item schemas
            if isinstance(self.items, Schema):
                for idx, elem in enumerate(value):
                    elem_path = format_path(path, idx)
                    yield from self.items.validate(elem, path=elem_path, line=line)
            elif isinstance(self.items, list):
                # Positional / tuple validation
                for idx, elem in enumerate(value):
                    if idx < len(self.items):
                        elem_path = format_path(path, idx)
                        yield from self.items[idx].validate(elem, path=elem_path, line=line)

"""Tests for Schema compilation and validation rules."""

import unittest

from jsonl_check.schema import Schema


class TestSchemaValidation(unittest.TestCase):
    def test_type_validation_primitives(self):
        schema = Schema({"type": "string"})
        self.assertEqual(list(schema.validate("hello")), [])
        errs = list(schema.validate(123))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "type_mismatch")
        self.assertEqual(errs[0].path, "$")

    def test_strict_boolean_vs_integer(self):
        # In Python, isinstance(True, int) is True, but JSON types must separate them
        int_schema = Schema({"type": "integer"})
        self.assertEqual(list(int_schema.validate(42)), [])
        errs = list(int_schema.validate(True))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "type_mismatch")

        bool_schema = Schema({"type": "boolean"})
        self.assertEqual(list(bool_schema.validate(False)), [])
        errs2 = list(bool_schema.validate(1))
        self.assertEqual(len(errs2), 1)
        self.assertEqual(errs2[0].code, "type_mismatch")

    def test_union_types(self):
        schema = Schema({"type": ["string", "null"]})
        self.assertEqual(list(schema.validate("test")), [])
        self.assertEqual(list(schema.validate(None)), [])
        errs = list(schema.validate(123))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "type_mismatch")

    def test_required_fields(self):
        schema = Schema({
            "type": "object",
            "required": ["id", "username"],
            "properties": {
                "id": {"type": "integer"},
                "username": {"type": "string"},
            },
        })
        # Valid
        self.assertEqual(list(schema.validate({"id": 1, "username": "alice"})), [])

        # Missing required
        errs = list(schema.validate({"id": 1}))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "missing_required")
        self.assertEqual(errs[0].path, "$.username")

    def test_nested_properties_and_path(self):
        schema = Schema({
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "required": ["email"],
                    "properties": {
                        "email": {"type": "string"},
                        "profile": {
                            "type": "object",
                            "properties": {
                                "age": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            },
        })

        data = {
            "user": {
                "email": "test@example.com",
                "profile": {
                    "age": -5,
                },
            },
        }
        errs = list(schema.validate(data))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "minimum_error")
        self.assertEqual(errs[0].path, "$.user.profile.age")

    def test_special_characters_in_path(self):
        schema = Schema({
            "type": "object",
            "properties": {
                "first name": {"type": "string"},
                "sub-item.code": {"type": "integer"},
            },
        })
        errs = list(schema.validate({"first name": 123, "sub-item.code": "bad"}))
        self.assertEqual(len(errs), 2)
        paths = {e.path for e in errs}
        self.assertIn("$['first name']", paths)
        self.assertIn("$['sub-item.code']", paths)

    def test_additional_properties_false(self):
        schema = Schema({
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "additionalProperties": False,
        })
        self.assertEqual(list(schema.validate({"name": "ok"})), [])
        errs = list(schema.validate({"name": "ok", "extra": 123}))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "unexpected_property")
        self.assertEqual(errs[0].path, "$.extra")

    def test_array_items_schema(self):
        schema = Schema({
            "type": "array",
            "items": {"type": "integer"},
        })
        self.assertEqual(list(schema.validate([1, 2, 3])), [])
        errs = list(schema.validate([1, "two", 3]))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "type_mismatch")
        self.assertEqual(errs[0].path, "$[1]")

    def test_array_tuple_items(self):
        schema = Schema({
            "type": "array",
            "items": [{"type": "string"}, {"type": "integer"}],
        })
        self.assertEqual(list(schema.validate(["a", 1])), [])
        errs = list(schema.validate([1, "a"]))
        self.assertEqual(len(errs), 2)
        self.assertEqual(errs[0].path, "$[0]")
        self.assertEqual(errs[1].path, "$[1]")

    def test_enum_and_const(self):
        enum_schema = Schema({"enum": ["red", "green", "blue"]})
        self.assertEqual(list(enum_schema.validate("green")), [])
        errs = list(enum_schema.validate("yellow"))
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "enum_mismatch")

        const_schema = Schema({"const": "active"})
        self.assertEqual(list(const_schema.validate("active")), [])
        errs2 = list(const_schema.validate("inactive"))
        self.assertEqual(len(errs2), 1)
        self.assertEqual(errs2[0].code, "const_mismatch")

    def test_string_constraints(self):
        schema = Schema({
            "type": "string",
            "minLength": 3,
            "maxLength": 6,
            "pattern": r"^[a-z]+$",
        })
        self.assertEqual(list(schema.validate("abc")), [])

        # Too short
        errs_short = list(schema.validate("ab"))
        self.assertEqual(errs_short[0].code, "min_length_error")

        # Too long
        errs_long = list(schema.validate("abcdefg"))
        self.assertEqual(errs_long[0].code, "max_length_error")

        # Pattern mismatch
        errs_pat = list(schema.validate("ABC"))
        self.assertEqual(errs_pat[0].code, "pattern_mismatch")

    def test_numeric_bounds(self):
        schema = Schema({
            "type": "number",
            "minimum": 10,
            "maximum": 20,
            "multipleOf": 2,
        })
        self.assertEqual(list(schema.validate(14)), [])
        self.assertEqual(list(schema.validate(14.0)), [])

        # Under minimum
        self.assertEqual(list(schema.validate(8))[0].code, "minimum_error")
        # Over maximum
        self.assertEqual(list(schema.validate(22))[0].code, "maximum_error")
        # Not multiple
        self.assertEqual(list(schema.validate(15))[0].code, "multiple_of_error")

    def test_array_bounds(self):
        schema = Schema({
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "uniqueItems": True,
        })
        self.assertEqual(list(schema.validate([1, 2])), [])

        # Too few items
        self.assertEqual(list(schema.validate([1]))[0].code, "min_items_error")
        # Too many items
        self.assertEqual(list(schema.validate([1, 2, 3, 4]))[0].code, "max_items_error")
        # Duplicate items
        self.assertEqual(list(schema.validate([1, 1]))[0].code, "unique_items_error")

    def test_object_bounds(self):
        schema = Schema({
            "type": "object",
            "minProperties": 1,
            "maxProperties": 2,
        })
        self.assertEqual(list(schema.validate({"a": 1})), [])
        self.assertEqual(list(schema.validate({}))[0].code, "min_properties_error")
        errs_max = list(schema.validate({"a": 1, "b": 2, "c": 3}))
        self.assertEqual(errs_max[0].code, "max_properties_error")


if __name__ == "__main__":
    unittest.main()

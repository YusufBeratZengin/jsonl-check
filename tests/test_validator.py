"""Tests for streaming validator, syntax checking, and line tracking."""

import os
import tempfile
import unittest

from jsonl_check.validator import (
    is_valid,
    validate_file,
    validate_json,
    validate_jsonl,
)


class TestValidator(unittest.TestCase):
    def test_jsonl_syntax_only_valid(self):
        lines = [
            '{"name": "Alice", "age": 30}\n',
            '{"name": "Bob", "age": 25}\n',
            '{"name": "Charlie", "age": 40}\n',
        ]
        errors = list(validate_jsonl(lines))
        self.assertEqual(len(errors), 0)

    def test_jsonl_corrupted_line_number_reported_accurately(self):
        # Line 1: valid
        # Line 2: valid
        # Line 3: broken JSON
        # Line 4: valid
        lines = [
            '{"id": 1, "status": "ok"}\n',
            '{"id": 2, "status": "ok"}\n',
            '{"id": 3, "status": UNQUOTED_VAL}\n',
            '{"id": 4, "status": "ok"}\n',
        ]
        errors = list(validate_jsonl(lines))
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.line, 3)
        self.assertEqual(err.code, "syntax_error")
        self.assertEqual(err.path, "$")

    def test_jsonl_schema_validation_line_and_path(self):
        schema = {
            "type": "object",
            "required": ["id", "email"],
            "properties": {
                "id": {"type": "integer"},
                "email": {"type": "string"},
                "profile": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "number", "minimum": 0},
                    },
                },
            },
        }
        lines = [
            '{"id": 1, "email": "alice@example.com", "profile": {"score": 95}}\n',
            # Line 2: score < 0
            '{"id": 2, "email": "bob@example.com", "profile": {"score": -10}}\n',
            '{"id": "not_an_int", "email": "charlie@example.com"}\n',  # Line 3: id not int
            '{"id": 4}\n',  # Line 4: missing email
        ]
        errors = list(validate_jsonl(lines, schema=schema))
        self.assertEqual(len(errors), 3)

        # Line 2 error
        self.assertEqual(errors[0].line, 2)
        self.assertEqual(errors[0].path, "$.profile.score")
        self.assertEqual(errors[0].code, "minimum_error")

        # Line 3 error
        self.assertEqual(errors[1].line, 3)
        self.assertEqual(errors[1].path, "$.id")
        self.assertEqual(errors[1].code, "type_mismatch")

        # Line 4 error
        self.assertEqual(errors[2].line, 4)
        self.assertEqual(errors[2].path, "$.email")
        self.assertEqual(errors[2].code, "missing_required")

    def test_fail_fast_stops_immediately(self):
        lines = [
            '{"id": "bad1"}\n',
            '{"id": "bad2"}\n',
            '{"id": "bad3"}\n',
        ]
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        # Normal: 3 errors
        all_errors = list(validate_jsonl(lines, schema=schema, fail_fast=False))
        self.assertEqual(len(all_errors), 3)

        # Fail fast: exactly 1 error
        ff_errors = list(validate_jsonl(lines, schema=schema, fail_fast=True))
        self.assertEqual(len(ff_errors), 1)
        self.assertEqual(ff_errors[0].line, 1)

    def test_max_errors_limit(self):
        lines = [
            '{"id": "bad1"}\n',
            '{"id": "bad2"}\n',
            '{"id": "bad3"}\n',
            '{"id": "bad4"}\n',
        ]
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        limited = list(validate_jsonl(lines, schema=schema, max_errors=2))
        self.assertEqual(len(limited), 2)
        self.assertEqual([e.line for e in limited], [1, 2])

    def test_blank_lines_handling(self):
        lines = [
            '{"id": 1}\n',
            '\n',
            '   \r\n',
            '{"id": 2}\n',
        ]
        # By default, ignore_empty=True -> 0 errors
        self.assertEqual(len(list(validate_jsonl(lines, ignore_empty=True))), 0)

        # With ignore_empty=False -> 2 syntax errors on lines 2 and 3
        errs = list(validate_jsonl(lines, ignore_empty=False))
        self.assertEqual(len(errs), 2)
        self.assertEqual(errs[0].line, 2)
        self.assertEqual(errs[1].line, 3)

    def test_single_json_document_validation(self):
        json_text = """{
  "name": "Package",
  "version": 1,
  "dependencies": [
    "alpha",
    123
  ]
}"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        }
        errors = list(validate_json(json_text, schema=schema))
        self.assertEqual(len(errors), 2)

        # version is on line 3
        self.assertEqual(errors[0].path, "$.version")
        self.assertEqual(errors[0].code, "type_mismatch")
        self.assertEqual(errors[0].line, 3)

        # dependencies[1] is on line 6
        self.assertEqual(errors[1].path, "$.dependencies[1]")
        self.assertEqual(errors[1].code, "type_mismatch")
        self.assertEqual(errors[1].line, 6)

    def test_single_json_syntax_error(self):
        bad_json = '{\n  "name": "Alice",\n  "age": ,\n}'
        errors = list(validate_json(bad_json))
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "syntax_error")
        self.assertEqual(errors[0].line, 3)

    def test_validate_file_auto_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = os.path.join(tmpdir, "data.jsonl")
            with open(jsonl_path, "w", encoding="utf-8") as f:
                f.write('{"x": 1}\n{"x": "bad"}\n')

            schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
            errors = list(validate_file(jsonl_path, schema=schema))
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].line, 2)

            # JSON file
            json_path = os.path.join(tmpdir, "data.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write('{\n  "x": "bad"\n}')

            errors_json = list(validate_file(json_path, schema=schema))
            self.assertEqual(len(errors_json), 1)
            self.assertEqual(errors_json[0].line, 2)

    def test_is_valid_helper(self):
        schema = {"type": "integer"}
        self.assertTrue(is_valid(42, schema=schema))
        self.assertFalse(is_valid("str", schema=schema))


if __name__ == "__main__":
    unittest.main()

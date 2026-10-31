"""Tests for Command Line Interface."""

import io
import json
import os
import sys
import tempfile
import unittest

from jsonl_check.cli import main


class TestCLI(unittest.TestCase):
    def test_valid_file_exit_zero(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1}\n{"id": 2}\n')
            temp_name = f.name
        try:
            exit_code = main([temp_name])
            self.assertEqual(exit_code, 0)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_invalid_syntax_exit_one_with_text_output(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1}\n{"bad json\n')
            temp_name = f.name
        try:
            captured_out = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_out
            try:
                exit_code = main([temp_name])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_code, 1)
            output = captured_out.getvalue()
            self.assertIn("line 2", output)
            self.assertIn("syntax_error", output)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_schema_validation_with_json_format_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = os.path.join(tmpdir, "data.jsonl")
            schema_file = os.path.join(tmpdir, "schema.json")

            with open(data_file, "w", encoding="utf-8") as f:
                f.write('{"id": 1, "name": "ok"}\n{"id": "two", "name": "bad"}\n')

            with open(schema_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                }))

            captured_out = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_out
            try:
                exit_code = main([
                    data_file,
                    "-s", schema_file,
                    "--format", "json",
                ])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_code, 1)
            output = captured_out.getvalue()
            parsed = json.loads(output)
            self.assertIsInstance(parsed, list)
            self.assertEqual(len(parsed), 1)
            err = parsed[0]
            self.assertEqual(err["line"], 2)
            self.assertEqual(err["path"], "$.id")
            self.assertEqual(err["code"], "type_mismatch")

    def test_schema_validation_with_jsonl_format_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = os.path.join(tmpdir, "data.jsonl")
            schema_file = os.path.join(tmpdir, "schema.json")

            with open(data_file, "w", encoding="utf-8") as f:
                f.write('{"val": "a"}\n{"val": "b"}\n')

            with open(schema_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "object",
                    "properties": {
                        "val": {"type": "integer"},
                    },
                }))

            captured_out = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_out
            try:
                exit_code = main([
                    data_file,
                    "-s", schema_file,
                    "--format", "jsonl",
                ])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_code, 1)
            lines = [line.strip() for line in captured_out.getvalue().splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            err1 = json.loads(lines[0])
            err2 = json.loads(lines[1])
            self.assertEqual(err1["line"], 1)
            self.assertEqual(err2["line"], 2)

    def test_cli_fail_fast(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"bad1\n{"bad2\n{"bad3\n')
            temp_name = f.name
        try:
            captured_out = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_out
            try:
                exit_code = main([temp_name, "--fail-fast", "--format", "jsonl"])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_code, 1)
            lines = [line for line in captured_out.getvalue().splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_cli_quiet(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"bad json\n')
            temp_name = f.name
        try:
            captured_out = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_out
            try:
                exit_code = main([temp_name, "-q"])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_code, 1)
            self.assertEqual(captured_out.getvalue().strip(), "")
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_missing_input_file_returns_code_two(self):
        captured_err = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured_err
        try:
            exit_code = main(["non_existent_file_12345.jsonl"])
        finally:
            sys.stderr = old_stderr

        self.assertEqual(exit_code, 2)
        self.assertIn("File not found", captured_err.getvalue())

    def test_missing_schema_file_returns_code_two(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1}\n')
            temp_name = f.name
        try:
            captured_err = io.StringIO()
            old_stderr = sys.stderr
            sys.stderr = captured_err
            try:
                exit_code = main([temp_name, "-s", "no_such_schema.json"])
            finally:
                sys.stderr = old_stderr

            self.assertEqual(exit_code, 2)
            self.assertIn("Schema file not found", captured_err.getvalue())
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_stdin_processing(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO('{"id": 1}\n{"id": 2}\n')
        try:
            exit_code = main(["-"])
            self.assertEqual(exit_code, 0)
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()

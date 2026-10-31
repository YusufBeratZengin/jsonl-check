"""Tests for streaming behavior and constant O(1) memory footprint."""

import gc
import io
import json
import tracemalloc
import unittest

from jsonl_check.cli import _stream_errors
from jsonl_check.validator import validate_jsonl


class TestStreaming(unittest.TestCase):
    def test_streaming_generator_large_dataset_accuracy(self):
        """Verify that streaming through 100,000 lines correctly flags specific corrupted lines."""
        total_lines = 100_000
        corrupt_syntax_line = 42_123
        schema_invalid_line = 85_700

        schema = {
            "type": "object",
            "required": ["id", "val"],
            "properties": {
                "id": {"type": "integer"},
                "val": {"type": "string"},
            },
        }

        def line_generator():
            for i in range(1, total_lines + 1):
                if i == corrupt_syntax_line:
                    yield '{"id": ' + str(i) + ', "val": UNQUOTED}\n'
                elif i == schema_invalid_line:
                    yield '{"id": ' + str(i) + ', "val": 99999}\n'
                else:
                    yield '{"id": ' + str(i) + ', "val": "ok"}\n'

        errors = list(validate_jsonl(line_generator(), schema=schema))
        self.assertEqual(len(errors), 2)

        # First error: syntax error at corrupt_syntax_line
        self.assertEqual(errors[0].line, corrupt_syntax_line)
        self.assertEqual(errors[0].code, "syntax_error")
        self.assertEqual(errors[0].path, "$")

        # Second error: schema error at schema_invalid_line
        self.assertEqual(errors[1].line, schema_invalid_line)
        self.assertEqual(errors[1].path, "$.val")
        self.assertEqual(errors[1].code, "type_mismatch")

    def test_streaming_memory_footprint_is_bounded(self):
        """Verify that streaming 50,000 lines retains small bounded memory."""
        gc.collect()
        tracemalloc.start()

        def massive_stream():
            for i in range(1, 50_001):
                yield '{"id": ' + str(i) + ', "tag": "item_' + str(i) + '"}\n'

        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "tag": {"type": "string"},
            },
        }

        # Iterate through the stream without storing all lines
        count = 0
        for _ in validate_jsonl(massive_stream(), schema=schema):
            count += 1

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.assertEqual(count, 0)
        # Peak memory used for processing 50,000 records should remain modest (< 10 MB)
        self.assertLess(peak, 10 * 1024 * 1024, f"Peak memory was {peak / 1024 / 1024:.2f} MB")

    def test_streaming_json_output_does_not_buffer(self):
        """Verify that _stream_errors with format='json' writes incrementally."""
        class StreamSink(io.StringIO):
            def __init__(self):
                super().__init__()
                self.write_calls = 0

            def write(self, s):
                self.write_calls += 1
                return super().write(s)

        from jsonl_check.errors import ValidationError

        def error_gen():
            for i in range(1, 10):
                yield ValidationError(line=i, path=f"$.item[{i}]", code="test_code", message="msg")

        sink = StreamSink()
        count = _stream_errors(error_gen(), output_format="json", out=sink)
        self.assertEqual(count, 9)
        # Writes happened iteratively
        self.assertGreater(sink.write_calls, 10)
        parsed = json.loads(sink.getvalue())
        self.assertEqual(len(parsed), 9)
        self.assertEqual(parsed[0]["line"], 1)
        self.assertEqual(parsed[-1]["line"], 9)


if __name__ == "__main__":
    unittest.main()

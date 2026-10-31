"""Streaming validation engine for JSON and JSONL documents."""

from __future__ import annotations

import io
import json
import os
from typing import Any, Iterable, Iterator, Optional, TextIO, Union

from .errors import ValidationError
from .scanner import JSONLocationScanner
from .schema import Schema


def validate_jsonl(
    stream: Iterable[str],
    schema: Optional[Union[Schema, dict[str, Any], str]] = None,
    fail_fast: bool = False,
    max_errors: Optional[int] = None,
    ignore_empty: bool = True,
) -> Iterator[ValidationError]:
    """Validate JSON Lines stream line-by-line with streaming O(1) memory.

    Args:
        stream: Iterable of text lines (e.g. an open file, sys.stdin, or list of strings).
        schema: Optional Schema object, schema dict, or JSON schema string.
        fail_fast: If True, stop immediately upon finding the first error.
        max_errors: If set, stop once this many errors have been yielded.
        ignore_empty: If True, blank lines are ignored; if False, flagged as syntax errors.

    Yields:
        ValidationError instances with line numbers and JSONPath expressions.
    """
    compiled_schema = Schema(schema) if schema is not None else None
    error_count = 0

    for line_no, raw_line in enumerate(stream, 1):
        line = raw_line.rstrip("\r\n")
        if not line or line.isspace():
            if ignore_empty:
                continue
            err = ValidationError(
                line=line_no,
                path="$",
                code="syntax_error",
                message="Empty line encountered in JSONL",
            )
            yield err
            error_count += 1
            if fail_fast or (max_errors is not None and error_count >= max_errors):
                return
            continue

        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as dec_err:
            err = ValidationError(
                line=line_no,
                column=dec_err.colno,
                path="$",
                code="syntax_error",
                message=f"JSON syntax error: {dec_err.msg}",
            )
            yield err
            error_count += 1
            if fail_fast or (max_errors is not None and error_count >= max_errors):
                return
            continue

        # If schema provided, validate parsed value
        if compiled_schema is not None:
            for val_err in compiled_schema.validate(parsed, path="$", line=line_no):
                yield val_err
                error_count += 1
                if fail_fast or (max_errors is not None and error_count >= max_errors):
                    return


def validate_json(
    source: Union[str, TextIO, io.StringIO],
    schema: Optional[Union[Schema, dict[str, Any], str]] = None,
    fail_fast: bool = False,
    max_errors: Optional[int] = None,
) -> Iterator[ValidationError]:
    """Validate a single JSON document with line and JSONPath tracking.

    Args:
        source: JSON string or file-like object.
        schema: Optional Schema object, schema dict, or JSON schema string.
        fail_fast: If True, stop immediately upon finding the first error.
        max_errors: If set, stop once this many errors have been yielded.

    Yields:
        ValidationError instances with exact line numbers and JSONPath expressions.
    """
    compiled_schema = Schema(schema) if schema is not None else None

    if hasattr(source, "read"):
        text = source.read()
    else:
        text = str(source)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as dec_err:
        yield ValidationError(
            line=dec_err.lineno,
            column=dec_err.colno,
            path="$",
            code="syntax_error",
            message=f"JSON syntax error: {dec_err.msg}",
        )
        return

    if compiled_schema is not None:
        scanner = JSONLocationScanner(text)
        error_count = 0
        for val_err in compiled_schema.validate(parsed, path="$", line=1):
            line_no, col_no = scanner.get_location(val_err.path)
            val_err.line = line_no
            if col_no is not None:
                val_err.column = col_no
            yield val_err
            error_count += 1
            if fail_fast or (max_errors is not None and error_count >= max_errors):
                return


def validate_file(
    file_or_path: Union[str, os.PathLike[str], TextIO],
    schema: Optional[Union[Schema, dict[str, Any], str]] = None,
    mode: str = "auto",
    fail_fast: bool = False,
    max_errors: Optional[int] = None,
    ignore_empty: bool = True,
    encoding: str = "utf-8",
) -> Iterator[ValidationError]:
    """Validate a JSON or JSONL file from path or stream.

    Args:
        file_or_path: File path or open file object.
        schema: Optional Schema.
        mode: "auto", "jsonl", or "json".
        fail_fast: Stop after first error.
        max_errors: Stop after max_errors errors.
        ignore_empty: Ignore blank lines in JSONL.
        encoding: File encoding when opening path (default: utf-8).

    Yields:
        ValidationError instances.
    """
    # Detect mode if auto
    actual_mode = mode.lower()
    if actual_mode == "auto":
        if isinstance(file_or_path, (str, os.PathLike)):
            path_str = str(file_or_path).lower()
            if path_str.endswith(".json") and not path_str.endswith(".jsonl"):
                actual_mode = "json"
            else:
                actual_mode = "jsonl"
        else:
            name = getattr(file_or_path, "name", "").lower()
            if name.endswith(".json") and not name.endswith(".jsonl"):
                actual_mode = "json"
            else:
                actual_mode = "jsonl"

    if actual_mode == "json":
        if isinstance(file_or_path, (str, os.PathLike)):
            with open(file_or_path, "r", encoding=encoding) as f:
                yield from validate_json(
                    f,
                    schema=schema,
                    fail_fast=fail_fast,
                    max_errors=max_errors,
                )
        else:
            yield from validate_json(
                file_or_path,
                schema=schema,
                fail_fast=fail_fast,
                max_errors=max_errors,
            )
    else:
        # JSONL mode (pure streaming line-by-line)
        if isinstance(file_or_path, (str, os.PathLike)):
            with open(file_or_path, "r", encoding=encoding) as f:
                yield from validate_jsonl(
                    f,
                    schema=schema,
                    fail_fast=fail_fast,
                    max_errors=max_errors,
                    ignore_empty=ignore_empty,
                )
        else:
            yield from validate_jsonl(
                file_or_path,
                schema=schema,
                fail_fast=fail_fast,
                max_errors=max_errors,
                ignore_empty=ignore_empty,
            )


def validate_value(
    value: Any,
    schema: Union[Schema, dict[str, Any], str],
    path: str = "$",
    line: int = 1,
) -> list[ValidationError]:
    """Validate an in-memory Python object against a schema and return error list."""
    compiled = Schema(schema) if not isinstance(schema, Schema) else schema
    return list(compiled.validate(value, path=path, line=line))


def is_valid(
    file_or_data: Any,
    schema: Optional[Union[Schema, dict[str, Any], str]] = None,
    mode: str = "auto",
) -> bool:
    """Check whether a file, stream, or value is valid without returning errors."""
    is_path = isinstance(file_or_data, (str, os.PathLike)) and os.path.isfile(str(file_or_data))
    if is_path or hasattr(file_or_data, "readline"):
        for _ in validate_file(file_or_data, schema=schema, mode=mode, fail_fast=True):
            return False
        return True
    else:
        if schema is None:
            return True
        for _ in validate_value(file_or_data, schema=schema):
            return False
        return True

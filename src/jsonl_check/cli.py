"""Command Line Interface for jsonl-check."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Iterator, Optional, TextIO

from .errors import ValidationError
from .schema import Schema
from .validator import validate_file

__version__ = "0.1.0"


def _format_text_error(err: ValidationError, filename: Optional[str] = None) -> str:
    loc = f"line {err.line}"
    if err.column is not None:
        loc += f", col {err.column}"
    if err.path and err.path != "$":
        loc += f" at {err.path}"
    prefix = f"{filename}: " if filename else ""
    return f"{prefix}{loc}: [{err.code}] {err.message}"


def _stream_errors(
    errors: Iterator[ValidationError],
    output_format: str,
    out: TextIO = sys.stdout,
    filename: Optional[str] = None,
    quiet: bool = False,
) -> int:
    """Stream errors to output and return total error count."""
    count = 0

    if quiet:
        for _ in errors:
            count += 1
        return count

    if output_format == "text":
        for err in errors:
            count += 1
            out.write(_format_text_error(err, filename) + "\n")
            out.flush()

    elif output_format == "jsonl":
        for err in errors:
            count += 1
            d = err.to_dict()
            if filename:
                d["file"] = filename
            out.write(json.dumps(d) + "\n")
            out.flush()

    elif output_format == "json":
        out.write("[\n")
        first = True
        for err in errors:
            count += 1
            d = err.to_dict()
            if filename:
                d["file"] = filename
            item_str = json.dumps(d, indent=2)
            indented = "\n".join("  " + line for line in item_str.splitlines())
            if not first:
                out.write(",\n")
            else:
                first = False
            out.write(indented)
            out.flush()
        out.write("\n]\n")
        out.flush()

    return count


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="jsonl-check",
        description="Fast, streaming JSON and JSONL validator with line numbers and JSONPath.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="-",
        help=(
            "Path to JSON or JSONL file to validate, or '-' to read from standard input "
            "(default: -)"
        ),
    )
    parser.add_argument(
        "-s",
        "--schema",
        metavar="SCHEMA_FILE",
        help="Path to JSON schema file for structural validation (optional)",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["auto", "jsonl", "json"],
        default="auto",
        help="Input format mode: auto, jsonl, or json (default: auto)",
    )
    parser.add_argument(
        "-f",
        "--fail-fast",
        action="store_true",
        help="Stop immediately upon encountering the first validation error",
    )
    parser.add_argument(
        "-n",
        "--max-errors",
        type=int,
        default=0,
        metavar="N",
        help="Maximum number of errors to report (default: 0 for unlimited)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "jsonl"],
        default="text",
        help="Output format for validation errors: text, json, or jsonl (default: text)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress error output; only return exit status",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: treat empty lines in JSONL files as syntax errors",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print summary statistics to stderr upon completion",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding of input file (default: utf-8)",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Returns exit code 0 on success, 1 on validation error, 2 on operational error.
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    start_time = time.perf_counter()

    # Load schema if specified
    compiled_schema: Optional[Schema] = None
    if args.schema:
        if not os.path.isfile(args.schema):
            sys.stderr.write(f"Error: Schema file not found: {args.schema}\n")
            return 2
        try:
            compiled_schema = Schema.from_file(args.schema)
        except Exception as ex:
            sys.stderr.write(f"Error: Failed to load schema: {ex}\n")
            return 2

    # Open file or stdin
    is_stdin = args.file == "-"
    target_stream = None
    display_filename = None

    if is_stdin:
        target_stream = sys.stdin
    else:
        if not os.path.exists(args.file):
            sys.stderr.write(f"Error: File not found: {args.file}\n")
            return 2
        display_filename = args.file

    max_errs = args.max_errors if args.max_errors > 0 else None

    try:
        if target_stream is not None:
            errors_iter = validate_file(
                target_stream,
                schema=compiled_schema,
                mode=args.mode,
                fail_fast=args.fail_fast,
                max_errors=max_errs,
                ignore_empty=not args.strict,
            )
            error_count = _stream_errors(
                errors_iter,
                output_format=args.format,
                out=sys.stdout,
                filename=display_filename,
                quiet=args.quiet,
            )
        else:
            errors_iter = validate_file(
                args.file,
                schema=compiled_schema,
                mode=args.mode,
                fail_fast=args.fail_fast,
                max_errors=max_errs,
                ignore_empty=not args.strict,
                encoding=args.encoding,
            )
            error_count = _stream_errors(
                errors_iter,
                output_format=args.format,
                out=sys.stdout,
                filename=display_filename,
                quiet=args.quiet,
            )
    except Exception as ex:
        sys.stderr.write(f"Error during validation: {ex}\n")
        return 2

    elapsed = time.perf_counter() - start_time

    if args.stats:
        status_msg = "OK" if error_count == 0 else f"FAILED ({error_count} errors)"
        sys.stderr.write(f"[jsonl-check] Finished in {elapsed:.3f}s. Result: {status_msg}\n")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

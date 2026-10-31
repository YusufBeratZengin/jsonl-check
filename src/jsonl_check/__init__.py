"""jsonl-check: Fast, streaming JSON and JSONL validator with line numbers and JSONPath."""

from .errors import ValidationError, format_path
from .schema import Schema
from .validator import (
    is_valid,
    validate_file,
    validate_json,
    validate_jsonl,
    validate_value,
)

__version__ = "0.1.0"
__all__ = [
    "ValidationError",
    "format_path",
    "Schema",
    "validate_file",
    "validate_json",
    "validate_jsonl",
    "validate_value",
    "is_valid",
    "__version__",
]

"""Error classes and JSONPath utilities for jsonl-check."""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Union

# Identifier regex for dot notation in JSONPath
_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def format_path(parent: str, key_or_index: Union[str, int]) -> str:
    """Append a key or list index to a JSONPath expression.

    Args:
        parent: Existing JSONPath, e.g. "$" or "$.users".
        key_or_index: String property name or integer array index.

    Returns:
        New JSONPath string, e.g. "$.users[0].name" or "$['invalid key']".
    """
    if not parent:
        parent = "$"

    if isinstance(key_or_index, int):
        return f"{parent}[{key_or_index}]"

    key = str(key_or_index)
    if _IDENT_RE.match(key):
        return f"{parent}.{key}"
    escaped = key.replace("\\", "\\\\").replace("'", "\\'")
    return f"{parent}['{escaped}']"


class ValidationError:
    """Represents a single validation or syntax error."""

    __slots__ = ("code", "column", "line", "message", "path", "value")

    def __init__(
        self,
        line: int,
        path: str = "$",
        code: str = "validation_error",
        message: str = "",
        value: Any = None,
        column: Optional[int] = None,
    ) -> None:
        self.line = int(line)
        self.column = int(column) if column is not None else None
        self.path = str(path) if path else "$"
        self.code = str(code)
        self.message = str(message)
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        """Convert error to a JSON-serializable dictionary."""
        data: dict[str, Any] = {
            "line": self.line,
            "path": self.path,
            "code": self.code,
            "message": self.message,
        }
        if self.column is not None:
            data["column"] = self.column
        if self.value is not None:
            try:
                # Ensure value can be serialized
                json.dumps(self.value)
                data["value"] = self.value
            except (TypeError, OverflowError, ValueError):
                data["value"] = repr(self.value)
        return data

    def __str__(self) -> str:
        loc = f"line {self.line}"
        if self.column is not None:
            loc += f", col {self.column}"
        if self.path and self.path != "$":
            loc += f" at {self.path}"
        return f"{loc}: [{self.code}] {self.message}"

    def __repr__(self) -> str:
        return (
            f"ValidationError(line={self.line!r}, path={self.path!r}, "
            f"code={self.code!r}, message={self.message!r}, column={self.column!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ValidationError):
            return NotImplemented
        return (
            self.line == other.line
            and self.column == other.column
            and self.path == other.path
            and self.code == other.code
            and self.message == other.message
            and self.value == other.value
        )

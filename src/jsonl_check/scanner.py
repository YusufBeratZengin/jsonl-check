"""Lightweight JSON path-to-line/column location scanner for single JSON files."""

from __future__ import annotations

import re
from typing import Optional

from .errors import format_path


class JSONLocationScanner:
    """Scans JSON source text to map JSONPath expressions to line and column numbers."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.locations: dict[str, tuple[int, int]] = {}
        self._scan()

    def get_location(self, path: str) -> tuple[int, Optional[int]]:
        """Return (line, column) for a given JSONPath, defaulting to (1, 1)."""
        if path in self.locations:
            return self.locations[path]
        return (1, 1)

    def _scan(self) -> None:
        text = self.text
        n = len(text)
        idx = 0
        line = 1
        col = 1

        self.locations["$"] = (1, 1)

        # Stack entries: dict(kind='object'|'array', path=str, key=str|None, index=int, expecting_val=bool)
        stack: list[dict] = []
        current_path = "$"

        while idx < n:
            ch = text[idx]

            # Whitespace
            if ch == "\n":
                line += 1
                col = 1
                idx += 1
                continue
            elif ch == "\r":
                idx += 1
                continue
            elif ch.isspace():
                col += 1
                idx += 1
                continue

            tok_line = line
            tok_col = col

            if ch == "{":
                if stack and stack[-1]["kind"] == "array" and stack[-1]["expecting_val"]:
                    elem_path = format_path(stack[-1]["path"], stack[-1]["index"])
                    self.locations[elem_path] = (tok_line, tok_col)
                    stack[-1]["expecting_val"] = False
                    current_path = elem_path
                elif stack and stack[-1]["kind"] == "object" and stack[-1]["key"] is not None:
                    current_path = format_path(stack[-1]["path"], stack[-1]["key"])

                stack.append({
                    "kind": "object",
                    "path": current_path,
                    "key": None,
                    "expecting_key": True,
                })
                idx += 1
                col += 1

            elif ch == "}":
                if stack and stack[-1]["kind"] == "object":
                    stack.pop()
                    current_path = stack[-1]["path"] if stack else "$"
                idx += 1
                col += 1

            elif ch == "[":
                if stack and stack[-1]["kind"] == "array" and stack[-1]["expecting_val"]:
                    elem_path = format_path(stack[-1]["path"], stack[-1]["index"])
                    self.locations[elem_path] = (tok_line, tok_col)
                    stack[-1]["expecting_val"] = False
                    current_path = elem_path
                elif stack and stack[-1]["kind"] == "object" and stack[-1]["key"] is not None:
                    current_path = format_path(stack[-1]["path"], stack[-1]["key"])

                stack.append({
                    "kind": "array",
                    "path": current_path,
                    "index": 0,
                    "expecting_val": True,
                })
                idx += 1
                col += 1

            elif ch == "]":
                if stack and stack[-1]["kind"] == "array":
                    stack.pop()
                    current_path = stack[-1]["path"] if stack else "$"
                idx += 1
                col += 1

            elif ch == ":":
                if stack and stack[-1]["kind"] == "object":
                    stack[-1]["expecting_key"] = False
                idx += 1
                col += 1

            elif ch == ",":
                if stack:
                    if stack[-1]["kind"] == "object":
                        stack[-1]["key"] = None
                        stack[-1]["expecting_key"] = True
                    elif stack[-1]["kind"] == "array":
                        stack[-1]["index"] += 1
                        stack[-1]["expecting_val"] = True
                idx += 1
                col += 1

            elif ch == '"':
                # Parse string
                str_start = idx
                idx += 1
                col += 1
                escaped = False
                while idx < n:
                    c = text[idx]
                    if escaped:
                        escaped = False
                    elif c == "\\":
                        escaped = True
                    elif c == '"':
                        idx += 1
                        col += 1
                        break
                    elif c == "\n":
                        line += 1
                        col = 0
                    idx += 1
                    col += 1

                raw_str = text[str_start + 1 : idx - 1]
                # Unescape simple quotes/slashes
                unescaped = raw_str.replace('\\"', '"').replace("\\\\", "\\")

                if stack:
                    top = stack[-1]
                    if top["kind"] == "object":
                        if top.get("expecting_key"):
                            top["key"] = unescaped
                            field_path = format_path(top["path"], unescaped)
                            self.locations[field_path] = (tok_line, tok_col)
                        else:
                            # It's a string value
                            if top["key"] is not None:
                                field_path = format_path(top["path"], top["key"])
                                self.locations[field_path] = (tok_line, tok_col)
                    elif top["kind"] == "array":
                        if top["expecting_val"]:
                            elem_path = format_path(top["path"], top["index"])
                            self.locations[elem_path] = (tok_line, tok_col)
                            top["expecting_val"] = False
            else:
                # Number, boolean, null
                start_idx = idx
                while idx < n and text[idx] not in " \t\r\n,]}":
                    idx += 1
                    col += 1

                if stack:
                    top = stack[-1]
                    if top["kind"] == "object" and top.get("key") is not None and not top.get("expecting_key"):
                        field_path = format_path(top["path"], top["key"])
                        self.locations[field_path] = (tok_line, tok_col)
                    elif top["kind"] == "array" and top.get("expecting_val"):
                        elem_path = format_path(top["path"], top["index"])
                        self.locations[elem_path] = (tok_line, tok_col)
                        top["expecting_val"] = False

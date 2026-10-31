# jsonl-check

A fast, lightweight, pure standard library Python CLI and library for streaming validation of **JSON** and **JSON Lines (JSONL / NDJSON)** documents against structural schemas.

Pinpoints syntax errors and schema mismatches with exact **line numbers**, column numbers, and standard **JSONPath** expressions (`$.users[0].age`).

---

## Key Features

- **Zero External Dependencies**: Pure Python standard library (>= 3.8).
- **Constant Memory Footprint $O(1)$**: Streaming architecture processes multi-gigabyte files (1 GB+) without high RAM usage.
- **Precise Error Reporting**: Reports exact line numbers (1-based), column offsets, and standard JSONPath expressions.
- **Dual Mode (JSON & JSONL)**: Automatically detects or explicitly validates single multi-line JSON documents or newline-delimited JSON Lines.
- **Machine-Readable Formats**: Supports human-readable `text`, structured `json` array, and streaming `jsonl` error output.
- **Schema-Free Syntax Checking**: Validates JSON syntax on each line when no schema is supplied.
- **Fail-Fast & Error Limiting**: Stop immediately upon encountering the first error (`-f / --fail-fast`) or after $N$ errors (`-n / --max-errors`).
- **Comprehensive Schema Validation**: Supports types, required fields, nested objects, array items, enums, numeric bounds, string lengths, regex patterns, and more.

---

## Installation

```bash
pip install jsonl-check
```

Or install locally from source:

```bash
git clone https://github.com/YusufBeratZengin/jsonl-check.git
cd jsonl-check
pip install .
```

---

## CLI Usage

### Basic Syntax Validation (No Schema)

Check that each line in a JSONL file is valid JSON syntax:

```bash
jsonl-check data.jsonl
```

### Validation Against a Schema

```bash
jsonl-check data.jsonl --schema schema.json
```

### Reading from Standard Input (Pipes)

```bash
cat large_dataset.jsonl | jsonl-check - --schema schema.json
```

### Machine-Readable Error Outputs

#### 1. JSON Array Output (`--format json`)
```bash
jsonl-check data.jsonl --schema schema.json --format json
```
Output:
```json
[
  {
    "line": 42,
    "path": "$.users[2].age",
    "code": "type_mismatch",
    "message": "Expected type integer, got string",
    "value": "twenty"
  }
]
```

#### 2. JSON Lines Output (`--format jsonl`)
Streams each error as a JSON line with zero memory buffering:
```bash
jsonl-check data.jsonl --schema schema.json --format jsonl
```

### Early Termination Options

- `--fail-fast` (`-f`): Exit immediately on the first syntax or validation error.
- `--max-errors N` (`-n N`): Stop after finding $N$ errors.

```bash
jsonl-check huge_log.jsonl --schema schema.json --fail-fast
```

### CLI Reference

| Flag | Description |
|------|-------------|
| `file` | Path to JSON or JSONL file (or `-` for stdin) |
| `-s, --schema PATH` | Path to JSON schema file |
| `-m, --mode {auto,jsonl,json}` | File mode (default: `auto`) |
| `-f, --fail-fast` | Stop at first validation error |
| `-n, --max-errors N` | Stop after $N$ errors (default: unlimited) |
| `--format {text,json,jsonl}` | Output format (default: `text`) |
| `-q, --quiet` | Suppress output; exit code only |
| `--strict` | Treat empty lines in JSONL as errors |
| `--stats` | Print summary statistics to stderr |
| `-v, --version` | Display version |

### Exit Codes

- `0`: Valid. No syntax or schema errors found.
- `1`: Invalid. One or more validation or syntax errors detected.
- `2`: Operational error (file not found, invalid schema, or bad argument).

---

## Python Library API

`jsonl-check` can be used directly as a Python library:

### 1. Streaming Validation of Files or Streams

```python
import jsonl_check

schema = {
    "type": "object",
    "required": ["id", "email"],
    "properties": {
        "id": {"type": "integer"},
        "email": {"type": "string"},
    },
}

with open("users.jsonl", "r", encoding="utf-8") as f:
    for error in jsonl_check.validate_jsonl(f, schema=schema):
        print(f"Line {error.line} at {error.path}: {error.message}")
        print(error.to_dict())
```

### 2. Validating by File Path

```python
for error in jsonl_check.validate_file("data.jsonl", schema="schema.json"):
    print(error)
```

### 3. Quick Boolean Check

```python
if jsonl_check.is_valid("data.jsonl", schema="schema.json"):
    print("All records valid!")
```

### 4. In-Memory Object Validation

```python
record = {"id": "wrong_type", "email": "test@example.com"}
errors = jsonl_check.validate_value(record, schema=schema)
for err in errors:
    print(err.code, err.path, err.message)
```

---

## Schema Specification

The schema compiler supports standard structural constraints:

| Keyword | Type | Description |
|---------|------|-------------|
| `type` | string or list | `"string"`, `"number"`, `"integer"`, `"boolean"`, `"null"`, `"object"`, `"array"`, `"any"`, or list like `["string", "null"]` |
| `required` | list[str] | List of required property keys for objects |
| `properties` | dict | Mapping of property name to sub-schema |
| `additionalProperties` | bool or dict | If `false`, disallows undeclared properties; if dict, validates undeclared properties |
| `items` | dict or list | Schema for array items (or tuple schema for positional items) |
| `enum` | list | List of allowed literal values |
| `const` | any | Exact expected value |
| `minimum`, `maximum` | number | Numeric range bounds |
| `exclusiveMinimum`, `exclusiveMaximum` | number | Strict numeric range bounds |
| `multipleOf` | number | Multiplier check |
| `minLength`, `maxLength` | integer | String length bounds |
| `pattern` | string | Regular expression pattern for strings |
| `minItems`, `maxItems` | integer | Array length bounds |
| `uniqueItems` | boolean | Disallows duplicate elements in array |
| `minProperties`, `maxProperties` | integer | Object key count bounds |

---

## Streaming & Memory Architecture

Traditional JSON processors parse entire documents or store all lines in memory. When analyzing 1 GB+ JSONL files with millions of rows, memory usage can easily exceed several gigabytes.

`jsonl-check` is designed from the ground up for constant $O(1)$ memory consumption:

1. **Incremental Line Streaming**: Iterates directly over file descriptors using buffered chunks.
2. **Immediate Garbage Collection**: Each parsed record is validated and immediately discarded.
3. **Streaming Output Handlers**: The JSON and JSONL output formatters write errors to `stdout` incrementally, ensuring that even validation runs with millions of errors never balloon memory.

---

## License

MIT License. Copyright (c) 2026 YusufBeratZengin.

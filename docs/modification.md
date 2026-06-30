# Codex Task: Add File Output Support to `cool_to_bril.py`

## ⚠️ CRITICAL CONSTRAINT

> **You MUST NOT modify any line of code outside of the two clearly delimited scopes below.**
> The only function you are allowed to change is `main()` (lines 800–815).
> You are also allowed to add one new helper function `bril_to_text()` anywhere before `main()`.
> Every other class, dataclass, method, and function in this file must remain byte-for-byte identical.

---

## Context

The file `cool_to_bril.py` already compiles Cool AST files into Bril. Currently, the `main()` function always prints the result to stdout and accepts exactly one argument (the input AST file). The goal is to extend the CLI so the user can optionally write the output to a file in either `.json` or `.bril` (text) format.

---

## What Needs to Change

### 1. Replace the `main()` function

The current `main()` is:

```python
def main(argv: Optional[list[str]] = None) -> int:
    """Compile an AST file to Bril JSON and write it to stdout."""

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python cool_to_bril.py <ast.json|ast.pickle>", file=sys.stderr)
        return 2

    program = load_ast(args[0])
    result = CoolToBrilCompiler().compile_program(program)
    print(json.dumps(result, indent=2))
    return 0
```

Replace it entirely with a version that uses `argparse` with the following interface:

```
usage: cool_to_bril.py [-h] [-o OUTPUT] [-f {json,bril}] input

positional arguments:
  input                 Path to the Cool AST file (.json or .pickle/.pkl)

optional arguments:
  -o OUTPUT, --output OUTPUT
                        Path to write the output file.
                        If omitted, output is printed to stdout.
  -f {json,bril}, --format {json,bril}
                        Output format. Default: inferred from -o extension,
                        or 'json' if -o is not provided.
```

#### Format inference rules (apply in this order):
1. If `--format` is explicitly given, use it.
2. Else if `--output` ends with `.bril`, use `bril` format.
3. Else if `--output` ends with `.json`, use `json` format.
4. Else default to `json`.

#### Output rules:
- If `--output` is given: write to that file path (create or overwrite).
- If `--output` is NOT given: print to stdout.
- In both cases, apply the resolved format.

#### New `main()` implementation:

```python
def main(argv: Optional[list[str]] = None) -> int:
    """Compile a Cool AST file to Bril and write JSON or text output."""

    import argparse

    parser = argparse.ArgumentParser(
        prog="cool_to_bril.py",
        description="Compile a Cool AST to Bril JSON or Bril text format.",
    )
    parser.add_argument(
        "input",
        help="Path to the Cool AST file (.json or .pickle/.pkl)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file path. Omit to print to stdout.",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "bril"],
        default=None,
        help="Output format: 'json' (default) or 'bril' (text).",
    )

    parsed = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Resolve format
    fmt = parsed.format
    if fmt is None:
        if parsed.output is not None:
            ext = Path(parsed.output).suffix.lower()
            if ext == ".bril":
                fmt = "bril"
            elif ext == ".json":
                fmt = "json"
            else:
                fmt = "json"
        else:
            fmt = "json"

    # Compile
    program = load_ast(parsed.input)
    bril_program = CoolToBrilCompiler().compile_program(program)

    # Serialize
    if fmt == "bril":
        content = bril_to_text(bril_program)
    else:
        content = json.dumps(bril_program, indent=2)

    # Write or print
    if parsed.output is not None:
        out_path = Path(parsed.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"Output written to {out_path}", file=sys.stderr)
    else:
        print(content)

    return 0
```

---

### 2. Add the `bril_to_text()` helper function

Add this function anywhere in the file **before** `main()`. It converts the Bril JSON dict into Bril text format (`.bril`).

```python
def bril_to_text(program: JsonDict) -> str:
    """Serialize a Bril program dictionary into Bril text (.bril) format.

    The text format is the human-readable syntax accepted by bril2json.
    Reference: https://capra.cs.cornell.edu/bril/lang/text.html
    """

    lines: list[str] = []

    for func in program.get("functions", []):
        # Function signature
        name = func["name"]
        args = func.get("args", [])
        ret_type = func.get("type", "")

        args_str = ", ".join(f"{a['name']}: {a['type']}" for a in args)
        if ret_type:
            sig = f"@{name}({args_str}): {ret_type} {{"
        else:
            sig = f"@{name}({args_str}) {{"
        lines.append(sig)

        for instr in func.get("instrs", []):
            # Label
            if "label" in instr:
                lines.append(f".{instr['label']}:")
                continue

            op = instr.get("op", "")
            dest = instr.get("dest")
            type_ = instr.get("type", "")
            args_list = instr.get("args", [])
            funcs = instr.get("funcs", [])
            value = instr.get("value")

            parts: list[str] = []

            if dest:
                parts.append(f"{dest}: {type_} = ")

            if op == "const":
                val_str = "true" if value is True else "false" if value is False else str(value)
                parts.append(f"const {val_str}")
            elif op == "ret":
                if args_list:
                    parts.append(f"ret {' '.join(args_list)}")
                else:
                    parts.append("ret")
            elif op in {"jmp"}:
                parts.append(f"jmp .{args_list[0]}" if args_list else "jmp")
            elif op == "br":
                # br cond .then .else
                if len(args_list) >= 3:
                    parts.append(f"br {args_list[0]} .{args_list[1]} .{args_list[2]}")
                else:
                    parts.append(f"br {' '.join(args_list)}")
            elif op == "call":
                func_ref = f"@{funcs[0]}" if funcs else "@unknown"
                call_args = " ".join(args_list)
                parts.append(f"call {func_ref}" + (f" {call_args}" if call_args else ""))
            else:
                # Generic value op: op arg1 arg2 ...
                call_args = " ".join(args_list)
                parts.append(f"{op}" + (f" {call_args}" if call_args else ""))

            lines.append("  " + "".join(parts) + ";")

        lines.append("}")
        lines.append("")  # blank line between functions

    return "\n".join(lines)
```

---

## Expected CLI Behavior After the Change

### Print JSON to stdout (original behavior, preserved)
```bash
python cool_to_bril.py program.ast.json
```

### Save as JSON file
```bash
python cool_to_bril.py program.ast.json -o output.json
# or explicitly:
python cool_to_bril.py program.ast.json -o output.json --format json
```

### Save as Bril text file
```bash
python cool_to_bril.py program.ast.json -o output.bril
# or explicitly (even with a different extension):
python cool_to_bril.py program.ast.json -o output.txt --format bril
```

### Print Bril text to stdout
```bash
python cool_to_bril.py program.ast.json --format bril
```

---

## Files to Change

| File | Action |
|---|---|
| `cool_to_bril.py` | Replace `main()` + add `bril_to_text()` before it |

## Files NOT to Touch

| File | Status |
|---|---|
| Any other existing file in the repo | 🚫 DO NOT TOUCH |
| Everything in `cool_to_bril.py` except `main()` | 🚫 DO NOT TOUCH |

---

## Acceptance Criteria

- [ ] No existing file other than `cool_to_bril.py` was modified
- [ ] No line outside of `main()` and the new `bril_to_text()` was changed in `cool_to_bril.py`
- [ ] `python cool_to_bril.py program.ast.json` still prints valid JSON to stdout
- [ ] `python cool_to_bril.py program.ast.json -o out.json` creates a valid JSON file
- [ ] `python cool_to_bril.py program.ast.json -o out.bril` creates a valid `.bril` text file
- [ ] `python cool_to_bril.py program.ast.json --format bril` prints Bril text to stdout
- [ ] Format is correctly inferred from the output file extension when `--format` is omitted
- [ ] `python cool_to_bril.py --help` prints the usage message correctly
# Codex Task: Cool → Bril Compiler + Bril Installation Guide

## Context

You are implementing a **compiler backend** that translates programs written in the **Cool** programming language into **Bril** (Big Red Intermediate Language), the educational IR developed at Cornell University.

Cool (Classroom Object-Oriented Language) is a statically typed, object-oriented language designed for teaching compilers. It supports classes, inheritance, methods, let bindings, case expressions, and basic arithmetic/boolean operations.

Bril is a simple, JSON-based intermediate representation. Each Bril program is a JSON object containing a list of functions, each with a list of instructions. Instructions are either **value operations** (produce a result), **effect operations** (side effects only), or **labels**.

---

## ⚠️ CRITICAL CONSTRAINT — READ BEFORE WRITING ANY CODE

> **You MUST NOT modify, refactor, rename, reformat, or delete any file that already exists in this repository.**
>
> This includes — but is not limited to — the lexer, parser, semantic analyser, AST definitions, type checker, and any existing utility or helper modules.
>
> **Your entire contribution must be additive only.** You are solely responsible for creating new files. If any existing file needs to be imported, import it as-is. If you find that an existing interface is inconvenient, adapt your new code to match it — never the other way around.
>
> Violations of this rule will cause the task to be considered failed, regardless of the correctness of the generated Bril output.

### What you MAY do
- Create new files (`cool_to_bril.py`, `test_cool_to_bril.py`, `BRIL_INSTALL.md`)
- Import from existing modules without altering them
- Add new top-level files to the project root

### What you MUST NOT do
- Edit, rewrite, or reformat any existing `.py`, `.cl`, `.md`, or any other file
- Rename or move existing files
- Add, remove, or change any line in the lexer, parser, semantic analyser, or AST modules
- Refactor existing code "for clarity" or "for consistency"

---

## Task Overview

Implement the following two deliverables:

1. **`cool_to_bril.py`** — A Python module/script that takes a Cool AST (Abstract Syntax Tree) as input and outputs a valid Bril program in JSON format.
2. **`BRIL_INSTALL.md`** — A Markdown file with clear, step-by-step instructions on how to install Bril on a local machine (macOS, Linux, and Windows).

---

## Deliverable 1: `cool_to_bril.py`

### Input

Assume the Cool AST is represented as Python dataclasses or dictionaries. You may define your own AST node types for the following Cool constructs:

- **Program**: list of class definitions
- **Class**: name, parent class, list of features (attributes + methods)
- **Attribute**: name, type, optional init expression
- **Method**: name, list of formals (param name + type), return type, body expression
- **Expressions**:
  - Integer literal, String literal, Bool literal (`true`/`false`)
  - Identifier (variable reference)
  - Assignment (`<-`)
  - Arithmetic: `+`, `-`, `*`, `/`
  - Comparison: `<`, `<=`, `=`
  - Boolean negation (`not`)
  - Integer negation (`~`)
  - If-Then-Else
  - While loop
  - Block (sequence of expressions)
  - Let binding (`let x : T <- e in body`)
  - Method dispatch: static, dynamic, and self dispatch
  - `new T`
  - `isvoid`
  - `case` expression

### Output

A valid **Bril JSON** object with the following structure:

```json
{
  "functions": [
    {
      "name": "function_name",
      "args": [{"name": "arg", "type": "int"}],
      "type": "int",
      "instrs": [
        {"op": "const", "dest": "v1", "type": "int", "value": 42},
        {"op": "ret", "args": ["v1"]}
      ]
    }
  ]
}
```

### Implementation Requirements

#### 1. AST Node Definitions

Define Python dataclasses for all Cool AST nodes listed above. Example:

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class IntLiteral:
    value: int

@dataclass
class BinOp:
    op: str  # "+", "-", "*", "/", "<", "<=", "="
    left: "Expr"
    right: "Expr"

@dataclass
class IfExpr:
    condition: "Expr"
    then_branch: "Expr"
    else_branch: "Expr"

# ... define all other node types
```

#### 2. Code Generation Class

Implement a `CoolToBrilCompiler` class with:

- A **fresh variable counter** to generate unique temporaries (e.g., `v0`, `v1`, `v2`, ...`)
- A **fresh label counter** for branch targets (e.g., `label0`, `label1`, ...)
- A **symbol table / environment** (stack of dicts) to track variable → Bril name mappings
- A `compile_program(program)` method that returns the full Bril JSON dict
- A `compile_class(cls)` method that compiles each method into a Bril function
- A `compile_expr(expr) -> str` method that emits instructions and returns the name of the variable holding the result

#### 3. Expression Compilation Rules

Implement `compile_expr` with a dispatch on node type, following these rules:

| Cool Construct | Bril Translation |
|---|---|
| `IntLiteral(n)` | `const` instruction with `type: int` |
| `BoolLiteral(b)` | `const` instruction with `type: bool` |
| `BinOp("+", l, r)` | `add` value op |
| `BinOp("-", l, r)` | `sub` value op |
| `BinOp("*", l, r)` | `mul` value op |
| `BinOp("/", l, r)` | `div` value op |
| `BinOp("<", l, r)` | `lt` value op |
| `BinOp("<=", l, r)` | `le` value op |
| `BinOp("=", l, r)` | `eq` value op |
| `Not(e)` | `not` value op |
| `Negate(e)` | multiply by `const -1` |
| `Identifier(name)` | look up in symbol table, emit `id` op |
| `Assign(name, e)` | compile `e`, emit `id` to update binding |
| `Block([e1,...,en])` | compile each; result is last |
| `IfExpr(cond, t, e)` | `br`, then/else labels, `jmp` to merge label |
| `WhileExpr(cond, body)` | loop label, `br`, body, `jmp` back, done label |
| `LetExpr(var, T, init, body)` | push new scope, compile init, bind name, compile body, pop scope |
| `Dispatch(obj, method, args)` | emit `call` instruction |
| `NewExpr(T)` | emit `call` to a constructor stub |
| `IsVoid(e)` | emit comparison against a null sentinel |

#### 4. Method Compilation

Each Cool method becomes a Bril function:
- Name: `ClassName.method_name`
- Args: map Cool formals to Bril `args` with appropriate types (`int`, `bool`; use `ptr` for objects)
- Return type: map Cool type to Bril type
- Body: compile the body expression and emit a `ret` with the result

#### 5. Type Mapping

```python
def cool_type_to_bril(cool_type: str) -> str:
    mapping = {
        "Int": "int",
        "Bool": "bool",
        "String": "ptr",   # treat as pointer for now
        "SELF_TYPE": "ptr",
    }
    return mapping.get(cool_type, "ptr")  # default: object pointer
```

#### 6. Output

The `compile_program` method must return a Python dict matching the Bril JSON schema. Serialize it with `json.dumps(result, indent=2)`.

Provide a `__main__` block that:
- Accepts a path to a file containing a pickled or JSON-serialized Cool AST
- Prints the resulting Bril JSON to stdout

---

### Example

**Cool input (mentally):**
```
class Main {
    main(): Int {
        let x: Int <- 3 + 4 in
            x * 2
    };
};
```

**Expected Bril output (approximate):**
```json
{
  "functions": [
    {
      "name": "Main.main",
      "args": [],
      "type": "int",
      "instrs": [
        {"op": "const", "dest": "v0", "type": "int", "value": 3},
        {"op": "const", "dest": "v1", "type": "int", "value": 4},
        {"op": "add",   "dest": "v2", "type": "int", "args": ["v0", "v1"]},
        {"op": "id",    "dest": "x",  "type": "int", "args": ["v2"]},
        {"op": "const", "dest": "v3", "type": "int", "value": 2},
        {"op": "mul",   "dest": "v4", "type": "int", "args": ["x", "v3"]},
        {"op": "ret", "args": ["v4"]}
      ]
    }
  ]
}
```

---

### Testing

Write at least **5 unit tests** in `test_cool_to_bril.py` using `pytest`:

1. Integer constant
2. Arithmetic expression (`3 + 4 * 2` — respecting Cool's left-to-right evaluation)
3. If-Then-Else with boolean condition
4. While loop
5. Let binding

Each test should construct an AST manually and assert the emitted Bril instructions match the expected output.

---

## Deliverable 2: `BRIL_INSTALL.md`

Create a Markdown file named `BRIL_INSTALL.md` with the following sections:

### Required sections:

1. **Introduction** — Brief description of what Bril is, who created it (Adrian Sampson at Cornell), and why it is useful for studying compilers and program analysis.

2. **Prerequisites** — List required tools:
   - Node.js (≥ 16) and npm (for the TypeScript/JavaScript tools)
   - Python 3.8+ (for the Python utilities)
   - Rust + Cargo (optional, for `brilirs` — the Bril interpreter written in Rust)
   - Git

3. **Installation: Core Bril Tools (via npm / TypeScript)**
   - Step-by-step: clone the repo, install dependencies, build
   - How to run the Bril interpreter (`brili`)
   - How to run the Bril text format parser (`bril2json`, `bril2txt`)

4. **Installation: Python Utilities**
   - How to install `bril-txt` and other Python tools from the repo
   - Setting up a virtual environment (recommended)

5. **Installation: `brilirs` (Rust Interpreter — optional)**
   - How to install Rust via `rustup`
   - How to build and run `brilirs`

6. **Verifying Your Installation**
   - Provide a minimal "Hello World" Bril program in both text (`.bril`) and JSON formats
   - Show the command to run it and the expected output

7. **macOS-specific notes** — Homebrew tips for Node.js and Rust

8. **Linux-specific notes** — apt/dnf commands for dependencies

9. **Windows-specific notes** — WSL2 recommendation and any Windows-native caveats

10. **Useful Links**
    - Bril GitHub: https://github.com/sampsyo/bril
    - Bril documentation: https://capra.cs.cornell.edu/bril/
    - CS 6120 course (where Bril is used): https://www.cs.cornell.edu/courses/cs6120/

---

## File Structure

After completing this task, **only the following new files should have been created**. All pre-existing files must remain byte-for-byte identical to how they were before this task started:

```
.
├── cool_to_bril.py        # ✅ NEW — Main compiler module (create this)
├── test_cool_to_bril.py   # ✅ NEW — Pytest test suite (create this)
├── BRIL_INSTALL.md        # ✅ NEW — Bril installation guide (create this)
│
├── lexico.py                # 🚫 DO NOT TOUCH
├── parser2.py               # 🚫 DO NOT TOUCH
├── semantic2.py             # 🚫 DO NOT TOUCH
└── [any other existing file]  # 🚫 DO NOT TOUCH
```

---

## Constraints & Style Guidelines

- **Zero modifications to existing code** — this is the highest-priority rule; see the ⚠️ CRITICAL CONSTRAINT section above
- **Python version**: 3.10+ (use `match`/`case` for AST dispatch if you prefer, or `isinstance` chains)
- **No external dependencies** for `cool_to_bril.py` beyond the Python standard library
- **Type hints** throughout — all functions must be fully annotated
- **Docstrings** on every class and public method
- All Bril instruction dicts must be valid per the Bril spec — include `dest`, `type`, `op`, and `args`/`value` as appropriate for each instruction kind
- Do **not** generate dead code; only emit instructions that are actually needed
- Labels must be unique across the entire function

---

## Acceptance Criteria

- [ ] **No existing file was modified** — `git diff` on pre-existing files shows zero changes
- [ ] `cool_to_bril.py` compiles without errors
- [ ] All 5 pytest tests pass (`pytest test_cool_to_bril.py -v`)
- [ ] The output of compiling the example above matches the expected Bril JSON (modulo fresh variable names)
- [ ] `BRIL_INSTALL.md` covers all 3 platforms and all installation methods listed above
- [ ] Running a compiled Bril program through `brili` produces the correct result
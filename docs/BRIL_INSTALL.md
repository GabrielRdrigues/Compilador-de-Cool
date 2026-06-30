# Bril Installation Guide

## Introduction

Bril, the Big Red Intermediate Language, is an educational compiler intermediate
representation created by Adrian Sampson at Cornell University for CS 6120. It is
useful for studying compilers and program analysis because Bril programs are
small, typed, instruction-oriented, and represented as JSON.

Official links:

- Bril GitHub: https://github.com/sampsyo/bril
- Bril documentation: https://capra.cs.cornell.edu/bril/
- CS 6120: https://www.cs.cornell.edu/courses/cs6120/

## Prerequisites

Install these tools first:

- Git
- Python 3.8 or newer
- Node.js 16 or newer and npm, useful for TypeScript/JavaScript tooling
- Deno, required by the current reference interpreter install path
- uv, recommended for Python command-line tools
- Rust and Cargo, optional for `brilirs`

Check versions:

```sh
git --version
python3 --version
node --version
npm --version
deno --version
uv --version
cargo --version
```

## Installation: Core Bril Tools

Clone the Bril repository:

```sh
git clone https://github.com/sampsyo/bril.git
cd bril
```

Install the reference interpreter:

```sh
deno install -g brili.ts
```

Make sure Deno's binary directory is on your `PATH`. On Unix-like shells, this is
usually:

```sh
export PATH="$HOME/.deno/bin:$PATH"
```

Run a Bril JSON program with:

```sh
brili < program.json
```

The current Bril repository also contains TypeScript tools and libraries in
`bril-ts`. If you work on those tools directly, install dependencies and run them
from the cloned repository according to the repository's current README and tool
documentation.

## Installation: Python Utilities

The text format parser and pretty-printer live in the `bril-txt` directory. From
inside the cloned Bril repository:

```sh
cd bril-txt
uv tool install .
```

This installs:

- `bril2json`, which converts text `.bril` input to JSON
- `bril2txt`, which converts JSON input back to text format

Example:

```sh
bril2json < hello.bril > hello.json
bril2txt < hello.json
```

If you prefer a local Python virtual environment for development:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

Then follow the package instructions in the relevant Bril subdirectory.

## Installation: brilirs

`brilirs` is the Rust interpreter for Bril. Install Rust with rustup:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Restart your shell or source Cargo's environment file:

```sh
. "$HOME/.cargo/env"
```

Build `brilirs` from the cloned Bril repository:

```sh
cd brilirs
cargo build --release
```

Run it with:

```sh
../target/release/brilirs < ../hello.json
```

If the repository layout changes, run `cargo build --release` from the directory
that contains `brilirs`'s `Cargo.toml`.

## Verifying Your Installation

Create `hello.bril`:

```bril
@main {
  msg: int = const 42;
  print msg;
}
```

Convert it to JSON:

```sh
bril2json < hello.bril > hello.json
```

Expected JSON shape:

```json
{
  "functions": [
    {
      "name": "main",
      "instrs": [
        {"op": "const", "dest": "msg", "type": "int", "value": 42},
        {"op": "print", "args": ["msg"]}
      ]
    }
  ]
}
```

Run it:

```sh
brili < hello.json
```

Expected output:

```text
42
```

You can also test a hand-written JSON program directly:

```json
{
  "functions": [
    {
      "name": "main",
      "instrs": [
        {"op": "const", "dest": "x", "type": "int", "value": 7},
        {"op": "print", "args": ["x"]}
      ]
    }
  ]
}
```

## macOS-specific Notes

Install common dependencies with Homebrew:

```sh
brew install git node deno python uv rustup-init
rustup-init
```

After installing Deno or Rust, reopen the terminal if `brili`, `cargo`, or
`rustc` is not found.

## Linux-specific Notes

On Debian or Ubuntu:

```sh
sudo apt update
sudo apt install git curl python3 python3-venv nodejs npm
```

Install Deno:

```sh
curl -fsSL https://deno.land/install.sh | sh
```

Install uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Rust:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

On Fedora:

```sh
sudo dnf install git curl python3 nodejs npm
```

Then install Deno, uv, and Rust using the same upstream installers above.

## Windows-specific Notes

WSL2 is the simplest and most compatible path. Install Ubuntu from the Microsoft
Store, open the WSL shell, and follow the Linux instructions.

For native Windows:

- Install Git for Windows.
- Install Node.js from https://nodejs.org/.
- Install Python from https://www.python.org/.
- Install Deno from https://deno.com/.
- Install Rust from https://rustup.rs/.
- Ensure the Deno and Cargo binary directories are on your `PATH`.

When a command uses Unix redirection such as `brili < hello.json`, run it in
PowerShell, Git Bash, or WSL2.

## Useful Links

- Bril GitHub: https://github.com/sampsyo/bril
- Bril documentation: https://capra.cs.cornell.edu/bril/
- Bril syntax reference: https://capra.cs.cornell.edu/bril/lang/syntax.html
- Bril core operations: https://capra.cs.cornell.edu/bril/lang/core.html
- CS 6120 course: https://www.cs.cornell.edu/courses/cs6120/

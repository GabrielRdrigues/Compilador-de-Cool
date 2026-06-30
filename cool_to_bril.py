"""Translate a small Cool AST into Bril JSON.

This module is intentionally additive and self-contained. It defines AST
dataclasses that mirror the parser2.py nodes, but the compiler also works with
objects that have the same class names and attributes, such as parser2.py's
dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Optional


JsonDict = dict[str, Any]
BrilType = str


class ASTNode:
    """Base class for all Cool AST nodes defined in this module."""


class Feature(ASTNode):
    """Base class for Cool class features."""


class Expr(ASTNode):
    """Base class for Cool expressions."""


@dataclass
class Program(ASTNode):
    """A complete Cool program."""

    classes: list["ClassDecl"]


@dataclass
class ClassDecl(ASTNode):
    """A Cool class declaration."""

    name: str
    parent: str | None
    features: list[Feature]


@dataclass
class Method(Feature):
    """A Cool method declaration."""

    name: str
    params: list["Formal"]
    return_type: str
    body: Expr


@dataclass
class Attribute(Feature):
    """A Cool attribute declaration."""

    name: str
    type_name: str
    init: Expr | None


@dataclass
class Formal(ASTNode):
    """A Cool method formal parameter."""

    name: str
    type_name: str


@dataclass
class Identifier(Expr):
    """A Cool identifier reference."""

    name: str


@dataclass
class IntLiteral(Expr):
    """A Cool integer literal."""

    value: int


@dataclass
class StringLiteral(Expr):
    """A Cool string literal."""

    value: str


@dataclass
class BoolLiteral(Expr):
    """A Cool boolean literal."""

    value: bool


@dataclass
class Assign(Expr):
    """A Cool assignment expression."""

    name: str
    expr: Expr


@dataclass
class BinaryOp(Expr):
    """A Cool binary operation."""

    op: str
    left: Expr
    right: Expr


@dataclass
class UnaryOp(Expr):
    """A Cool unary operation."""

    op: str
    expr: Expr


@dataclass
class IfExpr(Expr):
    """A Cool if-then-else expression."""

    condition: Expr
    then_expr: Expr
    else_expr: Expr


@dataclass
class WhileExpr(Expr):
    """A Cool while-loop expression."""

    condition: Expr
    body: Expr


@dataclass
class Block(Expr):
    """A Cool block expression."""

    expressions: list[Expr]


@dataclass
class LetDecl(ASTNode):
    """A single Cool let declaration."""

    name: str
    type_name: str
    init: Expr | None


@dataclass
class LetExpr(Expr):
    """A Cool let expression."""

    declarations: list[LetDecl]
    body: Expr


@dataclass
class NewExpr(Expr):
    """A Cool object allocation expression."""

    type_name: str


@dataclass
class Dispatch(Expr):
    """A Cool method dispatch expression."""

    receiver: Expr | None
    method: str
    args: list[Expr]
    static_type: str | None = None


@dataclass
class CaseBranch(ASTNode):
    """A single Cool case branch."""

    name: str
    type_name: str
    expr: Expr


@dataclass
class CaseExpr(Expr):
    """A Cool case expression."""

    expr: Expr
    branches: list[CaseBranch]


@dataclass
class Binding:
    """A variable binding in the Bril environment."""

    name: str
    type_name: BrilType


class CoolToBrilError(Exception):
    """Raised when a Cool AST cannot be lowered to the supported Bril subset."""


BRIL_CHAR_ESCAPES = {
    "\0": "\\0",
    "\a": "\\a",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\v": "\\v",
    "\f": "\\f",
    "\r": "\\r",
}

COOL_STRING_ESCAPES = {
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
}


def cool_type_to_bril(cool_type: str) -> BrilType:
    """Map a Cool type name to the simplified Bril type used by this backend."""

    mapping = {
        "Int": "int",
        "Bool": "bool",
        "String": "char",
        "SELF_TYPE": "int",
    }
    return mapping.get(cool_type, "int")


class CoolToBrilCompiler:
    """Compile Cool AST nodes into a Bril JSON program."""

    def __init__(self, semantic_analyzer: Optional[Any] = None) -> None:
        self.temp_counter = 0
        self.label_counter = 0
        self.scopes: list[dict[str, Binding]] = []
        self.instrs: list[JsonDict] = []
        self.value_types: dict[str, BrilType] = {}
        self.functions: list[JsonDict] = []
        self.current_class = ""
        self.semantic = semantic_analyzer  # Guarda a referência semântica

    def compile_program(self, program: Any) -> JsonDict:
        """Compile a whole Cool program into a Bril program dictionary."""
        self.functions = []

        for cls in self._get(program, "classes"):
            for feature in self._get(cls, "features"):
                # Verifica se o nó atual é um método inspecionando o nome da classe do objeto
                if feature.__class__.__name__ == "Method":
                    compiled_func = self.compile_method(cls, feature)
                    
                    # Ajusta o ponto de entrada para o interpretador Bril
                    if compiled_func["name"] == "Main.main":
                        compiled_func["name"] = "main"
                        
                    self.functions.append(compiled_func)

        # Stub para referências ao ponteiro 'self'
        self.functions.append({
            "name": "__cool_self",
            "args": [],
            "type": "int",
            "instrs": [
                {"op": "const", "dest": "res", "type": "int", "value": 0},
                {"op": "ret", "args": ["res"]}
            ]
        })

        # Runtime minimo compativel com o interpretador Bril atual.
        self.functions.append({
            "name": "IO.out_string",
            "args": [{"name": "self_ptr", "type": "int"}, {"name": "x", "type": "char"}],
            "type": "int",
            "instrs": [
                {"op": "print", "args": ["x"]},
                {"op": "ret", "args": ["self_ptr"]}
            ]
        })

        return {"functions": self.functions}
    
    def compile_class(self, cls: Any) -> None:
        """Compile every method in a Cool class into Bril functions."""

        old_class = self.current_class
        self.current_class = self._get(cls, "name")
        for feature in self._get(cls, "features"):
            if self._is_kind(feature, "Method"):
                self.functions.append(self.compile_method(cls, feature))
        self.current_class = old_class

    def compile_method(self, cls: Any, method: Any) -> JsonDict:
        """Compile one Cool method into a Bril function dictionary."""

        self._reset_function_state()
        self.current_class = self._get(cls, "name")
        args = []

        self._push_scope()
        
        # 1. Injeta os atributos da classe e ancestrais no escopo inicial do método
        if self.semantic and self.current_class in self.semantic.classes:
            for attr in self.semantic.all_attributes(self.current_class):
                bril_type = cool_type_to_bril(attr.type_name)
                # Define o atributo no escopo. Nota: Em uma runtime real, 
                # atributos usariam offset de ponteiro, mas para o escopo educacional 
                # mapeamos diretamente para o nome do identificador local.
                self._define(attr.name, attr.name, bril_type)

        # 2. Injeta os parâmetros formais (que podem sobrescrever os atributos)
        for param in self._get(method, "params"):
            name = self._get(param, "name")
            bril_type = cool_type_to_bril(self._get(param, "type_name"))
            args.append({"name": name, "type": bril_type})
            self._define(name, name, bril_type)

        result = self.compile_expr(self._get(method, "body"))
        self._emit({"op": "ret", "args": [result]})
        self._pop_scope()

        return_type = cool_type_to_bril(self._get(method, "return_type"))
        return {
            "name": f"{self._get(cls, 'name')}.{self._get(method, 'name')}",
            "args": args,
            "type": return_type,
            "instrs": self.instrs,
        }

    def compile_expr(self, expr: Any) -> str:
        """Compile a Cool expression and return the Bril variable holding it."""

        kind = self._kind(expr)

        if kind == "IntLiteral":
            dest = self._fresh_temp()
            self._emit_const(dest, "int", int(self._get(expr, "value")))
            return dest

        if kind == "BoolLiteral":
            dest = self._fresh_temp()
            self._emit_const(dest, "bool", bool(self._get(expr, "value")))
            return dest

        if kind == "StringLiteral":
            raw_value = str(self._get(expr, "value"))
            char_value = self._decode_single_char_literal(raw_value)
            dest = self._fresh_temp()
            self._emit_const(dest, "char", char_value)
            return dest

        if kind == "Identifier":
            name = self._get(expr, "name")
            if name == "self":
                return self._emit_runtime_placeholder("int", "__cool_self", [])
            binding = self._lookup(name)
            dest = self._fresh_temp()
            self._emit(
                {
                    "op": "id",
                    "dest": dest,
                    "type": binding.type_name,
                    "args": [binding.name],
                }
            )
            self.value_types[dest] = binding.type_name
            return dest

        if kind == "Assign":
            name = self._get(expr, "name")
            if name == "self":
                raise CoolToBrilError("cannot assign to self")
            value = self.compile_expr(self._get(expr, "expr"))
            binding = self._lookup(name)
            value_type = self._type_of(value)
            if value_type != binding.type_name:
                raise CoolToBrilError(
                    f"assignment to {name} expected {binding.type_name}, got {value_type}"
                )
            self._emit(
                {
                    "op": "id",
                    "dest": binding.name,
                    "type": binding.type_name,
                    "args": [value],
                }
            )
            return binding.name

        if kind in {"BinaryOp", "BinOp"}:
            return self._compile_binary(expr)

        if kind == "UnaryOp":
            return self._compile_unary(expr)

        if kind == "IfExpr":
            return self._compile_if(expr)

        if kind == "WhileExpr":
            return self._compile_while(expr)

        if kind == "Block":
            expressions = self._get(expr, "expressions")
            if not expressions:
                raise CoolToBrilError("Cool blocks must contain at least one expression")
            result = ""
            for expression in expressions:
                result = self.compile_expr(expression)
            return result

        if kind == "LetExpr":
            return self._compile_let(expr)

        if kind == "NewExpr":
            type_name = self._get(expr, "type_name")
            return self._emit_runtime_placeholder("int", f"{type_name}.__new", [])

        if kind == "Dispatch":
            return self._compile_dispatch(expr)

        if kind == "CaseExpr":
            return self._compile_case(expr)

        raise CoolToBrilError(f"unsupported expression node: {kind}")

    def _compile_binary(self, expr: Any) -> str:
        op_map = {
            "+": ("add", "int"),
            "-": ("sub", "int"),
            "*": ("mul", "int"),
            "/": ("div", "int"),
            "<": ("lt", "bool"),
            "<=": ("le", "bool"),
            "=": ("eq", "bool"),
        }
        op = self._get(expr, "op")
        if op not in op_map:
            raise CoolToBrilError(f"unsupported binary operator: {op}")

        left = self.compile_expr(self._get(expr, "left"))
        right = self.compile_expr(self._get(expr, "right"))
        bril_op, result_type = op_map[op]
        dest = self._fresh_temp()
        self._emit(
            {
                "op": bril_op,
                "dest": dest,
                "type": result_type,
                "args": [left, right],
            }
        )
        self.value_types[dest] = result_type
        return dest

    def _compile_unary(self, expr: Any) -> str:
        op = self._get(expr, "op")
        value = self.compile_expr(self._get(expr, "expr"))

        if op == "not":
            dest = self._fresh_temp()
            self._emit({"op": "not", "dest": dest, "type": "bool", "args": [value]})
            self.value_types[dest] = "bool"
            return dest

        if op == "~":
            minus_one = self._fresh_temp()
            self._emit_const(minus_one, "int", -1)
            dest = self._fresh_temp()
            self._emit(
                {
                    "op": "mul",
                    "dest": dest,
                    "type": "int",
                    "args": [value, minus_one],
                }
            )
            self.value_types[dest] = "int"
            return dest

        if op == "isvoid":
            zero = self._fresh_temp()
            self._emit_const(zero, self._type_of(value), 0)
            dest = self._fresh_temp()
            self._emit({"op": "eq", "dest": dest, "type": "bool", "args": [value, zero]})
            self.value_types[dest] = "bool"
            return dest

        raise CoolToBrilError(f"unsupported unary operator: {op}")

    def _compile_if(self, expr: Any) -> str:
        condition = self.compile_expr(self._get(expr, "condition"))
        then_label = self._fresh_label("if_then")
        else_label = self._fresh_label("if_else")
        done_label = self._fresh_label("if_done")
        result = self._fresh_temp()

        self._emit({"op": "br", "args": [condition], "labels": [then_label, else_label]})

        self._emit_label(then_label)
        then_value = self.compile_expr(self._get(expr, "then_expr"))
        result_type = self._type_of(then_value)
        self._emit({"op": "id", "dest": result, "type": result_type, "args": [then_value]})
        self._emit({"op": "jmp", "labels": [done_label]})

        self._emit_label(else_label)
        else_value = self.compile_expr(self._get(expr, "else_expr"))
        else_type = self._type_of(else_value)
        if else_type != result_type:
            raise CoolToBrilError(
                f"if branches lowered to incompatible Bril types: {result_type} and {else_type}"
            )
        self._emit({"op": "id", "dest": result, "type": result_type, "args": [else_value]})
        self._emit({"op": "jmp", "labels": [done_label]})

        self._emit_label(done_label)
        self.value_types[result] = result_type
        return result

    def _compile_while(self, expr: Any) -> str:
        condition_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        done_label = self._fresh_label("while_done")

        self._emit_label(condition_label)
        condition = self.compile_expr(self._get(expr, "condition"))
        self._emit({"op": "br", "args": [condition], "labels": [body_label, done_label]})

        self._emit_label(body_label)
        self.compile_expr(self._get(expr, "body"))
        self._emit({"op": "jmp", "labels": [condition_label]})

        self._emit_label(done_label)
        result = self._fresh_temp()
        self._emit_const(result, "int", 0)
        return result

    def _compile_let(self, expr: Any) -> str:
        self._push_scope()
        for declaration in self._get(expr, "declarations"):
            name = self._get(declaration, "name")
            type_name = cool_type_to_bril(self._get(declaration, "type_name"))
            init = self._get_optional(declaration, "init")

            if init is None:
                value = self._emit_default_value(type_name)
            else:
                value = self.compile_expr(init)
                value_type = self._type_of(value)
                if value_type != type_name:
                    raise CoolToBrilError(
                        f"let {name} expected {type_name}, got {value_type}"
                    )

            local = self._fresh_local(name)
            self._emit({"op": "id", "dest": local, "type": type_name, "args": [value]})
            self.value_types[local] = type_name
            self._define(name, local, type_name)

        result = self.compile_expr(self._get(expr, "body"))
        self._pop_scope()
        return result

    def _compile_dispatch(self, expr: Any) -> str:
        args = []
        receiver = self._get_optional(expr, "receiver")
        static_type = self._get_optional(expr, "static_type")

        # Se houver receptor explícito, compila ele
        if receiver is not None:
            args.append(self.compile_expr(receiver))
        elif receiver is None and self.current_class:
            # CORREÇÃO: Se o receptor for implícito (self), gera o identificador do self 
            # e o coloca como o primeiro argumento para satisfazer a assinatura do método (ex: IO.out_string)
            self_temp = self._emit_runtime_placeholder("int", "__cool_self", [])
            args.append(self_temp)

        # Adiciona os demais argumentos do método
        args.extend(self.compile_expr(arg) for arg in self._get(expr, "args"))

        method_name = self._get(expr, 'method')

        # Resolve qual classe realmente possui a implementação do método
        if static_type:
            function_name = f"{static_type}.{method_name}"
        elif receiver is None and self.current_class:
            if self.semantic:
                real_method = self.semantic.find_method(self.current_class, method_name)
                owner_class = real_method.owner if real_method else self.current_class
            else:
                owner_class = self.current_class
            function_name = f"{owner_class}.{method_name}"
        else:
            if receiver is not None and self.semantic:
                receiver_id = id(receiver)
                cool_type = self.semantic.expr_types.get(receiver_id, "Object")
                resolved_type = self.semantic.resolve_self_type(cool_type, self.current_class)
                real_method = self.semantic.find_method(resolved_type, method_name)
                owner_class = real_method.owner if real_method else resolved_type
                function_name = f"{owner_class}.{method_name}"
            else:
                function_name = f"__dispatch_{method_name}"

        unsupported = {
            "IO.in_string": "IO.in_string is not supported without modifying the Bril interpreter",
            "String.concat": "String.concat is not supported because this backend lowers String to char",
            "String.length": "String.length is not supported because this backend lowers String to char",
            "String.substr": "String.substr is not supported because this backend lowers String to char",
        }
        if function_name in unsupported:
            raise CoolToBrilError(unsupported[function_name])

        return self._emit_runtime_placeholder("int", function_name, args)
    
    def _compile_case(self, expr: Any) -> str:
        branches = self._get(expr, "branches")
        if not branches:
            raise CoolToBrilError("case expression must contain at least one branch")

        scrutinee = self.compile_expr(self._get(expr, "expr"))
        first_branch = branches[0]
        self._push_scope()
        branch_type = cool_type_to_bril(self._get(first_branch, "type_name"))
        branch_name = self._fresh_local(self._get(first_branch, "name"))
        self._emit({"op": "id", "dest": branch_name, "type": branch_type, "args": [scrutinee]})
        self.value_types[branch_name] = branch_type
        self._define(self._get(first_branch, "name"), branch_name, branch_type)
        result = self.compile_expr(self._get(first_branch, "expr"))
        self._pop_scope()
        return result

    def _reset_function_state(self) -> None:
        self.temp_counter = 0
        self.label_counter = 0
        self.scopes = []
        self.instrs = []
        self.value_types = {}

    def _fresh_temp(self) -> str:
        name = f"v{self.temp_counter}"
        self.temp_counter += 1
        return name

    def _fresh_label(self, prefix: str = "label") -> str:
        label = f"{prefix}_{self.label_counter}"
        self.label_counter += 1
        return label

    def _fresh_local(self, base: str) -> str:
        used = set(self.value_types)
        for scope in self.scopes:
            used.update(binding.name for binding in scope.values())
        if base not in used:
            return base
        index = 1
        while f"{base}_{index}" in used:
            index += 1
        return f"{base}_{index}"

    def _emit(self, instr: JsonDict) -> None:
        self.instrs.append(instr)

    def _emit_label(self, label: str) -> None:
        self.instrs.append({"label": label})

    def _emit_const(self, dest: str, type_name: BrilType, value: int | bool | str) -> None:
        self._emit({"op": "const", "dest": dest, "type": type_name, "value": value})
        self.value_types[dest] = type_name

    def _emit_default_value(self, type_name: BrilType) -> str:
        dest = self._fresh_temp()
        if type_name == "bool":
            self._emit_const(dest, "bool", False)
        elif type_name == "char":
            raise CoolToBrilError(
                "default String values are not supported because this backend lowers String to char"
            )
        else:
            self._emit_const(dest, type_name, 0)
        return dest

    def _emit_runtime_placeholder(
        self, type_name: BrilType, function_name: str, args: list[str]
    ) -> str:
        dest = self._fresh_temp()
        instr: JsonDict = {
            "op": "call",
            "dest": dest,
            "type": type_name,
            "funcs": [function_name],
        }
        if args:
            instr["args"] = args
        self._emit(instr)
        self.value_types[dest] = type_name
        return dest

    def _push_scope(self) -> None:
        self.scopes.append({})

    def _pop_scope(self) -> None:
        self.scopes.pop()

    def _define(self, source_name: str, bril_name: str, type_name: BrilType) -> None:
        if not self.scopes:
            self._push_scope()
        self.scopes[-1][source_name] = Binding(bril_name, type_name)
        self.value_types[bril_name] = type_name

    def _lookup(self, name: str) -> Binding:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise CoolToBrilError(f"identifier not found in scope: {name}")

    def _type_of(self, value_name: str) -> BrilType:
        if value_name not in self.value_types:
            raise CoolToBrilError(f"unknown Bril value type: {value_name}")
        return self.value_types[value_name]

    def _decode_single_char_literal(self, raw_value: str) -> str:
        value = self._decode_cool_string_literal(raw_value)
        if len(value) != 1:
            raise CoolToBrilError(
                f"Bril backend supports only single-character String literals; got {raw_value}"
            )
        return value

    @staticmethod
    def _decode_cool_string_literal(raw_value: str) -> str:
        if len(raw_value) >= 2 and raw_value[0] == '"' and raw_value[-1] == '"':
            raw_value = raw_value[1:-1]

        chars: list[str] = []
        index = 0
        while index < len(raw_value):
            char = raw_value[index]
            if char != "\\":
                chars.append(char)
                index += 1
                continue

            index += 1
            if index >= len(raw_value):
                chars.append("\\")
                break

            escaped = raw_value[index]
            chars.append(COOL_STRING_ESCAPES.get(escaped, escaped))
            index += 1

        return "".join(chars)

    @staticmethod
    def _kind(node: Any) -> str:
        return type(node).__name__

    @classmethod
    def _is_kind(cls, node: Any, expected: str) -> bool:
        return cls._kind(node) == expected

    @staticmethod
    def _get(node: Any, field: str) -> Any:
        if isinstance(node, dict):
            return node[field]
        return getattr(node, field)

    @staticmethod
    def _get_optional(node: Any, field: str) -> Any:
        if isinstance(node, dict):
            return node.get(field)
        return getattr(node, field, None)


def ast_from_dict(data: Any, context: str = "expr") -> Any:
    """Convert a JSON-compatible dictionary into the AST dataclasses above."""

    if not isinstance(data, dict):
        return data

    kind = (
        data.get("node_type")
        or data.get("kind")
        or data.get("_type")
        or data.get("class")
        or data.get("type")
    )

    if kind in {"Program", "program"} or ("classes" in data and context == "program"):
        return Program([ast_from_dict(cls, "class") for cls in data["classes"]])

    if kind in {"ClassDecl", "Class", "class"} or (
        {"name", "features"}.issubset(data) and context == "class"
    ):
        return ClassDecl(
            data["name"],
            data.get("parent"),
            [ast_from_dict(feature, "feature") for feature in data["features"]],
        )

    if kind in {"Method", "method"} or (
        {"name", "params", "return_type", "body"}.issubset(data)
        and context == "feature"
    ):
        return Method(
            data["name"],
            [ast_from_dict(param, "formal") for param in data["params"]],
            data["return_type"],
            ast_from_dict(data["body"], "expr"),
        )

    if kind in {"Attribute", "attribute"} or (
        {"name", "type_name"}.issubset(data) and context == "feature"
    ):
        return Attribute(
            data["name"],
            data["type_name"],
            ast_from_dict(data["init"], "expr") if data.get("init") is not None else None,
        )

    if kind in {"Formal", "formal"} or context == "formal":
        return Formal(data["name"], data["type_name"])

    if kind in {"LetDecl", "let_decl"} or context == "let_decl":
        return LetDecl(
            data["name"],
            data["type_name"],
            ast_from_dict(data["init"], "expr") if data.get("init") is not None else None,
        )

    if kind in {"CaseBranch", "case_branch"} or context == "case_branch":
        return CaseBranch(
            data["name"],
            data["type_name"],
            ast_from_dict(data["expr"], "expr"),
        )

    if kind in {"Identifier", "identifier"}:
        return Identifier(data["name"])

    if kind in {"IntLiteral", "int"}:
        return IntLiteral(int(data["value"]))

    if kind in {"StringLiteral", "string"}:
        return StringLiteral(str(data["value"]))

    if kind in {"BoolLiteral", "bool"}:
        return BoolLiteral(bool(data["value"]))

    if kind in {"Assign", "assign"}:
        return Assign(data["name"], ast_from_dict(data["expr"], "expr"))

    if kind in {"BinaryOp", "BinOp", "binary"}:
        return BinaryOp(
            data["op"],
            ast_from_dict(data["left"], "expr"),
            ast_from_dict(data["right"], "expr"),
        )

    if kind in {"UnaryOp", "unary"}:
        return UnaryOp(data["op"], ast_from_dict(data["expr"], "expr"))

    if kind in {"IfExpr", "if"}:
        return IfExpr(
            ast_from_dict(data["condition"], "expr"),
            ast_from_dict(data["then_expr"], "expr"),
            ast_from_dict(data["else_expr"], "expr"),
        )

    if kind in {"WhileExpr", "while"}:
        return WhileExpr(
            ast_from_dict(data["condition"], "expr"),
            ast_from_dict(data["body"], "expr"),
        )

    if kind in {"Block", "block"}:
        return Block([ast_from_dict(expr, "expr") for expr in data["expressions"]])

    if kind in {"LetExpr", "let"}:
        return LetExpr(
            [ast_from_dict(decl, "let_decl") for decl in data["declarations"]],
            ast_from_dict(data["body"], "expr"),
        )

    if kind in {"NewExpr", "new"}:
        return NewExpr(data["type_name"])

    if kind in {"Dispatch", "dispatch"}:
        receiver = data.get("receiver")
        return Dispatch(
            ast_from_dict(receiver, "expr") if receiver is not None else None,
            data["method"],
            [ast_from_dict(arg, "expr") for arg in data["args"]],
            data.get("static_type"),
        )

    if kind in {"CaseExpr", "case"}:
        return CaseExpr(
            ast_from_dict(data["expr"], "expr"),
            [ast_from_dict(branch, "case_branch") for branch in data["branches"]],
        )

    raise CoolToBrilError(f"cannot deserialize AST dictionary with kind {kind!r}")


def load_ast(path: str | Path) -> Any:
    """Load a Cool AST from a JSON or pickle file."""

    ast_path = Path(path)
    if ast_path.suffix.lower() in {".pickle", ".pkl"}:
        with ast_path.open("rb") as handle:
            return pickle.load(handle)

    with ast_path.open(encoding="utf-8") as handle:
        return ast_from_dict(json.load(handle), "program")


def format_bril_literal(type_name: BrilType, value: Any) -> str:
    """Format a constant literal for Bril text output."""

    if value is True:
        return "true"
    if value is False:
        return "false"
    if type_name == "char":
        if not isinstance(value, str) or len(value) != 1:
            raise CoolToBrilError(f"invalid Bril char literal: {value!r}")
        escaped = BRIL_CHAR_ESCAPES.get(value, value)
        return f"'{escaped}'"
    return str(value)


def bril_to_text(program: JsonDict) -> str:
    """Serialize a Bril program dictionary into Bril text (.bril) format."""

    lines: list[str] = []

    for func in program.get("functions", []):
        name = func["name"]
        args = func.get("args", [])
        ret_type = func.get("type", "")

        args_str = ", ".join(f"{arg['name']}: {arg['type']}" for arg in args)
        if ret_type:
            lines.append(f"@{name}({args_str}): {ret_type} {{")
        else:
            lines.append(f"@{name}({args_str}) {{")

        for instr in func.get("instrs", []):
            if "label" in instr:
                lines.append(f".{instr['label']}:")
                continue

            op = instr.get("op", "")
            dest = instr.get("dest")
            type_name = instr.get("type", "")
            args_list = instr.get("args", [])
            funcs = instr.get("funcs", [])
            labels = instr.get("labels", [])
            value = instr.get("value")

            parts: list[str] = []

            if dest:
                parts.append(f"{dest}: {type_name} = ")

            if op == "const":
                val_str = format_bril_literal(type_name, value)
                parts.append(f"const {val_str}")
            elif op == "ret":
                if args_list:
                    parts.append(f"ret {' '.join(args_list)}")
                else:
                    parts.append("ret")
            elif op == "jmp":
                if labels:
                    parts.append(f"jmp .{labels[0]}")
                else:
                    parts.append("jmp")
            elif op == "br":
                if args_list and len(labels) >= 2:
                    parts.append(f"br {args_list[0]} .{labels[0]} .{labels[1]}")
                else:
                    parts.append(f"br {' '.join(args_list)}")
            elif op == "call":
                func_ref = f"@{funcs[0]}" if funcs else "@unknown"
                call_args = " ".join(args_list)
                parts.append(f"call {func_ref}" + (f" {call_args}" if call_args else ""))
            else:
                op_args = " ".join(args_list)
                parts.append(f"{op}" + (f" {op_args}" if op_args else ""))

            lines.append("  " + "".join(parts) + ";")

        lines.append("}")
        lines.append("")

    return "\n".join(lines)


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
        "-o",
        "--output",
        default=None,
        help="Output file path. Omit to print to stdout.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["json", "bril"],
        default=None,
        help="Output format: 'json' (default) or 'bril' (text).",
    )

    parsed = parser.parse_args(argv if argv is not None else sys.argv[1:])

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

    program = load_ast(parsed.input)
    # Se você estender o load_ast para aceitar fontes e gerar o semântico:
    compiler = CoolToBrilCompiler(semantic_analyzer=getattr(program, '_semantic', None))
    bril_program = compiler.compile_program(program)

    if fmt == "bril":
        content = bril_to_text(bril_program)
    else:
        content = json.dumps(bril_program, indent=2)

    if parsed.output is not None:
        out_path = Path(parsed.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"Output written to {out_path}", file=sys.stderr)
    else:
        print(content)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

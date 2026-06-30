from dataclasses import dataclass
import sys
from typing import Any

from lexico import ErroLexico, lexico
from parser import (
    Assign,
    Attribute,
    BinaryOp,
    Block,
    BoolLiteral,
    CaseExpr,
    ClassDecl,
    Dispatch,
    ErroSintatico,
    Expr,
    Identifier,
    IfExpr,
    IntLiteral,
    LetExpr,
    Method,
    NewExpr,
    Parser2,
    Program,
    StringLiteral,
    UnaryOp,
    WhileExpr,
)


class ErroSemantico(Exception):
    pass


UNKNOWN = "<desconhecido>"


@dataclass
class MethodInfo:
    name: str
    params: list[tuple[str, str]]
    return_type: str
    owner: str
    node: Method | None = None


@dataclass
class AttributeInfo:
    name: str
    type_name: str
    owner: str
    node: Attribute | None = None


@dataclass
class ClassInfo:
    name: str
    parent: str | None
    node: ClassDecl | None
    attributes: dict[str, AttributeInfo]
    methods: dict[str, MethodInfo]
    basic: bool = False


class Scope:
    def __init__(self) -> None:
        self.frames: list[dict[str, str]] = []

    def push(self) -> None:
        self.frames.append({})

    def pop(self) -> None:
        self.frames.pop()

    def define(self, name: str, type_name: str) -> None:
        self.frames[-1][name] = type_name

    def lookup(self, name: str) -> str | None:
        for frame in reversed(self.frames):
            if name in frame:
                return frame[name]

        return None

    def describe(self) -> str:
        if not self.frames:
            return "  <vazio>"

        lines = []
        for index, frame in enumerate(self.frames, start=1):
            if frame:
                bindings = ", ".join(
                    f"{name}: {type_name}" for name, type_name in frame.items()
                )
            else:
                bindings = "<vazio>"

            lines.append(f"  frame {index}: {bindings}")

        return "\n".join(lines)


class SemanticAnalyzer2:
    BASIC_CLASSES = {"Object", "IO", "Int", "String", "Bool"}
    FORBIDDEN_INHERITANCE = {"Int", "String", "Bool", "SELF_TYPE"}
    BASIC_COMPARABLE = {"Int", "String", "Bool"}

    def __init__(self) -> None:
        self.program: Program | None = None
        self.classes: dict[str, ClassInfo] = {}
        self.current_class = ""
        self.current_method: str | None = None
        self.current_scope: Scope | None = None
        self.expr_types: dict[int, str] = {}
        self.install_basic_classes()

    def begin_program(self) -> None:
        self.program = None

    def end_program(self, program: Program) -> None:
        self.program = program
        self.validate_inheritance()
        self.validate_main()
        self.validate_method_overrides()
        self.check_feature_bodies()

    def begin_class(self, name: str, parent: str | None) -> None:
        self.context(name)

        if name == "SELF_TYPE" or name in self.BASIC_CLASSES:
            self.error(f"classe basica {name} nao pode ser redefinida")

        if name in self.classes:
            self.error(f"classe {name} foi declarada mais de uma vez")

        self.classes[name] = ClassInfo(name, parent or "Object", None, {}, {})

    def end_class(self, class_node: ClassDecl) -> None:
        self.classes[class_node.name].node = class_node
        self.current_class = ""
        self.current_method = None

    def register_attribute(self, attribute: Attribute) -> None:
        class_info = self.classes[self.current_class]

        if attribute.name == "self":
            self.error("atributo nao pode se chamar self")

        if attribute.name in class_info.attributes:
            self.error(
                f"atributo {attribute.name} foi declarado mais de uma vez na classe {self.current_class}"
            )

        class_info.attributes[attribute.name] = AttributeInfo(
            attribute.name, attribute.type_name, self.current_class, attribute
        )

        if attribute.init is not None:
            self.check_expr(attribute.init)

    def begin_method(
        self, name: str, params: list[Any], return_type: str
    ) -> None:
        class_info = self.classes[self.current_class]
        self.context(self.current_class, name)

        if name in class_info.methods:
            self.error(
                f"metodo {name} foi declarado mais de uma vez na classe {self.current_class}"
            )

        method_params = []
        seen_params: set[str] = set()
        for formal in params:
            if formal.name == "self":
                self.error(f"parametro de {name} nao pode se chamar self")

            if formal.name in seen_params:
                self.error(
                    f"parametro {formal.name} foi declarado mais de uma vez no metodo {name}"
                )

            if formal.type_name == "SELF_TYPE":
                self.error(
                    f"parametro {formal.name} do metodo {name} nao pode ter tipo SELF_TYPE"
                )

            seen_params.add(formal.name)
            method_params.append((formal.name, formal.type_name))

        class_info.methods[name] = MethodInfo(
            name, method_params, return_type, self.current_class
        )

        self.current_scope = self.create_incremental_scope()
        self.current_scope.push()

        for param_name, param_type in method_params:
            self.current_scope.define(param_name, param_type)

    def end_method(self, method: Method) -> None:
        class_info = self.classes[self.current_class]
        class_info.methods[method.name].node = method

        if self.current_scope is not None:
            self.current_scope.pop()

        self.current_scope = None
        self.current_method = None

    def begin_let(self) -> None:
        if self.current_scope is not None:
            self.current_scope.push()

    def register_let_decl(self, declaration: Any) -> None:
        if declaration.name == "self":
            self.error("variavel de let nao pode se chamar self")

        if declaration.init is not None:
            self.check_expr(declaration.init)

        if self.current_scope is not None:
            self.current_scope.define(declaration.name, declaration.type_name)

    def end_let(self, _expr: Any) -> None:
        if self.current_scope is not None:
            self.current_scope.pop()

    def begin_case(self) -> None:
        pass

    def begin_case_branch(self, name: str, type_name: str) -> None:
        if name == "self":
            self.error("variavel de branch do case nao pode se chamar self")

        if type_name == "SELF_TYPE":
            self.error("branch de case nao pode declarar tipo SELF_TYPE")

        if self.current_scope is not None:
            self.current_scope.push()
            self.current_scope.define(name, type_name)

    def end_case_branch(self) -> None:
        if self.current_scope is not None:
            self.current_scope.pop()

    def end_case(self, _expr: Any) -> None:
        pass

    def check_expr(self, expr: Expr) -> str:
        result = self.infer_incremental(expr)
        self.expr_types[id(expr)] = result
        return result

    def infer_incremental(self, expr: Expr) -> str:
        if isinstance(expr, IntLiteral):
            return "Int"

        if isinstance(expr, StringLiteral):
            return "String"

        if isinstance(expr, BoolLiteral):
            return "Bool"

        if isinstance(expr, Identifier):
            if self.current_scope is None:
                return UNKNOWN

            return self.current_scope.lookup(expr.name) or UNKNOWN

        if isinstance(expr, Assign):
            value_type = self.expr_types.get(id(expr.expr), UNKNOWN)
            target_type = UNKNOWN

            if self.current_scope is not None:
                target_type = self.current_scope.lookup(expr.name) or UNKNOWN

            if expr.name == "self":
                self.error("nao e permitido atribuir a self")

            if (
                value_type != UNKNOWN
                and target_type != UNKNOWN
                and self.can_compare_known_types(value_type, target_type)
                and not self.conforms(value_type, target_type, self.current_class)
            ):
                self.error(
                    f"atribuicao em {expr.name} usa tipo {value_type}, "
                    f"mas deveria conformar a {target_type}"
                )

            return value_type

        if isinstance(expr, BinaryOp):
            left_type = self.expr_types.get(id(expr.left), UNKNOWN)
            right_type = self.expr_types.get(id(expr.right), UNKNOWN)

            if UNKNOWN in (left_type, right_type):
                return UNKNOWN

            if expr.op in {"+", "-", "*", "/"}:
                self.require_type(left_type, "Int", f"operador {expr.op}")
                self.require_type(right_type, "Int", f"operador {expr.op}")
                return "Int"

            if expr.op in {"<", "<="}:
                self.require_type(left_type, "Int", f"operador {expr.op}")
                self.require_type(right_type, "Int", f"operador {expr.op}")
                return "Bool"

            if expr.op == "=":
                if (
                    left_type in self.BASIC_COMPARABLE
                    or right_type in self.BASIC_COMPARABLE
                ) and left_type != right_type:
                    self.error(
                        f"operador = nao pode comparar {left_type} com {right_type}"
                    )

                return "Bool"

        if isinstance(expr, UnaryOp):
            value_type = self.expr_types.get(id(expr.expr), UNKNOWN)
            if value_type == UNKNOWN:
                return UNKNOWN

            if expr.op == "~":
                self.require_type(value_type, "Int", "operador ~")
                return "Int"

            if expr.op == "not":
                self.require_type(value_type, "Bool", "operador not")
                return "Bool"

            if expr.op == "isvoid":
                return "Bool"

        if isinstance(expr, IfExpr):
            condition_type = self.expr_types.get(id(expr.condition), UNKNOWN)
            then_type = self.expr_types.get(id(expr.then_expr), UNKNOWN)
            else_type = self.expr_types.get(id(expr.else_expr), UNKNOWN)

            if condition_type != UNKNOWN:
                self.require_type(condition_type, "Bool", "condicao do if")

            if (
                then_type != UNKNOWN
                and else_type != UNKNOWN
                and self.can_compare_known_types(then_type, else_type)
            ):
                return self.least_common_ancestor(
                    then_type, else_type, self.current_class
                )

            return UNKNOWN

        if isinstance(expr, WhileExpr):
            condition_type = self.expr_types.get(id(expr.condition), UNKNOWN)
            if condition_type != UNKNOWN:
                self.require_type(condition_type, "Bool", "condicao do while")

            return "Object"

        if isinstance(expr, Block):
            if not expr.expressions:
                return "Object"

            return self.expr_types.get(id(expr.expressions[-1]), UNKNOWN)

        if isinstance(expr, LetExpr):
            return self.expr_types.get(id(expr.body), UNKNOWN)

        if isinstance(expr, NewExpr):
            return expr.type_name

        if isinstance(expr, Dispatch):
            return self.infer_incremental_dispatch(expr)

        if isinstance(expr, CaseExpr):
            branch_types = [
                self.expr_types.get(id(branch.expr), UNKNOWN)
                for branch in expr.branches
            ]
            known = [type_name for type_name in branch_types if type_name != UNKNOWN]
            if not known:
                return UNKNOWN

            result = known[0]
            for type_name in known[1:]:
                if not self.can_compare_known_types(result, type_name):
                    return UNKNOWN

                result = self.least_common_ancestor(
                    result, type_name, self.current_class
                )

            return result

        return UNKNOWN

    def infer_incremental_dispatch(self, expr: Dispatch) -> str:
        if expr.receiver is None:
            receiver_type = "SELF_TYPE"
            dispatch_type = self.current_class
        else:
            receiver_type = self.expr_types.get(id(expr.receiver), UNKNOWN)
            if receiver_type == UNKNOWN:
                return UNKNOWN

            dispatch_type = self.resolve_self_type(receiver_type, self.current_class)

        if expr.static_type is not None:
            dispatch_type = expr.static_type

        if dispatch_type not in self.classes:
            return UNKNOWN

        method = self.find_method(dispatch_type, expr.method)
        if method is None:
            return UNKNOWN

        if len(expr.args) != len(method.params):
            self.error(
                f"metodo {expr.method} espera {len(method.params)} argumento(s), "
                f"mas recebeu {len(expr.args)}"
            )

        for index, (arg, (_, expected_type)) in enumerate(
            zip(expr.args, method.params), start=1
        ):
            arg_type = self.expr_types.get(id(arg), UNKNOWN)
            if (
                arg_type != UNKNOWN
                and self.can_compare_known_types(arg_type, expected_type)
                and not self.conforms(arg_type, expected_type, self.current_class)
            ):
                self.error(
                    f"argumento {index} de {expr.method} tem tipo {arg_type}, "
                    f"mas deveria conformar a {expected_type}"
                )

        if method.return_type == "SELF_TYPE":
            return receiver_type

        return method.return_type

    def install_basic_classes(self) -> None:
        self.classes["Object"] = ClassInfo(
            "Object",
            None,
            None,
            {},
            {
                "abort": MethodInfo("abort", [], "Object", "Object"),
                "type_name": MethodInfo("type_name", [], "String", "Object"),
                "copy": MethodInfo("copy", [], "SELF_TYPE", "Object"),
            },
            basic=True,
        )
        self.classes["IO"] = ClassInfo(
            "IO",
            "Object",
            None,
            {},
            {
                "out_string": MethodInfo(
                    "out_string", [("x", "String")], "SELF_TYPE", "IO"
                ),
                "out_int": MethodInfo("out_int", [("x", "Int")], "SELF_TYPE", "IO"),
                "in_string": MethodInfo("in_string", [], "String", "IO"),
                "in_int": MethodInfo("in_int", [], "Int", "IO"),
            },
            basic=True,
        )
        self.classes["Int"] = ClassInfo("Int", "Object", None, {}, {}, basic=True)
        self.classes["String"] = ClassInfo(
            "String",
            "Object",
            None,
            {},
            {
                "length": MethodInfo("length", [], "Int", "String"),
                "concat": MethodInfo("concat", [("s", "String")], "String", "String"),
                "substr": MethodInfo(
                    "substr", [("i", "Int"), ("l", "Int")], "String", "String"
                ),
            },
            basic=True,
        )
        self.classes["Bool"] = ClassInfo("Bool", "Object", None, {}, {}, basic=True)

    def validate_inheritance(self) -> None:
        for class_info in self.classes.values():
            if class_info.name == "Object":
                continue

            parent = class_info.parent
            if parent in self.FORBIDDEN_INHERITANCE:
                self.context(class_info.name)
                self.error(f"classe {class_info.name} nao pode herdar de {parent}")

            if parent not in self.classes:
                self.context(class_info.name)
                self.error(
                    f"classe {class_info.name} herda de tipo desconhecido {parent}"
                )

        for class_name in self.classes:
            visited: set[str] = set()
            current: str | None = class_name

            while current is not None:
                if current in visited:
                    self.current_class = ""
                    self.current_method = None
                    self.error(f"heranca circular envolvendo a classe {class_name}")

                visited.add(current)
                current = self.classes[current].parent

    def validate_main(self) -> None:
        if "Main" not in self.classes:
            self.context("Main")
            self.error("programa precisa declarar a classe Main")

        main_method = self.find_method("Main", "main")
        if main_method is None or main_method.owner != "Main":
            self.context("Main")
            self.error("classe Main precisa declarar o metodo main")

        if main_method.params:
            self.context("Main", "main")
            self.error("metodo Main.main nao pode receber parametros")

    def validate_method_overrides(self) -> None:
        for class_info in self.user_classes():
            for method in class_info.methods.values():
                inherited = self.find_method(class_info.parent, method.name)
                if inherited is None:
                    continue

                self.context(class_info.name, method.name)
                inherited_types = [type_name for _, type_name in inherited.params]
                method_types = [type_name for _, type_name in method.params]

                if method_types != inherited_types:
                    self.error(
                        f"sobrescrita de {method.name} precisa manter os mesmos tipos de parametros"
                    )

                if method.return_type != inherited.return_type:
                    self.error(
                        f"sobrescrita de {method.name} precisa manter o mesmo tipo de retorno"
                    )

    def check_feature_bodies(self) -> None:
        for class_info in self.user_classes():
            assert class_info.node is not None
            self.current_class = class_info.name

            for feature in class_info.node.features:
                if isinstance(feature, Attribute):
                    self.check_attribute_body(class_info, feature)
                elif isinstance(feature, Method):
                    self.check_method_body(class_info, feature)

        self.current_class = ""
        self.current_method = None

    def check_attribute_body(self, class_info: ClassInfo, attribute: Attribute) -> None:
        self.context(class_info.name)
        self.require_declared_type(attribute.type_name, allow_self_type=True)

        inherited = self.find_attribute(class_info.parent, attribute.name)
        if inherited is not None:
            self.error(
                f"atributo {attribute.name} da classe {class_info.name} redefine atributo herdado"
            )

        if attribute.init is None:
            return

        scope = self.create_base_scope(class_info.name)
        init_type = self.infer_expr(attribute.init, scope)
        if not self.conforms(init_type, attribute.type_name, class_info.name):
            self.error(
                f"inicializacao do atributo {attribute.name} tem tipo {init_type}, "
                f"mas deveria conformar a {attribute.type_name}"
            )

    def check_method_body(self, class_info: ClassInfo, method: Method) -> None:
        self.context(class_info.name, method.name)
        self.require_declared_type(method.return_type, allow_self_type=True)

        scope = self.create_base_scope(class_info.name)
        scope.push()

        method_info = self.classes[class_info.name].methods[method.name]
        for name, type_name in method_info.params:
            self.require_declared_type(type_name, allow_self_type=False)
            scope.define(name, type_name)

        body_type = self.infer_expr(method.body, scope)
        if not self.conforms(body_type, method.return_type, class_info.name):
            self.error(
                f"corpo do metodo {method.name} tem tipo {body_type}, "
                f"mas deveria conformar a {method.return_type}"
            )

        scope.pop()

    def infer_expr(self, expr: Expr, scope: Scope) -> str:
        if isinstance(expr, IntLiteral):
            result = "Int"
        elif isinstance(expr, StringLiteral):
            result = "String"
        elif isinstance(expr, BoolLiteral):
            result = "Bool"
        elif isinstance(expr, Identifier):
            result = self.infer_identifier(expr, scope)
        elif isinstance(expr, Assign):
            result = self.infer_assign(expr, scope)
        elif isinstance(expr, BinaryOp):
            result = self.infer_binary(expr, scope)
        elif isinstance(expr, UnaryOp):
            result = self.infer_unary(expr, scope)
        elif isinstance(expr, IfExpr):
            result = self.infer_if(expr, scope)
        elif isinstance(expr, WhileExpr):
            result = self.infer_while(expr, scope)
        elif isinstance(expr, Block):
            result = "Object"
            for expression in expr.expressions:
                result = self.infer_expr(expression, scope)
        elif isinstance(expr, LetExpr):
            result = self.infer_let(expr, scope)
        elif isinstance(expr, NewExpr):
            self.require_declared_type(expr.type_name, allow_self_type=True)
            result = expr.type_name
        elif isinstance(expr, Dispatch):
            result = self.infer_dispatch(expr, scope)
        elif isinstance(expr, CaseExpr):
            result = self.infer_case(expr, scope)
        else:
            self.error(f"expressao sem regra semantica: {type(expr).__name__}")

        self.expr_types[id(expr)] = result
        return result

    def infer_identifier(self, expr: Identifier, scope: Scope) -> str:
        type_name = scope.lookup(expr.name)
        if type_name is None:
            self.error(f"identificador {expr.name} nao declarado no escopo")

        return type_name

    def infer_assign(self, expr: Assign, scope: Scope) -> str:
        if expr.name == "self":
            self.error("nao e permitido atribuir a self")

        target_type = scope.lookup(expr.name)
        if target_type is None:
            self.error(f"identificador {expr.name} nao declarado no escopo")

        value_type = self.infer_expr(expr.expr, scope)
        if not self.conforms(value_type, target_type, self.current_class):
            self.error(
                f"atribuicao em {expr.name} usa tipo {value_type}, "
                f"mas deveria conformar a {target_type}"
            )

        return value_type

    def infer_binary(self, expr: BinaryOp, scope: Scope) -> str:
        left_type = self.infer_expr(expr.left, scope)
        right_type = self.infer_expr(expr.right, scope)

        if expr.op in {"+", "-", "*", "/"}:
            self.require_type(left_type, "Int", f"operador {expr.op}")
            self.require_type(right_type, "Int", f"operador {expr.op}")
            return "Int"

        if expr.op in {"<", "<="}:
            self.require_type(left_type, "Int", f"operador {expr.op}")
            self.require_type(right_type, "Int", f"operador {expr.op}")
            return "Bool"

        if expr.op == "=":
            if (
                left_type in self.BASIC_COMPARABLE
                or right_type in self.BASIC_COMPARABLE
            ) and left_type != right_type:
                self.error(
                    f"operador = nao pode comparar {left_type} com {right_type}"
                )

            return "Bool"

        self.error(f"operador binario desconhecido {expr.op}")

    def infer_unary(self, expr: UnaryOp, scope: Scope) -> str:
        value_type = self.infer_expr(expr.expr, scope)

        if expr.op == "~":
            self.require_type(value_type, "Int", "operador ~")
            return "Int"

        if expr.op == "not":
            self.require_type(value_type, "Bool", "operador not")
            return "Bool"

        if expr.op == "isvoid":
            return "Bool"

        self.error(f"operador unario desconhecido {expr.op}")

    def infer_if(self, expr: IfExpr, scope: Scope) -> str:
        condition_type = self.infer_expr(expr.condition, scope)
        self.require_type(condition_type, "Bool", "condicao do if")
        then_type = self.infer_expr(expr.then_expr, scope)
        else_type = self.infer_expr(expr.else_expr, scope)
        return self.least_common_ancestor(then_type, else_type, self.current_class)

    def infer_while(self, expr: WhileExpr, scope: Scope) -> str:
        condition_type = self.infer_expr(expr.condition, scope)
        self.require_type(condition_type, "Bool", "condicao do while")
        self.infer_expr(expr.body, scope)
        return "Object"

    def infer_let(self, expr: LetExpr, scope: Scope) -> str:
        scope.push()

        for declaration in expr.declarations:
            if declaration.name == "self":
                self.error("variavel de let nao pode se chamar self")

            self.require_declared_type(declaration.type_name, allow_self_type=True)

            if declaration.init is not None:
                init_type = self.infer_expr(declaration.init, scope)
                if not self.conforms(
                    init_type, declaration.type_name, self.current_class
                ):
                    self.error(
                        f"inicializacao de {declaration.name} tem tipo {init_type}, "
                        f"mas deveria conformar a {declaration.type_name}"
                    )

            scope.define(declaration.name, declaration.type_name)

        body_type = self.infer_expr(expr.body, scope)
        scope.pop()
        return body_type

    def infer_case(self, expr: CaseExpr, scope: Scope) -> str:
        self.infer_expr(expr.expr, scope)
        branch_types_seen: set[str] = set()
        result_type: str | None = None

        for branch in expr.branches:
            if branch.name == "self":
                self.error("variavel de branch do case nao pode se chamar self")

            if branch.type_name == "SELF_TYPE":
                self.error("branch de case nao pode declarar tipo SELF_TYPE")

            self.require_declared_type(branch.type_name, allow_self_type=False)

            if branch.type_name in branch_types_seen:
                self.error(f"case possui branch duplicado para o tipo {branch.type_name}")

            branch_types_seen.add(branch.type_name)
            scope.push()
            scope.define(branch.name, branch.type_name)
            branch_result = self.infer_expr(branch.expr, scope)
            scope.pop()

            if result_type is None:
                result_type = branch_result
            else:
                result_type = self.least_common_ancestor(
                    result_type, branch_result, self.current_class
                )

        assert result_type is not None
        return result_type

    def infer_dispatch(self, expr: Dispatch, scope: Scope) -> str:
        if expr.receiver is None:
            receiver_type = "SELF_TYPE"
            dispatch_type = self.current_class
        else:
            receiver_type = self.infer_expr(expr.receiver, scope)
            dispatch_type = self.resolve_self_type(receiver_type, self.current_class)

        if expr.static_type is not None:
            self.require_declared_type(expr.static_type, allow_self_type=False)

            if not self.conforms(receiver_type, expr.static_type, self.current_class):
                self.error(
                    f"dispatch estatico para {expr.static_type} usado com receptor de tipo {receiver_type}"
                )

            dispatch_type = expr.static_type

        method = self.find_method(dispatch_type, expr.method)
        if method is None:
            self.error(f"metodo {expr.method} nao encontrado em {dispatch_type}")

        if len(expr.args) != len(method.params):
            self.error(
                f"metodo {expr.method} espera {len(method.params)} argumento(s), "
                f"mas recebeu {len(expr.args)}"
            )

        for index, (arg, (_, expected_type)) in enumerate(
            zip(expr.args, method.params), start=1
        ):
            arg_type = self.infer_expr(arg, scope)
            if not self.conforms(arg_type, expected_type, self.current_class):
                self.error(
                    f"argumento {index} de {expr.method} tem tipo {arg_type}, "
                    f"mas deveria conformar a {expected_type}"
                )

        if method.return_type == "SELF_TYPE":
            return receiver_type

        return method.return_type

    def create_incremental_scope(self) -> Scope:
        scope = Scope()
        scope.push()
        scope.define("self", "SELF_TYPE")

        class_info = self.classes.get(self.current_class)
        if class_info is not None:
            for attribute in class_info.attributes.values():
                scope.define(attribute.name, attribute.type_name)

        return scope

    def create_base_scope(self, class_name: str) -> Scope:
        scope = Scope()
        scope.push()
        scope.define("self", "SELF_TYPE")

        for attribute in self.all_attributes(class_name):
            scope.define(attribute.name, attribute.type_name)

        return scope

    def all_attributes(self, class_name: str) -> list[AttributeInfo]:
        parents_first: list[str] = []
        current: str | None = class_name

        while current is not None:
            parents_first.append(current)
            current = self.classes[current].parent

        attributes: list[AttributeInfo] = []
        for name in reversed(parents_first):
            attributes.extend(self.classes[name].attributes.values())

        return attributes

    def find_attribute(
        self, class_name: str | None, attribute_name: str
    ) -> AttributeInfo | None:
        current = class_name

        while current is not None:
            attribute = self.classes[current].attributes.get(attribute_name)
            if attribute is not None:
                return attribute

            current = self.classes[current].parent

        return None

    def find_method(self, class_name: str | None, method_name: str) -> MethodInfo | None:
        current = class_name

        while current is not None:
            method = self.classes[current].methods.get(method_name)
            if method is not None:
                return method

            current = self.classes[current].parent

        return None

    def conforms(self, actual: str, expected: str, current_class: str) -> bool:
        if expected == "SELF_TYPE":
            return actual == "SELF_TYPE"

        actual_resolved = self.resolve_self_type(actual, current_class)
        expected_resolved = self.resolve_self_type(expected, current_class)

        if actual_resolved not in self.classes or expected_resolved not in self.classes:
            return False

        current: str | None = actual_resolved
        while current is not None:
            if current == expected_resolved:
                return True

            current = self.classes[current].parent

        return False

    def least_common_ancestor(self, left: str, right: str, current_class: str) -> str:
        if left == "SELF_TYPE" and right == "SELF_TYPE":
            return "SELF_TYPE"

        left_resolved = self.resolve_self_type(left, current_class)
        right_resolved = self.resolve_self_type(right, current_class)
        left_ancestors = set(self.ancestors(left_resolved))

        for ancestor in self.ancestors(right_resolved):
            if ancestor in left_ancestors:
                return ancestor

        return "Object"

    def ancestors(self, class_name: str) -> list[str]:
        result = []
        current: str | None = class_name

        while current is not None:
            result.append(current)
            current = self.classes[current].parent

        return result

    def resolve_self_type(self, type_name: str, current_class: str) -> str:
        if type_name == "SELF_TYPE":
            return current_class

        return type_name

    def can_compare_known_types(self, left: str, right: str) -> bool:
        return self.resolve_self_type(left, self.current_class) in self.classes and (
            self.resolve_self_type(right, self.current_class) in self.classes
            or right == "SELF_TYPE"
        )

    def require_type(self, actual: str, expected: str, context: str) -> None:
        if actual != expected:
            self.error(f"{context} esperava {expected}, mas recebeu {actual}")

    def require_declared_type(self, type_name: str, allow_self_type: bool) -> None:
        if type_name == "SELF_TYPE":
            if allow_self_type:
                return

            self.error("SELF_TYPE nao e permitido neste contexto")

        if type_name not in self.classes:
            self.error(f"tipo {type_name} nao declarado")

    def user_classes(self) -> list[ClassInfo]:
        return [class_info for class_info in self.classes.values() if not class_info.basic]

    def context(self, class_name: str, method_name: str | None = None) -> None:
        self.current_class = class_name
        self.current_method = method_name

    def error(self, message: str) -> None:
        if self.current_method is not None:
            prefix = f"Erro semantico na classe {self.current_class}, metodo {self.current_method}: "
        elif self.current_class:
            prefix = f"Erro semantico na classe {self.current_class}: "
        else:
            prefix = "Erro semantico: "

        raise ErroSemantico(prefix + message)


def analisar_arquivo(caminho: str, debug_scopes: bool = False) -> Program:
    semantic = SemanticAnalyzer2()
    tokens = lexico(caminho)
    program = Parser2(tokens, semantic=semantic).parse()
    for class_info in semantic.user_classes():
        print("Nome da classe:",class_info.name)
        print("pai:",class_info.parent)
        print("atributos:",list(class_info.attributes.keys()))
        print("métodos:", list(class_info.methods.keys()))
        if debug_scopes:
            print("escopo visivel:")
            print(semantic.create_base_scope(class_info.name).describe())
        print()
    print("--------------------------------------------")
    return program


def parse_cli_args(argv: list[str]) -> tuple[str, bool]:
    caminho_arquivo = "codigo.txt"
    debug_scopes = False

    for arg in argv[1:]:
        if arg == "--debug-scopes":
            debug_scopes = True
        else:
            caminho_arquivo = arg

    return caminho_arquivo, debug_scopes


if __name__ == "__main__":
    caminho_arquivo, debug_scopes = parse_cli_args(sys.argv)

    try:
        analisar_arquivo(caminho_arquivo, debug_scopes=debug_scopes)
        print("Analise semantica concluida sem erros.")
        print("--------------------------------------------")
    except (ErroLexico, ErroSintatico, ErroSemantico) as erro:
        print(erro)

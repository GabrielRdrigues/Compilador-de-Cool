from dataclasses import dataclass
from typing import Any, Iterable
import sys

from lexico import ErroLexico, Token, lexico


class ErroSintatico(Exception):
    pass


class ASTNode:
    pass


class Feature(ASTNode):
    pass


class Expr(ASTNode):
    pass


@dataclass
class Program(ASTNode):
    classes: list["ClassDecl"]


@dataclass
class ClassDecl(ASTNode):
    name: str
    parent: str | None
    features: list[Feature]


@dataclass
class Method(Feature):
    name: str
    params: list["Formal"]
    return_type: str
    body: Expr


@dataclass
class Attribute(Feature):
    name: str
    type_name: str
    init: Expr | None


@dataclass
class Formal(ASTNode):
    name: str
    type_name: str


@dataclass
class Identifier(Expr):
    name: str


@dataclass
class IntLiteral(Expr):
    value: int


@dataclass
class StringLiteral(Expr):
    value: str


@dataclass
class BoolLiteral(Expr):
    value: bool


@dataclass
class Assign(Expr):
    name: str
    expr: Expr


@dataclass
class BinaryOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class UnaryOp(Expr):
    op: str
    expr: Expr


@dataclass
class IfExpr(Expr):
    condition: Expr
    then_expr: Expr
    else_expr: Expr


@dataclass
class WhileExpr(Expr):
    condition: Expr
    body: Expr


@dataclass
class Block(Expr):
    expressions: list[Expr]


@dataclass
class LetDecl(ASTNode):
    name: str
    type_name: str
    init: Expr | None


@dataclass
class LetExpr(Expr):
    declarations: list[LetDecl]
    body: Expr


@dataclass
class NewExpr(Expr):
    type_name: str


@dataclass
class Dispatch(Expr):
    receiver: Expr | None
    method: str
    args: list[Expr]
    static_type: str | None = None


@dataclass
class CaseBranch(ASTNode):
    name: str
    type_name: str
    expr: Expr


@dataclass
class CaseExpr(Expr):
    expr: Expr
    branches: list[CaseBranch]


class Parser2:
    def __init__(self, tokens: Iterable[Token], semantic: Any | None = None):
        self.tokens = list(tokens)

        if not self.tokens:
            self.tokens.append(Token("EOF", "", 1, 1))
        elif self.tokens[-1].tipo != "EOF":
            ultimo = self.tokens[-1]
            self.tokens.append(Token("EOF", "", ultimo.linha, ultimo.coluna))

        self.pos = 0
        self.semantic = semantic

    def parse(self) -> Program:
        return self.parse_program()

    def sem(self, action: str, *args: Any) -> Any:
        if self.semantic is None:
            return None

        method = getattr(self.semantic, action, None)
        if method is None:
            return None

        return method(*args)

    def checked(self, expr: Expr) -> Expr:
        self.sem("check_expr", expr)
        return expr

    def peek(self, offset: int = 0) -> Token:
        indice = self.pos + offset

        if indice < len(self.tokens):
            return self.tokens[indice]

        return self.tokens[-1]

    def advance(self) -> Token:
        token = self.peek()

        if not self.check("EOF"):
            self.pos += 1

        return token

    def check(self, tipo: str) -> bool:
        return self.peek().tipo == tipo

    def check_any(self, tipos: tuple[str, ...]) -> bool:
        return self.peek().tipo in tipos

    def match(self, tipo: str) -> bool:
        if self.check(tipo):
            self.advance()
            return True

        return False

    def expect(self, tipo: str) -> Token:
        if self.check(tipo):
            return self.advance()

        encontrado = self.peek().tipo
        self.erro(f"esperado {tipo}, encontrado {encontrado}")

    def erro(self, mensagem: str) -> None:
        token = self.peek()
        linha = getattr(token, "linha", "?")
        coluna = getattr(token, "coluna", "?")
        raise ErroSintatico(
            f"Erro sintatico na linha {linha}, coluna {coluna}: {mensagem}"
        )

    def parse_program(self) -> Program:
        self.sem("begin_program")

        if self.check("EOF"):
            self.erro("programa precisa ter pelo menos uma classe")

        classes = []

        while not self.check("EOF"):
            classes.append(self.parse_class())
            self.expect("SEMI")

        program = Program(classes)
        self.sem("end_program", program)
        return program

    def parse_class(self) -> ClassDecl:
        self.expect("CLASS")
        name = self.expect("TYPE_ID").lexema
        parent = None

        if self.match("INHERITS"):
            parent = self.expect("TYPE_ID").lexema

        self.sem("begin_class", name, parent)
        self.expect("LBRACE")
        features = []

        while not self.check("RBRACE"):
            if self.check("EOF"):
                self.erro("classe nao fechada antes do fim do arquivo")

            features.append(self.parse_feature())
            self.expect("SEMI")

        self.expect("RBRACE")
        class_node = ClassDecl(name, parent, features)
        self.sem("end_class", class_node)
        return class_node

    def parse_feature(self) -> Feature:
        name = self.expect("OBJECT_ID").lexema

        if self.match("LPAREN"):
            params = []

            if not self.check("RPAREN"):
                params.append(self.parse_formal())

                while self.match("COMMA"):
                    params.append(self.parse_formal())

            self.expect("RPAREN")
            self.expect("COLON")
            return_type = self.expect("TYPE_ID").lexema
            self.sem("begin_method", name, params, return_type)
            self.expect("LBRACE")
            body = self.parse_expr()
            self.expect("RBRACE")
            method = Method(name, params, return_type, body)
            self.sem("end_method", method)
            return method

        self.expect("COLON")
        type_name = self.expect("TYPE_ID").lexema
        init = None

        if self.match("ASSIGN"):
            init = self.parse_expr()

        attribute = Attribute(name, type_name, init)
        self.sem("register_attribute", attribute)
        return attribute

    def parse_formal(self) -> Formal:
        name = self.expect("OBJECT_ID").lexema
        self.expect("COLON")
        type_name = self.expect("TYPE_ID").lexema
        return Formal(name, type_name)

    def parse_expr(self) -> Expr:
        return self.parse_assignment()

    def parse_assignment(self) -> Expr:
        left = self.parse_not()

        if self.match("ASSIGN"):
            if not isinstance(left, Identifier):
                self.erro("lado esquerdo de atribuicao precisa ser um identificador")

            value = self.parse_assignment()
            return self.checked(Assign(left.name, value))

        return left

    def parse_not(self) -> Expr:
        if self.match("NOT"):
            return self.checked(UnaryOp("not", self.parse_not()))

        return self.parse_comparison()

    def parse_comparison(self) -> Expr:
        left = self.parse_add()

        if self.check_any(("LT", "LE", "EQ")):
            op = self.advance().lexema
            right = self.parse_add()

            if self.check_any(("LT", "LE", "EQ")):
                self.erro("comparacoes nao podem ser encadeadas sem parenteses")

            return self.checked(BinaryOp(op, left, right))

        return left

    def parse_add(self) -> Expr:
        expr = self.parse_mul()

        while self.check_any(("PLUS", "MINUS")):
            op = self.advance().lexema
            right = self.parse_mul()
            expr = self.checked(BinaryOp(op, expr, right))

        return expr

    def parse_mul(self) -> Expr:
        expr = self.parse_unary()

        while self.check_any(("STAR", "SLASH")):
            op = self.advance().lexema
            right = self.parse_unary()
            expr = self.checked(BinaryOp(op, expr, right))

        return expr

    def parse_unary(self) -> Expr:
        if self.match("ISVOID"):
            return self.checked(UnaryOp("isvoid", self.parse_unary()))

        if self.match("TILDE"):
            return self.checked(UnaryOp("~", self.parse_unary()))

        return self.parse_dispatch()

    def parse_dispatch(self) -> Expr:
        expr = self.parse_primary()

        while self.check_any(("DOT", "AT")):
            static_type = None

            if self.match("AT"):
                static_type = self.expect("TYPE_ID").lexema
                self.expect("DOT")
            else:
                self.expect("DOT")

            method = self.expect("OBJECT_ID").lexema
            args = self.parse_arguments()
            expr = self.checked(Dispatch(expr, method, args, static_type))

        return expr

    def parse_arguments(self) -> list[Expr]:
        self.expect("LPAREN")
        args = []

        if not self.check("RPAREN"):
            args.append(self.parse_expr())

            while self.match("COMMA"):
                args.append(self.parse_expr())

        self.expect("RPAREN")
        return args

    def parse_primary(self) -> Expr:
        if self.check("IF"):
            return self.parse_if()

        if self.check("WHILE"):
            return self.parse_while()

        if self.check("LBRACE"):
            return self.parse_block()

        if self.check("LET"):
            return self.parse_let()

        if self.check("CASE"):
            return self.parse_case()

        if self.match("LPAREN"):
            expr = self.parse_expr()
            self.expect("RPAREN")
            return expr

        if self.match("NEW"):
            type_name = self.expect("TYPE_ID").lexema
            return self.checked(NewExpr(type_name))

        if self.check("OBJECT_ID"):
            name = self.advance().lexema

            if self.check("LPAREN"):
                args = self.parse_arguments()
                return self.checked(Dispatch(None, name, args))

            return self.checked(Identifier(name))

        if self.check("INTEGER"):
            return self.checked(IntLiteral(int(self.advance().lexema)))

        if self.check("STRING"):
            return self.checked(StringLiteral(self.advance().lexema))

        if self.match("TRUE"):
            return self.checked(BoolLiteral(True))

        if self.match("FALSE"):
            return self.checked(BoolLiteral(False))

        self.erro(f"expressao inesperada com token {self.peek().tipo}")

    def parse_if(self) -> IfExpr:
        self.expect("IF")
        condition = self.parse_expr()
        self.expect("THEN")
        then_expr = self.parse_expr()
        self.expect("ELSE")
        else_expr = self.parse_expr()
        self.expect("FI")
        return self.checked(IfExpr(condition, then_expr, else_expr))

    def parse_while(self) -> WhileExpr:
        self.expect("WHILE")
        condition = self.parse_expr()
        self.expect("LOOP")
        body = self.parse_expr()
        self.expect("POOL")
        return self.checked(WhileExpr(condition, body))

    def parse_block(self) -> Block:
        self.expect("LBRACE")

        if self.check("RBRACE"):
            self.erro("bloco precisa ter pelo menos uma expressao")

        expressions = []

        while not self.check("RBRACE"):
            if self.check("EOF"):
                self.erro("bloco nao fechado antes do fim do arquivo")

            expressions.append(self.parse_expr())
            self.expect("SEMI")

        self.expect("RBRACE")
        return self.checked(Block(expressions))

    def parse_let(self) -> LetExpr:
        self.expect("LET")
        self.sem("begin_let")
        declarations = [self.parse_let_decl()]

        while self.match("COMMA"):
            declarations.append(self.parse_let_decl())

        self.expect("IN")
        body = self.parse_expr()
        let_expr = LetExpr(declarations, body)
        self.sem("end_let", let_expr)
        return self.checked(let_expr)

    def parse_let_decl(self) -> LetDecl:
        name = self.expect("OBJECT_ID").lexema
        self.expect("COLON")
        type_name = self.expect("TYPE_ID").lexema
        init = None

        if self.match("ASSIGN"):
            init = self.parse_expr()

        declaration = LetDecl(name, type_name, init)
        self.sem("register_let_decl", declaration)
        return declaration

    def parse_case(self) -> CaseExpr:
        self.expect("CASE")
        expr = self.parse_expr()
        self.expect("OF")
        self.sem("begin_case")

        if self.check("ESAC"):
            self.erro("case precisa ter pelo menos um branch")

        branches = []

        while not self.check("ESAC"):
            if self.check("EOF"):
                self.erro("case nao fechado antes do fim do arquivo")

            name = self.expect("OBJECT_ID").lexema
            self.expect("COLON")
            type_name = self.expect("TYPE_ID").lexema
            self.expect("DARROW")
            self.sem("begin_case_branch", name, type_name)
            branch_expr = self.parse_expr()
            self.sem("end_case_branch")
            self.expect("SEMI")
            branches.append(CaseBranch(name, type_name, branch_expr))

        self.expect("ESAC")
        case_expr = CaseExpr(expr, branches)
        self.sem("end_case", case_expr)
        return self.checked(case_expr)


if __name__ == "__main__":
    caminho_arquivo = sys.argv[1] if len(sys.argv) > 1 else "codigo.txt"

    try:
        tokens = lexico(caminho_arquivo)
        ast = Parser2(tokens).parse()
        print(ast)
    except (ErroLexico, ErroSintatico) as erro:
        print(erro)

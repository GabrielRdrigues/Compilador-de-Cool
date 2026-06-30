from dataclasses import dataclass


# Representa um token reconhecido pelo analisador lexico.
@dataclass # gera construtor automaticamente e outras coisas para facilitar o uso de classes
class Token:
    tipo: str
    lexema: str
    linha: int
    coluna: int


# Classe de erros
class ErroLexico(Exception):
    pass


# Mapeia cada palavra-chave da linguagem COOL para o tipo do token.
PALAVRAS_CHAVE = {
    "class": "CLASS",
    "inherits": "INHERITS",
    "if": "IF",
    "then": "THEN",
    "else": "ELSE",
    "fi": "FI",
    "while": "WHILE",
    "loop": "LOOP",
    "pool": "POOL",
    "let": "LET",
    "in": "IN",
    "case": "CASE",
    "of": "OF",
    "esac": "ESAC",
    "new": "NEW",
    "isvoid": "ISVOID",
    "not": "NOT",
    "true": "TRUE",
    "false": "FALSE",
}


# Mapeia simbolos de um caractere para o tipo do token.
SIMBOLOS_SIMPLES = {
    "{": "LBRACE",
    "}": "RBRACE",
    "(": "LPAREN",
    ")": "RPAREN",
    ":": "COLON",
    ";": "SEMI",
    ",": "COMMA",
    ".": "DOT",
    "@": "AT",
    "~": "TILDE",
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "<": "LT",
    "=": "EQ",
}


# Mapeia simbolos de dois caracteres para o tipo do token.
SIMBOLOS_COMPOSTOS = {
    "<-": "ASSIGN",
    "<=": "LE",
    "=>": "DARROW",
}


# A keyword yield faz com que a funcao se torne um gerador, e o yield faz
# com que o gerador retorne uma coisa de cada vez. Ao voltar na execucao do
# gerador, ele continua de onde parou. Para rodar cada etapa, use next() ou
# use o gerador dentro de um for.
def lexico(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        linha = 1
        coluna = 1

        # Le um caractere e atualiza linha/coluna para que o parser consiga
        # apontar exatamente onde aconteceu um erro sintatico.
        def ler_caractere():
            nonlocal linha, coluna

            caractere = arquivo.read(1)

            if not caractere:
                return caractere

            if caractere == "\n":
                linha += 1
                coluna = 1
            else:
                coluna += 1

            return caractere

        # Observa o proximo caractere sem consumir esse caractere do arquivo.
        def ver_proximo():
            posicao_atual = arquivo.tell()
            caractere = arquivo.read(1)
            arquivo.seek(posicao_atual)

            return caractere

        while True:
            caractere = ler_caractere()

            # EOF marca o fim da entrada para facilitar o parser depois.
            if not caractere:
                yield Token("EOF", "", linha, coluna)
                break

            linha_inicio = linha
            coluna_inicio = coluna - 1

            # Espacos, tabs, quebras de linha e carriage return nao viram token.
            if caractere in " \t\r\n":
                continue

            # Comentario de linha comeca com dois hifens e vai ate o fim da linha.
            if caractere == "-" and ver_proximo() == "-":
                ler_caractere()

                while True:
                    caractere = ler_caractere()

                    if not caractere or caractere == "\n":
                        break

                continue

            # Comentario de bloco comeca com (* e termina com *), tem que aceitar aninhamento
            if caractere == "(" and ver_proximo() == "*":
                ler_caractere()
                nivel_comentario = 1

                while nivel_comentario > 0:
                    caractere = ler_caractere()

                    if not caractere:
                        raise ErroLexico(
                            f"Comentario de bloco nao fechado na linha {linha_inicio}, coluna {coluna_inicio}"
                        )

                    if caractere == "(" and ver_proximo() == "*":
                        ler_caractere()
                        nivel_comentario += 1
                    elif caractere == "*" and ver_proximo() == ")":
                        ler_caractere()
                        nivel_comentario -= 1

                continue

            # Identificadores comecam com letra e podem continuar com letras,
            # numeros ou underscore.
            if caractere.isalpha():
                lexema = caractere

                while True:
                    proximo = ver_proximo()

                    if proximo.isalnum() or proximo == "_":
                        lexema += ler_caractere()
                    else:
                        break

                lexema_normalizado = lexema.lower()

                # O manual de COOL diz que keywords nao dependem de maiusculas,
                # exceto true/false, que precisam comecar com letra minuscula.
                if lexema_normalizado in PALAVRAS_CHAVE and (
                    lexema_normalizado not in ("true", "false")
                    or lexema[0].islower()
                ):
                    tipo = PALAVRAS_CHAVE[lexema_normalizado]
                elif lexema[0].isupper():
                    tipo = "TYPE_ID" # Página 15 do manual de COOL
                else:
                    tipo = "OBJECT_ID" # Página 15 do manual de COOL

                yield Token(tipo, lexema, linha_inicio, coluna_inicio)
                continue

            # Teste de inteiro
            if caractere.isdigit():
                lexema = caractere

                while ver_proximo().isdigit():
                    lexema += ler_caractere()

                yield Token("INTEGER", lexema, linha_inicio, coluna_inicio)
                continue

            # Teste de String
            if caractere == '"':
                lexema = '"'

                while True:
                    caractere_string = ler_caractere()

                    if not caractere_string:
                        raise ErroLexico(
                            f"String nao fechada na linha {linha_inicio}, coluna {coluna_inicio}"
                        )

                    lexema += caractere_string

                    if caractere_string == '"':
                        break

                    if caractere_string == "\\":
                        proximo = ler_caractere()

                        if not proximo:
                            raise ErroLexico(
                                f"String nao fechada na linha {linha_inicio}, coluna {coluna_inicio}"
                            )

                        lexema += proximo

                yield Token("STRING", lexema, linha_inicio, coluna_inicio)
                continue

            # par serve pra testar simbolos compostos
            par = caractere + ver_proximo()

            if par in SIMBOLOS_COMPOSTOS:
                ler_caractere()
                yield Token(SIMBOLOS_COMPOSTOS[par], par, linha_inicio, coluna_inicio)
                continue

            # Simbolos simples possuem apenas um caractere.
            if caractere in SIMBOLOS_SIMPLES:
                yield Token(SIMBOLOS_SIMPLES[caractere], caractere, linha_inicio, coluna_inicio)
                continue

            raise ErroLexico(
                f"Caractere invalido {caractere!r} na linha {linha_inicio}, coluna {coluna_inicio}"
            )


if __name__ == "__main__":
    for token in lexico("codigo.txt"):
        print(token)

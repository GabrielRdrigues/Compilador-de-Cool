import contextlib
import json
from pathlib import Path
from semantic import SemanticAnalyzer2
from lexico import lexico
from parser import Parser2
from cool_to_bril import CoolToBrilCompiler, bril_to_text

def executar_teste():
    arquivo = "codigo.txt"
    Path("out").mkdir(parents=True, exist_ok=True)

    print("1. Executando análise léxica, sintática e semântica...")
    semantic = SemanticAnalyzer2()
    tokens = lexico(arquivo)
    ast = Parser2(tokens, semantic=semantic).parse()

    print("2. Gerando código Bril")
    compiler = CoolToBrilCompiler(semantic_analyzer=semantic)
    bril_json = compiler.compile_program(ast)

    # Gravando saídas
    out_json = Path("out/final.json")
    out_bril = Path("out/final.bril")
    
    out_json.write_text(json.dumps(bril_json, indent=2), encoding="utf-8")
    out_bril.write_text(bril_to_text(bril_json), encoding="utf-8")
    
    print(f"JSON gerado em: {out_json}")
    print(f"Texto .bril gerado em: {out_bril}")

if __name__ == "__main__":
    executar_teste()
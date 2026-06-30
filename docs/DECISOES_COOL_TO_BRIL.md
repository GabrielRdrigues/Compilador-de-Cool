# Decisoes de Implementacao do `cool_to_bril`

Este documento registra o motivo das decisoes tomadas na implementacao do backend
de Cool para Bril presente em [cool_to_bril.py](/home/gabriel/Documents/U.F.F/Compiladores/cool_to_bril.py:1).
Ele nao descreve uma implementacao ideal de todos os recursos de Cool; descreve
as escolhas praticas feitas para que o compilador fosse incremental, testavel e
compativel com o restante do projeto.

## 1. Backend autocontido e aditivo

A primeira decisao foi manter o backend autocontido. Por isso, `cool_to_bril.py`
declara seus proprios dataclasses de AST, mas aceita qualquer objeto que tenha os
mesmos nomes de classes e atributos. O motivo foi reduzir acoplamento: o backend
consegue funcionar tanto com ASTs construidas localmente quanto com ASTs vindas
do parser ja existente, sem exigir refatoracao dos modulos de analise lexica,
sintatica ou semantica.

Essa escolha tambem explica o uso sistematico de helpers como `_get`,
`_get_optional` e `_kind`. Em vez de depender rigidamente de um tipo Python
especifico, o compilador trabalha por "shape" do dado. Isso torna mais facil
consumir ASTs em dicionario, objetos desserializados de JSON e instancias de
dataclasses.

## 2. Modelo de geracao baseado em um subconjunto seguro de Bril

O backend escolhe uma representacao simples de Bril: cada metodo Cool vira uma
funcao Bril, e cada expressao compila para uma sequencia de instrucoes que
produz um nome temporario final. O motivo dessa estrategia e simplicidade
operacional:

- `compile_program` agrega funcoes.
- `compile_class` ignora atributos como funcoes independentes e compila apenas
  metodos.
- `compile_method` reseta o estado por funcao e fecha a traducao com `ret`.
- `compile_expr` sempre devolve o nome do valor produzido pela expressao.

Essa decisao evita uma IR intermediaria propria e deixa o codigo facil de testar
por inspecao da lista de instrucoes gerada, como os testes atuais fazem.

## 3. Temporarios, labels e escopos explicitamente controlados

O compilador usa tres estruturas de estado centrais:

- `temp_counter` para gerar variaveis `v0`, `v1`, `v2`, ...
- `label_counter` para gerar labels unicos como `if_then_0` e `while_done_2`
- `scopes` como pilha de ambientes para mapear nomes Cool para nomes Bril

O motivo dessas escolhas foi preservar duas propriedades importantes:

- evitar colisao de nomes entre subexpressoes e entre escopos aninhados
- manter o Bril gerado previsivel, o que ajuda tanto em depuracao quanto em teste

O helper `_fresh_local` existe especificamente para o caso em que um nome fonte,
como `x`, ja esta ocupado no ambiente atual. Em vez de sobrescrever o binding,
o backend gera um nome derivado como `x_1`.

## 4. Mapeamento de tipos deliberadamente simplificado

O mapeamento de tipos foi reduzido para:

- `Int -> int`
- `Bool -> bool`
- `String -> ptr`
- `SELF_TYPE -> ptr`
- qualquer outro tipo Cool -> `ptr`

O motivo foi pragmatico: Bril tem um conjunto pequeno de tipos basicos, enquanto
Cool e orientada a objetos. Em vez de modelar objetos, layout de memoria,
tabelas de despacho e hierarquia em Bril neste momento, o backend trata valores
de objetos como ponteiros opacos. Isso permite compilar uma faixa util da
linguagem sem assumir uma runtime completa.

## 5. Literais e operacoes primitivas viram instrucoes nativas

As operacoes mais diretas de Cool foram mapeadas para operacoes centrais de
Bril porque essa traducao e local, legivel e sem ambiguidades:

- inteiros e booleanos viram `const`
- `+`, `-`, `*`, `/` viram `add`, `sub`, `mul`, `div`
- `<`, `<=`, `=` viram `lt`, `le`, `eq`
- `not` vira `not`

Para `~`, a decisao foi implementar via multiplicacao por `-1`, emitindo antes
um `const -1`. O motivo foi evitar introduzir uma operacao inexistente em Bril.

Para identificadores, o backend emite `id` em vez de reutilizar diretamente o
nome existente. O motivo foi manter a regra uniforme de que cada subexpressao
retorna explicitamente um valor Bril materializado.

## 6. Controle de fluxo estruturado com labels e merge explicito

As expressoes `if` e `while` sao traduzidas com labels, `br` e `jmp`. O motivo
foi respeitar a natureza de baixo nivel de Bril sem perder o significado da
estrutura original.

No `if`, o backend:

- compila a condicao
- cria labels para os ramos `then`, `else` e `done`
- grava o resultado de cada ramo em um temporario comum usando `id`

Essa etapa de merge explicito e importante porque o `if` em Cool e uma
expressao, nao apenas um comando.

No `while`, a decisao foi devolver um `ptr` nulo ao final. O motivo foi alinhar
com a semantica de Cool em que `while` resulta em `Object`, sem precisar criar
uma representacao mais sofisticada para esse valor.

## 7. `let` como abertura de escopo com valor default

`let` foi implementado empilhando um novo escopo e criando bindings locais para
cada declaracao. Quando uma variavel nao possui inicializacao explicita, o
backend emite um valor default:

- `false` para `bool`
- `0` para `int` e tambem para `ptr`

O motivo foi manter a compilacao total dentro do subconjunto atual sem depender
de inicializacao implicita externa. A verificacao de compatibilidade entre o
valor inicial e o tipo esperado tambem foi mantida no backend como defesa extra,
mesmo havendo analise semantica no projeto.

## 8. Recursos orientados a objetos usam placeholders de runtime

As partes mais orientadas a objetos de Cool ainda nao sao expandidas para uma
runtime real em Bril. Em vez disso, o backend emite chamadas placeholder:

- `StringLiteral` vira chamada para `__cool_string_literal`
- `self` vira chamada para `__cool_self`
- `new T` vira chamada para `T.__new`
- dispatch dinamico pode virar `__dispatch_<metodo>`
- dispatch estatico usa `Classe.metodo`

O motivo dessa decisao foi separar "forma da traducao" de "implementacao de
runtime". Assim, o backend ja consegue representar no Bril onde haveria
alocacao, self e chamadas de metodo, mesmo sem ainda implementar vtables,
objetos ou heap de verdade.

## 9. `case` foi reduzido a uma implementacao minima

`case` atualmente compila apenas o primeiro branch. Isso e uma decisao de
compromisso, nao uma modelagem completa do recurso. O motivo provavelmente foi
habilitar a presenca do no de AST e uma primeira traducao sem ainda resolver:

- teste dinamico do tipo do escrutinado
- selecao do branch correto
- regra de branch mais especifico
- runtime support para inspecao de tipos

Na pratica, isso significa que `case` esta representado no backend, mas ainda
nao deve ser tratado como suporte semantico completo de traducao.

## 10. Desserializacao de AST flexivel

O backend aceita AST em JSON ou pickle. A funcao `ast_from_dict` reconhece
diversas chaves como `node_type`, `kind`, `_type`, `class` e `type`.

O motivo foi facilitar interoperabilidade com diferentes exportadores de AST e
com testes pequenos escritos a mao. Isso reduz o custo de integrar o backend a
um front-end que talvez nao serialize exatamente no mesmo formato interno.

## 11. Serializacao em JSON como formato principal

O formato de saida principal e um dicionario Python compativel com o schema JSON
de Bril, serializado com `json.dumps(..., indent=2)`. O motivo foi aderencia ao
ecossistema oficial de Bril e facilidade de inspecao manual.

A adicao posterior de `bril_to_text()` e do CLI com `--format` seguiu a mesma
logica: JSON continua sendo o formato canonico interno, e o texto `.bril` e uma
serializacao derivada para leitura humana e interoperabilidade com ferramentas
como `bril2json`.

## 12. Estrategia de teste adotada

Os testes atuais validam a traducao por forma da saida, nao por execucao do
programa em uma runtime Bril completa. O motivo e coerente com o estado atual do
backend: varias construcoes de objetos ainda dependem de placeholders.

Por isso, os testes focam em:

- ordem de instrucoes
- nomes de labels
- tipos Bril emitidos
- estrutura de `if`, `while` e `let`

Esse recorte torna os testes estaveis e diretamente relacionados com a
responsabilidade real do arquivo hoje: gerar Bril bem formado para o subconjunto
ja suportado.

## 13. Consequencia pratica dessas decisoes

O `cool_to_bril.py` atual e melhor entendido como um backend educacional e
incremental para um subconjunto relevante de Cool. Ele ja e suficiente para:

- traduzir expressoes aritmeticas e booleanas
- lidar com escopo local e atribuicoes
- expressar controle de fluxo em Bril
- representar chamadas e alocacoes como pontos de extensao de runtime

Ele ainda nao deve ser interpretado como uma implementacao completa da semantica
orientada a objetos de Cool em Bril. Essa separacao foi uma decisao valida
porque permitiu entregar valor funcional cedo, sem bloquear o backend inteiro na
implementacao de runtime.

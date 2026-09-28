"""Uma string conceitual do Blink → a string que CADA base de fato entende.

O Blink propunha **uma** string e ela ia inteira para qualquer das três bases. As três não
falam a mesma língua, e o resultado era o defeito relatado: "a string sugerida costuma não
dar resultado". Medido contra as APIs reais, com
`("machine learning" OR "deep learning") AND bibliometric` como base de comparação
(83.693 no OpenAlex):

* **OpenAlex** (`filter=default.search:`) aceita booleano em maiúscula, aspas e parênteses
  aninhados — mas devolve **HTTP 400** com curinga (`bibliometric*`) e com **vírgula**, que
  é o separador de filtros da própria API. Um `[tiab]` colado no termo derruba de 83.693
  para 72. Booleano em minúscula não é operador: vira palavra, e o mesmo tema cai para
  31.823. Sem os parênteses, a precedência muda e a conta pula para 898.824.
* **PubMed** (E-utilities `term=`) é a mais completa: booleano, parênteses, aspas e curinga,
  tudo válido. Quebra na sintaxe de OUTRAS bases — `TITLE-ABS-KEY(...)` devolveu **1**
  registro para um tema com 1.310.
* **Crossref** (`query.bibliographic`) **não tem booleano nenhum**. O provider já apaga
  `AND`/`OR`/`NOT` e os parênteses antes de enviar, e as aspas a API ignora: medido, a
  string com e sem aspas devolve o MESMO total e os MESMOS três primeiros resultados. É
  ranking por relevância sobre um saco de palavras — os 3,4 milhões de "resultados" não são
  um corpus, são a base inteira ordenada. Quem manda é a ordem e o limite de download.

Daí a divisão de trabalho: o modelo escreve **uma** string conceitual, e a adaptação para
cada base é **determinística**, feita aqui. Pedir três strings ao modelo seria três vezes a
chance de ele inventar sintaxe — e as regras acima são fixas, não são questão de opinião.

**Sem Tk e sem i18n**, como `core/research_context.py`: as notas saem como CÓDIGO
(`"curinga_removido"`) e quem tem tela traduz. É o que deixa a suíte exercitar as três
adaptações sem abrir janela nem carregar catálogo.
"""

from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Tuple

#: Ordem em que as três aparecem na tela. Igual à do seletor da aba de Importação — duas
#: ordens diferentes para a mesma lista de três bases é confusão gratuita.
BASES: Tuple[str, ...] = ("openalex", "crossref", "pubmed")

ROTULOS: Dict[str, str] = {
    "openalex": "OpenAlex",
    "crossref": "Crossref",
    "pubmed": "PubMed",
}

#: Aspas que o modelo escreve por conta própria (e que todo editor de texto insere).
#: `“machine learning”` mediu 83.689 contra 83.693 da versão com aspas retas: o OpenAlex
#: não as reconhece como delimitador de frase, só as ignora. A diferença é pequena aqui e
#: pode não ser em outra consulta — retificar é barato e remove a dúvida.
ASPAS_TORTAS = str.maketrans({"“": '"', "”": '"', "‘": "'",
                              "’": "'", "«": '"', "»": '"'})

#: Envoltórios de campo de OUTRAS bases. O modelo os escreve por hábito porque a literatura
#: de bibliometria é escrita em cima do Scopus e da Web of Science, e nenhuma das três bases
#: do Blicsa entende qualquer um deles.
ENVOLTORIO = re.compile(
    r"\b(?:TITLE-ABS-KEY|TITLE_ABS_KEY|TITLE|ABS|KEY|AUTHKEY|SRCTITLE|PUBYEAR|DOCTYPE|ALL"
    r"|TS|TI|AB|AK|AU|SO|PY|DT|LA|CU|WC)\s*=?\s*\(",
    re.I)

#: Marcador de campo em colchete (`[tiab]`, `[MeSH Terms]`, `[Title/Abstract]`). É sintaxe
#: legítima **do PubMed** — some nas outras duas, onde vira texto procurado ao pé da letra.
TAG_DE_CAMPO = re.compile(r"\[[^\[\]]{1,40}\]")

OPERADORES = ("AND", "OR", "NOT")

#: Booleano fora de aspas, em qualquer caixa. O `(?![\w-])` impede casar o "or" de "editor"
#: e o "and" de "brand".
BOOLEANO_QUALQUER_CAIXA = re.compile(r"(?<![\w-])(and|or|not)(?![\w-])", re.I)

#: Palavras que não distinguem nada num ranking por relevância. Só entram no caminho do
#: Crossref, onde o que sobra da string é um saco de palavras: lá, "the" concorre com o
#: termo temático. Nas outras duas a string mantém a estrutura e isto não se aplica.
VAZIAS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to",
    "with", "e", "de", "da", "do", "das", "dos", "em", "para", "por", "com", "um", "uma",
    "et", "la", "le", "les", "des", "du", "aux",
}

#: Teto de termos que vão para o Crossref. Sem booleano, cada palavra a mais só dilui o
#: ranking: a partir de uma dezena de termos os primeiros resultados param de ter relação
#: visível com o tema. Não é limite de digitação do usuário — é limite do que ESTA tradução
#: gera automaticamente.
TETO_TERMOS_CROSSREF = 12


class Adaptacao(NamedTuple):
    """A string pronta para uma base, e o que foi preciso mudar para chegar nela.

    `notas` são códigos, não frases: a tela traduz (`t("strings_base.nota.<codigo>")`) e o
    teste compara sem depender de idioma.
    """

    base: str
    string: str
    notas: List[str]


# ── Higiene comum às três ────────────────────────────────────────────────────────

def _sem_envoltorios(texto: str) -> Tuple[str, bool]:
    """Tira `TITLE-ABS-KEY(...)`, `TS=(...)` e parentes, **preservando o conteúdo**.

    Apagar até o `)` levaria junto os termos, que é o que interessa. O casamento é feito na
    mão porque o conteúdo tem parênteses aninhados e expressão regular não conta parênteses.
    """
    mudou = False
    while True:
        m = ENVOLTORIO.search(texto)
        if not m:
            return texto, mudou
        # Do `(` que o envoltório abriu até o `)` que o fecha, contando os de dentro.
        i = m.end() - 1
        nivel = 0
        fim = None
        for j in range(i, len(texto)):
            if texto[j] == "(":
                nivel += 1
            elif texto[j] == ")":
                nivel -= 1
                if nivel == 0:
                    fim = j
                    break
        if fim is None:
            # Envoltório aberto e nunca fechado (resposta cortada no meio): tira só o rótulo.
            texto = texto[:m.start()] + texto[m.end():]
        else:
            texto = texto[:m.start()] + texto[m.end():fim] + texto[fim + 1:]
        mudou = True


def _fatiar_por_aspas(texto: str) -> List[Tuple[str, bool]]:
    """A string em pedaços `(trecho, dentro_de_aspas)`.

    Existe porque toda regra abaixo vale FORA das aspas e não dentro: subir `and` para
    maiúscula dentro de `"drug and alcohol"` mudaria o título procurado, e tirar a vírgula
    de `"Rio de Janeiro, Brazil"` mudaria o lugar.
    """
    partes: List[Tuple[str, bool]] = []
    atual: List[str] = []
    dentro = False
    for ch in texto:
        if ch == '"':
            partes.append(("".join(atual), dentro))
            atual = []
            dentro = not dentro
            partes.append(('"', False))
            continue
        atual.append(ch)
    partes.append(("".join(atual), dentro))
    return [(p, d) for p, d in partes if p != ""]


def _fora_das_aspas(texto: str, transformar) -> str:
    return "".join(p if dentro else transformar(p) for p, dentro in _fatiar_por_aspas(texto))


def _aspas_pareadas(texto: str) -> str:
    """Fecha a aspa que ficou aberta. Resposta cortada pelo limite de tokens produz isso."""
    return texto + '"' if texto.count('"') % 2 else texto


def _parenteses_sem_par(texto: str) -> List[int]:
    """Índices dos parênteses que não têm par, ignorando o que está entre aspas.

    Uma passada só, com pilha: o que sobra na pilha no fim são os `(` nunca fechados, e o
    que não acha par na hora é um `)` a mais. Parêntese entre aspas é conteúdo — `"(bio)"`
    é um termo, não um grupo.
    """
    pilha: List[int] = []
    sobrando: List[int] = []
    dentro = False
    for i, ch in enumerate(texto):
        if ch == '"':
            dentro = not dentro
        elif dentro:
            continue
        elif ch == "(":
            pilha.append(i)
        elif ch == ")":
            if pilha:
                pilha.pop()
            else:
                sobrando.append(i)
    return pilha + sobrando


def _parenteses_equilibrados(texto: str) -> Tuple[str, bool]:
    """Descarta parêntese sem par. Um `(` sobrando é 400 no OpenAlex e erro no PubMed."""
    sem_par = _parenteses_sem_par(texto)
    if not sem_par:
        return texto, False
    lista = list(texto)
    for pos in sorted(sem_par, reverse=True):
        del lista[pos]
    return "".join(lista), True


def _operadores_soltos(texto: str) -> Tuple[str, bool]:
    """Tira operador que sobrou na ponta ou grudado em parêntese.

    `"machine learning" AND` mediu 3.633.511 no OpenAlex: o operador pendurado não dá erro,
    ele silenciosamente descarta a restrição e devolve quase a base inteira. Silêncio é o
    pior dos dois modos de falhar — o 400 pelo menos aparece.
    """
    antes = texto
    alt = "|".join(OPERADORES)
    texto = re.sub(rf"\(\s*(?:{alt})\s+", "(", texto)
    texto = re.sub(rf"\s+(?:{alt})\s*\)", ")", texto)
    texto = re.sub(rf"^\s*(?:{alt})\s+", "", texto)
    texto = re.sub(rf"\s+(?:{alt})\s*$", "", texto)
    texto = re.sub(rf"\s+(?:{alt})(\s+(?:{alt}))+\s+", lambda m: f" {m.group(0).split()[0]} ", texto)
    return texto.strip(), texto.strip() != antes.strip()


def _espacos(texto: str) -> str:
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\(\s+", "(", texto)
    texto = re.sub(r"\s+\)", ")", texto)
    return texto.strip()


def normalizar(bruto: str) -> Tuple[str, List[str]]:
    """A higiene que vale para as TRÊS bases, antes de qualquer regra específica."""
    notas: List[str] = []
    texto = (bruto or "").replace("\n", " ").translate(ASPAS_TORTAS)
    if texto != (bruto or "").replace("\n", " "):
        notas.append("aspas_retificadas")

    texto = _aspas_pareadas(texto)

    texto, tirou_envoltorio = _sem_envoltorios(texto)
    if tirou_envoltorio:
        notas.append("sintaxe_de_outra_base")

    def _maiuscula(trecho: str) -> str:
        return BOOLEANO_QUALQUER_CAIXA.sub(lambda m: m.group(1).upper(), trecho)

    subido = _fora_das_aspas(texto, _maiuscula)
    if subido != texto:
        notas.append("booleano_em_maiuscula")
    texto = subido

    texto, desequilibrado = _parenteses_equilibrados(texto)
    if desequilibrado:
        notas.append("parenteses_equilibrados")

    texto, sobrou = _operadores_soltos(_espacos(texto))
    if sobrou:
        notas.append("operador_solto")

    return _espacos(texto), notas


# ── As três adaptações ───────────────────────────────────────────────────────────

def _para_openalex(texto: str, notas: List[str]) -> Adaptacao:
    """Booleano e parênteses ficam; curinga, vírgula e tag de campo saem — sob pena de 400.

    A vírgula não é preferência de estilo: o provider monta `filter=default.search:<string>`,
    e vírgula é o separador de filtros da API. `default.search:machine learning, deep
    learning` devolveu HTTP 400, ou seja, a busca inteira falha por causa de um caractere de
    pontuação no meio de uma frase.
    """
    notas = list(notas)

    if "*" in texto:
        # O curinga não tem equivalente: o OpenAlex não expande prefixo. Tirar o `*` reduz o
        # alcance (`bibliometric*` deixa de pegar `bibliometrics`), mas a alternativa é a
        # busca não rodar. A nota diz ao usuário o que ele perdeu, para ele poder escrever
        # `(bibliometric OR bibliometrics)` à mão se importar.
        texto = texto.replace("*", "")
        notas.append("curinga_removido")

    if "," in texto:
        texto = texto.replace(",", " ")
        notas.append("virgula_removida")

    if TAG_DE_CAMPO.search(texto):
        texto = TAG_DE_CAMPO.sub(" ", texto)
        notas.append("tag_de_campo_removida")

    texto, sobrou = _operadores_soltos(_espacos(texto))
    if sobrou and "operador_solto" not in notas:
        notas.append("operador_solto")

    return Adaptacao("openalex", _espacos(texto), notas)


def _atomos_positivos(texto: str) -> List[str]:
    """Frases e termos da string, **descartando tudo que está sob um `NOT`**.

    Para o Crossref, que apaga os operadores, o ramo negado seria devolvido como termo
    procurado: `NOT review` faria a busca preferir justamente as revisões que o usuário
    pediu para excluir. Descartar é a única leitura fiel do que ele escreveu.
    """
    tokens = re.findall(r'"[^"]*"|\(|\)|[^\s()]+', texto)
    atomos: List[str] = []
    i = 0
    while i < len(tokens):
        tk = tokens[i]
        if tk.upper() == "NOT":
            # Pula o átomo negado: um grupo entre parênteses inteiro, ou um termo só.
            i += 1
            if i < len(tokens) and tokens[i] == "(":
                nivel = 0
                while i < len(tokens):
                    if tokens[i] == "(":
                        nivel += 1
                    elif tokens[i] == ")":
                        nivel -= 1
                        if nivel == 0:
                            i += 1
                            break
                    i += 1
            else:
                i += 1
            continue
        if tk in ("(", ")") or tk.upper() in OPERADORES:
            i += 1
            continue
        atomos.append(tk)
        i += 1
    return atomos


def _para_crossref(texto: str, notas: List[str]) -> Adaptacao:
    """Sem operador nenhum: o que vai é o conjunto de termos, na ordem em que aparecem.

    Não é simplificação nossa — é o que a API faz. O `CrossrefProvider` apaga `AND`/`OR`/
    `NOT` e os parênteses antes de enviar, e as aspas a própria Crossref ignora (medido:
    com e sem aspas, mesmo total e mesmos três primeiros resultados). Mandar a string
    booleana inteira não dá erro: dá a ILUSÃO de ter funcionado, com milhões de
    "resultados" que são a base ordenada por relevância. Mais honesto entregar os termos e
    dizer que o recorte quem faz é o limite de download.
    """
    notas = list(notas)
    atomos = _atomos_positivos(texto)

    if "NOT" in texto.upper().split():
        notas.append("negacao_descartada")
    if any(c in texto for c in "()") or BOOLEANO_QUALQUER_CAIXA.search(texto):
        notas.append("sem_booleano")

    vistos = set()
    termos: List[str] = []
    for a in atomos:
        limpo = TAG_DE_CAMPO.sub("", a).strip('"').replace("*", "").strip(" ,;:")
        if not limpo or limpo.lower() in VAZIAS:
            continue
        chave = limpo.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        termos.append(limpo)

    if len(termos) > TETO_TERMOS_CROSSREF:
        termos = termos[:TETO_TERMOS_CROSSREF]
        notas.append("termos_cortados")

    return Adaptacao("crossref", " ".join(termos), notas)


def _para_pubmed(texto: str, notas: List[str]) -> Adaptacao:
    """A mais permissiva das três: booleano, parênteses, aspas e curinga passam inteiros.

    O que ela NÃO perdoa é sintaxe de outra base — `TITLE-ABS-KEY("machine learning" AND
    bibliometric)` devolveu **1** registro num tema com 1.310, porque o E-utilities procura
    "TITLE-ABS-KEY" como se fosse palavra do texto. Isso já saiu em `normalizar`; aqui só
    resta a vírgula, que o PubMed lê como parte do termo.
    """
    notas = list(notas)
    if "," in texto:
        texto = texto.replace(",", " ")
        notas.append("virgula_removida")
    return Adaptacao("pubmed", _espacos(texto), notas)


_ADAPTADORES = {
    "openalex": _para_openalex,
    "crossref": _para_crossref,
    "pubmed": _para_pubmed,
}


def adaptar(bruto: str, base: str) -> Adaptacao:
    """A string conceitual traduzida para UMA base. `base` é a chave do provider."""
    texto, notas = normalizar(bruto)
    if not texto:
        return Adaptacao(base, "", notas)
    return _ADAPTADORES[base](texto, notas)


def traduzir(bruto: str) -> List[Adaptacao]:
    """A string conceitual nas três bases, na ordem de `BASES`. Lista vazia se não há string."""
    if not (bruto or "").strip():
        return []
    return [adaptar(bruto, base) for base in BASES]

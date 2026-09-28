"""A string de busca que o Blink propôs, extraída da resposta dele.

O assistente de busca é instruído a terminar a análise com "uma nova string de busca
completa e pronta para copiar e colar" — e copiar e colar era literalmente o que sobrava
para o usuário: selecionar dentro de um `CTkTextbox` desabilitado, atravessar para a aba de
Importação e colar no campo. Este módulo acha a string na resposta para que um botão possa
fazer o caminho inteiro.

**Sem Tk de propósito**, como `core/credenciais.py`: achar a string numa resposta é
testável sem abrir janela, e é onde estão os casos difíceis.
"""

from __future__ import annotations

import re

#: Bloco cercado. `[^\n]*\n` engole o `python`/`text` que o modelo põe na cerca de abertura.
#: O `\Z` fecha o caso da resposta truncada pelo limite de tokens, com a cerca aberta.
CERCA = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.S)

CODIGO_INLINE = re.compile(r"`([^`\n]+)`")

#: Booleano em MAIÚSCULA, sem `re.I`. É o que separa uma string de busca de prosa: um texto
#: em português não escreve "AND" nem "NOT" em maiúscula, e com `re.I` qualquer frase com
#: "or" dentro de uma palavra viraria candidata.
BOOLEANO = re.compile(r"\b(?:AND|OR|NOT)\b")

#: Rótulo que o modelo põe antes da string: "Nova string: (...)". Sai fora.
ROTULO = re.compile(r"^\s*(?:nova\s+|sugest\w+\s+)*(?:string|query|busca)"
                    r"(?:\s+de\s+busca)?\s*[:=]\s*", re.I)

#: Acima disto não é string de busca, é a resposta inteira. Uma string real de bibliometria
#: passa dos 200 caracteres com facilidade, então o teto é folgado de propósito.
LIMITE = 2000


def _normalizar(bruto: str) -> str:
    """Junta as linhas do candidato numa só e tira rótulo e crases residuais."""
    linhas = [l.strip() for l in (bruto or "").strip().split("\n") if l.strip()]
    return ROTULO.sub("", " ".join(linhas)).strip().strip("`").strip()


def _parece_string_de_busca(texto: str) -> bool:
    """Booleano em maiúscula E (aspas OU parênteses).

    Só o booleano deixaria passar "use AND para restringir", que é uma frase que o Blink
    escreve com frequência — e aplicá-la no campo de busca daria zero resultado sem o
    usuário entender por quê.
    """
    if not texto or len(texto) > LIMITE:
        return False
    if not BOOLEANO.search(texto):
        return False
    return '"' in texto or "(" in texto


def extrair_string_de_busca(resposta: str) -> str:
    """A string proposta, ou `""` quando a resposta não traz uma.

    Três níveis de confiança, nessa ordem: bloco cercado, código inline, linha solta. O
    modelo quase sempre usa o primeiro, mas erra para os outros dois o bastante para valer
    o fallback — e a alternativa a achar é o botão não aparecer.

    Dentro de cada nível vale a ÚLTIMA candidata: o prompt pede a string nova no FIM da
    resposta, e a análise costuma citar a string ATUAL antes dela. Pegar a primeira
    devolveria ao usuário exatamente a string que ele já tem.
    """
    resposta = resposta or ""
    for candidatos in (CERCA.findall(resposta),
                       CODIGO_INLINE.findall(resposta),
                       resposta.split("\n")):
        achadas = [c for c in (_normalizar(x) for x in candidatos)
                   if _parece_string_de_busca(c)]
        if achadas:
            return achadas[-1]
    return ""

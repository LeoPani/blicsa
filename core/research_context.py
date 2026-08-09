"""Contexto de pesquisa do projeto: o que o pesquisador quer que a IA saiba antes de responder.

O corpus diz **o que** foi publicado. Não diz que a pessoa estuda cooperativas de catadores no
Sul do Brasil, que "informalidade" no vocabulário dela é categoria da sociologia do trabalho e
não do direito tributário, nem que a revisão é para uma tese de doutorado. Sem isso, a IA
responde sobre o corpus certo com o enquadramento errado — e o pesquisador tem que corrigir o
enquadramento em toda pergunta, o que é pior do que não ter assistente.

Este módulo é **sem Tk de propósito**: a montagem do prompt e o corte de orçamento são
decisões de conteúdo, e precisam ser testáveis sem abrir janela.

## A ordem é fixa, e a ordem é a decisão

    papel → idioma → contexto do usuário → dados do corpus → (pergunta, no turno do usuário)

O contexto do usuário vem **antes** dos dados, não depois. Posto depois, ele lê como
observação final sobre um material já apresentado; posto antes, ele é a lente pela qual o
material é lido. É a diferença entre "resuma estes abstracts — ah, e eu sou socióloga" e "você
está ajudando uma socióloga; aqui estão os abstracts".

A pergunta não entra aqui: ela é a mensagem `user`, e misturá-la no `system` apagaria a
distinção entre instrução permanente e turno de conversa.

## O que é sacrificado quando não cabe

Orçamento estourado corta **abstracts**, nunca o contexto do usuário. O raciocínio é de custo
de erro: abstract cortado tira uma evidência de um conjunto que tem outras; contexto cortado
faz a resposta inteira sair enquadrada errada, e o usuário não tem como saber por quê — ele
digitou o contexto e viu o indicador aceso.

Papel e diretiva de idioma **nunca** são cortados. Sem papel o assistente deixa de ser o
Blink; sem a diretiva ele responde no idioma do prompt em vez do idioma da interface, que é um
bug visível e imediato para quem usa o app em francês.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Teto do que o usuário pode digitar no campo. Não é limitação técnica — é editorial: acima
#: disso o "contexto" virou introdução de artigo, dilui o que importa e come o orçamento dos
#: abstracts, que é justamente o que a Fase 3 promete preservar.
LIMITE_CONTEXTO = 1200

#: Orçamento total do system prompt, em caracteres. Herdado do `system_prompt[:4000]` que
#: existia no `main.py` — mantido no mesmo valor de propósito, para que a mudança desta fase
#: seja **como** se corta, não **quanto**.
ORCAMENTO_PADRAO = 4000

#: Abaixo disto, o bloco de corpus é descartado inteiro em vez de entrar como toco. Meio
#: abstract não é meia evidência: é uma frase solta que o modelo cita como se fosse o achado
#: do artigo.
MINIMO_CORPUS = 200

#: Separadores de registro no bloco de corpus, do mais forte para o mais fraco. O corte
#: procura nesta ordem para nunca partir um registro ao meio.
SEPARADORES = ("\n\n---\n", "\n\n", "\n")

MARCA_CORTE = "\n[…]"

CABECALHO_CONTEXTO_PADRAO = "Contexto de pesquisa informado pelo usuário:"
CABECALHO_CORPUS_PADRAO = "Contexto relevante do corpus:"

#: Nome de cada idioma **em inglês**, que é como o modelo o reconhece com mais confiabilidade.
NOMES_IDIOMA = {"pt_BR": "Brazilian Portuguese", "en": "English", "fr": "French"}


def diretiva_idioma(lang: str | None) -> str:
    """A instrução de idioma que vai no system prompt.

    Mora aqui, e não no `main.py`, porque o teste de i18n precisa exercitar a **função real**.
    Enquanto ela era um trecho solto dentro de um método da janela, o teste replicava a lógica
    à mão e passava a verde mesmo se o `main.py` divergisse — que é o único jeito de esse
    teste falhar de verdade.
    """
    alvo = NOMES_IDIOMA.get(lang or "", "English")
    return (f"IMPORTANT: Always respond to the user in {alvo}, "
            f"regardless of the language of this prompt.")


def normalizar(texto: object) -> str:
    """Campo → texto guardável. Tolera `None`, número e o que mais vier de um `.blicsa` velho.

    Não é paranoia: `config.json` é um dicionário livre gravado por versões diferentes do app,
    e já apareceu `None` onde se esperava string. Um `AttributeError` aqui derrubaria o
    carregamento do projeto inteiro por causa de um campo de texto opcional.
    """
    if texto is None or isinstance(texto, bool):
        return ""
    if not isinstance(texto, str):
        texto = str(texto)
    # Espaço em volta some; quebras internas ficam — o usuário escreve em parágrafos e a
    # estrutura dele é informação.
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").strip()
    return texto[:LIMITE_CONTEXTO]


def esta_ativo(texto: object) -> bool:
    """Há contexto de verdade? É o que acende o indicador na interface.

    Campo só com espaços/quebras é campo vazio: acender o indicador nesse caso prometeria ao
    usuário um enquadramento que não está sendo enviado a lugar nenhum.
    """
    return bool(normalizar(texto))


def _corta_em_fronteira(texto: str, teto: int) -> str:
    """Corta `texto` para caber em `teto` caracteres **sem partir um registro**.

    Devolve string vazia se nem um registro inteiro couber — ver `MINIMO_CORPUS`.
    """
    if teto <= 0:
        return ""
    if len(texto) <= teto:
        return texto

    util = teto - len(MARCA_CORTE)
    if util <= 0:
        return ""

    for sep in SEPARADORES:
        pedaco = texto[:util]
        pos = pedaco.rfind(sep)
        if pos > 0:
            return texto[:pos] + MARCA_CORTE
    return ""


@dataclass(frozen=True)
class PromptMontado:
    """O prompt e o que aconteceu para ele caber. O diagnóstico não é enfeite: é o que permite
    ao teste afirmar *qual* parte foi sacrificada, em vez de só medir o tamanho final."""

    texto: str
    contexto_incluido: bool = False
    contexto_cortado: bool = False
    corpus_incluido: bool = False
    corpus_cortado: bool = False
    corpus_descartado: bool = False
    secoes: tuple[str, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.texto)


def montar(
    papel: str,
    idioma: str,
    contexto_usuario: object = "",
    dados_corpus: str = "",
    orcamento: int = ORCAMENTO_PADRAO,
    cabecalho_contexto: str = CABECALHO_CONTEXTO_PADRAO,
    cabecalho_corpus: str = CABECALHO_CORPUS_PADRAO,
) -> PromptMontado:
    """Monta o system prompt na ordem fixa e corta o que não couber, nessa prioridade.

    `papel` e `idioma` entram sempre e inteiros — se só eles já estouram o orçamento, o
    resultado sai acima do teto de propósito. Devolver um papel mutilado para respeitar um
    número seria trocar um problema mensurável por um invisível.
    """
    papel = (papel or "").strip()
    idioma = (idioma or "").strip()
    contexto = normalizar(contexto_usuario)
    corpus = (dados_corpus or "").strip()

    partes: list[str] = [p for p in (papel, idioma) if p]
    secoes: list[str] = []
    if papel:
        secoes.append("papel")
    if idioma:
        secoes.append("idioma")

    fixo = "\n\n".join(partes)
    contexto_incluido = contexto_cortado = False
    corpus_incluido = corpus_cortado = corpus_descartado = False

    if contexto:
        bloco = f"{cabecalho_contexto}\n{contexto}"
        # Teto do contexto = o que sobra depois do que nunca se corta. Só morde quando o
        # orçamento é pequeno demais para o campo inteiro; o limite normal é LIMITE_CONTEXTO.
        teto = orcamento - len(fixo) - 2
        if len(bloco) > teto:
            util = teto - len(cabecalho_contexto) - 1 - len(MARCA_CORTE)
            if util > 0:
                bloco = f"{cabecalho_contexto}\n{contexto[:util]}{MARCA_CORTE}"
                contexto_cortado = True
            else:
                bloco = ""
        if bloco:
            partes.append(bloco)
            secoes.append("contexto")
            contexto_incluido = True

    montado = "\n\n".join(partes)

    if corpus:
        teto = orcamento - len(montado) - 2 - len(cabecalho_corpus) - 1
        cortado = _corta_em_fronteira(corpus, teto)
        if cortado and len(cortado) >= min(MINIMO_CORPUS, len(corpus)):
            partes.append(f"{cabecalho_corpus}\n{cortado}")
            secoes.append("corpus")
            corpus_incluido = True
            corpus_cortado = cortado != corpus
        else:
            corpus_descartado = True

    return PromptMontado(
        texto="\n\n".join(partes),
        contexto_incluido=contexto_incluido,
        contexto_cortado=contexto_cortado,
        corpus_incluido=corpus_incluido,
        corpus_cortado=corpus_cortado,
        corpus_descartado=corpus_descartado,
        secoes=tuple(secoes),
    )


def montar_system_prompt(*a, **kw) -> str:
    """Atalho para quem só quer o texto (a maioria dos pontos de chamada)."""
    return montar(*a, **kw).texto


def bloco_corpus(registros: list[str]) -> str:
    """Junta registros do corpus com o separador que o corte reconhece.

    Existe para que o produtor e o cortador concordem sobre onde termina um registro. Antes
    desta fase o `main.py` montava esse bloco com `"\\\\n\\\\n---\\\\n"` — barra invertida
    escapada duas vezes, ou seja, o modelo recebia a sequência literal `\\n` no meio do texto
    em vez de quebras de linha, e não havia fronteira nenhuma para cortar.
    """
    return "\n\n---\n".join(r for r in registros if r and r.strip())

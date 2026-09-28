"""Cada chamada de IA que a pesquisa fez, registrada com o que ela mexeu no resultado.

O Blicsa tinha ONZE pontos que chamam o modelo e **nenhum** deles gravava nada. O único
contador que existia, `blink_usage` no `diary.json` legado, era incrementado dentro de
`_legacy_diary(query, provider)` — que só roda quando o usuário faz uma BUSCA. Ou seja:
contava buscas e chamava de uso do Blink. Quem fosse declarar o uso de IA no artigo
(exigência de Elsevier, Nature e do COPE desde 2023) teria de reconstruir tudo de memória.

O eixo do módulo não é "quantas vezes" — é **onde a saída do modelo foi parar**:

* `INTERPRETA` — o texto do modelo VIRA o resultado. Só um ponto é assim, e é o mais
  perigoso: `label_clusters` nomeia os clusters, e esse nome vai para a figura do mapa que
  é publicada. Quem lê o artigo vê um rótulo temático sem saber que quem o escreveu foi um
  modelo de linguagem.
* `DESCREVE` — o modelo produz texto interpretativo mostrado como conteúdo de IA (insights
  do corpus, do mapa, do Sankey, do temático, do historiográfico, obras seminais). Marcado
  na tela pela convenção de `ui/ai_marking.py`, e citável se o autor quiser.
* `ACONSELHA` — ajuda o pesquisador a decidir e some (chat, assistente de busca). Não entra
  no resultado, mas entra na cadeia de decisão: a string de busca que o Blink sugeriu
  define o corpus inteiro.

Essa separação é a coisa que a declaração de uso precisa dizer, e é a que nenhum contador
de chamadas consegue expressar.

**Sem Tk**, como `core/strings_por_base.py`: a agregação é aritmética sobre o backlog e se
testa sem abrir janela.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

#: A ação gravada no `backlog.jsonl`. Nome curto porque convive com "search", "import",
#: "dedup", "analysis" e "export", que já estavam lá.
ACAO = "ia"

#: Onde a saída do modelo foi parar. A ordem é do mais grave para o menos.
INTERPRETA = "interpreta"
DESCREVE = "descreve"
ACONSELHA = "aconselha"

NATUREZAS = (INTERPRETA, DESCREVE, ACONSELHA)

#: Os onze pontos do app que chamam o modelo, com a natureza de cada um. A chave é o que
#: vai gravado; o rótulo legível sai do catálogo i18n (`ia.ponto.<chave>`), porque o
#: relatório é lido — e exportado — no idioma da pessoa.
#:
#: Um ponto novo que não apareça aqui é registrado assim mesmo, com natureza `DESCREVE` e o
#: próprio nome como rótulo: perder o registro seria pior que errar a classificação, e
#: `tests/test_uso_de_ia.py` tem uma guarda estrutural contra esquecer de cadastrá-lo.
PONTOS: Dict[str, str] = {
    "rotulos_de_cluster": INTERPRETA,
    "insights_do_corpus": DESCREVE,
    "insights_do_mapa": DESCREVE,
    "insights_sankey": DESCREVE,
    "insights_tematico": DESCREVE,
    "insights_historiografico": DESCREVE,
    "obras_seminais": DESCREVE,
    "blink_chat": ACONSELHA,
    "assistente_de_busca": ACONSELHA,
    "revisao_de_resultados": ACONSELHA,
    "chat_da_galeria": ACONSELHA,
}


def natureza(ponto: str) -> str:
    """Onde a saída deste ponto foi parar. `DESCREVE` para ponto não cadastrado."""
    return PONTOS.get(ponto, DESCREVE)


def evento(ponto: str, modelo: str, provedor: str, uso: Optional[dict] = None,
           erro: str = "", **extras: Any) -> Dict[str, Any]:
    """O `detail` de uma linha `ia` do backlog.

    `uso` é o objeto que a API devolve (`prompt_tokens`, `completion_tokens`,
    `total_tokens`) — **ausente não é zero**. Provedor que não manda contagem, chamada que
    falhou no meio e resposta cortada dão `None`, e somar isso como zero faria o relatório
    afirmar um consumo que ninguém mediu. O agregador conta os eventos sem medida à parte.

    `erro` preenchido registra a TENTATIVA: a chamada que falhou também é uso de IA na
    cadeia de decisão, e some do relatório se só o sucesso for gravado.
    """
    detalhe: Dict[str, Any] = {
        "ponto": ponto,
        "natureza": natureza(ponto),
        "modelo": modelo or "",
        "provedor": provedor or "",
    }
    if uso:
        detalhe["tokens"] = {
            "entrada": int(uso.get("prompt_tokens") or 0),
            "saida": int(uso.get("completion_tokens") or 0),
            "total": int(uso.get("total_tokens") or 0),
        }
    if erro:
        detalhe["erro"] = str(erro)[:300]
    detalhe.update({k: v for k, v in extras.items() if v not in (None, "")})
    return detalhe


def provedor_do_endereco(base_url: str) -> str:
    """Nome do provedor a partir do endereço da API. É o que vai na declaração de uso.

    O modelo sozinho não basta: `openai/gpt-oss-120b` roda no Groq, e dizer "OpenAI" num
    artigo por causa do prefixo do nome seria declarar errado a quem processou os dados.
    """
    endereco = (base_url or "").lower()
    for marca, nome in (("groq.com", "Groq"),
                        ("openai.com", "OpenAI"),
                        ("anthropic.com", "Anthropic"),
                        ("googleapis.com", "Google"),
                        ("mistral.ai", "Mistral"),
                        ("openrouter.ai", "OpenRouter"),
                        ("together.xyz", "Together"),
                        ("deepseek.com", "DeepSeek"),
                        ("localhost", "local"),
                        ("127.0.0.1", "local")):
        if marca in endereco:
            return nome
    if not endereco:
        return ""
    # Endereço desconhecido: devolve o host cru em vez de "desconhecido". Num relatório de
    # método, o host É a informação — quem lê sabe reconhecê-lo.
    sem_esquema = endereco.split("://")[-1]
    return sem_esquema.split("/")[0]


def eventos_de_ia(backlog: Iterable[dict]) -> List[dict]:
    """As linhas `ia` do backlog, em ordem cronológica de gravação."""
    return [e for e in (backlog or []) if e.get("action") == ACAO]


def resumir(backlog: Iterable[dict]) -> Dict[str, Any]:
    """Agregação do uso de IA: por natureza, por ponto, por modelo, e o consumo.

    `sem_medida` é campo de primeira classe e não um detalhe: é quantas chamadas não
    trouxeram contagem de tokens. Sem ele, um total de 12.000 tokens em 30 chamadas das
    quais 20 não mediram nada pareceria o consumo da pesquisa inteira.
    """
    eventos = eventos_de_ia(backlog)

    por_natureza = {n: 0 for n in NATUREZAS}
    por_ponto: Dict[str, int] = {}
    por_modelo: Dict[str, Dict[str, int]] = {}
    provedores: List[str] = []
    entrada = saida = total = 0
    sem_medida = 0
    falhas = 0

    for e in eventos:
        d = e.get("detail", {}) or {}
        ponto = d.get("ponto", "?")
        nat = d.get("natureza") or natureza(ponto)

        por_natureza[nat] = por_natureza.get(nat, 0) + 1
        por_ponto[ponto] = por_ponto.get(ponto, 0) + 1
        if d.get("erro"):
            falhas += 1

        prov = d.get("provedor") or ""
        if prov and prov not in provedores:
            provedores.append(prov)

        modelo = d.get("modelo") or "?"
        acc = por_modelo.setdefault(modelo, {"chamadas": 0, "entrada": 0, "saida": 0,
                                             "total": 0, "sem_medida": 0})
        acc["chamadas"] += 1

        tok = d.get("tokens")
        if not tok:
            sem_medida += 1
            acc["sem_medida"] += 1
            continue
        entrada += tok.get("entrada", 0)
        saida += tok.get("saida", 0)
        total += tok.get("total", 0)
        acc["entrada"] += tok.get("entrada", 0)
        acc["saida"] += tok.get("saida", 0)
        acc["total"] += tok.get("total", 0)

    return {
        "chamadas": len(eventos),
        "falhas": falhas,
        "por_natureza": por_natureza,
        "por_ponto": dict(sorted(por_ponto.items(), key=lambda kv: -kv[1])),
        "por_modelo": por_modelo,
        "provedores": provedores,
        "tokens": {"entrada": entrada, "saida": saida, "total": total},
        "sem_medida": sem_medida,
        "primeiro": _quando(eventos[0]) if eventos else "",
        "ultimo": _quando(eventos[-1]) if eventos else "",
    }


def _quando(evento_do_backlog: dict) -> str:
    return str(evento_do_backlog.get("ts", ""))[:19].replace("T", " ")


def houve_interpretacao(backlog: Iterable[dict]) -> bool:
    """Alguma saída de modelo entrou no RESULTADO? Muda o texto da declaração de uso.

    Um artigo cujo mapa traz rótulos de cluster escritos por IA precisa dizer isso; um em
    que a IA só sugeriu strings de busca declara outra coisa. Confundir os dois é o erro
    que a declaração existe para não deixar acontecer.
    """
    return any((e.get("detail") or {}).get("natureza") == INTERPRETA
               for e in eventos_de_ia(backlog))


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")

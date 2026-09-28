"""O relatório da pesquisa: o que se anexa ao artigo, montado do que o projeto registrou.

Não é um painel de estatística de uso. É o documento que responde a três perguntas que
alguém vai fazer — o parecerista, o orientador, o editor da revista:

1. **A IA participou? Onde?** Elsevier, Nature e o COPE exigem a declaração desde 2023, e
   ela não é "usei IA": tem de dizer o que a IA fez. O relatório separa o ponto em que a
   saída do modelo VIROU o resultado (os rótulos de cluster vão para a figura publicada) do
   ponto em que ela só aconselhou. Ver `core/uso_de_ia.py`.
2. **Como se refaz esta busca?** Base, string exata, filtros, data, encontrados contra
   baixados, motivo de parada. É o item 'search' do PRISMA-S, e a string que importa é a que
   FOI para a API — não a que o usuário digitou, que passa pelo tradutor de
   `core/strings_por_base.py`.
3. **Quantos registros entraram e quantos sobraram?** Encontrados → baixados → importados →
   duplicatas → corpus final. O fluxograma do PRISMA, cujos números já estavam todos no
   backlog, espalhados por uma linha do tempo que ninguém somava.

Tudo isto sai do `backlog.jsonl` do projeto, que é append-only: o relatório **lê**, nunca
grava. Um relatório que precisasse de estado próprio poderia divergir do que aconteceu, e
divergir num documento de método é pior do que não existir.

**Sem Tk.** Usa `core.i18n` (como `core/parsers.py` e `core/visualizer.py` já fazem) porque
o relatório é lido e exportado no idioma da pessoa.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.i18n import t
from core.uso_de_ia import (ACONSELHA, DESCREVE, INTERPRETA, houve_interpretacao,
                            resumir)

#: Ações do backlog que contam registros entrando ou saindo do corpus.
_FLUXO = ("search", "import", "dedup")


# ── Montagem ────────────────────────────────────────────────────────────────────

def montar(backlog: List[dict], *, projeto: str = "", versao: str = "",
           contexto: str = "", df=None) -> Dict[str, Any]:
    """O relatório inteiro como dado, antes de virar texto.

    Separado da renderização porque as três saídas (tela, Markdown, JSON) mostram o MESMO
    relatório: se cada uma o montasse por conta própria, o PDF anexado ao artigo poderia
    discordar da tela em que a pessoa conferiu.
    """
    backlog = backlog or []
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "projeto": projeto,
        "ambiente": ambiente(versao),
        "contexto_pesquisa": (contexto or "").strip(),
        "ia": {
            "resumo": resumir(backlog),
            "interpretou": houve_interpretacao(backlog),
        },
        "buscas": buscas(backlog),
        "fluxo": fluxo_de_registros(backlog),
        "corpus": cobertura(df),
    }


def ambiente(versao: str = "") -> Dict[str, str]:
    """Versões do que produziu o resultado. Vai na seção de materiais e métodos."""
    return {
        "blicsa": versao or "",
        "python": platform.python_version(),
        "sistema": f"{platform.system()} {platform.release()}",
        "executavel": "empacotado" if getattr(sys, "frozen", False) else "código-fonte",
    }


def buscas(backlog: List[dict]) -> List[Dict[str, Any]]:
    """Uma linha por busca executada, na ordem em que aconteceram.

    `query` é o que o usuário digitou e `query_interpretada` é o que de fato foi para a API
    — as duas, porque a diferença entre elas é justamente o que um leitor precisaria saber
    para refazer a busca e não conseguir reproduzir o número.
    """
    saida = []
    for e in backlog or []:
        if e.get("action") != "search":
            continue
        d = e.get("detail", {}) or {}
        saida.append({
            "quando": _quando(e),
            "base": d.get("provider", ""),
            "string": d.get("query", ""),
            "string_enviada": d.get("query_interpretada", "") or d.get("query", ""),
            "filtros": d.get("filters", {}) or {},
            "encontrados": d.get("encontrados"),
            "baixados": d.get("baixados"),
            "motivo_de_parada": d.get("stop_reason", ""),
            "arquivo": d.get("arquivo", ""),
        })
    return saida


def fluxo_de_registros(backlog: List[dict]) -> Dict[str, Any]:
    """Os números do fluxograma: encontrados → baixados → importados → duplicatas.

    `corpus_final` sai do último `import`, que registra o total do corpus DEPOIS de somar —
    e não da subtração dos anteriores. Somar e subtrair daria um número plausível e errado
    sempre que a pessoa importasse um arquivo local, que não passa por busca nenhuma.
    """
    encontrados = baixados = importados = duplicatas = 0
    corpus_final = 0
    for e in backlog or []:
        acao = e.get("action")
        if acao not in _FLUXO:
            continue
        d = e.get("detail", {}) or {}
        if acao == "search":
            encontrados += int(d.get("encontrados") or 0)
            baixados += int(d.get("baixados") or 0)
        elif acao == "import":
            importados += int(d.get("registros") or 0)
            corpus_final = int(d.get("total_corpus") or corpus_final)
        elif acao == "dedup" and d.get("aplicado"):
            duplicatas += int(d.get("pares") or 0)
    return {
        "encontrados": encontrados,
        "baixados": baixados,
        "importados": importados,
        "duplicatas_removidas": duplicatas,
        "corpus_final": corpus_final,
    }


def cobertura(df) -> Dict[str, Any]:
    """O que o corpus tem e o que lhe falta. Alimenta a seção de limitações do artigo.

    Preenchimento de campo NÃO é detalhe de implementação: um corpus com 30% de resumos não
    sustenta análise de coocorrência de termos, e um sem referências não sustenta
    acoplamento bibliográfico nem cocitação. Hoje isso se descobre quando o mapa sai ralo.
    """
    vazio = {"registros": 0, "ano_min": None, "ano_max": None, "bases": {},
             "com_resumo": 0.0, "com_referencias": 0.0, "com_doi": 0.0,
             "com_palavras_chave": 0.0, "acesso_aberto": 0.0}
    if df is None or getattr(df, "empty", True):
        return vazio

    total = len(df)

    def _pct(coluna) -> float:
        if coluna not in df.columns:
            return 0.0
        serie = df[coluna]
        preenchidos = serie.notna() & (serie.astype(str).str.strip() != "")
        return round(100.0 * int(preenchidos.sum()) / total, 1)

    anos = []
    if "year" in df.columns:
        try:
            import pandas as pd
            validos = pd.to_numeric(df["year"], errors="coerce").dropna()
            # Ano 0 é o vazio do schema (`SCHEMA_REGISTRO`), não uma data: incluí-lo faria
            # todo relatório dizer que o corpus começa no ano zero.
            validos = validos[validos > 0]
            anos = [int(validos.min()), int(validos.max())] if len(validos) else []
        except Exception:
            anos = []

    bases: Dict[str, int] = {}
    if "origin" in df.columns:
        try:
            bases = {str(k): int(v) for k, v in df["origin"].value_counts().items() if str(k)}
        except Exception:
            bases = {}

    aberto = 0.0
    if "is_oa" in df.columns:
        try:
            aberto = round(100.0 * int(df["is_oa"].fillna(False).astype(bool).sum()) / total, 1)
        except Exception:
            aberto = 0.0

    return {
        "registros": total,
        "ano_min": anos[0] if anos else None,
        "ano_max": anos[1] if anos else None,
        "bases": bases,
        "com_resumo": _pct("abstract"),
        "com_referencias": _pct("references"),
        "com_doi": _pct("doi"),
        "com_palavras_chave": _pct("keywords"),
        "acesso_aberto": aberto,
    }


# ── A declaração de uso de IA ───────────────────────────────────────────────────

def declaracao_de_uso(relatorio: Dict[str, Any]) -> str:
    """O parágrafo que se cola na seção de métodos ou na declaração de contribuições.

    Escrito para ser colado sem edição, e por isso **muda de forma conforme o que houve**:
    corpus sem IA nenhuma diz que não houve; uso apenas consultivo diz o que a IA não fez;
    uso que entrou no resultado nomeia o ponto. Um texto fixo com lacunas seria mais simples
    e diria a mesma coisa em todos os três casos, que é justamente o que uma declaração de
    uso não pode fazer.
    """
    resumo = relatorio.get("ia", {}).get("resumo", {}) or {}
    if not resumo.get("chamadas"):
        return t("relatorio.decl_sem_ia")

    modelos = ", ".join(sorted(resumo.get("por_modelo", {}))) or "?"
    provedores = ", ".join(resumo.get("provedores", [])) or "?"
    versao = relatorio.get("ambiente", {}).get("blicsa", "")

    partes = [t("relatorio.decl_abertura", modelos=modelos, provedores=provedores,
                versao=versao, chamadas=resumo.get("chamadas", 0))]

    por_nat = resumo.get("por_natureza", {}) or {}
    if por_nat.get(INTERPRETA):
        # Os pontos NOMEADOS, e não uma frase fixa sobre clusters: hoje a nomeação de
        # clusters é o único ponto que entra no resultado, e uma declaração que dissesse
        # "os clusters" por escrito passaria a mentir no dia em que houver o segundo.
        partes.append(t("relatorio.decl_interpreta", n=por_nat[INTERPRETA],
                        pontos=_pontos_da_natureza(resumo, INTERPRETA)))
    if por_nat.get(DESCREVE):
        partes.append(t("relatorio.decl_descreve", n=por_nat[DESCREVE]))
    if por_nat.get(ACONSELHA):
        partes.append(t("relatorio.decl_aconselha", n=por_nat[ACONSELHA]))

    # A frase que fecha é a que o editor procura: o que a IA NÃO fez. Sem ela, a declaração
    # lista atividades e deixa em aberto a única pergunta que interessa.
    partes.append(t("relatorio.decl_responsabilidade"))
    return " ".join(partes)


# ── Renderização ────────────────────────────────────────────────────────────────

def _pontos_da_natureza(resumo: Dict[str, Any], alvo: str) -> str:
    """Os nomes legíveis dos pontos de uma natureza, para a declaração citá-los."""
    from core.uso_de_ia import PONTOS

    nomes = [t(f"ia.ponto.{p}") for p in (resumo.get("por_ponto") or {})
             if PONTOS.get(p, DESCREVE) == alvo]
    return ", ".join(nomes)


def _ordem_de_gravidade(item) -> tuple:
    """Ordena os pontos do mais grave para o menos: o que entra no resultado vem primeiro.

    Ordenar por número de chamadas poria o chat — que não entra em nada — acima da nomeação
    de clusters, que vai para a figura publicada. Numa tabela de declaração de uso, a ordem
    é a informação.
    """
    from core.uso_de_ia import PONTOS

    ponto, chamadas = item
    return (list((INTERPRETA, DESCREVE, ACONSELHA)).index(PONTOS.get(ponto, DESCREVE)),
            -chamadas, ponto)


def para_json(relatorio: Dict[str, Any]) -> str:
    """A versão legível por máquina, para material suplementar.

    Leva a declaração já montada: quem processar o JSON não deveria ter de reimplementar as
    regras de redação dela para chegar ao mesmo parágrafo.
    """
    completo = dict(relatorio)
    completo.setdefault("declaracao_de_uso_de_ia", declaracao_de_uso(relatorio))
    return json.dumps(completo, ensure_ascii=False, indent=2)


def para_markdown(relatorio: Dict[str, Any]) -> str:
    """O relatório em Markdown — o formato que se cola no artigo e vira PDF."""
    from core.uso_de_ia import PONTOS

    l: List[str] = []
    projeto = relatorio.get("projeto") or t("relatorio.sem_projeto")
    l.append(f"# {t('relatorio.titulo')}: {projeto}")
    l.append("")
    l.append(f"_{t('relatorio.gerado_em')}: {_legivel(relatorio.get('gerado_em', ''))}_")
    l.append("")

    if relatorio.get("contexto_pesquisa"):
        l.append(f"## {t('relatorio.sec_contexto')}")
        l.append("")
        l.append(relatorio["contexto_pesquisa"])
        l.append("")

    # 1. Declaração
    l.append(f"## {t('relatorio.sec_declaracao')}")
    l.append("")
    l.append(declaracao_de_uso(relatorio))
    l.append("")

    resumo = relatorio.get("ia", {}).get("resumo", {}) or {}
    if resumo.get("chamadas"):
        l.append(f"### {t('relatorio.sec_pontos')}")
        l.append("")
        l += _tabela([t("relatorio.col_ponto"), t("relatorio.col_natureza"),
                      t("relatorio.col_chamadas")],
                     [[t(f"ia.ponto.{p}"), t(f"ia.natureza.{PONTOS.get(p, DESCREVE)}"), str(n)]
                      for p, n in sorted((resumo.get("por_ponto") or {}).items(),
                                         key=_ordem_de_gravidade)])
        l.append("")

        # 4. Consumo
        l.append(f"### {t('relatorio.sec_consumo')}")
        l.append("")
        l += _tabela([t("relatorio.col_modelo"), t("relatorio.col_chamadas"),
                      t("relatorio.col_entrada"), t("relatorio.col_saida"),
                      t("relatorio.col_total")],
                     [[m, str(v["chamadas"]), str(v["entrada"]), str(v["saida"]),
                       str(v["total"])]
                      for m, v in (resumo.get("por_modelo") or {}).items()])
        l.append("")
        if resumo.get("sem_medida"):
            l.append(f"> {t('relatorio.sem_medida', n=resumo['sem_medida'])}")
            l.append("")
        if resumo.get("falhas"):
            l.append(f"> {t('relatorio.falhas', n=resumo['falhas'])}")
            l.append("")

    # 2. Cadeia de busca
    l.append(f"## {t('relatorio.sec_buscas')}")
    l.append("")
    if not relatorio.get("buscas"):
        l.append(t("relatorio.sem_buscas"))
        l.append("")
    for i, b in enumerate(relatorio["buscas"], start=1):
        l.append(f"**{i}. {b['base']}** — {_legivel(b['quando'])}")
        l.append("")
        l.append("```")
        l.append(b["string_enviada"])
        l.append("```")
        if b["string"] and b["string"] != b["string_enviada"]:
            l.append("")
            l.append(t("relatorio.string_digitada", s=b["string"]))
        detalhes = [t("relatorio.encontrados_baixados",
                      e=_ou_traco(b["encontrados"]), b=_ou_traco(b["baixados"]))]
        if b["filtros"]:
            detalhes.append(t("relatorio.filtros",
                              f=", ".join(f"{k}={v}" for k, v in b["filtros"].items())))
        if b["motivo_de_parada"]:
            detalhes.append(t("relatorio.parada", m=b["motivo_de_parada"]))
        l.append("")
        l.append(" · ".join(detalhes))
        l.append("")

    # 3. Fluxo de registros
    fluxo = relatorio.get("fluxo", {}) or {}
    l.append(f"## {t('relatorio.sec_fluxo')}")
    l.append("")
    l += _tabela([t("relatorio.col_etapa"), t("relatorio.col_registros")],
                 [[t("relatorio.fluxo_encontrados"), str(fluxo.get("encontrados", 0))],
                  [t("relatorio.fluxo_baixados"), str(fluxo.get("baixados", 0))],
                  [t("relatorio.fluxo_importados"), str(fluxo.get("importados", 0))],
                  [t("relatorio.fluxo_duplicatas"), str(fluxo.get("duplicatas_removidas", 0))],
                  [t("relatorio.fluxo_final"), str(fluxo.get("corpus_final", 0))]])
    l.append("")

    # 5. Cobertura
    c = relatorio.get("corpus", {}) or {}
    l.append(f"## {t('relatorio.sec_cobertura')}")
    l.append("")
    if not c.get("registros"):
        l.append(t("relatorio.sem_corpus"))
        l.append("")
    else:
        periodo = (f"{c['ano_min']}–{c['ano_max']}" if c.get("ano_min") else "—")
        l.append(t("relatorio.corpus_resumo", n=c["registros"], periodo=periodo))
        l.append("")
        l += _tabela([t("relatorio.col_campo"), t("relatorio.col_preenchido")],
                     [[t("relatorio.campo_resumo"), f"{c['com_resumo']}%"],
                      [t("relatorio.campo_referencias"), f"{c['com_referencias']}%"],
                      [t("relatorio.campo_doi"), f"{c['com_doi']}%"],
                      [t("relatorio.campo_palavras"), f"{c['com_palavras_chave']}%"],
                      [t("relatorio.campo_oa"), f"{c['acesso_aberto']}%"]])
        l.append("")
        if c.get("bases"):
            l.append(t("relatorio.bases",
                       b=", ".join(f"{k} ({v})" for k, v in c["bases"].items())))
            l.append("")

    # 6. Ambiente
    a = relatorio.get("ambiente", {}) or {}
    l.append(f"## {t('relatorio.sec_ambiente')}")
    l.append("")
    l.append(f"- Blicsa {a.get('blicsa', '?')} ({a.get('executavel', '?')})")
    l.append(f"- Python {a.get('python', '?')} · {a.get('sistema', '?')}")
    l.append("")

    return "\n".join(l)


def _tabela(cabecalho: List[str], linhas: List[List[str]]) -> List[str]:
    """Tabela Markdown. Sem linha nenhuma, devolve o aviso — nunca um cabeçalho solto."""
    if not linhas:
        return [f"_{t('relatorio.tabela_vazia')}_"]
    saida = ["| " + " | ".join(cabecalho) + " |",
             "| " + " | ".join("---" for _ in cabecalho) + " |"]
    saida += ["| " + " | ".join(c.replace("|", "\\|") for c in linha) + " |"
              for linha in linhas]
    return saida


def _quando(entrada: dict) -> str:
    return str(entrada.get("ts", ""))[:19].replace("T", " ")


def _legivel(iso: str) -> str:
    return str(iso or "")[:19].replace("T", " ")


def _ou_traco(valor: Optional[int]) -> str:
    """`—` para o que não foi medido. Zero é uma afirmação; ausência não é."""
    return "—" if valor is None else str(valor)

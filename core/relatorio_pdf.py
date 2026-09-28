"""O relatório da pesquisa em PDF — o anexo que se submete junto com o artigo.

Gerado a partir do **dicionário** de `core/relatorio.montar`, e não do Markdown que
`para_markdown` produz. Reescrever um parser de Markdown aqui só para desfazer o que
acabamos de formatar seria trabalho em dobro com uma chance a mais de divergir: o PDF
anexado ao artigo tem de dizer exatamente o que a tela disse.

**Dependência opcional.** O `reportlab` fica em `requirements-pdf.txt`, junto do
`pdfplumber` — o extra de PDF que o projeto já tinha. Sem ele o Markdown e o JSON continuam
funcionando e a tela diz o comando de instalação, em vez de o botão falhar com um
`ModuleNotFoundError` que não ensina nada.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.i18n import t
from core.relatorio import declaracao_de_uso
from core.uso_de_ia import ACONSELHA, DESCREVE, INTERPRETA, PONTOS

#: Mesma tinta do design system (`ui/design_tokens.INK`), repetida aqui porque este módulo
#: não pode importar `ui/` — ele roda sem Tk, e é assim que o teste o exercita.
TINTA = "#141414"
CINZA = "#8A877F"
PAPEL = "#F6F4EE"


class ReportlabAusente(RuntimeError):
    """O extra de PDF não está instalado. A mensagem já é a que se mostra ao usuário."""

    def __init__(self):
        super().__init__(t("relatorio.pdf_ausente"))


def disponivel() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        return False


def gerar(relatorio: Dict[str, Any], caminho: str) -> str:
    """Escreve o PDF em `caminho` e o devolve. Levanta `ReportlabAusente` sem o extra."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_JUSTIFY
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                        Table, TableStyle)
    except Exception as ex:
        raise ReportlabAusente() from ex

    base = getSampleStyleSheet()
    tinta = colors.HexColor(TINTA)
    estilos = {
        "titulo": ParagraphStyle("t", parent=base["Title"], textColor=tinta, fontSize=20,
                                 spaceAfter=4),
        "sub": ParagraphStyle("s", parent=base["Normal"], textColor=colors.HexColor(CINZA),
                              fontSize=9, spaceAfter=14),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=tinta, fontSize=13,
                             spaceBefore=16, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], textColor=tinta, fontSize=11,
                             spaceBefore=10, spaceAfter=4),
        # `TA_JUSTIFY` na declaração: é o parágrafo que vai colado num artigo, e é o único
        # bloco longo do documento.
        "corpo": ParagraphStyle("p", parent=base["BodyText"], fontSize=9.5, leading=14,
                                alignment=TA_JUSTIFY, spaceAfter=6),
        "nota": ParagraphStyle("n", parent=base["BodyText"], fontSize=8.5, leading=12,
                               textColor=colors.HexColor(CINZA), spaceAfter=4),
        "codigo": ParagraphStyle("c", parent=base["Code"], fontSize=8.5, leading=12,
                                 backColor=colors.HexColor(PAPEL), borderPadding=6,
                                 spaceAfter=6),
    }

    doc = SimpleDocTemplate(caminho, pagesize=A4, title=t("relatorio.titulo"),
                            author="Blicsa", leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)

    def tabela(cabecalho: List[str], linhas: List[List[str]]):
        if not linhas:
            return Paragraph(t("relatorio.tabela_vazia"), estilos["nota"])
        tab = Table([cabecalho] + linhas, hAlign="LEFT", repeatRows=1)
        tab.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), tinta),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PAPEL)),
            ("LINEBELOW", (0, 0), (-1, 0), 1, tinta),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor(CINZA)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return tab

    fluxo: List[Any] = []
    projeto = relatorio.get("projeto") or t("relatorio.sem_projeto")
    fluxo.append(Paragraph(f"{t('relatorio.titulo')}: {_esc(projeto)}", estilos["titulo"]))
    fluxo.append(Paragraph(
        f"{t('relatorio.gerado_em')} {str(relatorio.get('gerado_em', ''))[:19].replace('T', ' ')}",
        estilos["sub"]))

    if relatorio.get("contexto_pesquisa"):
        fluxo.append(Paragraph(t("relatorio.sec_contexto"), estilos["h2"]))
        fluxo.append(Paragraph(_esc(relatorio["contexto_pesquisa"]), estilos["corpo"]))

    fluxo.append(Paragraph(t("relatorio.sec_declaracao"), estilos["h2"]))
    fluxo.append(Paragraph(_esc(declaracao_de_uso(relatorio)), estilos["corpo"]))

    resumo = (relatorio.get("ia") or {}).get("resumo") or {}
    if resumo.get("chamadas"):
        ordem = {INTERPRETA: 0, DESCREVE: 1, ACONSELHA: 2}
        pontos = sorted((resumo.get("por_ponto") or {}).items(),
                        key=lambda kv: (ordem.get(PONTOS.get(kv[0], DESCREVE), 9), -kv[1]))
        fluxo.append(Paragraph(t("relatorio.sec_pontos"), estilos["h3"]))
        fluxo.append(tabela(
            [t("relatorio.col_ponto"), t("relatorio.col_natureza"), t("relatorio.col_chamadas")],
            [[t(f"ia.ponto.{p}"), t(f"ia.natureza.{PONTOS.get(p, DESCREVE)}"), str(n)]
             for p, n in pontos]))

        fluxo.append(Paragraph(t("relatorio.sec_consumo"), estilos["h3"]))
        fluxo.append(tabela(
            [t("relatorio.col_modelo"), t("relatorio.col_chamadas"), t("relatorio.col_entrada"),
             t("relatorio.col_saida"), t("relatorio.col_total")],
            [[m, str(v["chamadas"]), str(v["entrada"]), str(v["saida"]), str(v["total"])]
             for m, v in (resumo.get("por_modelo") or {}).items()]))
        if resumo.get("sem_medida"):
            fluxo.append(Spacer(1, 4))
            fluxo.append(Paragraph(t("relatorio.sem_medida", n=resumo["sem_medida"]),
                                   estilos["nota"]))
        if resumo.get("falhas"):
            fluxo.append(Paragraph(t("relatorio.falhas", n=resumo["falhas"]), estilos["nota"]))

    fluxo.append(Paragraph(t("relatorio.sec_buscas"), estilos["h2"]))
    if not relatorio.get("buscas"):
        fluxo.append(Paragraph(t("relatorio.sem_buscas"), estilos["nota"]))
    for i, b in enumerate(relatorio.get("buscas") or [], start=1):
        fluxo.append(Paragraph(
            f"<b>{i}. {_esc(b['base'])}</b> — {_esc(b['quando'])}", estilos["corpo"]))
        fluxo.append(Paragraph(_esc(b["string_enviada"]), estilos["codigo"]))
        if b["string"] and b["string"] != b["string_enviada"]:
            fluxo.append(Paragraph(
                _esc(t("relatorio.string_digitada", s=b["string"])), estilos["nota"]))
        detalhes = [t("relatorio.encontrados_baixados",
                      e=_traco(b["encontrados"]), b=_traco(b["baixados"]))]
        if b.get("filtros"):
            detalhes.append(t("relatorio.filtros",
                              f=", ".join(f"{k}={v}" for k, v in b["filtros"].items())))
        if b.get("motivo_de_parada"):
            detalhes.append(t("relatorio.parada", m=b["motivo_de_parada"]))
        fluxo.append(Paragraph(_esc(" · ".join(detalhes)), estilos["nota"]))
        fluxo.append(Spacer(1, 6))

    f = relatorio.get("fluxo") or {}
    fluxo.append(Paragraph(t("relatorio.sec_fluxo"), estilos["h2"]))
    fluxo.append(tabela(
        [t("relatorio.col_etapa"), t("relatorio.col_registros")],
        [[t("relatorio.fluxo_encontrados"), str(f.get("encontrados", 0))],
         [t("relatorio.fluxo_baixados"), str(f.get("baixados", 0))],
         [t("relatorio.fluxo_importados"), str(f.get("importados", 0))],
         [t("relatorio.fluxo_duplicatas"), str(f.get("duplicatas_removidas", 0))],
         [t("relatorio.fluxo_final"), str(f.get("corpus_final", 0))]]))

    c = relatorio.get("corpus") or {}
    fluxo.append(Paragraph(t("relatorio.sec_cobertura"), estilos["h2"]))
    if not c.get("registros"):
        fluxo.append(Paragraph(t("relatorio.sem_corpus"), estilos["nota"]))
    else:
        periodo = f"{c['ano_min']}–{c['ano_max']}" if c.get("ano_min") else "—"
        fluxo.append(Paragraph(t("relatorio.corpus_resumo", n=c["registros"], periodo=periodo),
                               estilos["corpo"]))
        fluxo.append(tabela(
            [t("relatorio.col_campo"), t("relatorio.col_preenchido")],
            [[t("relatorio.campo_resumo"), f"{c['com_resumo']}%"],
             [t("relatorio.campo_referencias"), f"{c['com_referencias']}%"],
             [t("relatorio.campo_doi"), f"{c['com_doi']}%"],
             [t("relatorio.campo_palavras"), f"{c['com_palavras_chave']}%"],
             [t("relatorio.campo_oa"), f"{c['acesso_aberto']}%"]]))
        if c.get("bases"):
            fluxo.append(Spacer(1, 4))
            fluxo.append(Paragraph(
                _esc(t("relatorio.bases",
                       b=", ".join(f"{k} ({v})" for k, v in c["bases"].items()))),
                estilos["nota"]))

    a = relatorio.get("ambiente") or {}
    fluxo.append(Paragraph(t("relatorio.sec_ambiente"), estilos["h2"]))
    fluxo.append(Paragraph(
        f"Blicsa {_esc(a.get('blicsa', '?'))} ({_esc(a.get('executavel', '?'))})<br/>"
        f"Python {_esc(a.get('python', '?'))} · {_esc(a.get('sistema', '?'))}",
        estilos["nota"]))

    doc.build(fluxo)
    return caminho


def _esc(texto: Any) -> str:
    """Escapa o que o `Paragraph` do reportlab leria como marcação.

    O texto vem de string de busca e de contexto escrito pelo usuário: um `<` ou um `&`
    numa query (`year<2020`, `A&B`) faria o reportlab levantar erro de parse e o PDF inteiro
    deixaria de sair por causa de um caractere.
    """
    return (str(texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _traco(valor) -> str:
    return "—" if valor is None else str(valor)

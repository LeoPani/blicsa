"""Amarelo significa uma coisa só: "isto foi gerado por IA".

O valor do sinal está na exclusividade. Se o amarelo às vezes quer dizer "IA", às vezes
"atenção" e às vezes "muitas citações", ele não quer dizer nada — e o usuário perde a
capacidade de distinguir dado de máquina só de olhar.

Estes testes guardam duas coisas: que **todo** ponto de IA é marcado, e que **nenhum** ponto de
dado usa amarelo.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

from ui.ai_marking import (NOTA_RODAPE_EXPORT, PREFIXO_EXPORT, marcar_texto_export,
                           nota_rodape_export, rotulo_cluster_e_de_ia)

RAIZ = Path(__file__).parent.parent
INVENTARIO = RAIZ / "docs" / "inventario-ia.md"

#: Arquivos onde YELLOW/#F5BE00 é legítimo, com o motivo. Qualquer outro uso reprova.
USOS_LEGITIMOS = {
    "ui/design_tokens.py":       "define o token",
    "ui/styles.py":              "reexporta o token",
    "ui/ai_marking.py":          "a marcação de IA em si",
    "ui/ai_onboarding_panel.py": "declara explicitamente que NÃO usa amarelo",
}

#: Botões que DISPARAM a IA continuam amarelos — são a porta de entrada, e o amarelo ali
#: reforça a mesma associação. Declarado no inventário como a única exceção.
BOTOES_IA = ("✨ Blink", "Análise IA do Corpus", "_trigger_ai", "_trigger_import_ai_assistant")


# ── Conformidade: o amarelo não escapa do inventário ──────────────────────────────

def test_amarelo_nao_e_usado_fora_do_inventario():
    """Varredura de código. Um uso novo de amarelo em dado passaria despercebido em revisão."""
    r = subprocess.run(["git", "ls-files", "*.py"], capture_output=True, text=True, cwd=RAIZ)
    infratores = []
    for nome in r.stdout.splitlines():
        if nome in USOS_LEGITIMOS or nome.startswith(("tests/", "dist/", "build/")):
            continue
        texto = (RAIZ / nome).read_text(encoding="utf-8", errors="replace")
        for i, linha in enumerate(texto.splitlines(), 1):
            codigo = linha.split("#", 1)[0]
            if not re.search(r"\bYELLOW\b|#F5BE00", codigo, re.I):
                continue
            if any(b in linha for b in BOTOES_IA):
                continue                      # botão que dispara IA: exceção declarada
            if re.search(r"^\s*from .* import|^\s*import ", codigo):
                continue                      # import não é uso
            infratores.append(f"{nome}:{i}: {linha.strip()[:90]}")
    assert not infratores, (
        "amarelo usado fora dos pontos do inventário — cada um destes dilui o sinal:\n"
        + "\n".join(infratores))


def test_paleta_de_clusters_nao_tem_amarelo():
    """Nó do mapa é DADO. Um cluster amarelo seria lido como "gerado por IA", que é falso."""
    from ui.design_tokens import CLUSTER_PALETTE, YELLOW

    assert YELLOW not in CLUSTER_PALETTE
    assert "#F5BE00" not in [c.upper() for c in CLUSTER_PALETTE]
    # E a paleta continua com cores suficientes e distintas.
    assert len(CLUSTER_PALETTE) >= 8
    assert len(set(c.upper() for c in CLUSTER_PALETTE)) == len(CLUSTER_PALETTE), "cor repetida"


def test_badge_de_citacoes_nao_e_amarelo():
    """Contagem de citações vem da base — é o oposto de conteúdo gerado."""
    texto = (RAIZ / "ui/search_feed.py").read_text(encoding="utf-8")
    trecho = re.search(r'text=f"★ \{cites\}".{0,120}', texto, re.S)
    assert trecho, "o badge de citações sumiu — teste desatualizado"
    assert "#F5BE00" not in trecho.group(0) and "YELLOW" not in trecho.group(0)


def test_barra_de_progresso_nao_e_amarela():
    """Progresso é estado da aplicação, não conteúdo."""
    texto = (RAIZ / "main.py").read_text(encoding="utf-8")
    trecho = re.search(r"_progress_bar = ctk\.CTkProgressBar\(.{0,200}", texto, re.S)
    assert trecho and "YELLOW" not in trecho.group(0)


# ── A cor nunca vem sozinha ───────────────────────────────────────────────────────

def test_marcacao_sempre_carrega_o_rotulo_textual():
    """Regra inegociável: daltonismo e impressão em P&B perdem a cor.

    O módulo de marcação não pode expor um caminho que aplique amarelo sem o selo."""
    fonte = (RAIZ / "ui/ai_marking.py").read_text(encoding="utf-8")
    # Todo ponto que aplica YELLOW no módulo está dentro de algo que também cria o selo.
    assert "def selo_ia" in fonte
    assert 't("ai.badge")' in fonte, "o selo tem que sair do catálogo i18n, não de literal"

    import ast
    arvore = ast.parse(fonte)
    classe = next(n for n in arvore.body
                  if isinstance(n, ast.ClassDef) and n.name == "AIContentFrame")
    corpo = ast.get_source_segment(fonte, classe)
    assert "YELLOW" in corpo, "a faixa deixou de ser amarela"
    assert "selo_ia" in corpo, "o bloco aplica amarelo SEM criar o selo textual"


def test_rotulo_ia_existe_nos_tres_idiomas():
    for loc in ("pt_BR", "en", "fr"):
        cat = json.loads((RAIZ / f"locales/{loc}.json").read_text(encoding="utf-8"))
        assert cat.get("ai.badge", "").strip(), f"{loc}: ai.badge vazio"
        assert len(cat["ai.badge"]) <= 4, f"{loc}: selo longo demais para um badge"


def test_contraste_do_texto_sobre_o_amarelo_passa_wcag_aaa():
    """`#141414` sobre `#F5BE00`. Documentado em docs/inventario-ia.md."""
    from ui.design_tokens import INK, YELLOW

    def _luminancia(hexa: str) -> float:
        r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    l1, l2 = sorted((_luminancia(INK), _luminancia(YELLOW)), reverse=True)
    razao = (l1 + 0.05) / (l2 + 0.05)
    assert razao >= 7.0, f"contraste {razao:.1f}:1 — abaixo do AAA (7:1)"
    # E o valor documentado tem que bater com o medido.
    doc = INVENTARIO.read_text(encoding="utf-8")
    assert f"{razao:.1f}".replace(".", ",") in doc, (
        f"o inventário não registra o contraste medido ({razao:.1f}:1)")


# ── Rótulos de cluster: IA vs. humano ─────────────────────────────────────────────

def test_rotulo_editado_pelo_humano_perde_a_marcacao_de_ia():
    """Marcar como IA algo que a pessoa escreveu é tão errado quanto o inverso."""
    origens = {0: "ia", 1: "usuario", 2: "ia"}
    assert rotulo_cluster_e_de_ia(0, origens) is True
    assert rotulo_cluster_e_de_ia(1, origens) is False, "rótulo editado à mão não é IA"
    assert rotulo_cluster_e_de_ia(2, origens) is True


def test_cluster_sem_origem_conhecida_nao_e_marcado():
    """Adversarial: na dúvida, NÃO marcar. Marcar dado do usuário como IA é o erro pior —
    faz o pesquisador desconfiar do próprio trabalho."""
    assert rotulo_cluster_e_de_ia(0, None) is False
    assert rotulo_cluster_e_de_ia(0, {}) is False
    assert rotulo_cluster_e_de_ia(99, {0: "ia"}) is False


def test_origem_de_cluster_aceita_chave_texto_ou_inteiro():
    """O id vem inteiro do Louvain e vira texto ao passar pelo JSON do projeto."""
    assert rotulo_cluster_e_de_ia(3, {"3": "ia"}) is True
    assert rotulo_cluster_e_de_ia("3", {3: "ia"}) is True


# ── Exports: a marcação viaja em TEXTO ────────────────────────────────────────────

def test_export_marca_secoes_com_prefixo():
    assert marcar_texto_export("Insights do corpus") == "[IA] Insights do corpus"
    assert PREFIXO_EXPORT == "[IA]"


def test_marcacao_de_export_e_idempotente():
    """Adversarial: exportar duas vezes, ou marcar um título já marcado, não empilha."""
    uma = marcar_texto_export("Análise temática")
    assert marcar_texto_export(uma) == uma == "[IA] Análise temática"


def test_export_tem_nota_de_rodape_nos_tres_idiomas():
    """Cor se perde em PDF monocromático; o texto não. A nota explica o marcador."""
    for loc in ("pt_BR", "en", "fr"):
        nota = nota_rodape_export(loc)
        assert nota.strip(), f"{loc}: nota vazia"
        assert PREFIXO_EXPORT in nota, f"{loc}: a nota não explica o marcador [IA]"
        assert len(nota) > 60, f"{loc}: nota curta demais para explicar"
    assert len(set(NOTA_RODAPE_EXPORT.values())) == 3, "notas idênticas entre idiomas"


def test_nota_de_rodape_pede_verificacao_antes_de_citar():
    """Honestidade científica: quem lê precisa saber que aquilo saiu de um modelo."""
    TERMOS = {"pt_BR": "citar", "en": "citing", "fr": "citer"}
    for loc, termo in TERMOS.items():
        assert termo in nota_rodape_export(loc).lower(), f"{loc}: falta a ressalva de citação"


def test_titulo_vazio_nao_vira_prefixo_orfao():
    """Adversarial: seção sem título não pode exportar um `[IA]` solto."""
    assert marcar_texto_export("") == PREFIXO_EXPORT
    assert marcar_texto_export("   ") == PREFIXO_EXPORT


# ── O inventário e o código não podem divergir ────────────────────────────────────

def test_inventario_existe_e_lista_os_pontos_de_ia():
    assert INVENTARIO.exists(), "docs/inventario-ia.md é entregável da fase"
    doc = INVENTARIO.read_text(encoding="utf-8")
    for funcao in ("generate_insights", "label_clusters", "generate_seminal_insights",
                   "generate_thematic_insights", "generate_sankey_insights",
                   "generate_historiograph_insights", "chat_history_stream"):
        assert funcao in doc, f"o inventário não cita {funcao}"


def test_toda_funcao_de_ia_do_client_esta_no_inventario():
    """Guarda contra uma função nova de IA entrar sem marcação: se `ai/client.py` ganhar um
    `generate_*`, o inventário fica desatualizado e este teste avisa."""
    import ast

    fonte = (RAIZ / "ai/client.py").read_text(encoding="utf-8")
    geradoras = {n.name for n in ast.walk(ast.parse(fonte))
                 if isinstance(n, ast.FunctionDef)
                 and (n.name.startswith("generate_") or n.name == "label_clusters")}
    doc = INVENTARIO.read_text(encoding="utf-8")
    faltando = sorted(f for f in geradoras if f not in doc)
    assert not faltando, f"funções de IA fora do inventário: {faltando}"


# ── Texto do próprio app NÃO é conteúdo de IA ─────────────────────────────────────

def test_saudacao_do_app_nao_e_marcada_como_ia():
    """A saudação vem do catálogo i18n — foi escrita por quem desenvolveu, não por um modelo.

    Marcá-la como IA dilui o sinal no sentido oposto ao usual: diz ao usuário que uma máquina
    escreveu o que nós escrevemos. Descoberto ao capturar a evidência: o selo "IA" aparecia
    sobre `blink.saudacao`.
    """
    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")

    assert "gerado_por_ia=True" in fonte, "o parâmetro de distinção sumiu da assinatura"
    # Toda chamada que renderiza a saudação tem que desligar a marcação.
    for linha in fonte.splitlines():
        if 't("blink.saudacao")' in linha and "_add_blink_message" in linha:
            assert "gerado_por_ia=False" in linha, (
                f"saudação marcada como IA: {linha.strip()}")


# ── Pontos de renderização FORA do funil do chat ──────────────────────────────────

def _metodo_do_main(nome: str) -> "ast.FunctionDef":
    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    return next(n for n in ast.walk(ast.parse(fonte))
                if isinstance(n, ast.FunctionDef) and n.name == nome)


def _chama(no: "ast.AST", funcao: str) -> bool:
    """`funcao(...)` é de fato CHAMADA dentro de `no`?

    Buscar a string no código-fonte não serve: a linha de `import` contém o nome e faz o
    teste passar mesmo quando a chamada foi removida.
    """
    return any(isinstance(n, ast.Call)
               and ((isinstance(n.func, ast.Name) and n.func.id == funcao)
                    or (isinstance(n.func, ast.Attribute) and n.func.attr == funcao))
               for n in ast.walk(no))

def test_dialogo_de_insights_e_marcado():
    """Sankey, mapa temático e historiografia renderizam em `_show_insights`, que **não**
    passa por `_add_blink_message`.

    Descoberto ao preparar a captura `ia_marcacao_insights`: o inventário declarava os três
    pontos como "faixa + selo" e não havia marcação nenhuma na tela. O funil do chat cobre
    sete pontos, e a existência do funil escondeu que estes três não estão nele.
    """
    metodo = _metodo_do_main("_show_insights")

    # A CHAMADA, não a menção: a primeira versão deste teste procurava a string
    # "AIContentFrame" no corpo do método e passava a verde com o defeito reinjetado —
    # a linha de `import` sozinha já satisfazia a busca. Achado pela reinjeção.
    assert _chama(metodo, "AIContentFrame"), "o diálogo de insights renderiza IA sem marcação"

    corpo = ast.get_source_segment((RAIZ / "main.py").read_text(encoding="utf-8"), metodo)
    assert "marcado.corpo" in corpo, "o texto não está DENTRO do bloco marcado"


def test_analise_seminal_e_marcada():
    """Marcação textual, porque o destino é um textbox já montado no grid da aba."""
    assert _chama(_metodo_do_main("_show_seminal_insights"), "marcar_texto_export"), (
        "a análise seminal renderiza IA sem marcação")


def test_todo_renderizador_de_ia_do_main_esta_marcado():
    """Guarda estrutural: os workers de IA só podem entregar o resultado a um renderizador
    que marque. Um `self.after(0, self._nova_tela, resultado)` novo cai aqui."""
    import ast

    MARCADOS = {"_add_blink_message", "_show_insights", "_show_seminal_insights",
                "_show_ai_error_dialog", "_set_idle", "_set_busy", "_inject_ai_context"}
    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    destinos = set()
    for n in ast.walk(arvore):
        if not (isinstance(n, ast.FunctionDef) and
                ("_worker" in n.name or n.name.startswith("_ai_"))):
            continue
        corpo = ast.get_source_segment(fonte, n) or ""
        if "analyst." not in corpo and "AIAnalyst" not in corpo:
            continue
        for chamada in ast.walk(n):
            # Só `self.<metodo>`: `self.after(0, algum_widget.pack_forget)` é manipulação de
            # widget, não entrega de conteúdo gerado.
            if (isinstance(chamada, ast.Call) and isinstance(chamada.func, ast.Attribute)
                    and chamada.func.attr == "after" and len(chamada.args) >= 2
                    and isinstance(chamada.args[1], ast.Attribute)
                    and isinstance(chamada.args[1].value, ast.Name)
                    and chamada.args[1].value.id == "self"):
                destinos.add(chamada.args[1].attr)

    fora = sorted(d for d in destinos if d not in MARCADOS)
    assert not fora, (
        f"worker de IA entrega o resultado a renderizador não declarado: {fora}. "
        "Ou ele marca o conteúdo, ou não deveria receber saída de modelo.")


def test_resposta_do_modelo_continua_marcada():
    """O outro lado da guarda: desligar a marcação para texto do app não pode desligá-la
    para o que o modelo escreve — que é o caso que justifica a convenção inteira."""
    import ast

    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    metodo = next(n for n in ast.walk(arvore)
                  if isinstance(n, ast.FunctionDef) and n.name == "_add_blink_message")
    # Os defaults casam com os ÚLTIMOS argumentos; pegar o primeiro Constant devolveria o
    # default de `text` ("") em vez do de `gerado_por_ia`.
    nomes = [a.arg for a in metodo.args.args]
    defaults = dict(zip(nomes[-len(metodo.args.defaults):], metodo.args.defaults))
    assert defaults["gerado_por_ia"].value is True, (
        "o padrão tem que ser MARCAR: esquecer o parâmetro numa chamada nova não pode "
        "deixar conteúdo de IA sem selo")

    corpo = ast.get_source_segment(fonte, metodo)
    assert 'role == "assistant" and gerado_por_ia' in corpo

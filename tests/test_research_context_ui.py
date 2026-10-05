"""A barra do contexto de pesquisa: o exemplo não vira valor, e o indicador não mente.

Dois riscos moram nesta tela e nenhum dos dois aparece olhando para ela:

1. **o texto de exemplo viajar para o modelo.** Um placeholder que `valor()` devolvesse faria
   o Blink responder sobre cooperativas de catadores para quem estuda semicondutores — e a
   resposta pareceria só um pouco estranha, nunca obviamente errada;
2. **o indicador aceso sem contexto indo junto** (ou apagado com ele indo). O indicador é a
   única prova que o usuário tem de que a IA está levando o enquadramento dele em conta.

Medição nos dois eixos (largura e altura) com a fonte REAL de cada widget, nos três idiomas,
mais a variação de origem — mesma regra do `test_layout_widths.py`.
"""

import ast
import json
import re
from pathlib import Path

import pytest

from core import i18n
from core.research_context import montar_system_prompt

RAIZ = Path(__file__).parent.parent
FONTE_BARRA = RAIZ / "ui" / "research_context_bar.py"
IDIOMAS = ("pt_BR", "en", "fr")


def _ctk():
    return pytest.importorskip("customtkinter")


def _root(ctk):
    try:
        r = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    # Fora da tela em vez de withdraw(): janela retirada não realiza geometria e todo
    # winfo_width() volta 1px.
    r.geometry("900x600+3000+3000")
    return r


def _barra(ctk, root, valor=""):
    from ui.research_context_bar import ResearchContextBar

    b = ResearchContextBar(root, valor=valor)
    b.pack(fill="x", padx=20)
    root.update_idletasks()
    return b


@pytest.fixture
def tela():
    ctk = _ctk()
    i18n.load_locales("pt_BR")
    root = _root(ctk)
    yield ctk, root
    root.destroy()
    i18n.load_locales("pt_BR")


# ── O exemplo é exemplo, não valor ────────────────────────────────────────────────

def test_exemplo_aparece_com_campo_vazio(tela):
    ctk, root = tela
    b = _barra(ctk, root)
    assert b.campo.get("1.0", "end").strip() == i18n.t("ai.contexto_placeholder")


def test_exemplo_nunca_e_devolvido_como_valor(tela):
    """O invariante central da barra. Sem ele, o exemplo vira a pesquisa de quem não reparou
    que aquilo era um exemplo."""
    ctk, root = tela
    b = _barra(ctk, root)
    assert b.valor() == ""


def test_exemplo_nao_chega_ao_system_prompt(tela):
    """Ponta a ponta: o que o modelo receberia se o usuário nunca tocasse no campo."""
    ctk, root = tela
    b = _barra(ctk, root)
    prompt = montar_system_prompt("papel", "idioma", b.valor(), "")
    assert i18n.t("ai.contexto_placeholder") not in prompt
    assert "catadores" not in prompt


def test_foco_limpa_o_exemplo_e_desfoque_vazio_o_traz_de_volta(tela):
    ctk, root = tela
    b = _barra(ctk, root)
    b._ao_focar()
    assert b.campo.get("1.0", "end").strip() == ""
    assert b.valor() == ""
    b._ao_desfocar()
    assert b.campo.get("1.0", "end").strip() == i18n.t("ai.contexto_placeholder")
    assert b.valor() == ""


def test_texto_do_usuario_igual_ao_exemplo_ainda_conta_como_valor(tela):
    """Adversarial: quem digitar literalmente o exemplo quis dizer aquilo. O que distingue
    valor de placeholder é o ESTADO da barra, não a comparação do texto — comparar textos
    apagaria a escolha deliberada de um usuário."""
    ctk, root = tela
    b = _barra(ctk, root)
    b._ao_focar()
    b.campo.insert("1.0", i18n.t("ai.contexto_placeholder"))
    assert b.valor() == i18n.t("ai.contexto_placeholder")


def test_definir_com_valor_do_projeto_substitui_o_exemplo(tela):
    ctk, root = tela
    b = _barra(ctk, root)
    b.definir("cooperativas de catadores, sociologia do trabalho")
    assert b.valor() == "cooperativas de catadores, sociologia do trabalho"
    assert b._mostrando_exemplo is False


def test_definir_vazio_volta_ao_exemplo(tela):
    """Projeto sem contexto, aberto depois de um projeto com contexto: a barra não pode
    guardar o texto do projeto anterior."""
    ctk, root = tela
    b = _barra(ctk, root, valor="algo")
    b.definir("")
    assert b.valor() == ""
    assert b._mostrando_exemplo is True


@pytest.mark.parametrize("lixo", [None, 0, {"a": 1}])
def test_definir_tolera_valor_de_projeto_corrompido(tela, lixo):
    ctk, root = tela
    b = _barra(ctk, root)
    b.definir(lixo)  # não levanta
    assert isinstance(b.valor(), str)


# ── O indicador ───────────────────────────────────────────────────────────────────

def test_indicador_apagado_sem_contexto(tela):
    ctk, root = tela
    b = _barra(ctk, root)
    assert b._indicador_aceso is False


def test_indicador_acende_com_contexto(tela):
    ctk, root = tela
    b = _barra(ctk, root, valor="estudo cooperativas de catadores")
    assert b._indicador_aceso is True
    assert b.indicador.cget("text") == i18n.t("ai.contexto_ativo")


def test_indicador_apaga_quando_o_contexto_e_apagado(tela):
    ctk, root = tela
    b = _barra(ctk, root, valor="algo")
    b._ao_focar()
    b.campo.delete("1.0", "end")
    b._ao_editar()
    assert b._indicador_aceso is False


def test_indicador_nao_e_amarelo(tela):
    """Amarelo significa "gerado por IA" (docs/inventario-ia.md). Este campo é o oposto: é o
    que a PESSOA escreveu. Marcá-lo de amarelo diria a ela que uma máquina redigiu o
    enquadramento da própria pesquisa dela."""
    from ui.design_tokens import BLUE, YELLOW

    ctk, root = tela
    b = _barra(ctk, root, valor="algo")
    assert b.indicador.cget("fg_color") == BLUE
    assert b.indicador.cget("fg_color") != YELLOW


def test_fonte_da_barra_nao_menciona_amarelo():
    """Guarda na fonte: o teste acima só olha o indicador aceso."""
    codigo = "\n".join(l.split("#", 1)[0] for l in FONTE_BARRA.read_text(encoding="utf-8").splitlines())
    assert not re.search(r"\bYELLOW\b|#F5BE00", codigo, re.I)


def test_contador_so_aparece_perto_do_teto(tela):
    """Cortar em silêncio seria pior do que avisar: o usuário digitou e não veria sumir."""
    from core.research_context import LIMITE_CONTEXTO

    ctk, root = tela
    b = _barra(ctk, root, valor="curto")
    assert b.contador.cget("text") == ""
    b.definir("x" * (LIMITE_CONTEXTO - 10))
    b._atualizar_indicador()
    assert b.contador.cget("text") == f"{LIMITE_CONTEXTO - 10}/{LIMITE_CONTEXTO}"


# ── Paridade i18n a partir da FONTE REAL do widget ────────────────────────────────

def _chaves_i18n(caminho: Path) -> set[str]:
    """Toda chave passada a `t(...)` como literal no módulo, extraída por AST.

    Lista fixa de chaves envelhece em silêncio: quem acrescenta um `t("ai.novo")` no widget
    não lembra de acrescentá-lo ao teste, e a chave só falta na tela do usuário francês.
    Lendo a fonte, a chave nova entra no teste sozinha.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    chaves = set()
    for n in ast.walk(arvore):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "t"
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            chaves.add(n.args[0].value)
    return chaves


def test_a_fonte_do_widget_realmente_usa_i18n():
    """Guarda do guarda: se o widget passar a usar literais, o extrator devolveria vazio e a
    paridade passaria a verde sem verificar nada."""
    chaves = _chaves_i18n(FONTE_BARRA)
    assert len(chaves) >= 4, f"poucas chaves extraídas ({chaves}) — o widget usa literais?"
    assert "ai.contexto_placeholder" in chaves


@pytest.mark.parametrize("lang", IDIOMAS)
def test_paridade_i18n_das_chaves_do_widget(lang):
    cat = json.loads((RAIZ / f"locales/{lang}.json").read_text(encoding="utf-8"))
    faltando = sorted(k for k in _chaves_i18n(FONTE_BARRA) if k not in cat)
    assert not faltando, f"{lang}: faltam {faltando}"
    vazias = sorted(k for k in _chaves_i18n(FONTE_BARRA) if not str(cat[k]).strip())
    assert not vazias, f"{lang}: vazias {vazias}"


def test_exemplo_e_concreto_nos_tres_idiomas():
    """"Descreva sua pesquisa" não ensina nada. O exemplo tem que mostrar um termo sendo
    desambiguado, que é o que vale a pena escrever ali."""
    for lang in IDIOMAS:
        cat = json.loads((RAIZ / f"locales/{lang}.json").read_text(encoding="utf-8"))
        exemplo = cat["ai.contexto_placeholder"]
        assert len(exemplo) > 100, f"{lang}: exemplo curto demais para ensinar"
        assert exemplo.lower().startswith(("ex.", "ex ", "e.g")), f"{lang}: não se anuncia como exemplo"


def test_textos_da_barra_sao_traduzidos_de_fato():
    """Três catálogos com o mesmo texto é catálogo copiado, não traduzido."""
    for chave in ("ai.contexto_titulo", "ai.contexto_placeholder", "ai.contexto_ativo",
                  "ai.contexto_ajuda", "ai.contexto_prompt"):
        vals = []
        for lang in IDIOMAS:
            cat = json.loads((RAIZ / f"locales/{lang}.json").read_text(encoding="utf-8"))
            vals.append(cat[chave])
        assert len(set(vals)) == 3, f"{chave}: textos repetidos entre idiomas — {vals}"


# ── Medição dos dois eixos, nos três idiomas ──────────────────────────────────────

@pytest.mark.parametrize("lang", IDIOMAS)
def test_medicao_dos_dois_eixos_e_origem(lang):
    """Largura e altura pedidas pelos widgets reais, e a origem do campo.

    O francês é o idioma mais largo do projeto e é onde o estouro aparece primeiro.
    """
    ctk = _ctk()
    i18n.load_locales(lang)
    root = _root(ctk)
    try:
        b = _barra(ctk, root, valor="contexto para acender o indicador")
        root.update_idletasks()

        cabecalho = b.rotulo.master
        # Janela ainda não desenhada mede 1 px (Tk 8.6 no Linux) ou 0 (macOS): nos dois
        # casos vale a largura de projeto da barra.
        largura_disponivel = cabecalho.winfo_width()
        if largura_disponivel <= 1:
            largura_disponivel = 860
        pedido = (b.rotulo.winfo_reqwidth() + b.indicador.winfo_reqwidth()
                  + b.contador.winfo_reqwidth() + 8)
        assert pedido <= largura_disponivel, (
            f"{lang}: cabeçalho pede {pedido}px em {largura_disponivel}px disponíveis")

        # Eixo vertical: a ajuda quebra em `wraplength` e não pode crescer sem limite.
        assert b.campo.winfo_reqheight() >= 40, f"{lang}: campo raso demais"
        assert b.ajuda.winfo_reqheight() <= 60, (
            f"{lang}: ajuda com {b.ajuda.winfo_reqheight()}px — mais de duas linhas")

        # Origem: o campo começa na mesma coluna do rótulo, em qualquer idioma.
        assert b.campo.winfo_x() == b.rotulo.master.winfo_x(), (
            f"{lang}: campo desalinhado do cabeçalho")
    finally:
        root.destroy()
        i18n.load_locales("pt_BR")

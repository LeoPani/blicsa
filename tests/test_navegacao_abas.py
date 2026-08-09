"""`_switch_tab` só pode receber chave de aba que existe.

O modo de falha é silencioso e total: `_switch_tab` esconde **todas** as abas e só então
tenta mostrar a pedida. Chave inexistente = tela em branco, sem exceção, sem log, sem nada
para o usuário clicar além da navegação lateral.

Existiam duas chamadas com `"viz"`, que nunca foi chave de aba — uma depois de carregar um
arquivo e outra depois de abrir um projeto. Os dois são momentos em que o usuário acabou de
fazer a coisa mais importante da sessão e a recompensa era uma tela vazia.

Achado ao gerar a captura `ia_marcacao_clusters`: o script pedia `"viz"` (copiado do
`capture_evidence.py`, que carrega o mesmo mapeamento errado) e a evidência saiu em branco.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).parent.parent
FONTE = RAIZ / "main.py"


def _chaves_registradas() -> set[str]:
    """As chaves do dicionário `self._tabs`, lidas da fonte (sem instanciar a UI)."""
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    for n in ast.walk(arvore):
        if not (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Attribute)
                and n.target.attr == "_tabs" and isinstance(n.value, ast.Dict)):
            continue
        return {k.value for k in n.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    raise AssertionError("não achei o dicionário `self._tabs` em main.py")


def _chaves_pedidas() -> set[str]:
    """Toda chave literal passada a `_switch_tab(...)`."""
    fonte = FONTE.read_text(encoding="utf-8")
    pedidas = set()
    for n in ast.walk(ast.parse(fonte)):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_switch_tab" and n.args
                and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            pedidas.add(n.args[0].value)
    return pedidas


def test_registro_de_abas_foi_encontrado():
    """Guarda do guarda: se a estrutura do `main.py` mudar e o extrator devolver vazio, o
    teste principal passaria a verde sem comparar nada."""
    registradas = _chaves_registradas()
    assert len(registradas) >= 8, f"poucas abas extraídas: {registradas}"
    assert {"home", "corpus", "analises"} <= registradas


def test_switch_tab_so_usa_abas_que_existem():
    fantasmas = sorted(_chaves_pedidas() - _chaves_registradas())
    assert not fantasmas, (
        f"_switch_tab chamado com chave inexistente: {fantasmas}. "
        "Ele esconde todas as abas antes de mostrar a pedida — o usuário fica com a tela "
        "em branco, sem erro nenhum.")


def test_viz_nao_voltou():
    """A chave específica que causou o defeito, nomeada para que a regressão seja óbvia
    na saída do teste."""
    assert "viz" not in _chaves_pedidas()


# ── Item 13 da Auditoria 1: nenhuma tela órfã, nenhum botão sem destino ──────────

def _botoes_da_sidebar() -> set[str]:
    """Chaves da lista literal que monta os botões de navegação em `_build_sidebar`."""
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    for n in ast.walk(arvore):
        if not (isinstance(n, ast.List) and n.elts
                and all(isinstance(e, ast.Tuple) and len(e.elts) == 3 for e in n.elts)):
            continue
        chaves = {e.elts[0].value for e in n.elts if isinstance(e.elts[0], ast.Constant)}
        if {"home", "export"} <= chaves:
            return chaves
    raise AssertionError("não achei a lista de botões da sidebar em main.py")


def test_a_extracao_da_sidebar_encontrou_os_botoes():
    """Guarda do guarda: extrator vazio faria os testes abaixo passarem sem comparar nada."""
    botoes = _botoes_da_sidebar()
    assert len(botoes) >= 8, f"poucos botões extraídos: {botoes}"


def test_nenhuma_aba_e_orfa():
    """Aba registrada que nem tem botão nem é destino de `_switch_tab` é tela construída,
    montada na memória e inalcançável — o caso da 'Meus Projetos' antes de `75fdb33`."""
    orfas = sorted(_chaves_registradas() - _botoes_da_sidebar() - _chaves_pedidas())
    assert not orfas, f"abas sem nenhum caminho até elas: {orfas}"


def test_todo_botao_da_sidebar_tem_aba():
    """O inverso: botão apontando para chave inexistente esconde todas as abas e deixa a
    tela em branco, que é o mesmo modo de falha do `_switch_tab('viz')`."""
    sem_destino = sorted(_botoes_da_sidebar() - _chaves_registradas())
    assert not sem_destino, f"botão da sidebar sem aba correspondente: {sem_destino}"


def test_review_e_alcancavel_por_codigo():
    """`review` não tem botão de propósito — é tela de fluxo, entra depois da busca. O que
    ela não pode é deixar de ter *qualquer* caminho."""
    assert "review" in _chaves_registradas()
    assert "review" in _chaves_pedidas(), "a tela de revisão ficou sem caminho até ela"

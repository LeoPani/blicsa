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

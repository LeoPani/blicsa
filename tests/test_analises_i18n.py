"""As análises respondem no idioma da interface — não sempre em português.

Cinco prompts de `ai/client.py` pediam *"linguagem técnica acadêmica em português"* em texto
fixo. O idioma da resposta ficava preso ao texto do prompt, e quem usasse o app em inglês ou
francês recebia o mapa temático, o Sankey, a historiografia, as obras seminais e os insights
do corpus **em português** — com a interface inteira ao redor no idioma certo.

O que estes testes guardam é o caminho real: `AIAnalyst` de verdade, com o transporte HTTP
substituído, para inspecionar o `system_prompt` que **iria** ao modelo. Não há reimplementação
da montagem do prompt aqui — um teste que reconstrói a lógica passa a verde mesmo quando a
função real diverge, que é exatamente como `tests/test_blink_i18n.py` guardava o chat sem
guardar coisa alguma.
"""

import ast
import pathlib
import re

import pytest

from core import i18n
from core.research_context import NOMES_IDIOMA

RAIZ = pathlib.Path(__file__).resolve().parent.parent

IDIOMAS = ("pt_BR", "en", "fr")

#: Cada análise com argumentos plausíveis. A cobertura anunciada — "as cinco funções nos três
#: idiomas" — só é verdade se esta lista estiver completa, e é
#: `test_a_lista_cobre_todas_as_analises_do_client` que a mantém assim.
ANALISES = {
    "generate_insights": lambda a: a.generate_insights([("resíduos", 12)], {"docs": 40}),
    "generate_sankey_insights": lambda a: a.generate_sankey_insights("fluxo A -> B"),
    "generate_thematic_insights": lambda a: a.generate_thematic_insights("quadrante 1"),
    "generate_historiograph_insights": lambda a: a.generate_historiograph_insights("A cita B"),
    "generate_seminal_insights": lambda a: a.generate_seminal_insights("Freire 1968"),
    # Não é uma das cinco do pedido, mas passa pelo mesmo `_chat` e pedia rótulo "em
    # português" no prompt. Sem corrigi-la, a diretiva do `system` mandaria responder em
    # francês enquanto o `user` mandava rotular em português — contradição pior do que o bug.
    "label_clusters": lambda a: a.label_clusters([{"cluster_id": 0, "top_nodes": ["x"]}]),
}


@pytest.fixture
def espiao(monkeypatch):
    """Analista real, transporte falso: devolve `(analista, visto)` com o que foi enviado."""
    from ai import client as mod

    visto = {}

    def _falso(base_url, api_key, model, system_prompt, user_prompt,
               temperature=0.3, timeout=30):
        visto["system"] = system_prompt
        visto["user"] = user_prompt
        return "0: Rótulo"

    monkeypatch.setattr(mod, "call_openai_chat", _falso)
    return mod.AIAnalyst(api_key="k"), visto


@pytest.fixture(autouse=True)
def restaura_idioma():
    """Cada teste troca o idioma do processo; sem isto o vizinho herda o último."""
    anterior = i18n.get_lang()
    yield
    # `load_locales` e não `set_lang`: o segundo persiste em settings e sujaria a
    # configuração real do usuário que roda a suíte.
    i18n.load_locales(anterior)


# ── O pedido: as cinco funções, nos três idiomas ──────────────────────────────────

@pytest.mark.parametrize("idioma", IDIOMAS)
@pytest.mark.parametrize("nome", sorted(ANALISES))
def test_analise_pede_resposta_no_idioma_da_interface(nome, idioma, espiao):
    analista, visto = espiao
    i18n.load_locales(idioma)

    ANALISES[nome](analista)

    esperado = NOMES_IDIOMA[idioma]
    assert f"respond to the user in {esperado}" in visto["system"], (
        f"{nome} em {idioma}: o system prompt não pede resposta em {esperado}")

    # Pedir o idioma certo não basta: pedir também os outros dois deixaria o modelo escolher.
    for outro in set(NOMES_IDIOMA.values()) - {esperado}:
        assert f"respond to the user in {outro}" not in visto["system"], (
            f"{nome} em {idioma}: o prompt também pede {outro}")


@pytest.mark.parametrize("idioma", IDIOMAS)
@pytest.mark.parametrize("nome", sorted(ANALISES))
def test_nenhuma_analise_manda_responder_em_portugues(nome, idioma, espiao):
    """O defeito original, afirmado pelo que o modelo recebe — não pela ausência de uma
    string no arquivo. Vale para `system` e `user`: a cláusula vivia no prompt do usuário."""
    analista, visto = espiao
    i18n.load_locales(idioma)

    ANALISES[nome](analista)

    inteiro = visto["system"] + "\n" + visto["user"]
    fixacoes = re.findall(r"\bem (?:portugu[êe]s|ingl[êe]s|franc[êe]s)\b", inteiro, re.I)
    assert not fixacoes, f"{nome} em {idioma}: prompt ainda fixa idioma → {fixacoes}"


def test_a_diretiva_muda_de_fato_entre_os_tres_idiomas(espiao):
    """Guarda contra o teste acima passar por acidente: se a diretiva fosse constante, as
    três asserções de ausência ainda poderiam passar num idioma e falhar sem ninguém ver."""
    analista, visto = espiao
    vistas = set()
    for idioma in IDIOMAS:
        i18n.load_locales(idioma)
        analista.generate_thematic_insights("quadrante 1")
        vistas.add(visto["system"])
    assert len(vistas) == 3, "o system prompt não distingue os três idiomas"


# ── Guardas estruturais ───────────────────────────────────────────────────────────

def _fonte_client() -> str:
    return (RAIZ / "ai/client.py").read_text(encoding="utf-8")


def _analises_declaradas() -> set[str]:
    classe = next(n for n in ast.parse(_fonte_client()).body
                  if isinstance(n, ast.ClassDef) and n.name == "AIAnalyst")
    return {n.name for n in classe.body
            if isinstance(n, ast.FunctionDef)
            and (n.name.startswith("generate_") or n.name == "label_clusters")}


def test_a_lista_cobre_todas_as_analises_do_client():
    """Uma análise nova nasceria fora de `ANALISES`, e a parametrização acima continuaria
    verde cobrindo menos do que este arquivo anuncia."""
    declaradas = _analises_declaradas()
    assert declaradas == set(ANALISES), (
        f"fora da lista: {sorted(declaradas ^ set(ANALISES))}")


def test_nenhum_literal_de_prompt_fixa_idioma():
    """Varredura por AST das strings dos métodos de análise, ignorando docstrings.

    O teste de comportamento acima só vê o prompt de uma chamada por vez; este pega a
    cláusula de volta mesmo que ela reapareça num ramo condicional que nenhum caso exercita.
    """
    fonte = _fonte_client()
    classe = next(n for n in ast.parse(fonte).body
                  if isinstance(n, ast.ClassDef) and n.name == "AIAnalyst")

    padrao = re.compile(r"\bem (?:portugu[êe]s|ingl[êe]s|franc[êe]s)\b", re.I)
    achados = []
    for metodo in [n for n in classe.body if isinstance(n, ast.FunctionDef)]:
        corpo = metodo.body[1:] if ast.get_docstring(metodo) else metodo.body
        for no in ast.walk(ast.Module(body=corpo, type_ignores=[])):
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                if padrao.search(no.value):
                    achados.append(f"{metodo.name}: {no.value[:60]!r}")
    assert not achados, "prompt com idioma fixo:\n" + "\n".join(achados)


def test_o_idioma_vem_da_funcao_compartilhada_e_nao_de_uma_copia():
    """`diretiva_idioma` é a mesma função do chat do Blink. Uma segunda redação equivalente
    aqui divergiria em silêncio — e o sintoma seria o chat numa língua e o mapa temático
    noutra, na mesma janela."""
    fonte = _fonte_client()
    metodo = next(n for n in ast.walk(ast.parse(fonte))
                  if isinstance(n, ast.FunctionDef) and n.name == "_system_com_contexto")
    chamadas = {n.func.id for n in ast.walk(metodo)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "diretiva_idioma" in chamadas, (
        "_system_com_contexto não chama diretiva_idioma — o idioma virou cópia local")


def test_estilo_das_analises_nao_carrega_idioma():
    """As constantes de registro são o lugar de onde a cláusula foi tirada; se voltarem a
    carregá-la, todos os cinco prompts regridem de uma vez."""
    from ai import client

    for nome in ("ESTILO_ANALISE", "ESTILO_ANALISE_SEMINAL"):
        texto = getattr(client, nome)
        assert not re.search(r"\bem (?:portugu[êe]s|ingl[êe]s|franc[êe]s)\b", texto, re.I), (
            f"{nome} voltou a fixar idioma: {texto!r}")


def test_papel_e_idioma_precedem_o_contexto_do_usuario(monkeypatch):
    """A ordem canônica de `core/research_context.py` vale também para estas análises: a
    diretiva é lente, não observação final — tem de vir antes do que o usuário escreveu."""
    from ai import client as mod

    visto = {}
    monkeypatch.setattr(mod, "call_openai_chat",
                        lambda **kw: (visto.update(system=kw["system_prompt"]), "0: X")[1])
    i18n.load_locales("fr")

    marca = "estudo cooperativas de catadores"
    mod.AIAnalyst(api_key="k", contexto_pesquisa=marca).generate_sankey_insights("A -> B")

    system = visto["system"]
    assert system.index("respond to the user in French") < system.index(marca)

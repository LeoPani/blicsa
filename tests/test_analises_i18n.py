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


def _chaves_de_catalogo_no_client() -> set[str]:
    """Toda literal com forma de chave `ai.*` em `ai/client.py`.

    Por **forma**, não por ponto de chamada: as chaves chegam ao catálogo por dois caminhos
    (`_t("ai.obj_…")` direto e tuplas dentro de `_secoes(...)`), e uma extração amarrada a um
    deles deixa o outro sem paridade — foi o que aconteceu.
    """
    chaves = {n.value for n in ast.walk(ast.parse(_fonte_client()))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and re.fullmatch(r"ai\.[a-z0-9_]+", n.value)}
    assert chaves, "nenhuma chave `ai.*` extraída de ai/client.py"
    return chaves


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


# ── Não basta pedir o idioma: o prompt não pode arrastar o modelo ────────────────
#
# A suíte anterior parou aqui, e a chamada real reprovou 7 das 18 análises. O que faltava
# não era diretiva — era o resto do prompt. Cada teste abaixo nasceu de um resultado medido,
# e o registro está em docs/RELATORIO-IA-UX.md.

#: Título de seção de cada análise, por chave de catálogo. Título de seção é **conteúdo**:
#: o modelo o copia para a resposta, e em português ele encabeçava relatórios em francês.
SECOES = {
    "generate_sankey_insights": ("ai.sec_fluxo", "ai.sec_atores"),
    "generate_thematic_insights": ("ai.sec_quadrantes", "ai.sec_motores", "ai.sec_emergentes"),
    "generate_historiograph_insights": ("ai.sec_evolucao", "ai.sec_marcos"),
    "generate_seminal_insights": ("ai.sec_seminais",),
}


@pytest.mark.parametrize("idioma", IDIOMAS)
@pytest.mark.parametrize("nome", sorted(SECOES))
def test_titulos_de_secao_vao_no_idioma_da_interface(nome, idioma, espiao):
    analista, visto = espiao
    i18n.load_locales(idioma)

    ANALISES[nome](analista)

    for chave in SECOES[nome]:
        esperado = i18n.t(chave)
        assert f"## {esperado}" in visto["user"], (
            f"{nome} em {idioma}: seção '{chave}' não saiu como '{esperado}'")


@pytest.mark.parametrize("idioma", ["en", "fr"])
@pytest.mark.parametrize("nome", sorted(SECOES))
def test_secao_em_portugues_nao_sobra_fora_do_pt_BR(nome, idioma, espiao):
    """O título pt_BR no prompt de um usuário francês era o defeito de verdade: mesmo quando
    o corpo saía em francês, o relatório vinha encabeçado por 'Frentes de Pesquisa
    Emergentes'. Medido em chamada real antes de existir este teste."""
    analista, visto = espiao
    i18n.load_locales(idioma)

    ANALISES[nome](analista)

    i18n.load_locales("pt_BR")
    for chave in SECOES[nome]:
        titulo_pt = i18n.t(chave)
        assert f"## {titulo_pt}" not in visto["user"], (
            f"{nome} em {idioma}: seção ainda em português ('{titulo_pt}')")


#: Nomes das análises que o modelo copiava do corpo do prompt. Medido: "Mapa Temático"
#: aparecia em 3 de 3 respostas em inglês antes destes irem para o catálogo.
TERMOS_QUE_VAZAVAM = {
    "generate_thematic_insights": "ai.obj_tematico",
    "generate_sankey_insights": "ai.obj_sankey",
    "generate_historiograph_insights": "ai.obj_historiografia",
}


@pytest.mark.parametrize("idioma", ["en", "fr"])
@pytest.mark.parametrize("nome", sorted(TERMOS_QUE_VAZAVAM))
def test_nome_da_analise_nao_chega_em_portugues(nome, idioma, espiao):
    analista, visto = espiao
    i18n.load_locales(idioma)

    ANALISES[nome](analista)
    traduzido = i18n.t(TERMOS_QUE_VAZAVAM[nome])

    i18n.load_locales("pt_BR")
    em_portugues = i18n.t(TERMOS_QUE_VAZAVAM[nome])

    assert traduzido in visto["user"], f"{nome} em {idioma}: nome da análise não traduzido"
    assert em_portugues not in visto["user"], (
        f"{nome} em {idioma}: '{em_portugues}' ainda vai ao modelo e volta na resposta")


@pytest.mark.parametrize("idioma", IDIOMAS)
@pytest.mark.parametrize("nome", sorted(ANALISES))
def test_lembrete_de_idioma_encerra_o_turno_do_usuario(nome, idioma, espiao):
    """A diretiva no `system` sozinha perdia para o corpo do prompt — 7 das 18 análises
    saíam em português. O prompt é longo e vem depois dela; a última instrução do turno é a
    que o modelo honra. Este teste guarda a **posição**, que é o que a medição mostrou
    importar, não a mera presença."""
    from core.research_context import diretiva_idioma

    analista, visto = espiao
    i18n.load_locales(idioma)

    ANALISES[nome](analista)

    assert visto["user"].rstrip().endswith(diretiva_idioma(idioma)), (
        f"{nome} em {idioma}: o turno do usuário não termina com a diretiva de idioma")


def test_o_lembrete_do_usuario_e_a_mesma_funcao_do_system():
    """Se o lembrete fosse redigido à parte, ele e o `system` divergiriam — e o prompt
    passaria a pedir duas coisas parecidas mas não idênticas, que é como se produz um modelo
    hesitante entre dois idiomas."""
    fonte = _fonte_client()
    metodo = next(n for n in ast.walk(ast.parse(fonte))
                  if isinstance(n, ast.FunctionDef) and n.name == "_com_lembrete_de_idioma")
    chamadas = {n.func.id for n in ast.walk(metodo)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "diretiva_idioma" in chamadas


def test_toda_chave_de_catalogo_usada_no_client_existe_nos_tres():
    """Paridade extraída da **fonte real**, não de lista fixa: quem acrescentar um
    `_t("ai.sec_nova", …)` e esquecer os catálogos veria a chave crua virar título de seção
    no relatório do usuário francês — `_t` cai para o português, que é o menos ruim, mas o
    lugar de descobrir isso é aqui."""
    import json

    chaves = _chaves_de_catalogo_no_client()

    for lang in IDIOMAS:
        cat = json.loads((RAIZ / f"locales/{lang}.json").read_text(encoding="utf-8"))
        faltando = sorted(chaves - set(cat))
        assert not faltando, f"{lang} sem: {faltando}"


def test_a_extracao_de_chaves_realmente_ve_as_secoes():
    """Guarda do guarda, e não é hipotética: a primeira versão desta extração procurava
    `ast.Call` de `_t(...)` e **não via** as chaves `ai.sec_*`, que chegam ao catálogo como
    tuplas dentro de `_secoes(...)`. O teste de paridade passava a verde sobre um terço das
    chaves. Quem encontrou foi `scripts/reinject_ia_ux.py`, apagando `ai.sec_quadrantes` do
    catálogo francês e vendo o teste continuar verde."""
    vistas = _chaves_de_catalogo_no_client()
    esperadas = {c for grupo in SECOES.values() for c in grupo} | set(TERMOS_QUE_VAZAVAM.values())
    assert esperadas <= vistas, f"a extração não enxerga: {sorted(esperadas - vistas)}"


def test_secoes_sao_traduzidas_de_fato_e_nao_copiadas():
    """Catálogo com a seção copiada do português passaria em tudo acima e entregaria
    português ao usuário francês."""
    import json

    cats = {lang: json.loads((RAIZ / f"locales/{lang}.json").read_text(encoding="utf-8"))
            for lang in IDIOMAS}
    iguais = [chave for grupo in SECOES.values() for chave in grupo
              if len({cats[lang][chave] for lang in IDIOMAS}) < 3]
    assert not iguais, f"seções idênticas em dois ou mais catálogos: {iguais}"


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

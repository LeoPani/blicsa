"""Contexto de pesquisa do projeto: ordem fixa no prompt e corte que preserva o que importa.

Dois invariantes sustentam a fase inteira, e os dois só são visíveis em teste — quem usa o app
vê uma resposta plausível tanto faz se o contexto entrou ou não:

1. **a ordem** — papel → idioma → contexto do usuário → dados do corpus. Contexto depois dos
   dados lê como rodapé; antes, é a lente.
2. **quem é sacrificado** — quando não cabe, cortam-se abstracts. O contexto do usuário só cede
   depois que o corpus inteiro já foi descartado, e papel/idioma não cedem nunca.

As fixtures são adversariais de propósito: o caminho feliz (contexto curto, corpus pequeno,
orçamento folgado) nunca exercita o corte, que é justamente onde a decisão mora.
"""

import json
import zipfile
from pathlib import Path

import pytest

from core.research_context import (CABECALHO_CONTEXTO_PADRAO, CABECALHO_CORPUS_PADRAO,
                                   LIMITE_CONTEXTO, MARCA_CORTE, MINIMO_CORPUS,
                                   ORCAMENTO_PADRAO, PromptMontado, bloco_corpus, esta_ativo,
                                   montar, montar_system_prompt, normalizar)

RAIZ = Path(__file__).parent.parent

PAPEL = "Você é o 'Blink', um assistente de pesquisa bibliométrica."
IDIOMA = "IMPORTANT: Always respond to the user in Brazilian Portuguese."
CONTEXTO = ("Estudo cooperativas de catadores de recicláveis no Sul do Brasil. "
            "'Informalidade' aqui é categoria da sociologia do trabalho, não do direito "
            "tributário. A revisão é para o capítulo 2 de uma tese de doutorado.")


def registros_corpus(n: int = 60) -> list[str]:
    """Registros individuais — expostos para que o teste de fronteira compare com a origem."""
    return [
        f"Title: Artigo {i} sobre gestão de resíduos sólidos urbanos\n"
        f"Abstract: {'texto do abstract ' * 12}({i})"
        for i in range(n)
    ]


def corpus_grande(n: int = 60) -> str:
    """Corpus realista: registros com título e abstract, do tamanho que a busca produz."""
    return bloco_corpus(registros_corpus(n))


# ── Normalização: o campo aceita o que vier de um .blicsa velho ───────────────────

@pytest.mark.parametrize("entrada,esperado", [
    (None, ""),
    ("", ""),
    ("   \n\t  ", ""),
    ("  texto  ", "texto"),
    ("linha 1\r\nlinha 2", "linha 1\nlinha 2"),
    ("linha 1\rlinha 2", "linha 1\nlinha 2"),
    (123, "123"),
    (True, ""),
])
def test_normalizar_tolera_lixo_de_projeto_antigo(entrada, esperado):
    """`config.json` é dicionário livre gravado por versões diferentes do app. Um
    `AttributeError` aqui derrubaria a abertura do projeto inteiro por causa de um campo
    de texto opcional."""
    assert normalizar(entrada) == esperado


def test_normalizar_preserva_paragrafos_do_usuario():
    """Quebra interna é estrutura que a pessoa escreveu — só o espaço em volta some."""
    assert normalizar("  um\n\ndois  ") == "um\n\ndois"


def test_campo_tem_teto_editorial():
    """Acima do teto o 'contexto' virou introdução de artigo: dilui o que importa e come o
    orçamento dos abstracts, que é o que esta fase promete preservar."""
    assert normalizar("x" * 5000) == "x" * LIMITE_CONTEXTO


@pytest.mark.parametrize("valor", [None, "", "   ", "\n\n", "\t"])
def test_indicador_nao_acende_com_campo_vazio(valor):
    """Acender prometeria um enquadramento que não está sendo enviado a lugar nenhum."""
    assert esta_ativo(valor) is False


def test_indicador_acende_com_contexto_real():
    assert esta_ativo(CONTEXTO) is True


# ── A ordem é a decisão ───────────────────────────────────────────────────────────

def test_ordem_papel_idioma_contexto_corpus():
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(3))
    assert p.secoes == ("papel", "idioma", "contexto", "corpus")
    posicoes = [p.texto.index(x) for x in
                (PAPEL, IDIOMA, CABECALHO_CONTEXTO_PADRAO, CABECALHO_CORPUS_PADRAO)]
    assert posicoes == sorted(posicoes), "as seções saíram fora de ordem"


def test_contexto_do_usuario_vem_antes_dos_dados_do_corpus():
    """O invariante que justifica a fase: posto depois dos dados, o contexto lê como
    observação final sobre material já apresentado; antes, é a lente que enquadra a leitura."""
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(3))
    assert p.texto.index(CONTEXTO) < p.texto.index(CABECALHO_CORPUS_PADRAO)


def test_pergunta_nao_entra_no_system_prompt():
    """A pergunta é a mensagem `user`. Misturá-la aqui apagaria a distinção entre instrução
    permanente e turno de conversa — e ela viraria instrução para todos os turnos seguintes."""
    pergunta = "Quais as frentes emergentes deste corpus?"
    assert pergunta not in montar_system_prompt(PAPEL, IDIOMA, CONTEXTO, corpus_grande(3))


# ── Sem seção órfã ────────────────────────────────────────────────────────────────

def test_sem_contexto_nao_sobra_cabecalho_orfao():
    """Adversarial: cabeçalho sem corpo diz ao modelo que existe um contexto vazio, que é
    diferente de não existir contexto."""
    p = montar(PAPEL, IDIOMA, "", corpus_grande(2))
    assert CABECALHO_CONTEXTO_PADRAO not in p.texto
    assert p.contexto_incluido is False
    assert p.secoes == ("papel", "idioma", "corpus")


def test_sem_corpus_nao_sobra_cabecalho_orfao():
    p = montar(PAPEL, IDIOMA, CONTEXTO, "")
    assert CABECALHO_CORPUS_PADRAO not in p.texto
    assert p.corpus_incluido is False
    assert p.secoes == ("papel", "idioma", "contexto")


def test_prompt_minimo_e_so_papel_e_idioma():
    p = montar(PAPEL, IDIOMA)
    assert p.texto == f"{PAPEL}\n\n{IDIOMA}"
    assert p.secoes == ("papel", "idioma")


# ── Corte de orçamento: quem cede, e nessa ordem ──────────────────────────────────

def test_orcamento_e_respeitado_com_corpus_gigante():
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(200))
    assert len(p) <= ORCAMENTO_PADRAO, f"estourou: {len(p)} > {ORCAMENTO_PADRAO}"
    assert p.corpus_cortado is True


def test_corte_sacrifica_abstracts_e_preserva_o_contexto_do_usuario():
    """O invariante central. Corpus 50x maior que o orçamento; o contexto sai inteiro."""
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(500))
    assert CONTEXTO in p.texto, "o contexto do usuário foi cortado antes dos abstracts"
    assert p.contexto_cortado is False
    assert p.corpus_cortado is True
    assert len(p) <= ORCAMENTO_PADRAO


def test_corte_nao_parte_registro_ao_meio():
    """Meio abstract não é meia evidência: é uma frase solta que o modelo cita como se fosse
    o achado do artigo.

    A afirmação é de IGUALDADE com o prefixo da origem, não de formato. Conferir só que cada
    pedaço "começa com Title: e contém Abstract:" deixava passar um corte no meio da última
    frase — o pedaço truncado satisfaz as duas condições. Foi assim que este teste passou
    verde com o defeito reinjetado, na primeira rodada.
    """
    registros = registros_corpus(200)
    p = montar(PAPEL, IDIOMA, CONTEXTO, bloco_corpus(registros))
    corpo = p.texto.split(CABECALHO_CORPUS_PADRAO + "\n", 1)[1]
    assert corpo.endswith(MARCA_CORTE), "o corte não sinalizou que houve truncamento"
    corpo = corpo[: -len(MARCA_CORTE)]

    quantos = len(corpo.split("\n\n---\n"))
    assert 0 < quantos < len(registros), "fixture não exercita o corte"
    assert corpo == bloco_corpus(registros[:quantos]), (
        "o que sobrou não é um número inteiro de registros — o corte caiu no meio de um")


def test_titulo_sem_abstract_nao_entra_como_se_fosse_evidencia():
    """Adversarial: orçamento que comporta o título do primeiro registro mas não o abstract.

    A fronteira mais fraca (`\\n`) encontra o fim do título e devolveria um registro de 56
    caracteres — um título solto que o modelo lê como achado do conjunto. É exatamente o caso
    que `MINIMO_CORPUS` existe para barrar, e o teste anterior não o alcançava: com orçamento
    ainda menor, nem o título cabia e o bloco caía por outro caminho.
    """
    registros = registros_corpus(50)
    base = montar(PAPEL, IDIOMA, CONTEXTO, "")
    orcamento = len(base) + 2 + len(CABECALHO_CORPUS_PADRAO) + 1 + 120

    p = montar(PAPEL, IDIOMA, CONTEXTO, bloco_corpus(registros), orcamento=orcamento)
    assert p.corpus_incluido is False, "um título sem abstract entrou como se fosse evidência"
    assert p.corpus_descartado is True
    assert CONTEXTO in p.texto


def test_orcamento_apertado_descarta_o_corpus_inteiro_e_mantem_o_contexto():
    """Adversarial: sobra espaço para um toco de abstract, e um toco é pior que nada."""
    orcamento = len(PAPEL) + len(IDIOMA) + len(CONTEXTO) + len(CABECALHO_CONTEXTO_PADRAO) + 60
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(50), orcamento=orcamento)
    assert p.corpus_incluido is False
    assert p.corpus_descartado is True
    assert CONTEXTO in p.texto
    assert CABECALHO_CORPUS_PADRAO not in p.texto


def test_corpus_de_registro_unico_gigante_e_descartado_nao_picotado():
    """Adversarial: um registro só, maior que o orçamento. Não há fronteira onde cortar, e
    cortar no meio da palavra devolveria uma frase truncada como se fosse o achado."""
    p = montar(PAPEL, IDIOMA, CONTEXTO, "Title: X\nAbstract: " + ("y" * 9000))
    assert p.corpus_incluido is False
    assert p.corpus_descartado is True
    assert len(p) <= ORCAMENTO_PADRAO


def test_contexto_so_cede_depois_que_o_corpus_ja_foi_descartado():
    """A ordem de sacrifício, afirmada explicitamente: corpus primeiro, contexto depois."""
    orcamento = len(PAPEL) + len(IDIOMA) + 120
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(50), orcamento=orcamento)
    assert p.corpus_descartado is True
    assert p.contexto_cortado is True
    assert p.contexto_incluido is True
    assert p.texto.rstrip().endswith(MARCA_CORTE)
    assert len(p) <= orcamento


def test_papel_e_idioma_nunca_sao_cortados():
    """Sem papel o assistente deixa de ser o Blink; sem a diretiva ele responde no idioma do
    prompt em vez do idioma da interface — bug visível e imediato para quem usa em francês."""
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(50), orcamento=10)
    assert PAPEL in p.texto and IDIOMA in p.texto
    assert p.secoes[:2] == ("papel", "idioma")


def test_orcamento_menor_que_papel_mais_idioma_devolve_os_dois_inteiros():
    """Adversarial: devolver um papel mutilado para respeitar um número trocaria um problema
    mensurável por um invisível."""
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(5), orcamento=1)
    assert p.texto == f"{PAPEL}\n\n{IDIOMA}"
    assert p.contexto_incluido is False and p.corpus_incluido is False


def test_corpus_que_cabe_inteiro_nao_ganha_marca_de_corte():
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(2))
    assert p.corpus_cortado is False
    assert MARCA_CORTE not in p.texto


# ── O bloco de corpus usa separadores REAIS ───────────────────────────────────────

def test_bloco_corpus_usa_quebra_de_linha_de_verdade():
    """Antes desta fase o `main.py` montava o bloco com `\\\\n\\\\n---\\\\n`: barra invertida
    escapada duas vezes, ou seja, o modelo recebia a sequência literal de dois caracteres
    `\\n` no meio do texto, e não havia fronteira nenhuma onde cortar."""
    b = bloco_corpus(["Title: A\nAbstract: a", "Title: B\nAbstract: b"])
    assert "\\n" not in b, "separador literal — o modelo receberia barra invertida como texto"
    assert b == "Title: A\nAbstract: a\n\n---\nTitle: B\nAbstract: b"


def test_bloco_corpus_ignora_registro_vazio():
    assert bloco_corpus(["A", "", "   ", None, "B"]) == "A\n\n---\nB"


def test_main_nao_monta_mais_o_bloco_com_barra_escapada():
    """Guarda de regressão na fonte: o defeito era invisível na tela e só aparecia no que
    chegava ao modelo."""
    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    assert '"\\\\n\\\\n---\\\\n".join' not in fonte, (
        "o bloco de corpus voltou a ser montado com barra invertida escapada")


# ── Persistência retrocompatível no .blicsa ───────────────────────────────────────

def test_contexto_sobrevive_a_ida_e_volta_no_blicsa(tmp_path):
    from core.project import load_blicsa_project, save_blicsa_project

    alvo = tmp_path / "p.blicsa"
    save_blicsa_project(str(alvo), df=None, config={"name": "t", "research_context": CONTEXTO},
                        positions=None, G=None, cluster_labels=None)
    lido = load_blicsa_project(str(alvo))
    assert lido["config"]["research_context"] == CONTEXTO


def test_projeto_salvo_por_versao_anterior_abre_sem_contexto(tmp_path):
    """Retrocompatibilidade: `.blicsa` sem a chave abre, e o indicador fica apagado."""
    from core.project import load_blicsa_project, save_blicsa_project

    alvo = tmp_path / "velho.blicsa"
    save_blicsa_project(str(alvo), df=None, config={"name": "velho"},
                        positions=None, G=None, cluster_labels=None)
    lido = load_blicsa_project(str(alvo))
    assert "research_context" not in lido["config"]
    assert esta_ativo(lido["config"].get("research_context")) is False


def test_fixture_real_de_projeto_antigo_nao_quebra():
    """As fixtures são projetos de verdade, salvos por versões anteriores do app."""
    from core.project import load_blicsa_project

    for nome in ("projeto_schema_1_0.blicsa", "projeto_schema_v3_so_titulo.blicsa"):
        caminho = RAIZ / "tests" / "fixtures" / nome
        cfg = load_blicsa_project(str(caminho))["config"]
        assert esta_ativo(cfg.get("research_context")) is False


def test_leitor_do_config_sempre_devolve_texto():
    """A fronteira entre o arquivo e o app. Devolver um dicionário aqui faria o contexto ser
    interpolado como `{'a': 1}` no prompt do modelo, ou estourar mais adiante, longe da causa."""
    from core.project import research_context_do_config

    assert research_context_do_config(None) == ""
    assert research_context_do_config({}) == ""
    assert research_context_do_config("não é dict") == ""
    assert research_context_do_config({"research_context": None}) == ""
    for valor in ({"a": 1}, 42, ["x"], True):
        assert isinstance(research_context_do_config({"research_context": valor}), str)


def test_contexto_corrompido_no_projeto_nao_derruba_a_abertura(tmp_path):
    """Adversarial: `.blicsa` editado à mão, com o campo em tipo errado."""
    from core.project import load_blicsa_project

    alvo = tmp_path / "corrompido.blicsa"
    with zipfile.ZipFile(alvo, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": "1.0"}))
        zf.writestr("config.json", json.dumps({"name": "x", "research_context": {"a": 1}}))
    cfg = load_blicsa_project(str(alvo))["config"]
    # Não levanta, e não vira contexto de mentira.
    montar(PAPEL, IDIOMA, cfg.get("research_context"))
    assert normalizar(cfg.get("research_context")) == "{'a': 1}"


# ── As análises das OUTRAS telas recebem o contexto ───────────────────────────────

#: Cada análise com argumentos plausíveis. Não é lista decorativa: é o que permite afirmar
#: "todas recebem", em vez de "a que eu lembrei de testar recebe".
CHAMADAS = {
    "generate_sankey_insights": lambda a: a.generate_sankey_insights("fluxo A -> B"),
    "generate_thematic_insights": lambda a: a.generate_thematic_insights("quadrante 1"),
    "generate_historiograph_insights": lambda a: a.generate_historiograph_insights("A cita B"),
    "generate_seminal_insights": lambda a: a.generate_seminal_insights("Freire 1968"),
    "label_clusters": lambda a: a.label_clusters([{"cluster_id": 0, "top_nodes": ["x"]}]),
}


@pytest.fixture
def analista_espiao(monkeypatch):
    """Analista real com o transporte HTTP substituído — captura o que iria para o modelo."""
    from ai import client as mod

    visto = {}

    def _falso(base_url, api_key, model, system_prompt, user_prompt,
               temperature=0.3, timeout=30):
        visto["system"] = system_prompt
        visto["user"] = user_prompt
        return "0: Rótulo"

    monkeypatch.setattr(mod, "call_openai_chat", _falso)
    return mod.AIAnalyst(api_key="k", contexto_pesquisa=CONTEXTO), visto


@pytest.mark.parametrize("nome", sorted(CHAMADAS))
def test_toda_analise_leva_o_contexto_ao_modelo(nome, analista_espiao):
    """O pedido da fase, verificado uma por uma: Sankey, mapa temático, historiografia,
    obras seminais, insights do corpus e rótulos de cluster."""
    analista, visto = analista_espiao
    CHAMADAS[nome](analista)
    assert CONTEXTO in visto["system"], f"{nome}: o contexto não chegou ao system prompt"


@pytest.mark.parametrize("nome", sorted(CHAMADAS))
def test_analise_sem_contexto_nao_ganha_cabecalho_orfao(nome, monkeypatch):
    """Projeto sem contexto: o prompt não pode anunciar um contexto vazio."""
    from ai import client as mod

    visto = {}
    monkeypatch.setattr(mod, "call_openai_chat",
                        lambda **kw: (visto.update(system=kw["system_prompt"]), "0: X")[1])
    CHAMADAS[nome](mod.AIAnalyst(api_key="k"))
    assert CABECALHO_CONTEXTO_PADRAO not in visto["system"]


def test_nenhuma_analise_escapa_do_ponto_unico():
    """Guarda estrutural: uma análise nova que chame `call_openai_chat` direto, em vez de
    `_chat`, nasceria sem contexto e nenhum teste acima notaria — porque ela não existiria
    na lista. Esta varredura é o que fecha a porta."""
    import ast

    fonte = (RAIZ / "ai/client.py").read_text(encoding="utf-8")
    classe = next(n for n in ast.parse(fonte).body
                  if isinstance(n, ast.ClassDef) and n.name == "AIAnalyst")
    for metodo in [n for n in classe.body if isinstance(n, ast.FunctionDef)]:
        if not (metodo.name.startswith("generate_") or metodo.name == "label_clusters"):
            continue
        corpo = ast.get_source_segment(fonte, metodo)
        assert "self._chat(" in corpo, (
            f"{metodo.name} não passa por `_chat` — nasceria sem o contexto de pesquisa")


def test_todas_as_geradoras_do_client_estao_na_lista_de_chamadas():
    """Guarda do guarda: uma geradora nova torna a lista `CHAMADAS` incompleta, e os testes
    parametrizados acima passariam a verde cobrindo menos do que anunciam."""
    import ast

    fonte = (RAIZ / "ai/client.py").read_text(encoding="utf-8")
    geradoras = {n.name for n in ast.walk(ast.parse(fonte))
                 if isinstance(n, ast.FunctionDef)
                 and (n.name.startswith("generate_") or n.name == "label_clusters")}
    assert geradoras == set(CHAMADAS), f"fora da lista: {sorted(geradoras ^ set(CHAMADAS))}"


def test_main_passa_o_contexto_ao_criar_o_analista():
    """`_get_ai_analyst` é a fábrica usada por todas as telas de análise."""
    import ast

    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    metodo = next(n for n in ast.walk(ast.parse(fonte))
                  if isinstance(n, ast.FunctionDef) and n.name == "_get_ai_analyst")
    corpo = ast.get_source_segment(fonte, metodo)
    assert "contexto_pesquisa=self._contexto_pesquisa()" in corpo


def test_main_nao_reaproveita_system_prompt_congelado():
    """`_research_messages[0]` é montado quando a tela do Blink nasce. Reaproveitá-lo mandava
    o prompt SEM o contexto que o usuário escreveu depois — e com o indicador aceso na tela,
    afirmando o contrário."""
    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    assert '_research_messages[0]["content"]' not in fonte


def test_prompt_montado_reporta_o_que_aconteceu():
    """O diagnóstico permite ao teste afirmar *qual* parte foi sacrificada, em vez de só medir
    o tamanho final — que passaria mesmo se o contexto tivesse sido cortado."""
    p = montar(PAPEL, IDIOMA, CONTEXTO, corpus_grande(200))
    assert isinstance(p, PromptMontado)
    assert (p.contexto_incluido, p.corpus_incluido, p.corpus_cortado) == (True, True, True)
    assert MINIMO_CORPUS > 0

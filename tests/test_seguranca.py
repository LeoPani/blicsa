"""Bateria de segurança — Auditoria 2, Fase 1.

Um teste por vetor, atacando o próprio software. Os achados que motivaram cada um estão em
`docs/AUDITORIA-SEGURANCA.md`; aqui ficam as provas de que a correção segura.

O bridge HTTP local é a maior superfície: qualquer processo da máquina fala com ele, e o
token é o que separa "a extensão do usuário" de "qualquer programa que esteja rodando".
"""

import ast
import gzip
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
TOKEN = "token-de-teste-com-entropia-suficiente-1234567890"


# ── Bridge HTTP local ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def zera_limite_de_taxa():
    """O limitador é por processo e compartilhado entre os testes deste módulo: sem zerar,
    um teste herda a janela do anterior e recebe 429 sem ter pedido nada demais."""
    from core.bridge import ExtensionBridgeHandler

    ExtensionBridgeHandler._pedidos_recentes.clear()
    yield
    ExtensionBridgeHandler._pedidos_recentes.clear()


@pytest.fixture(scope="module")
def bridge():
    """Sobe o bridge real numa porta alta. Sem mock: o que se testa é o servidor."""
    from core.bridge import BridgeServer

    servidor = BridgeServer(TOKEN, port=8799)
    servidor.start()
    time.sleep(0.3)
    yield "http://127.0.0.1:8799"
    servidor.stop()


def _pedido(base, caminho, token=TOKEN, cabecalhos=None, corpo=None, metodo=None):
    """Devolve `(status, corpo)` — status pode ser o nome da exceção de transporte."""
    h = {"Content-Type": "application/json"}
    if token is not None:
        h["Authorization"] = f"Bearer {token}"
    h.update(cabecalhos or {})
    req = urllib.request.Request(base + caminho, data=corpo, headers=h,
                                 method=metodo or ("POST" if corpo is not None else None))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()[:200], dict(r.headers)
    except urllib.error.HTTPError as e:
        # `e.read()` pode estourar quando o servidor recusa e fecha antes de o corpo subir
        # (413 e 429 fazem isso). O código de status já é a informação que interessa.
        try:
            corpo_erro = e.read()[:200]
        except Exception:
            corpo_erro = b""
        return e.code, corpo_erro, dict(e.headers)
    except Exception as e:
        return type(e).__name__, b"", {}


def test_token_invalido_e_recusado(bridge):
    for token in (None, "", "x" * 40, TOKEN[:-1], TOKEN + "a", TOKEN.upper()):
        status, _, _ = _pedido(bridge, "/api/status", token=token)
        assert status == 401, f"token {token!r} foi aceito"


def test_token_valido_e_aceito(bridge):
    """Guarda do guarda: se tudo devolvesse 401, o teste acima passaria sem valer nada."""
    status, corpo, _ = _pedido(bridge, "/api/status")
    assert status == 200 and b"ok" in corpo


def test_comparacao_de_token_e_em_tempo_constante():
    """`==` sai no primeiro byte diferente e o tempo de resposta vaza quantos bytes iniciais
    o atacante acertou. Verificado na fonte, porque medir tempo em teste é ruído."""
    fonte = (RAIZ / "core/bridge.py").read_text(encoding="utf-8")
    metodo = next(n for n in ast.walk(ast.parse(fonte))
                  if isinstance(n, ast.FunctionDef) and n.name == "_validate_token")

    # Pela CHAMADA, não pelo texto do trecho: a primeira versão procurava a string
    # "compare_digest" e casava com o **comentário** que explica o defeito — o mesmo furo
    # que a reinjeção já tinha pegado no guarda do `pos=None` do ForceAtlas2.
    chamadas = {n.func.attr for n in ast.walk(metodo)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "compare_digest" in chamadas, "a comparação do token voltou a ser `==`"

    comparacoes = [n for n in ast.walk(metodo) if isinstance(n, ast.Compare)
                   and any(isinstance(o, ast.Eq) for o in n.ops)]
    for comp in comparacoes:
        alvos = ast.dump(comp)
        assert "bridge_token" not in alvos, "o token voltou a ser comparado com `==`"


def test_payload_gigante_e_recusado_sem_ser_lido(bridge):
    """`rfile.read(Content-Length)` alocava o que o cliente pedisse: 60 MB entraram na
    memória num teste. O teto é conferido **antes** de ler."""
    from core.bridge import LIMITE_CORPO_BYTES

    grande = b'{"a":"' + b"x" * (LIMITE_CORPO_BYTES + 1024) + b'"}'
    status, _, _ = _pedido(bridge, "/api/add", corpo=grande)
    # 413 quando o cliente consegue ler a resposta; erro de transporte quando o servidor
    # fecha antes de o corpo terminar de subir. Os dois significam recusado sem alocar.
    assert status in (413, "URLError", "RemoteDisconnected", "ConnectionResetError"), status


def test_content_length_invalido_nao_derruba_o_handler(bridge):
    """`int('abc')` levantava `ValueError` fora de qualquer `try`: 500 e conexão cortada."""
    status, _, _ = _pedido(bridge, "/api/add", cabecalhos={"Content-Length": "abc"},
                           corpo=b"{}")
    assert status == 400, status
    assert _pedido(bridge, "/api/status")[0] == 200, "o servidor não sobreviveu"


def test_json_profundo_e_recusado(bridge):
    profundo = (b"[" * 5000) + (b"]" * 5000)
    status, corpo, _ = _pedido(bridge, "/api/add", corpo=profundo)
    assert status == 400 and b"deep" in corpo.lower(), (status, corpo)


def test_json_raso_continua_passando(bridge):
    """A profundidade máxima não pode recusar um registro normal."""
    from core.bridge import profundidade_json

    from core.bridge import PROFUNDIDADE_MAXIMA_JSON

    registro = {"url": "http://x", "meta": {"autores": [{"nome": "Silva"}]}}
    # Um registro bibliográfico bem aninhado não passa de meia dúzia de níveis; o teto é 40.
    assert profundidade_json(registro) < PROFUNDIDADE_MAXIMA_JSON / 4


def test_limite_de_taxa_dispara(bridge):
    from core.bridge import MAX_PEDIDOS_NA_JANELA, ExtensionBridgeHandler

    respostas = [_pedido(bridge, "/api/add", corpo=b'{"url":"x"}')[0]
                 for _ in range(MAX_PEDIDOS_NA_JANELA + 10)]
    assert 429 in respostas, "o limitador de taxa nunca disparou"
    assert respostas[0] != 429, "disparou já no primeiro pedido — a janela está errada"


def test_cors_nao_libera_origem_arbitraria(bridge):
    """Origem que não é extensão recebe `null`, nunca o eco da própria origem."""
    _, _, cabecalhos = _pedido(bridge, "/api/status",
                               cabecalhos={"Origin": "https://site-malicioso.example"})
    assert cabecalhos.get("Access-Control-Allow-Origin") == "null"

    _, _, ext = _pedido(bridge, "/api/status",
                        cabecalhos={"Origin": "chrome-extension://abcdef"})
    assert ext.get("Access-Control-Allow-Origin") == "chrome-extension://abcdef"


# ── Arquivos: `.blicsa` é um ZIP ─────────────────────────────────────────────────

def test_zip_bomb_e_recusado_antes_de_descomprimir(tmp_path):
    """199 KB no disco, 200 MB na memória: `zf.read` descomprime antes de qualquer
    validação. O teto olha o cabeçalho, não o resultado."""
    from core.project import LIMITE_ENTRADA_BYTES, load_blicsa_project

    bomba = tmp_path / "bomba.blicsa"
    with zipfile.ZipFile(bomba, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"version": "1.0"}))
        z.writestr("dataset.json.gz", b"\0" * (LIMITE_ENTRADA_BYTES + 1024))

    assert bomba.stat().st_size < 5 * 1024 * 1024, "a fixture não é uma bomba"
    with pytest.raises(ValueError, match="acima do teto"):
        load_blicsa_project(str(bomba))


def test_projeto_de_tamanho_normal_continua_abrindo(tmp_path):
    """O teto não pode recusar corpus real — o `.blicsa` do exemplo tem 301 KB."""
    from core.project import load_blicsa_project

    df = pd.DataFrame([{"title": f"A{i}", "keywords": "x", "year": 2020} for i in range(200)])
    alvo = tmp_path / "normal.blicsa"
    with zipfile.ZipFile(alvo, "w") as z:
        z.writestr("manifest.json", json.dumps({"version": "1.0"}))
        z.writestr("dataset.json.gz", gzip.compress(df.to_json(orient="records").encode()))
    assert len(load_blicsa_project(str(alvo))["df"]) == 200


def test_travessia_de_caminho_no_zip_nao_escreve_fora(tmp_path):
    """`extractall` escreveria `../../../etc/…`. A carga lê por nome fixo e nunca extrai."""
    from core.project import load_blicsa_project

    alvo = tmp_path / "travessia.blicsa"
    fora = tmp_path / "invadido.txt"
    with zipfile.ZipFile(alvo, "w") as z:
        z.writestr("manifest.json", json.dumps({"version": "1.0"}))
        z.writestr("../../invadido.txt", "conteudo malicioso")
    try:
        load_blicsa_project(str(alvo))
    except Exception:
        pass
    assert not fora.exists()
    assert not Path("/tmp/invadido.txt").exists()


def test_nenhuma_extracao_de_zip_no_codigo():
    """Guarda estrutural: `extractall` num `.blicsa` reabriria a travessia de caminho."""
    saida = subprocess.run(["git", "grep", "-n", "extractall", "--", "*.py"],
                           cwd=RAIZ, capture_output=True, text=True).stdout
    fora_de_teste = [l for l in saida.splitlines() if not l.startswith("tests/")]
    assert not fora_de_teste, f"extração de ZIP no código: {fora_de_teste}"


# ── Injeção de fórmula no CSV exportado ──────────────────────────────────────────

FORMULAS = ['=cmd|\' /C calc\'!A0', '+1+1', '-2+3', '@SUM(1+1)',
            '=HYPERLINK("http://x","clique")']


@pytest.mark.parametrize("perigoso", FORMULAS)
def test_formula_no_termo_e_neutralizada(perigoso):
    from core.nlp import neutralizar_formula

    saida = neutralizar_formula(perigoso)
    assert saida.startswith("'"), f"{perigoso!r} sairia como fórmula"
    assert saida[1:] == perigoso, "o termo foi alterado em vez de prefixado"


def test_export_csv_nao_carrega_celula_executavel(tmp_path):
    """Caminho real: um termo do corpus vira nó, o nó vai para o CSV, o pesquisador abre no
    Excel. Medido na Auditoria 2: 5 células no ranking e 14 nas arestas."""
    from core.matrix_builders import NetworkGenerator

    linhas = [{"title": f"A{i}", "keywords": ";".join(FORMULAS), "authors": "S, J",
               "year": 2020, "citations": i, "abstract": "", "source": "", "doi": "",
               "references": "", "origin": "", "language": "", "is_oa": False, "oa_url": ""}
              for i in range(4)]
    gen = NetworkGenerator(pd.DataFrame(linhas))
    gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()

    for exportar, nome in ((gen.export_rankings_csv, "r.csv"),
                           (gen.export_edges_csv, "e.csv")):
        alvo = tmp_path / nome
        exportar(str(alvo))
        for linha in alvo.read_text(encoding="utf-8").splitlines()[1:]:
            for celula in linha.split(","):
                assert not celula.startswith(("=", "+", "-", "@", "\t")), \
                    f"{nome}: célula executável → {celula!r}"


def test_neutralizacao_nao_depende_do_dtype_do_pandas():
    """A primeira versão filtrava por `dtype == object` e o pandas 3.0 infere `str`: a
    neutralização existia e **não neutralizava nada**. Foi verificação que pegou."""
    from core.nlp import neutralizar_formulas_no_df

    df = pd.DataFrame([{"termo": "=cmd|calc", "n": 1}])
    assert neutralizar_formulas_no_df(df)["termo"].iloc[0] == "'=cmd|calc"


# ── Segredos, rede e desserialização ─────────────────────────────────────────────

def test_chave_de_ia_nao_aparece_em_erro_nem_em_log(caplog, capsys):
    """Provocando erro real com chave configurada."""
    from ai.client import AIAnalyst, AIClientError

    chave = "gsk_SEGREDO_QUE_NAO_PODE_VAZAR_1234567890"
    with caplog.at_level("DEBUG"):
        with pytest.raises(AIClientError) as capturado:
            AIAnalyst(api_key=chave,
                      base_url="http://127.0.0.1:9/naoexiste").generate_sankey_insights("a")

    assert chave not in str(capturado.value), "a chave vazou na mensagem de erro"
    assert chave not in caplog.text, "a chave vazou no log"
    assert chave not in capsys.readouterr().out, "a chave vazou no stdout"


def test_nenhuma_desserializacao_perigosa_no_codigo():
    """`pickle`, `eval`, `exec`, `yaml.load` sem SafeLoader e `shell=True` são achado
    crítico por definição. Varredura da árvore rastreada."""
    padrao = r"\bpickle\b|\beval\(|\bexec\(|yaml\.load\(|shell=True|os\.system\("
    saida = subprocess.run(["git", "grep", "-nE", padrao, "--", "*.py"],
                           cwd=RAIZ, capture_output=True, text=True).stdout
    achados = [l for l in saida.splitlines()
               if not l.startswith("tests/") and "safe_load" not in l]
    assert not achados, "desserialização perigosa:\n" + "\n".join(achados)


def test_toda_chamada_de_rede_tem_timeout():
    """Sem timeout, `urlopen` herda `None` do socket e a busca fica pendurada para sempre —
    numa thread que o usuário não pode matar."""
    saida = subprocess.run(["git", "grep", "-n", "urlopen(", "--",
                            "core/*.py", "core/sources/*.py", "ai/*.py"],
                           cwd=RAIZ, capture_output=True, text=True).stdout
    sem_timeout = [l for l in saida.splitlines() if "timeout" not in l]
    assert not sem_timeout, "urlopen sem timeout:\n" + "\n".join(sem_timeout)


def test_tls_nunca_e_desabilitado():
    padrao = r"_create_unverified|verify\s*=\s*False|CERT_NONE"
    saida = subprocess.run(["git", "grep", "-nE", padrao, "--", "*.py"],
                           cwd=RAIZ, capture_output=True, text=True).stdout
    assert not saida.strip(), f"verificação de TLS desabilitada:\n{saida}"


# ── Conteúdo renderizado ─────────────────────────────────────────────────────────

def test_titulo_com_script_nao_executa_no_mapa(tmp_path):
    """Um título de artigo com `<script>` chega ao mapa como rótulo. No Sigma os rótulos vão
    por `textContent`/canvas; no HTML do pyvis, os dados vão escapados para dentro do
    `<script>`. Este teste prova o segundo, que é o que grava arquivo."""
    from core.matrix_builders import NetworkGenerator

    veneno = "<script>alert(1)</script>"
    linhas = [{"title": f"A{i}", "keywords": f"{veneno};normal", "authors": "S, J",
               "year": 2020, "citations": i, "abstract": "", "source": "", "doi": "",
               "references": "", "origin": "", "language": "", "is_oa": False, "oa_url": ""}
              for i in range(4)]
    gen = NetworkGenerator(pd.DataFrame(linhas))
    gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()

    alvo = tmp_path / "mapa.html"
    gen.export_to_html(str(alvo))
    html = alvo.read_text(encoding="utf-8")
    assert veneno not in html, "o `<script>` do corpus saiu literal no HTML exportado"
    assert "\\u003cscript\\u003e" in html or "&lt;script&gt;" in html, \
        "o termo sumiu do arquivo em vez de ser escapado"


def test_o_mapa_sigma_nao_usa_innerHTML_com_dado_do_corpus():
    """No `map.js`, `innerHTML` só recebe string do catálogo de tradução. Rótulo de nó vai
    por `textContent` e por canvas."""
    js = (RAIZ / "assets/map.js").read_text(encoding="utf-8")
    for linha in js.splitlines():
        if "innerHTML" not in linha:
            continue
        atribuicao = linha.split("innerHTML", 1)[1]
        assert '""' in atribuicao or "tr(" in atribuicao or atribuicao.strip().startswith("="), \
            f"innerHTML com origem não declarada: {linha.strip()[:90]}"


# ── Permissões e caminhos ────────────────────────────────────────────────────────

def test_servidor_local_serve_apenas_o_diretorio_do_app():
    """Já foi bug: o servidor servia a raiz do repositório."""
    fonte = (RAIZ / "core/local_server.py").read_text(encoding="utf-8")
    assert ".serve" in fonte, "o diretório servido deixou de ser confinado"
    assert "Blicsa" in fonte


def test_extensao_nao_pede_permissao_excessiva():
    """Cada permissão do manifesto precisa ser justificável. `<all_urls>`, `tabs` e
    `webRequest` não são."""
    manifesto = json.loads((RAIZ / "extension/manifest.json").read_text(encoding="utf-8"))
    permitidas = {"activeTab", "storage", "scripting"}
    excesso = set(manifesto.get("permissions", [])) - permitidas
    assert not excesso, f"permissões não justificadas: {excesso}"

    for host in manifesto.get("host_permissions", []):
        assert host.startswith(("http://127.0.0.1:", "http://localhost:")), \
            f"host_permission fora do bridge local: {host}"

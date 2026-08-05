#!/usr/bin/env python3
"""Reinjeta cada defeito da camada de IA e confirma que o teste fica VERMELHO."""
import pathlib, shutil, subprocess, sys, tempfile

RAIZ = pathlib.Path("/Users/leopani/PyBibliomics")
TIMEOUT_S = 90

CASOS = [
    ("diagnósticos agrupados num erro genérico",
     "ai/onboarding.py",
     '''        if e.code in (401, 403):
            return ResultadoTeste("invalida", "ai.key_invalid", detalhe=f"HTTP {e.code}")
        if e.code == 429:
            return ResultadoTeste("limite", "ai.key_rate_limit", detalhe="HTTP 429")''',
     '        pass',
     "tests/test_ai_onboarding.py::test_os_quatro_diagnosticos_sao_DISTINTOS_entre_si"),

    ("sem internet vira 'chave inválida'",
     "ai/onboarding.py",
     'return ResultadoTeste("sem_internet", "ai.key_offline",',
     'return ResultadoTeste("invalida", "ai.key_invalid",',
     "tests/test_ai_onboarding.py::test_sem_internet"),

    ("500 do provedor vira 'chave recusada'",
     "ai/onboarding.py",
     'return ResultadoTeste("erro", "ai.key_error", detalhe=f"HTTP {e.code}")',
     'return ResultadoTeste("invalida", "ai.key_invalid", detalhe=f"HTTP {e.code}")',
     "tests/test_ai_onboarding.py::test_erro_http_desconhecido_nao_vira_chave_invalida"),

    ("trim da chave some",
     "ai/onboarding.py",
     '    chave = (chave or "").strip()\n    if not chave:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     '    chave = (chave or "")\n    if not chave:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     "tests/test_ai_onboarding.py::test_chave_com_espacos_em_volta_e_aceita"),

    ("campo vazio passa a gastar requisição",
     "ai/onboarding.py",
     '    if not chave:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     '    if False:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     "tests/test_ai_onboarding.py::test_chave_vazia_e_rejeitada_sem_bater_na_rede"),

    ("mascaramento devolve a chave inteira",
     "ai/onboarding.py",
     '    return f"{chave[:4]}…{chave[-4:]}"',
     '    return chave',
     "tests/test_ai_onboarding.py::test_chave_e_exibida_mascarada"),

    ("redação da chave no diagnóstico some",
     "ai/onboarding.py",
     '                              detalhe=_redigir(str(e.reason), chave)[:120])',
     '                              detalhe=str(e.reason)[:120])',
     "tests/test_ai_onboarding.py::test_diagnostico_nunca_carrega_a_chave"),

    ("teste de conexão deixa de ser mínimo (gasta cota do usuário)",
     "ai/onboarding.py",
     '"max_tokens": 1,',
     '"max_tokens": 512,',
     "tests/test_ai_onboarding.py::test_chamada_de_teste_e_minima"),

    ("URL do tutorial errada",
     "ai/onboarding.py",
     'URL_CONSOLE_GROQ = "https://console.groq.com/keys"',
     'URL_CONSOLE_GROQ = "https://groq.com"',
     "tests/test_ai_onboarding.py::test_url_do_tutorial_e_a_correta"),

    ("declaração de custo zero some",
     "locales/pt_BR.json",
     "O Blicsa não cobra nada e não intermedia pagamento.",
     "Configure abaixo.",
     "tests/test_ai_onboarding.py::test_custo_zero_esta_declarado_nos_tres_idiomas"),
    # ── Fase 2: amarelo como marcador de IA ──
    ("amarelo volta para a paleta de clusters (dado)",
     "ui/design_tokens.py",
     'CLUSTER_PALETTE = ["#DF3117", "#1E4DA0", "#C97B2D",',
     'CLUSTER_PALETTE = ["#DF3117", "#1E4DA0", "#F5BE00",',
     "tests/test_ai_marking.py::test_paleta_de_clusters_nao_tem_amarelo"),

    ("badge de citações volta a ser amarelo",
     "ui/search_feed.py",
     'text=f"★ {cites}", fg_color=INK, text_color=WHITE,',
     'text=f"★ {cites}", fg_color="#F5BE00", text_color=INK,',
     "tests/test_ai_marking.py::test_badge_de_citacoes_nao_e_amarelo"),

    ("bloco de IA perde o selo textual (fica só a cor)",
     "ui/ai_marking.py",
     "        self.selo = selo_ia(cabecalho)\n        self.selo.pack(side=\"left\")",
     "        pass",
     "tests/test_ai_marking.py::test_marcacao_sempre_carrega_o_rotulo_textual"),

    ("rótulo editado pelo humano volta a ser marcado como IA",
     "ui/ai_marking.py",
     '            return str(origens[chave] or "").lower() == "ia"',
     '            return True',
     "tests/test_ai_marking.py::test_rotulo_editado_pelo_humano_perde_a_marcacao_de_ia"),

    ("export perde o prefixo [IA]",
     "ui/ai_marking.py",
     'return f"{PREFIXO_EXPORT} {titulo}".strip()',
     'return titulo',
     "tests/test_ai_marking.py::test_export_marca_secoes_com_prefixo"),

    ("nota de rodapé do export some",
     "ui/ai_marking.py",
     '"dos dados do corpus. Confira antes de citar."',
     '"dos dados do corpus."',
     "tests/test_ai_marking.py::test_nota_de_rodape_pede_verificacao_antes_de_citar"),
]


def main() -> int:
    falhas = []
    with tempfile.TemporaryDirectory() as tmp:
        backup = pathlib.Path(tmp)
        for arq in {c[1] for c in CASOS}:
            shutil.copy2(RAIZ / arq, backup / arq.replace("/", "__"))
        for nome, arq, original, defeito, teste in CASOS:
            caminho = RAIZ / arq
            texto = caminho.read_text(encoding="utf-8")
            if original not in texto:
                print(f"  [SETUP RUIM] {nome}: trecho não encontrado em {arq}")
                falhas.append(nome); continue
            caminho.write_text(texto.replace(original, defeito, 1), encoding="utf-8")
            try:
                r = subprocess.run([sys.executable, "-m", "pytest", teste, "-q", "--no-header"],
                                   cwd=RAIZ, capture_output=True, text=True, timeout=TIMEOUT_S)
                vermelho = r.returncode != 0
                motivo = "ficou VERMELHO" if vermelho else "continuou VERDE"
            except subprocess.TimeoutExpired:
                vermelho, motivo = True, f"TRAVOU (>{TIMEOUT_S}s)"
            shutil.copy2(backup / arq.replace("/", "__"), caminho)
            print(f"  [{'OK  ' if vermelho else 'FURO'}] {nome}\n         → {motivo} "
                  f"{'✓' if vermelho else '✗'}", flush=True)
            if not vermelho:
                falhas.append(nome)
    print()
    if falhas:
        print(f"{len(falhas)} teste(s) NÃO protegem o que deveriam:")
        for f in falhas: print(f"  - {f}")
        return 1
    print(f"Todos os {len(CASOS)} defeitos reinjetados foram detectados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

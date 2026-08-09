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

    # ── Fase 3: contexto de pesquisa por projeto ──
    ("contexto do usuário passa a vir DEPOIS dos dados do corpus",
     "core/research_context.py",
     '            partes.append(f"{cabecalho_corpus}\\n{cortado}")',
     '            partes.insert(-1, f"{cabecalho_corpus}\\n{cortado}")',
     "tests/test_research_context.py::test_contexto_do_usuario_vem_antes_dos_dados_do_corpus"),

    ("corte calcula o orçamento como se o contexto não existisse",
     "core/research_context.py",
     "        teto = orcamento - len(montado) - 2 - len(cabecalho_corpus) - 1",
     "        teto = orcamento - len(fixo) - 2 - len(cabecalho_corpus) - 1",
     "tests/test_research_context.py::test_orcamento_e_respeitado_com_corpus_gigante"),

    ("corte sacrifica o contexto do usuário em vez dos abstracts",
     "core/research_context.py",
     "        teto = orcamento - len(fixo) - 2\n",
     "        teto = 200\n",
     "tests/test_research_context.py::test_corte_sacrifica_abstracts_e_preserva_o_contexto_do_usuario"),

    ("corte parte um registro do corpus ao meio",
     "core/research_context.py",
     "    for sep in SEPARADORES:\n"
     "        pedaco = texto[:util]\n"
     "        pos = pedaco.rfind(sep)\n"
     "        if pos > 0:\n"
     "            return texto[:pos] + MARCA_CORTE\n"
     '    return ""',
     "    return texto[:util] + MARCA_CORTE",
     "tests/test_research_context.py::test_corte_nao_parte_registro_ao_meio"),

    ("toco de abstract entra no lugar de descartar o bloco",
     "core/research_context.py",
     "        if cortado and len(cortado) >= min(MINIMO_CORPUS, len(corpus)):",
     "        if cortado:",
     "tests/test_research_context.py::test_titulo_sem_abstract_nao_entra_como_se_fosse_evidencia"),

    ("papel e idioma passam a ser cortados junto",
     "core/research_context.py",
     "    partes: list[str] = [p for p in (papel, idioma) if p]",
     "    partes: list[str] = [p[:20] for p in (papel, idioma) if p]",
     "tests/test_research_context.py::test_papel_e_idioma_nunca_sao_cortados"),

    ("cabeçalho de contexto sai mesmo com o campo vazio",
     "core/research_context.py",
     "    if contexto:\n        bloco = f",
     "    if True:\n        bloco = f",
     "tests/test_research_context.py::test_sem_contexto_nao_sobra_cabecalho_orfao"),

    ("normalizar deixa de tolerar valor não-texto de projeto antigo",
     "core/research_context.py",
     "    if texto is None or isinstance(texto, bool):\n        return \"\"\n"
     "    if not isinstance(texto, str):\n        texto = str(texto)",
     "    pass",
     "tests/test_research_context.py::test_normalizar_tolera_lixo_de_projeto_antigo"),

    ("separador do bloco de corpus volta a ser barra escapada",
     "core/research_context.py",
     '    return "\\n\\n---\\n".join(r for r in registros if r and r.strip())',
     '    return "\\\\n\\\\n---\\\\n".join(r for r in registros if r and r.strip())',
     "tests/test_research_context.py::test_bloco_corpus_usa_quebra_de_linha_de_verdade"),

    ("leitor do config devolve o valor cru do arquivo",
     "core/project.py",
     "    return normalizar(config.get(CHAVE_CONTEXTO_PESQUISA))",
     '    return config.get(CHAVE_CONTEXTO_PESQUISA) or ""',
     "tests/test_research_context.py::test_leitor_do_config_sempre_devolve_texto"),

    ("análises das outras telas deixam de receber o contexto",
     "ai/client.py",
     "            system_prompt=self._system_com_contexto(system),",
     "            system_prompt=system,",
     "tests/test_research_context.py::test_toda_analise_leva_o_contexto_ao_modelo"),

    ("fábrica do analista para de repassar o contexto",
     "main.py",
     "            contexto_pesquisa=self._contexto_pesquisa(),",
     "",
     "tests/test_research_context.py::test_main_passa_o_contexto_ao_criar_o_analista"),

    ("chat volta a montar o bloco de corpus com barra escapada",
     "main.py",
     "                        corpus_txt = bloco_corpus(abstracts)",
     '                        corpus_txt = "\\\\n\\\\n---\\\\n".join(abstracts)',
     "tests/test_research_context.py::test_main_nao_monta_mais_o_bloco_com_barra_escapada"),

    ("análise do mapa reaproveita o system prompt congelado",
     "main.py",
     "                system_prompt = self._blink_system_prompt(dados_corpus=full_context)",
     '                system_prompt = self._research_messages[0]["content"]',
     "tests/test_research_context.py::test_main_nao_reaproveita_system_prompt_congelado"),

    ("texto de exemplo do campo vira valor enviado ao modelo",
     "ui/research_context_bar.py",
     '        if self._mostrando_exemplo:\n            return ""\n'
     '        return normalizar(self.campo.get("1.0", "end"))',
     '        return normalizar(self.campo.get("1.0", "end"))',
     "tests/test_research_context_ui.py::test_exemplo_nunca_e_devolvido_como_valor"),

    ("indicador de contexto fica amarelo (cor reservada para IA)",
     "ui/research_context_bar.py",
     "                                      fg_color=BLUE, text_color=WHITE_CARD,",
     '                                      fg_color="#F5BE00", text_color=INK,',
     "tests/test_research_context_ui.py::test_indicador_nao_e_amarelo"),

    ("indicador acende com o campo vazio",
     "core/research_context.py",
     "    return bool(normalizar(texto))",
     "    return True",
     "tests/test_research_context_ui.py::test_indicador_apagado_sem_contexto"),

    ("teste de conexão perde o User-Agent (chave boa vira 'chave recusada')",
     "ai/onboarding.py",
     '            "User-Agent": USER_AGENT,\n',
     "",
     "tests/test_ai_onboarding.py::test_teste_de_conexao_manda_user_agent"),

    ("User-Agent volta a ser literal em ai/client.py",
     "ai/client.py",
     '        "User-Agent": USER_AGENT\n    }\n    if api_key:',
     '        "User-Agent": "Blicsa/1.0 (Python)"\n    }\n    if api_key:',
     "tests/test_ai_onboarding.py::test_teste_de_conexao_usa_o_mesmo_user_agent_do_cliente"),

    (".env volta a sobrescrever o ambiente real (chave velha vence a boa)",
     "main.py",
     "                    os.environ.setdefault(k.strip(), v.strip().strip('\"').strip(\"'\"))",
     "                    os.environ[k.strip()] = v.strip().strip('\"').strip(\"'\")",
     "tests/test_ai_onboarding.py::test_main_carrega_dotenv_com_setdefault"),

    ("diálogo de insights volta a renderizar IA sem marcação",
     "main.py",
     "        marcado = AIContentFrame(dlg)",
     "        marcado = ctk.CTkFrame(dlg)",
     "tests/test_ai_marking.py::test_dialogo_de_insights_e_marcado"),

    ("análise de obras seminais perde a marcação textual",
     "main.py",
     "        insert_markdown(self._seminal_box, f\"{marcar_texto_export('')} {text}\".strip())",
     "        insert_markdown(self._seminal_box, text)",
     "tests/test_ai_marking.py::test_analise_seminal_e_marcada"),
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

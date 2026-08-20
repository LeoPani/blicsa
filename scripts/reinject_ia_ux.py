#!/usr/bin/env python3
"""Reinjeta cada defeito da camada de IA e confirma que o teste fica VERMELHO."""
import pathlib, shutil, subprocess, sys, tempfile

# Derivado do próprio arquivo, não fixo: o caminho absoluto anterior carregava o nome
# de usuário do autor para dentro de um repositório público e fazia o script rodar só
# na máquina dele — quem clonasse recebia "trecho não encontrado" em todos os casos.
RAIZ = pathlib.Path(__file__).resolve().parent.parent
TIMEOUT_S = 90

CASOS = [
    ("diagnósticos agrupados num erro genérico",
     "core/credenciais.py",
     '''    if codigo in (401, 403):
        return ResultadoTeste("invalida", f"{prefixo}.key_invalid", detalhe=f"HTTP {codigo}")
    if codigo == 429:
        return ResultadoTeste("limite", f"{prefixo}.key_rate_limit", detalhe="HTTP 429")''',
     '    pass',
     "tests/test_ai_onboarding.py::test_os_quatro_diagnosticos_sao_DISTINTOS_entre_si"),

    ("sem internet vira 'chave inválida'",
     "core/credenciais.py",
     'return None, ResultadoTeste("sem_internet", f"{prefixo}.key_offline",',
     'return None, ResultadoTeste("invalida", f"{prefixo}.key_invalid",',
     "tests/test_ai_onboarding.py::test_sem_internet"),

    ("500 do provedor vira 'chave recusada'",
     "core/credenciais.py",
     '    return ResultadoTeste("erro", f"{prefixo}.key_error", detalhe=f"HTTP {codigo}")',
     '    return ResultadoTeste("invalida", f"{prefixo}.key_invalid", detalhe=f"HTTP {codigo}")',
     "tests/test_ai_onboarding.py::test_erro_http_desconhecido_nao_vira_chave_invalida"),

    ("trim da chave some",
     "core/credenciais.py",
     '    chave = (chave or "").strip()\n    if not chave:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     '    chave = (chave or "")\n    if not chave:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     "tests/test_ai_onboarding.py::test_chave_com_espacos_em_volta_e_aceita"),

    ("campo vazio passa a gastar requisição",
     "core/credenciais.py",
     '    if not chave:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     '    if False:\n        return ResultadoTeste("vazia", "ai.key_empty")',
     "tests/test_ai_onboarding.py::test_chave_vazia_e_rejeitada_sem_bater_na_rede"),

    ("mascaramento devolve a chave inteira",
     "core/credenciais.py",
     '    return f"{chave[:4]}…{chave[-4:]}"',
     '    return chave',
     "tests/test_ai_onboarding.py::test_chave_e_exibida_mascarada"),

    ("redação da chave no diagnóstico some",
     "core/credenciais.py",
     '                              detalhe=_redigir(str(e.reason), chave)[:120])',
     '                              detalhe=str(e.reason)[:120])',
     "tests/test_ai_onboarding.py::test_diagnostico_nunca_carrega_a_chave"),

    ("teste de conexão deixa de ser mínimo (gasta cota do usuário)",
     "core/credenciais.py",
     '"max_tokens": 1}',
     '"max_tokens": 512,',
     "tests/test_ai_onboarding.py::test_chamada_de_teste_e_minima"),

    ("URL do tutorial errada",
     "core/credenciais.py",
     '"groq":       ("https://console.groq.com/keys",',
     '"groq":       ("https://groq.com",',
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
     "core/credenciais.py",
     '    cab = {"User-Agent": USER_AGENT}\n    cab.update(cabecalhos or {})',
     '    cab = dict(cabecalhos or {})',
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

    # ── Idioma das análises ───────────────────────────────────────────────────────
    # O defeito original: as cinco análises presas ao português por texto fixo no prompt.

    ("as análises voltam a mandar responder em português",
     "ai/client.py",
     'ESTILO_ANALISE = ("Use linguagem técnica acadêmica. Seja direto, conciso, objetivo e evite "',
     'ESTILO_ANALISE = ("Use linguagem técnica acadêmica em português. Seja direto, conciso, objetivo e evite "',
     "tests/test_analises_i18n.py::test_estilo_das_analises_nao_carrega_idioma"),

    ("a cláusula de idioma volta a um prompt só (mapa temático)",
     "ai/client.py",
     '''                      ("ai.sec_emergentes", "Temas Emergentes e Básicos"))
            +
            f"\\n{ESTILO_ANALISE}"''',
     '''                      ("ai.sec_emergentes", "Temas Emergentes e Básicos"))
            +
            "\\nUse linguagem técnica acadêmica em português."''',
     "tests/test_analises_i18n.py::test_nenhum_literal_de_prompt_fixa_idioma"),

    ("o system das análises perde a diretiva de idioma",
     "ai/client.py",
     "        return montar_system_prompt(papel=papel, idioma=diretiva_idioma(self._lang()),",
     '        return montar_system_prompt(papel=papel, idioma="",',
     "tests/test_analises_i18n.py::test_analise_pede_resposta_no_idioma_da_interface"),

    ("a diretiva das análises congela num idioma",
     "ai/client.py",
     "            return get_lang()",
     '            return "pt_BR"',
     "tests/test_analises_i18n.py::test_a_diretiva_muda_de_fato_entre_os_tres_idiomas"),

    ("o rótulo de cluster volta a ser pedido em português",
     "ai/client.py",
     '"ID: Label conciso (2-5 palavras)\\n"',
     '"ID: Label conciso em português (2-5 palavras)\\n"',
     "tests/test_analises_i18n.py::test_nenhuma_analise_manda_responder_em_portugues"),

    # Os três seguintes vêm da MEDIÇÃO com chamada real, não de leitura de código: a diretiva
    # sozinha deixava 7 das 18 análises em português.

    ("títulos de seção voltam a ser fixos em português",
     "ai/client.py",
     '''            + _secoes(("ai.sec_fluxo", "Fluxo de Conhecimento (Sankey)"),
                      ("ai.sec_atores", "Principais Atores e Fontes"))
            +''',
     '''            + "## Fluxo de Conhecimento (Sankey)\\n## Principais Atores e Fontes\\n"
            +''',
     "tests/test_analises_i18n.py::test_secao_em_portugues_nao_sobra_fora_do_pt_BR"),

    ("o nome da análise volta a ir em português ao modelo",
     "ai/client.py",
     """            f"Analise os dados do {_t('ai.obj_tematico', 'Mapa Temático')} abaixo:\\n\\n\"""",
     '''            "Analise os dados do Mapa Temático abaixo:\\n\\n"''',
     "tests/test_analises_i18n.py::test_nome_da_analise_nao_chega_em_portugues"),

    ("o lembrete de idioma some do fim do turno do usuário",
     "ai/client.py",
     "            user_prompt=self._com_lembrete_de_idioma(user),",
     "            user_prompt=user,",
     "tests/test_analises_i18n.py::test_lembrete_de_idioma_encerra_o_turno_do_usuario"),

    ("o lembrete vai para o começo do turno, onde o prompt o soterra",
     "ai/client.py",
     '        return f"{user}\\n\\n{diretiva_idioma(self._lang())}"',
     '        return f"{diretiva_idioma(self._lang())}\\n\\n{user}"',
     "tests/test_analises_i18n.py::test_lembrete_de_idioma_encerra_o_turno_do_usuario"),

    ("catálogo com seção copiada do português (tradução de mentira)",
     "locales/fr.json",
     '"ai.sec_fluxo": "Flux de connaissances (Sankey)"',
     '"ai.sec_fluxo": "Fluxo de Conhecimento (Sankey)"',
     "tests/test_analises_i18n.py::test_secoes_sao_traduzidas_de_fato_e_nao_copiadas"),

    ("chave de seção some do catálogo francês",
     "locales/fr.json",
     '"ai.sec_quadrantes": "Analyse des quadrants stratégiques"',
     '"ai.sec_quadrantes_REMOVIDA": "Analyse des quadrants stratégiques"',
     "tests/test_analises_i18n.py::test_toda_chave_de_catalogo_usada_no_client_existe_nos_tres"),

    ("a diretiva vai parar depois do contexto do usuário",
     "ai/client.py",
     "        return montar_system_prompt(papel=papel, idioma=diretiva_idioma(self._lang()),\n"
     "                                    contexto_usuario=self.contexto_pesquisa,",
     "        return montar_system_prompt(papel=papel, idioma=\"\",\n"
     "                                    contexto_usuario=self.contexto_pesquisa\n"
     "                                    + \"\\n\\n\" + diretiva_idioma(self._lang()),",
     "tests/test_analises_i18n.py::test_papel_e_idioma_precedem_o_contexto_do_usuario"),

    # ── Auditoria 1, Fase 1: mapas com corpus adversariais ──
    # Os dois defeitos que a bateria encontrou medindo, não lendo código.

    ("ForceAtlas2 volta a sortear a posição inicial sem semente",
     "core/visualizer.py",
     "    return fa2.forceatlas2_networkx_layout(\n"
     "        G, pos=posicoes_iniciais(G, seed), iterations=iterations)",
     "    return fa2.forceatlas2_networkx_layout(G, pos=None, iterations=iterations)",
     "tests/test_mapas_adversariais.py::test_layout_repetido_no_mesmo_processo_tambem_bate"),

    ("semente do layout deixa de ser fixa (vira o relógio)",
     "core/visualizer.py",
     "    rng = random.Random(seed)",
     "    import time as _t; rng = random.Random(_t.time_ns())",
     "tests/test_mapas_adversariais.py::test_posicoes_iniciais_sao_a_fonte_da_reprodutibilidade"),

    ("zero citação volta a ser lido como ausência de dado",
     "core/sigma_exporter.py",
     '                "avg_citations": _metric(attr, "citations_mean", "avg_citations"),',
     '                "avg_citations": _metric(attr, "citations_mean", "avg_citations",\n'
     '                                         zero_is_missing=True),',
     "tests/test_sigma_export.py::test_zero_citacoes_e_zero_e_nao_ausencia_de_dado"),

    ("escritor volta a gravar 0.0 como sentinela de citação ausente",
     "core/matrix_builders.py",
     '                self.G.nodes[node]["citations_mean"] = (\n'
     '                    round(float(cits.mean()), 1) if tem_citacao else None)',
     '                self.G.nodes[node]["citations_mean"] = (\n'
     '                    round(float(cits.mean()), 1) if tem_citacao else 0.0)',
     "tests/test_mapas_adversariais.py::test_ausencia_real_de_citacao_continua_sendo_ausencia"),

    ("ano deixa de usar 0 como ausência (a assimetria se perde)",
     "core/sigma_exporter.py",
     '                "avg_year": _metric(attr, "year_mean", "avg_year", zero_is_missing=True),',
     '                "avg_year": _metric(attr, "year_mean", "avg_year"),',
     "tests/test_mapas_adversariais.py::test_ano_continua_usando_zero_como_ausencia"),

    ("ordem de inserção dos nós deixa de ser ordenada (Louvain volta a variar)",
     "core/matrix_builders.py",
     "        for t in sorted(valid):",
     "        for t in valid:",
     "tests/test_mapas_adversariais.py::test_mapa_e_reproduzivel_entre_processos"),

    ("termo volta a carregar quebra de linha (export de linha corrompe)",
     "core/matrix_builders.py",
     "                    apply_thesaurus(normalizar_termo(k).lower(), thesaurus)",
     "                    apply_thesaurus(k.strip().lower(), thesaurus)",
     "tests/test_mapas_adversariais.py::test_termo_com_quebra_nao_corrompe_export_de_linha"),

    ("normalizar_termo passa a apagar caractere legítimo",
     "core/nlp.py",
     '    return _ESPACO_BRANCO.sub(" ", termo or "").strip()',
     '    return re.sub(r"[^a-z0-9 ]", "", (termo or "").lower()).strip()',
     "tests/test_mapas_adversariais.py::test_normalizar_termo_preserva_o_que_e_conteudo"),

    ("export GEXF volta a gravar 0 no lugar de ausência",
     "core/matrix_builders.py",
     '                valor = data.get(chave)\n'
     '                if valor is None:\n'
     '                    data.pop(chave, None)',
     '                valor = data.get(chave) or 0.0\n'
     '                if False:\n'
     '                    data.pop(chave, None)',
     "tests/test_mapas_adversariais.py::test_export_nao_grava_zero_no_lugar_de_ausencia"),

    ("VOSviewer volta a escrever a string None no score",
     "core/matrix_builders.py",
     '            cits_txt = "" if mean_cits is None else mean_cits',
     '            cits_txt = mean_cits',
     "tests/test_mapas_adversariais.py::test_export_nao_grava_zero_no_lugar_de_ausencia"),

    ("builder deixa de gravar o ano de estreia (animação volta ao ano médio)",
     "core/matrix_builders.py",
     "                first_year=first_year,",
     "                first_year=0,",
     "tests/test_mapas_adversariais.py::test_termo_estreia_no_primeiro_ano_e_nao_no_ano_medio"),

    # A primeira versão deste caso renomeava a chave na INICIALIZAÇÃO do dicionário de
    # resultado, que a leitura sobrescreve adiante — mutação inócua, teste verde, e o furo
    # era do caso de reinjeção, não do teste. Agora o defeito é o que de fato acontece: o
    # arquivo de origens não chega a ser gravado no .blicsa.
    ("ida e volta perde a origem do rótulo (IA vira humano)",
     "core/project.py",
     "        if cluster_label_origins:",
     "        if False:",
     "tests/test_mapas_adversariais.py::test_ida_e_volta_preserva_mapa_clusters_rotulos_e_parametros"),

    # ── Auditoria 1, Fase 2: fluxo de ponta a ponta ──
    ("tela de boas-vindas volta sozinha ao trocar de idioma",
     "main.py",
     '        if not getattr(self, "_boas_vindas_dispensadas", False):\n'
     "            self._welcome_frame.place(relx=0, rely=0, relwidth=1, relheight=1)",
     "        self._welcome_frame.place(relx=0, rely=0, relwidth=1, relheight=1)",
     "tests/test_fluxo_auditoria.py::test_trocar_de_idioma_nao_devolve_o_usuario_ao_inicio"),

    # A primeira versão deste caso renomeava o método e inseria um stub — mutação que não
    # tocava o caminho da PRIMEIRA abertura, então o teste ficava verde com razão. O defeito
    # certo é a guarda invertida: a tela nunca aparece, nem para quem nunca escolheu nada.
    ("boas-vindas somem para quem ainda não escolheu nada",
     "main.py",
     '        if not getattr(self, "_boas_vindas_dispensadas", False):',
     '        if getattr(self, "_boas_vindas_dispensadas", False):',
     "tests/test_fluxo_auditoria.py::test_boas_vindas_aparecem_na_primeira_abertura"),

    ("import do WoS volta a ler só o formato tab-delimited",
     "core/parsers.py",
     "        if self._wos_e_etiquetado():\n"
     "            raw = self._load_wos_etiquetado()\n"
     "        else:\n"
     "            raw = pd.read_csv(self.file_path, sep=\"\\t\", skiprows=1, encoding=\"utf-8-sig\")",
     '        raw = pd.read_csv(self.file_path, sep="\\t", skiprows=1, encoding="utf-8-sig")',
     "tests/test_fluxo_auditoria.py::test_wos_etiquetado_e_lido"),

    ("linha de continuação do WoS é ignorada (perde o 2º autor)",
     "core/parsers.py",
     "                if linha.startswith(\"   \") and tag:",
     "                if False and tag:",
     "tests/test_fluxo_auditoria.py::test_wos_etiquetado_junta_linhas_de_continuacao"),

    ("último registro do WoS sem ER é descartado",
     "core/parsers.py",
     "        if atual:                      # arquivo sem `ER` no último registro\n"
     "            registros.append(atual)",
     "        pass",
     "tests/test_fluxo_auditoria.py::test_ultimo_registro_sem_ER_nao_e_descartado"),

    ("cabeçalho FN/VR do WoS vira registro fantasma",
     "core/parsers.py",
     '                    if tag in ("FN", "VR"):\n'
     "                        tag = None\n"
     "                        continue",
     "                    pass",
     "tests/test_fluxo_auditoria.py::test_cabecalho_do_arquivo_nao_vira_registro"),

    ("aba órfã deixa de ser detectada",
     "main.py",
     '            "review":  self._build_tab_review(),',
     '            "review_ORFA":  self._build_tab_review(),',
     "tests/test_navegacao_abas.py::test_switch_tab_so_usa_abas_que_existem"),

    # ── Etapa 2: migração das citações ambíguas de projeto antigo ──
    ("carga deixa de migrar o citations_mean ambíguo",
     "core/project.py",
     '    migrar_citacoes_ambiguas(result.get("G"), result.get("df"))',
     "    pass",
     "tests/test_migracao_citacoes.py::test_projeto_antigo_recupera_a_citacao_que_o_grafo_perdeu"),

    ("migração inventa citação onde havia zero de verdade",
     "core/project.py",
     "    ambiguos = _nos_com_citacao_zero(G)",
     "    ambiguos = set(G.nodes())",
     "tests/test_migracao_citacoes.py::test_so_os_nos_ambiguos_sao_recalculados"),

    ("filtro de subconjunto do compute_overlay_scores deixa de valer",
     "core/matrix_builders.py",
     "        for node in (self.G.nodes if apenas is None else [n for n in self.G.nodes if n in apenas]):",
     "        for node in self.G.nodes:",
     "tests/test_migracao_citacoes.py::test_compute_overlay_scores_respeita_o_subconjunto"),

    ("falha da migração volta a derrubar a carga do projeto",
     "core/project.py",
     "    except Exception as e:\n"
     '        # Projeto que abre com métrica velha é melhor do que projeto que não abre. A carga',
     "    except ZeroDivisionError as e:\n"
     '        # Projeto que abre com métrica velha é melhor do que projeto que não abre. A carga',
     "tests/test_migracao_citacoes.py::test_falha_da_migracao_nao_impede_o_projeto_de_abrir"),

    # ── Etapa 3: código sem chamador ──
    ("botão da análise seminal some da tela",
     "main.py",
     "            font=ctk.CTkFont(weight=\"bold\"), command=self._trigger_seminal_insights",
     "            font=ctk.CTkFont(weight=\"bold\"), command=lambda: None",
     "tests/test_analise_seminal_ligada.py::test_o_botao_esta_na_tela_e_aponta_para_o_gatilho"),

    ("resposta seminal deixa de chegar ao painel",
     "main.py",
     "        self.after(0, self._show_seminal_insights, texto)",
     "        pass",
     "tests/test_analise_seminal_ligada.py::test_o_botao_leva_a_resposta_do_modelo_ate_o_painel"),

    # O trecho tem de ser ÚNICO no arquivo: os dois ramos do tratador são idênticos linha a
    # linha, e a primeira versão deste caso casava com zero ocorrências (a mutação nem era
    # aplicada). Ancorar no comentário que só existe no ramo do AIClientError resolve.
    ("erro sem chave volta a fechar sobre a variável do except",
     "main.py",
     "            # usuário sem chave não recebia aviso nenhum.\n"
     "            self.after(0, self._set_idle, t(\"seminal.erro\"))\n"
     "            self.after(0, lambda erro=e: messagebox.showerror(t(\"ai.error_title\"), str(erro)))",
     "            # usuário sem chave não recebia aviso nenhum.\n"
     "            self.after(0, self._set_idle, t(\"seminal.erro\"))\n"
     "            self.after(0, lambda: messagebox.showerror(t(\"ai.error_title\"), str(e)))",
     "tests/test_analise_seminal_ligada.py::test_sem_chave_de_ia_recusa_sem_traceback"),

    ("análise e biblioteca voltam a contar referências de jeitos diferentes",
     "main.py",
     "            top_refs = self._top_referencias()\n            if not top_refs:",
     "            top_refs = self._top_referencias(5)\n            if not top_refs:",
     "tests/test_analise_seminal_ligada.py::test_analise_e_biblioteca_partem_da_mesma_lista"),

    ("botões de animação e pôster somem da aba de exportação",
     "main.py",
     "            font=ctk.CTkFont(weight=\"bold\"), command=self._export_map_animation",
     "            font=ctk.CTkFont(weight=\"bold\"), command=lambda: None",
     "tests/test_exportacao_animacao_ligada.py::test_os_dois_botoes_estao_na_tela"),

    ("exportar sem mapa volta a abrir o diálogo de arquivo",
     "main.py",
     "        if not self._mapa_pronto():\n            return\n        caminho = filedialog.asksaveasfilename(\n"
     "            defaultextension=\".gif\",",
     "        if False:\n            return\n        caminho = filedialog.asksaveasfilename(\n"
     "            defaultextension=\".gif\",",
     "tests/test_exportacao_animacao_ligada.py::test_sem_mapa_avisa_e_nao_abre_dialogo"),

    ("sem ffmpeg o app deixa de gravar o GIF alternativo",
     "main.py",
     "                    alternativa = destino.with_suffix(\".gif\")\n"
     "                    export_gif(imagens, str(alternativa))",
     "                    alternativa = destino.with_suffix(\".gif\")",
     "tests/test_exportacao_animacao_ligada.py::test_sem_ffmpeg_grava_gif_no_lugar_do_mp4"),

    ("corpus sem ano volta a gerar arquivo vazio em silêncio",
     "main.py",
     "            if not quadros:",
     "            if False:",
     "tests/test_exportacao_animacao_ligada.py::test_corpus_sem_ano_explica_em_vez_de_gerar_arquivo_vazio"),

    # ── Etapa 4: markdown, mensagens de erro, estados de busca ──
    ("asterisco de multiplicação volta a sumir do texto",
     "core/markdown_parser.py",
     r'    r"|\*(?=\S)(?:[^*]*?\S)?\*"           # *itálico*, sem espaço colado ao asterisco',
     r'    r"|\*.*?\*"                            # *itálico*',
     "tests/test_markdown_parser.py::test_asterisco_de_multiplicacao_nao_some_do_texto"),

    ("bloco cercado volta a vazar a crase para o texto",
     "core/markdown_parser.py",
     "        if line.lstrip().startswith(CERCA):",
     "        if False:",
     "tests/test_markdown_parser.py::test_bloco_cercado_sai_inteiro_e_sem_a_cerca"),

    ("negrito+itálico volta a deixar asterisco solto",
     "core/markdown_parser.py",
     "            if part.startswith(\"***\") and part.endswith(\"***\"):",
     "            if False:",
     "tests/test_markdown_parser.py::test_negrito_e_italico_juntos"),

    ("fonte em tupla volta a derrubar a configuração das tags",
     "core/markdown_parser.py",
     '    if not hasattr(base_font, "cget"):',
     "    if isinstance(base_font, str):",
     "tests/test_markdown_parser.py::test_configure_aceita_caixa_com_fonte_em_string"),

    ("erro de projeto volta a mostrar a mensagem da biblioteca",
     "main.py",
     "        messagebox.showerror(titulo, t(chave))",
     "        messagebox.showerror(titulo, str(erro))",
     "tests/test_mensagens_de_erro_projeto.py::test_a_mensagem_sai_traduzida_e_sem_jargao"),

    ("detalhe técnico do projeto deixa de ir para o log",
     "main.py",
     '        log.info(f"[ERRO] {type(erro).__name__}: {erro}  → {chave}\\n")',
     "        pass",
     "tests/test_mensagens_de_erro_projeto.py::test_o_detalhe_tecnico_vai_para_o_log_e_nao_some"),

    ("dataset corrompido volta ao diagnóstico genérico",
     "core/project.py",
     '    (gzip.BadGzipFile, "projeto.erro_corrompido"),',
     "    ",
     "tests/test_mensagens_de_erro_projeto.py::test_cada_falha_tem_diagnostico_proprio"),

    ("rede caída volta a mostrar o Errno na tela",
     "main.py",
     '            self.after(0, lambda c=chave: messagebox.showerror(t("busca.erro_titulo"), t(c)))',
     '            self.after(0, lambda e_msg=str(e): messagebox.showerror("Erro na busca", e_msg))',
     "tests/test_busca_estados_de_erro.py::test_rede_caida_explica_em_vez_de_mostrar_errno"),

    ("limite de taxa passa a ser diagnosticado como falta de conexão",
     "core/sources/base.py",
     "    if isinstance(erro, urllib.error.HTTPError):",
     "    if False:",
     "tests/test_busca_estados_de_erro.py::test_cada_falha_de_busca_tem_diagnostico_proprio"),

    ("busca sem resultados volta ao português fixo",
     "main.py",
     '                        t("busca.sem_resultado_titulo"), t("busca.sem_resultado")))',
     '                        "Busca concluída", "Nenhum registro encontrado para essa busca."))',
     "tests/test_busca_estados_de_erro.py::test_busca_sem_resultados_avisa_e_orienta"),

    # ── Auditoria 2, Fase 1: segurança ──
    ("fórmula volta a sair executável no CSV",
     "core/nlp.py",
     "    return PREFIXO_SEGURO + valor if valor.startswith(GATILHOS_DE_FORMULA) else valor",
     "    return valor",
     "tests/test_seguranca.py::test_export_csv_nao_carrega_celula_executavel"),

    ("neutralização volta a depender do dtype do pandas",
     "core/nlp.py",
     "        seguro[coluna] = seguro[coluna].map(neutralizar_formula)",
     "        if seguro[coluna].dtype == object:\n"
     "            seguro[coluna] = seguro[coluna].map(neutralizar_formula)",
     "tests/test_seguranca.py::test_neutralizacao_nao_depende_do_dtype_do_pandas"),

    ("token do bridge volta a ser comparado com ==",
     "core/bridge.py",
     "        return hmac.compare_digest(token, self.bridge_token)",
     "        return token == self.bridge_token",
     "tests/test_seguranca.py::test_comparacao_de_token_e_em_tempo_constante"),

    ("bridge volta a alocar o corpo que o cliente pedir",
     "core/bridge.py",
     "        if content_length < 0 or content_length > LIMITE_CORPO_BYTES:",
     "        if False:",
     "tests/test_seguranca.py::test_payload_gigante_e_recusado_sem_ser_lido"),

    ("Content-Length inválido volta a derrubar o handler",
     "core/bridge.py",
     "            content_length = int(self.headers.get('Content-Length', 0) or 0)\n"
     "        except (TypeError, ValueError):",
     "            content_length = int(self.headers.get('Content-Length', 0) or 0)\n"
     "        except ZeroDivisionError:",
     "tests/test_seguranca.py::test_content_length_invalido_nao_derruba_o_handler"),

    ("JSON profundo volta a ser aceito",
     "core/bridge.py",
     "        if profundidade_json(data) > PROFUNDIDADE_MAXIMA_JSON:",
     "        if False:",
     "tests/test_seguranca.py::test_json_profundo_e_recusado"),

    ("limitador de taxa do bridge deixa de valer",
     "core/bridge.py",
     "        if not self._dentro_do_limite_de_taxa():",
     "        if False:",
     # O defeito muta o PONTO DE CHAMADA no handler HTTP; `test_limite_de_taxa_dispara`
     # exercita a REGRA isolada, chamando `_dentro_do_limite_de_taxa()` direto, e por isso
     # continuava verde. Não era cobertura ausente: era mira errada. Medido com o defeito
     # injetado — o de unidade passa, este falha.
     "tests/test_seguranca.py::test_limite_de_taxa_responde_429_pela_rede"),

    ("CORS volta a ecoar qualquer origem",
     "core/bridge.py",
     '            self.send_header("Access-Control-Allow-Origin", "null")',
     '            self.send_header("Access-Control-Allow-Origin", origin)',
     "tests/test_seguranca.py::test_cors_nao_libera_origem_arbitraria"),

    ("zip bomb volta a ser descomprimido na memória",
     "core/project.py",
     "    if info.file_size > LIMITE_ENTRADA_BYTES:",
     "    if False:",
     "tests/test_seguranca.py::test_zip_bomb_e_recusado_antes_de_descomprimir"),

    ("chamada ao Zotero volta a ficar sem timeout",
     "core/sources/zotero.py",
     "            with urllib.request.urlopen(req, timeout=30) as res:",
     "            with urllib.request.urlopen(req) as res:",
     "tests/test_seguranca.py::test_toda_chamada_de_rede_tem_timeout"),
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

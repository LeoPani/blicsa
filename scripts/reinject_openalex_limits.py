#!/usr/bin/env python3
"""Reinjeta cada defeito e confirma que o teste correspondente fica VERMELHO.

Um teste que continua verde com o defeito de volta não protege nada. Cada caso aqui é
(arquivo, trecho original, trecho defeituoso, teste que tem que quebrar).
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path("/Users/leopani/PyBibliomics")

#: Segundos por caso. Generoso para o teste mais pesado, curto o bastante para
#: que um laço infinito seja detectado em vez de travar a suíte.
TIMEOUT_S = 90

CASOS = [
    ("teto de 1000 no campo vazio volta",
     "main.py",
     "        try:\n            n = int(self._search_max_entry.get().strip())\n"
     "        except (ValueError, TypeError, AttributeError):\n            return UNLIMITED\n"
     "        return n if n >= 1 else UNLIMITED",
     "        try:\n            n = int(self._search_max_entry.get().strip() or '1000')\n"
     "        except (ValueError, TypeError, AttributeError):\n            return 1000\n"
     "        return n if n >= 1 else 1000",
     "tests/test_sort_count.py::test_qtd_vazio_e_ilimitado_de_verdade"),

    ("importação volta a usar paginação numerada",
     "core/sources/openalex.py",
     '            "cursor": "*",',
     '            "page": 1,',
     "tests/test_openalex_limits.py::test_importacao_nunca_manda_o_parametro_page"),

    ("guarda do cursor repetido some (risco de laço infinito)",
     "core/sources/openalex.py",
     'if not next_cursor or next_cursor == params.get("cursor"):',
     'if not next_cursor:',
     "tests/test_openalex_limits.py::test_importacao_nao_entra_em_laco_com_cursor_repetido"),

    ("pré-cheque do teto de navegação some",
     "core/sources/openalex.py",
     "        if self.BROWSE_MAX_RESULTS and pg * pp > self.BROWSE_MAX_RESULTS:\n"
     "            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pg, pp, self.DISPLAY_NAME)\n",
     "",
     "tests/test_openalex_limits.py::test_teto_nao_gasta_requisicao"),

    ("guarda vira >= e recusa a página 400 legítima",
     "core/sources/openalex.py",
     "if self.BROWSE_MAX_RESULTS and pg * pp > self.BROWSE_MAX_RESULTS:",
     "if self.BROWSE_MAX_RESULTS and pg * pp >= self.BROWSE_MAX_RESULTS:",
     "tests/test_openalex_limits.py::test_pagina_400_passa_e_401_avisa"),

    ("400 da API volta a virar erro genérico",
     "core/sources/openalex.py",
     "            if e.code == 400:\n"
     "                raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pg, pp, self.DISPLAY_NAME) from e\n",
     "",
     "tests/test_openalex_limits.py::test_http_400_da_api_vira_a_mesma_mensagem"),

    ("qualquer erro HTTP vira 'refine sua busca'",
     "core/sources/openalex.py",
     "            if e.code == 400:",
     "            if e.code in (400, 404, 500):",
     "tests/test_openalex_limits.py::test_outros_erros_http_nao_viram_limite_de_pagina"),

    ("total some do estado de erro",
     "core/browse.py",
     "                        total=self.total, error=str(e), error_key=error_i18n_key(e),\n"
     "                        error_args=error_i18n_args(e), browse_max=self.browse_max)",
     "                        error=str(e), error_key=error_i18n_key(e),\n"
     "                        error_args=error_i18n_args(e), browse_max=self.browse_max)",
     "tests/test_openalex_limits.py::test_paginator_devolve_a_mensagem_e_mantem_o_total"),

    ("mensagem vira erro genérico",
     "locales/pt_BR.json",
     "O {fonte} permite navegar até 10.000 resultados por busca. Esta busca tem mais do "
     "que isso, mas as páginas seguintes não podem ser abertas. Refine a busca com os "
     "filtros da lateral para chegar ao que procura, ou importe o conjunto completo — a "
     "importação não tem esse limite e traz todos os registros para análise.",
     "Erro ao carregar a página.",
     "tests/test_openalex_limits.py::test_mensagem_existe_nos_tres_idiomas_e_diz_o_que_fazer"),

    ("mensagem perde SÓ a sugestão de importar",
     "locales/pt_BR.json",
     "ou importe o conjunto completo — a "
     "importação não tem esse limite e traz todos os registros para análise.",
     "e tente de novo.",
     "tests/test_openalex_limits.py::test_mensagem_existe_nos_tres_idiomas_e_diz_o_que_fazer"),
    # ── Pager: anunciar só páginas navegáveis ──
    ("pager volta a anunciar as páginas teóricas",
     "core/browse.py",
     """        if self.browse_max <= 0:
            return self.pages
        teto = max(1, self.browse_max // max(1, self.per_page))
        return max(1, min(self.pages, teto))""",
     "        return self.pages",
     "tests/test_openalex_limits.py::test_pager_anuncia_paginas_navegaveis_nao_as_teoricas"),

    ("teto do provider não chega mais à Page",
     "core/browse.py",
     "self.browse_max = int(getattr(provider, \"BROWSE_MAX_RESULTS\", 0) or 0)",
     "self.browse_max = 0",
     "tests/test_openalex_limits.py::test_sessao_propaga_o_teto_para_a_pagina"),

    ("busca pequena passa a ser marcada como cortada",
     "core/browse.py",
     "        return self.navigable_pages < self.pages",
     "        return self.browse_max > 0",
     "tests/test_openalex_limits.py::test_pager_busca_pequena_nao_e_cortada"),

    # ── PubMed: teto silencioso do retmax ──
    ("PubMed volta a pedir a lista inteira de PMIDs (teto de 10.000)",
     "core/sources/pubmed.py",
     """            "usehistory": "y",
            "retmax": 0,""",
     '            "retmax": max_results,',
     "tests/test_pubmed_limits.py::test_esearch_pede_historico_e_nao_pede_pmids"),

    ("EFetch do PubMed para de paginar pelo histórico",
     "core/sources/pubmed.py",
     """            if webenv and query_key:
                efetch_params["WebEnv"] = webenv
                efetch_params["query_key"] = query_key""",
     """            if False:
                pass""",
     "tests/test_pubmed_limits.py::test_efetch_pagina_pelo_historico"),

    ("saída por lote vazio some (laço infinito no PubMed)",
     "core/sources/pubmed.py",
     """            if not brutos:""",
     """            if False:""",
     "tests/test_pubmed_limits.py::test_efetch_vazio_no_meio_nao_vira_laco_infinito"),

    ("degradação sem histórico volta a ser silenciosa",
     "core/sources/pubmed.py",
     """            self.stop_reason = self.stop_reason or (
                "histórico do PubMed indisponível (sem WebEnv/QueryKey): "
                "o NCBI limita a 10.000 registros sem ele")""",
     "            pass",
     "tests/test_pubmed_limits.py::test_sem_historico_degrada_mas_diz_que_degradou"),

    ("fim de conjunto volta a se disfarçar de 'atingiu limite'",
     "core/sources/pubmed.py",
     '''self.stop_reason = ("atingiu limite" if count_fetched >= int(max_results)''',
     '''self.stop_reason = ("atingiu limite" if count_fetched >= alvo''',
     "tests/test_pubmed_limits.py::test_base_menor_que_o_pedido_para_sem_laco"),

    ("navegação do PubMed perde o teto e a mensagem",
     "core/sources/pubmed.py",
     """        if self.BROWSE_MAX_RESULTS and pagina * por_pagina > self.BROWSE_MAX_RESULTS:
            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pagina, por_pagina,
                                       self.DISPLAY_NAME)
""",
     "",
     "tests/test_pubmed_limits.py::test_navegacao_declara_teto_e_avisa_na_fronteira"),

    ("mensagem passa a nomear a fonte errada",
     "core/sources/pubmed.py",
     """            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pagina, por_pagina,
                                       self.DISPLAY_NAME)""",
     """            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pagina, por_pagina,
                                       "OpenAlex")""",
     "tests/test_pubmed_limits.py::test_mensagem_nomeia_a_fonte_certa"),
    ("truncagem pela API volta a ser silenciosa",
     "core/sources/pubmed.py",
     """            if self.truncated_by_api and count_fetched >= alvo:""",
     """            if False:""",
     "tests/test_pubmed_limits.py::test_teto_da_api_e_9999_e_nao_e_silencioso"),

    ("teto do PubMed some e a colheita tenta passar dos 9.999",
     "core/sources/pubmed.py",
     """            self.truncated_by_api = True
            alvo = PUBMED_MAX_FETCHABLE""",
     """            self.truncated_by_api = False""",
     "tests/test_pubmed_limits.py::test_fronteira_exata_do_teto"),
]


def main() -> int:
    falhas = []
    with tempfile.TemporaryDirectory() as tmp:
        backup = pathlib.Path(tmp)
        for arq in {c[1] for c in CASOS}:
            destino = backup / arq.replace("/", "__")
            shutil.copy2(RAIZ / arq, destino)

        for nome, arq, original, defeito, teste in CASOS:
            caminho = RAIZ / arq
            texto = caminho.read_text(encoding="utf-8")
            if original not in texto:
                print(f"  [SETUP RUIM] {nome}: trecho original não encontrado em {arq}")
                falhas.append(nome)
                continue
            caminho.write_text(texto.replace(original, defeito, 1), encoding="utf-8")

            # Timeout obrigatório: um dos defeitos reinjetados é justamente a remoção da
            # saída de um laço. Sem limite, o pytest roda para sempre e a ferramenta que
            # deveria detectar o defeito trava junto com ele — travar É o sintoma, então
            # estouro de tempo conta como VERMELHO.
            try:
                r = subprocess.run([sys.executable, "-m", "pytest", teste, "-q", "--no-header"],
                                   cwd=RAIZ, capture_output=True, text=True, timeout=TIMEOUT_S)
                vermelho = r.returncode != 0
                motivo = "ficou VERMELHO" if vermelho else "continuou VERDE"
            except subprocess.TimeoutExpired:
                vermelho = True
                motivo = f"TRAVOU (>{TIMEOUT_S}s) — o laço infinito se manifestou"

            shutil.copy2(backup / arq.replace("/", "__"), caminho)

            marca = "OK  " if vermelho else "FURO"
            print(f"  [{marca}] {nome}")
            print(f"         → {teste.split('::')[-1]}: {motivo} "
                  f"{'✓' if vermelho else '✗'}", flush=True)
            if not vermelho:
                falhas.append(nome)

    print()
    if falhas:
        print(f"{len(falhas)} teste(s) NÃO protegem o que deveriam:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print(f"Todos os {len(CASOS)} defeitos reinjetados foram detectados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

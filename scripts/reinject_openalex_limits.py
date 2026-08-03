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
     "            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pg, pp)\n",
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
     "                raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pg, pp) from e\n",
     "",
     "tests/test_openalex_limits.py::test_http_400_da_api_vira_a_mesma_mensagem"),

    ("qualquer erro HTTP vira 'refine sua busca'",
     "core/sources/openalex.py",
     "            if e.code == 400:",
     "            if e.code in (400, 404, 500):",
     "tests/test_openalex_limits.py::test_outros_erros_http_nao_viram_limite_de_pagina"),

    ("total some do estado de erro",
     "core/browse.py",
     "                        total=self.total, error=str(e), error_key=error_i18n_key(e))",
     "                        error=str(e), error_key=error_i18n_key(e))",
     "tests/test_openalex_limits.py::test_paginator_devolve_a_mensagem_e_mantem_o_total"),

    ("mensagem vira erro genérico",
     "locales/pt_BR.json",
     "O OpenAlex permite navegar até 10.000 resultados por busca. Esta busca tem mais do "
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

            r = subprocess.run([sys.executable, "-m", "pytest", teste, "-q", "--no-header"],
                               cwd=RAIZ, capture_output=True, text=True)
            vermelho = r.returncode != 0

            shutil.copy2(backup / arq.replace("/", "__"), caminho)

            marca = "OK  " if vermelho else "FURO"
            print(f"  [{marca}] {nome}")
            print(f"         → {teste.split('::')[-1]}: "
                  f"{'ficou VERMELHO ✓' if vermelho else 'continuou VERDE ✗'}")
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

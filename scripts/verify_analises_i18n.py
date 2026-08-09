#!/usr/bin/env python3
"""Prova, com chamada REAL ao modelo, que as análises respondem no idioma da interface.

Existe porque a suíte não consegue provar isto. `tests/test_analises_i18n.py` afirma que o
`system_prompt` **pede** resposta em francês; só uma chamada de verdade mostra que a resposta
**vem** em francês. A distinção não é teórica: os seis defeitos de 08/08 estavam todos sob uma
suíte verde, e apareceram no primeiro contato com o provedor.

Como `scripts/capture_ia_marcacao.py`, este script **recusa** rodar sem chave utilizável, em
vez de imprimir um relatório que parece bom.

    python3 scripts/verify_analises_i18n.py

A chave sai de `core.settings.get_api_key()` — a mesma precedência do app (env → keyring →
settings.json), para que o que é verificado seja o que o usuário roda.
"""
from __future__ import annotations

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ai.client import AIClientError, AIAnalyst  # noqa: E402
from core import i18n  # noqa: E402
from core.research_context import NOMES_IDIOMA  # noqa: E402
from core.settings import get_api_key  # noqa: E402

IDIOMAS = ("pt_BR", "en", "fr")

#: Entrada em inglês de propósito. Se o corpus estivesse em português, uma resposta em
#: português não distinguiria "seguiu a diretiva" de "copiou a língua do material".
QUADRANTES = (
    "Motor theme: waste picker cooperatives (centrality 0.81, density 0.74)\n"
    "Niche theme: informal recycling metrics (centrality 0.22, density 0.88)\n"
    "Emerging theme: circular economy policy (centrality 0.19, density 0.21)"
)

FLUXO = "Silva -> waste picking -> Waste Management; Costa -> informality -> Habitat Intl"
CITACOES = "Freire 1968 -> Santos 1995 -> Dias 2011"
REFERENCIAS = "Freire, P. (1968) Pedagogia do Oprimido; Ostrom, E. (1990) Governing the Commons"

ANALISES = {
    "generate_insights": lambda a: a.generate_insights(
        [("waste picking", 31), ("informality", 22)], {"docs": 200}),
    "generate_sankey_insights": lambda a: a.generate_sankey_insights(FLUXO),
    "generate_thematic_insights": lambda a: a.generate_thematic_insights(QUADRANTES),
    "generate_historiograph_insights": lambda a: a.generate_historiograph_insights(CITACOES),
    "generate_seminal_insights": lambda a: a.generate_seminal_insights(REFERENCIAS),
    "label_clusters": lambda a: a.label_clusters(
        [{"cluster_id": 0, "top_nodes": ["waste", "recycling", "cooperative"]},
         {"cluster_id": 1, "top_nodes": ["policy", "governance", "informality"]}]),
}

#: Marcadores de língua: palavras funcionais frequentes e **exclusivas** de cada idioma na
#: prática deste texto. Heurística declarada, não medição — o veredito final é a leitura da
#: amostra impressa, que é justamente por isso que ela é impressa.
MARCAS = {
    "pt_BR": (r"\b(?:são|não|também|pesquisa|dos|das|temas?|análise)\b", "português"),
    "en": (r"\b(?:the|research|themes?|analysis|these|with)\b", "inglês"),
    "fr": (r"\b(?:les|des|recherche|thèmes?|analyse|cette|avec)\b", "francês"),
}


def _idioma_aparente(texto: str) -> str:
    pontos = {lang: len(re.findall(rx, texto, re.I)) for lang, (rx, _) in MARCAS.items()}
    vencedor = max(pontos, key=pontos.get)
    return vencedor if pontos[vencedor] else "?"


def main() -> int:
    chave = get_api_key()
    if not chave:
        print("SEM CHAVE — configure a chave nos Ajustes do Blicsa e rode de novo.\n"
              "Nenhuma verificação foi feita.")
        return 2

    print(f"Chave: {chave[:6]}…{chave[-4:]}  ·  {len(IDIOMAS)} idiomas × "
          f"{len(ANALISES)} análises = {len(IDIOMAS) * len(ANALISES)} chamadas reais\n")

    # Duas listas, nunca uma. "A chamada não chegou ao provedor" e "a resposta veio na língua
    # errada" são achados diferentes, e misturá-los produziria o mesmo diagnóstico mentiroso
    # que o 403 sem User-Agent produzia ao ser classificado como "chave recusada".
    furos: list[str] = []
    erros: list[str] = []

    idioma_anterior = i18n.get_lang()
    try:
        for lang in IDIOMAS:
            i18n.load_locales(lang)  # não persiste: não mexe no idioma escolhido pelo usuário
            esperado = MARCAS[lang][1]
            print(f"── {lang} ({NOMES_IDIOMA[lang]}) " + "─" * 40)
            for nome in ANALISES:
                analista = AIAnalyst(api_key=chave)
                try:
                    saida = ANALISES[nome](analista)
                except AIClientError as e:
                    print(f"  [ERRO] {nome}: {e}")
                    erros.append(f"{lang}/{nome}: {e}")
                    # Erro de transporte não diz nada sobre idioma. Insistir nas 17 chamadas
                    # seguintes só gastaria a cota do usuário para repetir a mesma linha.
                    if len(erros) >= 3 and not furos:
                        print("\nTrês chamadas seguidas falharam antes de chegar ao modelo — "
                              "abortando.\nNada foi verificado sobre idioma.")
                        return 2
                    continue
                texto = saida if isinstance(saida, str) else " ".join(map(str, saida.values()))
                visto = _idioma_aparente(texto)
                ok = visto == lang
                amostra = re.sub(r"[#*`\n]+", " ", texto).strip()[:110]
                print(f"  [{'OK  ' if ok else 'FURO'}] {nome}: saiu em {MARCAS.get(visto, ('', visto))[1]}"
                      f" (esperado {esperado})\n         {amostra}…")
                if not ok:
                    furos.append(f"{lang}/{nome}: saiu em {visto}, esperado {lang}")
            print()
    finally:
        i18n.load_locales(idioma_anterior)

    verificadas = len(IDIOMAS) * len(ANALISES) - len(erros)

    if erros:
        print(f"{len(erros)} chamada(s) não chegaram ao modelo — sobre estas, NADA foi "
              f"verificado sobre idioma:")
        for e in erros:
            print(f"  - {e}")
        print()

    if furos:
        print(f"{len(furos)} análise(s) NÃO respeitaram o idioma da interface:")
        for f in furos:
            print(f"  - {f}")
        return 1

    if not verificadas:
        print("Nenhuma chamada completou. Verificação NÃO realizada.")
        return 2

    print(f"{verificadas} chamada(s) completaram e todas responderam no idioma da interface.")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())

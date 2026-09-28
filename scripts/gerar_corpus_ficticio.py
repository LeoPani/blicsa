#!/usr/bin/env python3
"""Gera um corpus bibliográfico FICTÍCIO nos formatos de export do Scopus (CSV) e do
Web of Science (plain text etiquetado), para testar o import do Blicsa à mão.

Nada aqui é real: autores, periódicos, títulos e resumos são inventados, e os DOIs usam
o prefixo 10.5555, reservado pela DOI Foundation para testes — nenhum resolve.

O corpus é construído para ter *estrutura*, não só volume:

- 4 clusters temáticos de palavras-chave, para o mapa de co-ocorrência ter comunidades;
- coautoria com grupos estáveis e alguns autores-ponte entre clusters;
- 2014–2025 com volume crescente, para a linha do tempo e a animação terem o que mostrar;
- referências internas ao próprio corpus (cada trabalho cita trabalhos anteriores), para
  a rede de cocitação não sair vazia;
- citações correlacionadas com idade e com quantas vezes o trabalho é citado dentro do
  corpus, em vez de números aleatórios;
- sobreposição deliberada entre os dois arquivos, para exercitar as três passadas do
  `find_duplicates`: 8 trabalhos com o MESMO DOI nos dois arquivos, 1 par de título quase
  igual sem DOI, e 1 par mesmo-autor-mesmo-ano.

Uso:
    python3 scripts/gerar_corpus_ficticio.py [--saida exemplos] [--seed 20260818]
"""
from __future__ import annotations

import argparse
import csv
import difflib
import random
import re
from pathlib import Path

SEED_PADRAO = 20260818

# ── Vocabulário temático ────────────────────────────────────────────────────
# Cada cluster é (nome, palavras-chave, cabeças de título, caudas de título, termos de resumo).
CLUSTERS = [
    {
        "nome": "visao_embarcada",
        "keywords": [
            "computer vision", "deep learning", "TinyML", "object detection",
            "edge inference", "model quantization", "convolutional neural networks",
            "embedded systems",
        ],
        "cabecas": [
            "Lightweight convolutional networks", "Quantized object detectors",
            "On-device inference pipelines", "TinyML architectures",
            "Real-time semantic segmentation", "Energy-aware vision models",
            "Edge-cloud offloading strategies", "Self-supervised feature learning",
        ],
        "caudas": [
            "for wearable cameras", "on microcontroller-class hardware",
            "in low-power assistive devices", "under constrained memory budgets",
            "for continuous scene understanding", "in embedded vision pipelines",
        ],
        "topico": "how compact vision models can run within the power and memory envelope of wearable hardware",
        "metodo": "train a family of quantized detectors and profile them on microcontroller-class boards",
        "avaliacao": "latency, energy draw and detection accuracy on an indoor scene benchmark",
        "resultado": "8-bit quantization preserves most of the accuracy while cutting inference time by roughly half",
    },
    {
        "nome": "tecnologia_assistiva",
        "keywords": [
            "assistive technology", "visual impairment", "assisted navigation",
            "orientation and mobility", "universal design", "usability",
            "independent living", "rehabilitation",
        ],
        "cabecas": [
            "Assistive navigation systems", "Wayfinding support",
            "Obstacle detection aids", "User-centred design",
            "Participatory design practices", "Longitudinal adoption studies",
            "Accessibility guidelines", "Orientation and mobility training",
        ],
        "caudas": [
            "for people with visual impairment", "in urban public transport",
            "in indoor environments", "for older adults with low vision",
            "in rehabilitation centres", "for independent living",
        ],
        "topico": "how assistive navigation devices are actually adopted outside the laboratory",
        "metodo": "follow a cohort of participants through a structured orientation and mobility programme",
        "avaliacao": "task completion, perceived autonomy and abandonment rates over six months",
        "resultado": "sustained use depends far more on training and fit than on sensor accuracy",
    },
    {
        "nome": "interacao_multimodal",
        "keywords": [
            "spatial audio", "haptic feedback", "multimodal interfaces",
            "sonification", "human-computer interaction", "cognitive load",
            "sensory substitution", "wearable interfaces",
        ],
        "cabecas": [
            "Spatial audio feedback", "Haptic vibrotactile cues",
            "Multimodal interface design", "Sonification strategies",
            "Cognitive load assessment", "Cross-modal attention studies",
            "Audio-tactile substitution",
        ],
        "caudas": [
            "in wearable guidance devices", "for scene description interfaces",
            "during pedestrian navigation", "in head-mounted assistive systems",
            "for real-time obstacle alerts", "under divided-attention conditions",
        ],
        "topico": "how audio and tactile channels compete for attention when a device narrates the surroundings",
        "metodo": "compare sonification schemes against vibrotactile encodings in a within-subject experiment",
        "avaliacao": "reaction time, route deviation and NASA-TLX cognitive load scores",
        "resultado": "sparse tactile cues outperform continuous audio once the environment gets noisy",
    },
    {
        "nome": "avaliacao_politicas",
        "keywords": [
            "technology assessment", "cost-effectiveness", "public policy",
            "technology transfer", "intellectual property", "innovation ecosystems",
            "health economics", "public procurement",
        ],
        "cabecas": [
            "Health technology assessment", "Cost-effectiveness analysis",
            "Randomised evaluation", "Technology transfer pathways",
            "Intellectual property strategies", "Public procurement policies",
            "Regulatory frameworks",
        ],
        "caudas": [
            "of assistive wearable devices", "in public health systems",
            "for low-cost assistive technology", "in emerging innovation ecosystems",
            "for university spin-offs", "under constrained public budgets",
        ],
        "topico": "what it costs a public health system to deploy assistive wearables at scale",
        "metodo": "build a decision-analytic model calibrated with procurement data from three regions",
        "avaliacao": "incremental cost per quality-adjusted life year and budget impact over five years",
        "resultado": "locally manufactured devices reach acceptable thresholds where imported ones do not",
    },
]

# ── Periódicos fictícios ────────────────────────────────────────────────────
# (título completo, abreviação estilo WoS, slug do DOI, cluster preferencial)
PERIODICOS = [
    ("Journal of Embedded Vision Systems", "J EMBED VIS SYST", "jevs", 0),
    ("Sensors and Wearable Computing", "SENSOR WEARABLE COMPUT", "swc", 0),
    ("Assistive Technology Letters", "ASSIST TECHNOL LETT", "atl", 1),
    ("Frontiers in Accessible Computing", "FRONT ACCESS COMPUT", "fac", 1),
    ("Journal of Multimodal Interfaces", "J MULTIMODAL INTERFACES", "jmi", 2),
    ("Interaction and Perception Review", "INTERACT PERCEPT REV", "ipr", 2),
    ("Technology Assessment Quarterly", "TECHNOL ASSESS Q", "taq", 3),
    ("Journal of Innovation and Public Policy", "J INNOV PUBLIC POLICY", "jipp", 3),
    ("Revista Brasileira de Tecnologia Inclusiva", "REV BRAS TECNOL INCL", "rbti", 1),
]

# ── Autores fictícios ───────────────────────────────────────────────────────
# (sobrenome, iniciais, nome por extenso, cluster de origem)
AUTORES = [
    ("Silva", "JM", "Joao M.", 0), ("Costa", "AR", "Ana R.", 0),
    ("Nakamura", "T", "Takeshi", 0), ("Oliveira", "PH", "Pedro H.", 0),
    ("Bergstrom", "K", "Karin", 0), ("Almeida", "LF", "Luiza F.", 0),
    ("Moreira", "RC", "Rafael C.", 1), ("Duarte", "MS", "Marina S.", 1),
    ("Okonkwo", "C", "Chidi", 1), ("Ferreira", "GB", "Gabriel B.", 1),
    ("Lindqvist", "EM", "Elsa M.", 1), ("Barbosa", "TA", "Thiago A.", 1),
    ("Rezende", "VL", "Vitoria L.", 1), ("Haddad", "N", "Nadia", 2),
    ("Santoro", "GP", "Giulia P.", 2), ("Menezes", "FR", "Fernanda R.", 2),
    ("Kowalski", "JZ", "Jakub Z.", 2), ("Andrade", "BM", "Bruno M.", 2),
    ("Tanaka", "YU", "Yuki U.", 2), ("Cardoso", "IS", "Isabela S.", 3),
    ("Muller", "SD", "Stefan D.", 3), ("Pereira", "AC", "Alice C.", 3),
    ("Nogueira", "DR", "Diego R.", 3), ("Ibrahim", "HA", "Hana A.", 3),
    ("Vasconcelos", "LM", "Leandro M.", 3), ("Prado", "CE", "Camila E.", 0),
    ("Ramalho", "JP", "Julio P.", 1), ("Sousa", "MV", "Mateus V.", 2),
]

# Quantos trabalhos por ano — crescente, como um campo que amadurece.
POR_ANO = {
    2014: 3, 2015: 4, 2016: 5, 2017: 6, 2018: 7, 2019: 8,
    2020: 9, 2021: 10, 2022: 11, 2023: 12, 2024: 11, 2025: 10,
}


def _iniciais_pontuadas(iniciais: str) -> str:
    """'JM' → 'J.M.' (formato de autor do Scopus)."""
    return "".join(f"{c}." for c in iniciais)


def gerar_trabalhos(rnd: random.Random) -> list[dict]:
    """Monta o pool de trabalhos únicos, já com autoria, keywords e referências internas."""
    trabalhos: list[dict] = []
    usados: set[str] = set()
    seq_por_slug: dict[str, int] = {}

    # Autores agrupados por cluster, para a coautoria ter comunidades de verdade.
    por_cluster: dict[int, list[int]] = {}
    for idx, (_, _, _, cl) in enumerate(AUTORES):
        por_cluster.setdefault(cl, []).append(idx)

    for ano, quantidade in POR_ANO.items():
        for _ in range(quantidade):
            cl = rnd.randrange(len(CLUSTERS))
            c = CLUSTERS[cl]

            # Título único: cabeça + cauda, com sufixo de recorte se já tiver saído.
            for _tentativa in range(40):
                titulo = f"{rnd.choice(c['cabecas'])} {rnd.choice(c['caudas'])}"
                if titulo not in usados:
                    break
            else:
                titulo = f"{titulo}: a follow-up study"
            usados.add(titulo)

            # Autoria: núcleo do cluster + 0-2 pontes de outro cluster.
            n_autores = rnd.randint(2, 5)
            nucleo = rnd.sample(por_cluster[cl], min(n_autores, len(por_cluster[cl])))
            equipe = list(nucleo)
            if rnd.random() < 0.45:
                outro = rnd.choice([k for k in por_cluster if k != cl])
                equipe.append(rnd.choice(por_cluster[outro]))

            # Palavras-chave: 3-4 do cluster + 1 de fora (a ponte temática do mapa).
            kws = rnd.sample(c["keywords"], rnd.randint(3, 4))
            if rnd.random() < 0.35:
                fora = CLUSTERS[rnd.choice([k for k in range(len(CLUSTERS)) if k != cl])]
                kws.append(rnd.choice(fora["keywords"]))

            candidatos = [p for p in PERIODICOS if p[3] == cl] or PERIODICOS
            titulo_per, abrev, slug, _ = rnd.choice(
                candidatos if rnd.random() < 0.75 else PERIODICOS
            )
            seq_por_slug[slug] = seq_por_slug.get(slug, 0) + 1
            doi = f"10.5555/{slug}.{ano}.{seq_por_slug[slug]:04d}"

            abstract = (
                f"This study investigates {c['topico']}. "
                f"We {c['metodo']}, and assess the approach through {c['avaliacao']}. "
                f"Findings indicate that {c['resultado']}. "
                f"We discuss the implications for {rnd.choice(c['caudas'])[3:]}."
            )

            volume = rnd.randint(3, 28)
            pagina = rnd.randint(1, 240)
            trabalhos.append({
                "id": len(trabalhos),
                "cluster": cl,
                "titulo": titulo,
                "ano": ano,
                "periodico": titulo_per,
                "abrev": abrev,
                "doi": doi,
                "autores": equipe,
                "keywords": kws,
                "abstract": abstract,
                "volume": volume,
                "issue": rnd.randint(1, 4),
                "pag_inicio": pagina,
                "pag_fim": pagina + rnd.randint(8, 24),
                "refs": [],
                "citacoes": 0,
            })

    # ── Referências internas: cada trabalho cita anteriores, de preferência do
    # mesmo cluster. É isso que dá uma rede de cocitação com comunidades.
    for t in trabalhos:
        anteriores = [o for o in trabalhos if o["ano"] < t["ano"]]
        if not anteriores:
            continue
        mesmo = [o for o in anteriores if o["cluster"] == t["cluster"]]
        outros = [o for o in anteriores if o["cluster"] != t["cluster"]]
        n = min(len(anteriores), rnd.randint(3, 8))
        n_mesmo = min(len(mesmo), max(1, int(n * 0.7)))
        escolhidos = rnd.sample(mesmo, n_mesmo)
        if outros and n - n_mesmo > 0:
            escolhidos += rnd.sample(outros, min(len(outros), n - n_mesmo))
        t["refs"] = sorted(o["id"] for o in escolhidos)
        for o in escolhidos:
            o["citacoes"] += 1

    # Citações externas: quem é citado dentro do corpus tende a ser citado fora,
    # e trabalho velho acumula mais.
    ano_max = max(POR_ANO)
    for t in trabalhos:
        idade = ano_max - t["ano"]
        base = t["citacoes"] * rnd.randint(3, 9)
        t["citacoes_total"] = int(base + idade * rnd.randint(1, 6) + rnd.randint(0, 12))

    return trabalhos


# ── Formatação por base ─────────────────────────────────────────────────────

def _autores_scopus(t: dict) -> str:
    return "; ".join(
        f"{AUTORES[i][0]} {_iniciais_pontuadas(AUTORES[i][1])}" for i in t["autores"]
    )


def _autores_wos(t: dict) -> list[str]:
    return [f"{AUTORES[i][0]}, {AUTORES[i][1]}" for i in t["autores"]]


def _autores_wos_completo(t: dict) -> list[str]:
    return [f"{AUTORES[i][0]}, {AUTORES[i][2]}" for i in t["autores"]]


def _ref_scopus(o: dict) -> str:
    """Referência no estilo do campo References do Scopus."""
    autores = "., ".join(
        f"{AUTORES[i][0]} {_iniciais_pontuadas(AUTORES[i][1])}" for i in o["autores"][:3]
    )
    return (f"{autores}, {o['titulo']}, {o['periodico']}, {o['volume']}, "
            f"pp. {o['pag_inicio']}-{o['pag_fim']}, ({o['ano']})")


def _ref_wos(o: dict) -> str:
    """Referência no estilo do campo CR do Web of Science."""
    primeiro = AUTORES[o["autores"][0]]
    return (f"{primeiro[0]} {primeiro[1]}, {o['ano']}, {o['abrev']}, "
            f"V{o['volume']}, P{o['pag_inicio']}, DOI {o['doi']}")


# ── Duplicatas plantadas ────────────────────────────────────────────────────
_ENCHIMENTO = ": a replication and extension of the original findings"


def _norm_titulo(s: str) -> str:
    """Mesma normalização do `core.parsers._norm_title`, para prever a similaridade."""
    s = re.sub(r"[^\w\s]", "", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _similaridade(a: str, b: str) -> float:
    return difflib.SequenceMatcher(
        None, _norm_titulo(a), _norm_titulo(b), autojunk=False).ratio()


def _variante(titulo: str, alvo: float) -> str:
    """Título parecido com `titulo` numa similaridade próxima de `alvo`.

    O sufixo é dimensionado pela relação `ratio ≈ 2L / (2L + N)` e depois ajustado
    caractere a caractere, para o corpus nascer com as duplicatas que ele promete —
    e não com pares que passam raspando do limiar do dedup.
    """
    base = len(_norm_titulo(titulo))
    n = max(3, round(2 * base * (1 - alvo) / alvo))
    melhor, melhor_dist = titulo, 1.0
    for delta in range(-8, 9):
        corte = n + delta
        if not 3 <= corte <= len(_ENCHIMENTO):
            continue
        sufixo = _ENCHIMENTO[:corte].rstrip()
        candidato = f"{titulo}{sufixo}"
        dist = abs(_similaridade(titulo, candidato) - alvo)
        if dist < melhor_dist:
            melhor, melhor_dist = candidato, dist
    return melhor


def plantar_duplicatas(scopus: list[dict], wos: list[dict]):
    """Prepara, no lote do WoS, os pares que exercitam as passadas 2 e 3 do dedup.

    Os dois pares ficam INTEIROS dentro do arquivo do WoS, e não cruzando os dois
    arquivos, porque `_first_surname` lê 'Silva, JM' (WoS) como "silva" e
    'Silva J.M.' (Scopus) como "silva j.m." — a passada 3 não cruza as duas bases.
    Ver a seção de achados no README ao lado.
    """
    compartilhados = {t["doi"] for t in scopus}
    livres = [i for i, t in enumerate(wos) if t["doi"] not in compartilhados]

    # Passada 2 — título ~96% igual, MESMO ano, e sem DOI nos dois: o par vira o único
    # bucket sem DOI do arquivo, então o dedup compara exatamente estes dois.
    # O original é substituído por uma cópia sem DOI (em vez de alterado no lugar) para
    # não apagar o DOI das referências que outros trabalhos fazem a ele.
    i_a = livres[len(livres) // 3]
    a1 = dict(wos[i_a])
    a1["id"], a1["doi"] = 900001, ""
    a2 = dict(a1)
    a2["id"] = 900002
    a2["titulo"] = _variante(a1["titulo"], 0.96)
    wos[i_a] = a1
    wos.append(a2)

    # Passada 3 — mesmo primeiro autor e mesmo ano, título ~82% igual, DOIs distintos.
    # Escolhe uma base cujo par (primeiro autor, ano) não se repete no arquivo, senão
    # outro registro toma a chave antes e o par plantado nunca chega a ser comparado.
    def chave(t: dict) -> tuple[int, int]:
        return (t["autores"][0], t["ano"])

    ocupadas = [chave(t) for t in wos]
    base_b = next(
        (wos[i] for i in reversed(livres) if ocupadas.count(chave(wos[i])) == 1),
        wos[livres[-1]],
    )
    b2 = dict(base_b)
    b2["id"] = 900003
    b2["titulo"] = _variante(base_b["titulo"], 0.82)
    b2["doi"] = base_b["doi"].replace(".0", ".9", 1)
    wos.append(b2)


CABECALHO_SCOPUS = [
    "Authors", "Author(s) ID", "Title", "Year", "Source title", "Volume", "Issue",
    "Page start", "Page end", "Page count", "Cited by", "DOI", "Link", "Abstract",
    "Author Keywords", "Index Keywords", "References", "Document Type",
    "Publication Stage", "Open Access", "Source", "EID",
]


def escrever_scopus(caminho: Path, trabalhos: list[dict], pool: list[dict]):
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(CABECALHO_SCOPUS)
        for t in trabalhos:
            ids = "; ".join(str(57000000000 + i * 137) for i in t["autores"])
            refs = "; ".join(_ref_scopus(pool[r]) for r in t["refs"])
            indice = "; ".join(CLUSTERS[t["cluster"]]["keywords"][:3])
            w.writerow([
                _autores_scopus(t), ids, t["titulo"], t["ano"], t["periodico"],
                t["volume"], t["issue"], t["pag_inicio"], t["pag_fim"],
                t["pag_fim"] - t["pag_inicio"] + 1, t["citacoes_total"], t["doi"],
                f"https://doi.org/{t['doi']}", t["abstract"],
                "; ".join(t["keywords"]), indice, refs,
                "Article", "Final", "All Open Access" if t["id"] % 3 == 0 else "",
                "Scopus", f"2-s2.0-{85000000000 + t['id'] * 7919}",
            ])


def escrever_wos(caminho: Path, trabalhos: list[dict], pool: list[dict]):
    """Export *plain text* etiquetado do WoS: `TAG valor`, continuação com 3 espaços.

    Título e resumo ficam em UMA linha só de propósito. O WoS real quebra os dois em
    várias linhas, e o parser do Blicsa junta continuação com '; ' — o que é o certo para
    AU/DE/CR e errado para TI/AB. Manter esses dois em linha única deixa o corpus limpo
    para o teste manual, sem esconder o problema (veja o README ao lado).
    """
    linhas: list[str] = ["FN Clarivate Analytics Web of Science", "VR 1.0"]
    for t in trabalhos:
        au = _autores_wos(t)
        af = _autores_wos_completo(t)
        crs = [_ref_wos(pool[r]) for r in t["refs"]]

        linhas.append("PT J")
        linhas.append(f"AU {au[0]}")
        linhas.extend(f"   {a}" for a in au[1:])
        linhas.append(f"AF {af[0]}")
        linhas.extend(f"   {a}" for a in af[1:])
        linhas.append(f"TI {t['titulo']}")
        linhas.append(f"SO {t['periodico'].upper()}")
        linhas.append("LA English")
        linhas.append("DT Article")
        linhas.append(f"DE {'; '.join(t['keywords'])}")
        linhas.append(f"ID {'; '.join(CLUSTERS[t['cluster']]['keywords'][:3]).upper()}")
        linhas.append(f"AB {t['abstract']}")
        linhas.append(f"PY {t['ano']}")
        linhas.append(f"VL {t['volume']}")
        linhas.append(f"IS {t['issue']}")
        linhas.append(f"BP {t['pag_inicio']}")
        linhas.append(f"EP {t['pag_fim']}")
        linhas.append(f"DI {t['doi']}")
        linhas.append(f"TC {t['citacoes_total']}")
        linhas.append(f"Z9 {t['citacoes_total'] + t['id'] % 5}")
        if crs:
            linhas.append(f"CR {crs[0]}")
            linhas.extend(f"   {c}" for c in crs[1:])
            linhas.append(f"NR {len(crs)}")
        linhas.append(f"UT WOS:{900000000000000 + t['id']:015d}")
        linhas.append("ER")
        linhas.append("")
    linhas.append("EF")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Gera corpus fictício Scopus/WoS para o Blicsa")
    ap.add_argument("--saida", default="exemplos", help="pasta de destino (padrão: exemplos)")
    ap.add_argument("--seed", type=int, default=SEED_PADRAO, help="semente do gerador")
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    pool = gerar_trabalhos(rnd)

    corte_scopus = int(len(pool) * 0.72)      # Scopus fica com o começo do pool
    inicio_wos = corte_scopus - 8             # e os 8 últimos deles reaparecem no WoS
    scopus = pool[:corte_scopus]
    wos = list(pool[inicio_wos:])

    # Passada 1 do dedup (DOI igual) já está coberta pelos 8 trabalhos compartilhados
    # acima; as passadas 2 e 3 pedem pares construídos.
    plantar_duplicatas(scopus, wos)

    saida = Path(args.saida)
    if not saida.is_absolute():
        saida = Path(__file__).resolve().parent.parent / saida
    saida.mkdir(parents=True, exist_ok=True)

    csv_path = saida / "corpus_ficticio_scopus.csv"
    txt_path = saida / "corpus_ficticio_wos.txt"
    escrever_scopus(csv_path, scopus, pool)
    escrever_wos(txt_path, wos, pool)

    unicos = len({t["doi"] for t in scopus} | {t["doi"] for t in wos if t["doi"]})
    print(f"[OK] {csv_path}  → {len(scopus)} registros (Scopus CSV)")
    print(f"[OK] {txt_path}  → {len(wos)} registros (WoS plain text)")
    print(f"     anos {min(POR_ANO)}–{max(POR_ANO)}, {len(AUTORES)} autores, "
          f"{len(PERIODICOS)} periódicos, {len(CLUSTERS)} clusters temáticos")
    print(f"     {unicos} DOIs únicos; 8 duplicatas por DOI, 1 por título similar (~96%) "
          f"e 1 por autor+ano (~82%)")


if __name__ == "__main__":
    main()

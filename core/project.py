import json
import zipfile
import gzip
import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import networkx as nx

logger = logging.getLogger("blicsa.project")

CURRENT_MANIFEST_VERSION = "1.0"

#: Schema canônico de um registro, com o valor "vazio" de cada coluna.
#:
#: É o mesmo formato que os providers produzem (`_normalize_work`, `_record_from_medline`).
#: Existe aqui porque um `.blicsa` salvo por uma versão antiga do app **não** tem
#: necessariamente todas estas colunas, e o resto do código as acessa direto — `df["keywords"]`
#: levanta `KeyError` e o cálculo de rede morre com uma mensagem de uma palavra só.
SCHEMA_REGISTRO: dict[str, object] = {
    "authors": "", "title": "", "year": 0, "source": "", "keywords": "",
    "document_type": "",
    "abstract": "", "citations": 0, "doi": "", "references": "", "origin": "",
    "language": "", "is_oa": False, "oa_url": "",
}

#: Colunas que precisam ser numéricas: o filtro de período faz `df["year"] >= n`, que
#: compara string com int e estoura se a coluna vier como texto.
COLUNAS_NUMERICAS = ("year", "citations")


#: Chave do contexto de pesquisa no `config.json` do `.blicsa`.
#:
#: Vive no config, e não num arquivo próprio dentro do ZIP, porque é **parâmetro do projeto**
#: como o campo de análise e a resolução do cluster — e porque o config já é um dicionário
#: livre: acrescentar uma chave não muda a versão do manifesto e nem quebra a leitura de
#: quem não a conhece. A retrocompatibilidade sai de graça e nos dois sentidos: um `.blicsa`
#: novo abre numa versão antiga do app (que ignora a chave) e vice-versa.
CHAVE_CONTEXTO_PESQUISA = "research_context"


def research_context_do_config(config: dict | None) -> str:
    """Contexto de pesquisa gravado no projeto, ou "" — nunca levanta.

    Projeto de versão anterior não tem a chave; `.blicsa` editado à mão pode ter `None`, um
    número ou um dicionário no lugar do texto. Nenhum desses casos pode impedir o projeto de
    abrir: seria perder dataset, mapa e parâmetros por causa de um campo de texto opcional —
    exatamente o modo de falha que o `_id_cluster` já corrigiu para os rótulos.
    """
    from core.research_context import normalizar

    if not isinstance(config, dict):
        return ""
    return normalizar(config.get(CHAVE_CONTEXTO_PESQUISA))


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Garante o schema canônico num DataFrame vindo de qualquer versão do app.

    Preenche coluna ausente com o vazio do tipo e força `year`/`citations` a numérico.
    **Não descarta colunas extras** — `language_source`, por exemplo, existe em projetos de
    julho e não custa nada manter.

    Por que na carga e não em cada uso: os acessos diretos a coluna estão espalhados por
    `matrix_builders`, `nlp`, `map_animation` e `main`. Reparar num ponto é o que torna a
    retrocompatibilidade uma propriedade do arquivo carregado, e não uma lembrança de quem
    escreve a próxima função que lê um campo.
    """
    if df is None:
        return df
    if df.empty and not len(df.columns):
        # DataFrame vazio ganha o schema mesmo assim: código que faz `df["year"]` numa
        # busca sem resultado quebraria igual.
        return pd.DataFrame({c: pd.Series(dtype="int64" if c in COLUNAS_NUMERICAS
                                          else ("bool" if isinstance(v, bool) else "object"))
                             for c, v in SCHEMA_REGISTRO.items()})

    faltando = [c for c in SCHEMA_REGISTRO if c not in df.columns]
    for coluna in faltando:
        df[coluna] = SCHEMA_REGISTRO[coluna]
    if faltando:
        logger.warning("[Project] schema antigo: %d coluna(s) ausente(s) preenchida(s) — %s",
                       len(faltando), ", ".join(faltando))

    for coluna in COLUNAS_NUMERICAS:
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").fillna(0).astype("int64")

    # `is_oa` vindo como "true"/"false" de JSON antigo não pode virar bool truthy sempre.
    if df["is_oa"].dtype == object:
        df["is_oa"] = df["is_oa"].map(
            lambda v: str(v).strip().lower() in ("true", "1", "sim", "yes") if isinstance(v, str)
            else bool(v)).fillna(False)

    # Texto ausente vira string vazia; `NaN` num campo de texto vira "nan" ao virar str.
    for coluna, vazio in SCHEMA_REGISTRO.items():
        if isinstance(vazio, str):
            df[coluna] = df[coluna].fillna("").astype(str).replace({"nan": "", "None": ""})

    return df

# ── Projeto = PASTA (~/Blicsa/projects/<slug>/) ─────────────────────────────
#   project.blicsa   snapshot salvo (formato ZIP atual, intocado)
#   backlog.jsonl    APPEND-ONLY, uma linha JSON por ação (fora do ZIP de
#                    propósito: reescrever ZIP a cada ação convida corrupção)
#   searches/        JSON bruto de cada busca (search_<ts>.json) p/ reuso offline
#   exports/         saídas geradas (mapas, CSV, GML, XLSX)

PROJECTS_DIR = Path.home() / "Blicsa" / "projects"

BACKLOG_ACTIONS = ("search", "import", "dedup", "corpus_add", "analysis",
                   "export", "map", "extension_add")


def slugify(name: str) -> str:
    """Nome legível → slug de pasta (ascii, minúsculo, hífens)."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "projeto"


def project_dir(slug: str, projects_dir=None) -> Path:
    return Path(projects_dir or PROJECTS_DIR) / slug


def _unique_slug(name: str, base: Path) -> str:
    slug = slugify(name)
    candidate, n = slug, 2
    while (base / candidate).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def _scaffold(d: Path):
    (d / "searches").mkdir(parents=True, exist_ok=True)
    (d / "exports").mkdir(parents=True, exist_ok=True)
    (d / "backlog.jsonl").touch()


def create_project(name: str, projects_dir=None) -> str:
    """Cria a pasta do projeto com snapshot vazio + backlog. Retorna o slug."""
    base = Path(projects_dir or PROJECTS_DIR)
    base.mkdir(parents=True, exist_ok=True)
    slug = _unique_slug(name, base)
    d = base / slug
    _scaffold(d)
    save_blicsa_project(str(d / "project.blicsa"), df=None,
                        config={"name": name}, positions=None, G=None,
                        cluster_labels=None)
    return slug


def open_project(slug: str, projects_dir=None) -> dict:
    """Abre <slug>/project.blicsa e devolve o estado + backlog + caminhos."""
    d = project_dir(slug, projects_dir)
    data = load_blicsa_project(str(d / "project.blicsa"))
    data["slug"] = slug
    data["path"] = str(d)
    data["backlog"] = load_backlog(slug, projects_dir)
    return data


def append_backlog(slug: str, action: str, detail: dict, projects_dir=None) -> dict:
    """Acrescenta UMA linha ao backlog.jsonl (append-only, nunca reescreve)."""
    d = project_dir(slug, projects_dir)
    _scaffold(d)  # tolera projetos migrados sem subpastas
    entry = {"ts": datetime.now().isoformat(timespec="seconds"),
             "action": action, "detail": detail or {}}
    with open(d / "backlog.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_backlog(slug: str, projects_dir=None) -> list:
    """Lê o backlog inteiro; linha corrompida é PULADA com warning (as demais
    continuam legíveis — resiliência do append-only)."""
    path = project_dir(slug, projects_dir) / "backlog.jsonl"
    entries = []
    if not path.exists():
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                logger.warning(f"[Backlog] linha {n} corrompida em {path} — pulada")
    return entries


def save_search_raw(slug: str, records: list, projects_dir=None) -> str:
    """Grava o JSON bruto de uma busca em searches/search_<ts>.json.
    Retorna o caminho RELATIVO à pasta do projeto (vai no backlog)."""
    d = project_dir(slug, projects_dir)
    _scaffold(d)
    rel = f"searches/search_{int(time.time())}.json"
    with open(d / rel, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return rel


def load_search_raw(slug: str, rel_path: str, projects_dir=None) -> list:
    """Carrega os resultados salvos de uma busca (local-first, sem rede)."""
    with open(project_dir(slug, projects_dir) / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_loose_projects(projects_dir=None) -> list:
    """MIGRAÇÃO SUAVE: cada *.blicsa solto em projects/ vira uma pasta
    <slug>/project.blicsa (arquivo preservado via move). Retorna slugs criados."""
    base = Path(projects_dir or PROJECTS_DIR)
    migrated = []
    if not base.exists():
        return migrated
    for f in sorted(base.glob("*.blicsa")):
        if not f.is_file():
            continue
        slug = _unique_slug(f.stem, base)
        d = base / slug
        _scaffold(d)
        f.rename(d / "project.blicsa")
        migrated.append(slug)
        logger.info(f"[Projects] migrado: {f.name} -> {slug}/project.blicsa")
    return migrated


def list_projects(projects_dir=None) -> list:
    """Slugs das pastas de projeto existentes (com project.blicsa), mais recente 1º."""
    base = Path(projects_dir or PROJECTS_DIR)
    if not base.exists():
        return []
    dirs = [d for d in base.iterdir() if d.is_dir() and (d / "project.blicsa").exists()]
    dirs.sort(key=lambda d: (d / "project.blicsa").stat().st_mtime, reverse=True)
    return [d.name for d in dirs]

def save_blicsa_project(
    path: str,
    df: pd.DataFrame | None,
    config: dict,
    positions: dict | None,
    G: nx.Graph | None,
    cluster_labels: dict | None,
    searches: list | None = None,
    thumbnail_path: str | None = None,
    cluster_label_origins: dict | None = None,
):
    """Save full Blicsa project to a .blicsa ZIP archive."""
    manifest = {
        "version": CURRENT_MANIFEST_VERSION,
        "app": "PyBibliomics Blicsa",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Temporary directory or direct writing to zip
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        # Searches
        if searches is not None:
            zf.writestr("searches.json", json.dumps(searches, indent=2, ensure_ascii=False))
            
        # Thumbnail
        if thumbnail_path and os.path.exists(thumbnail_path):
            zf.write(thumbnail_path, "thumbnail.png")

        # 2. Config
        zf.writestr("config.json", json.dumps(config, indent=2, ensure_ascii=False))

        # 3. Dataset (JSON Gzipped)
        if df is not None and not df.empty:
            df_json = df.to_json(orient="records", force_ascii=False)
            compressed_df = gzip.compress(df_json.encode("utf-8"))
            zf.writestr("dataset.json.gz", compressed_df)

        # 4. Layout (Positions)
        if positions:
            # Convert node names to string and positions to list for JSON serialization
            serialized_pos = {str(node): [float(c) for c in coords] for node, coords in positions.items()}
            zf.writestr("layout.json", json.dumps(serialized_pos, indent=2))

        # 5. Network (Graph G)
        if G is not None:
            network_data = {
                "nodes": [{"id": str(n), "attributes": data} for n, data in G.nodes(data=True)],
                "edges": [{"source": str(u), "target": str(v), "attributes": data} for u, v, data in G.edges(data=True)]
            }
            zf.writestr("network.json", json.dumps(network_data, indent=2, ensure_ascii=False))

        # 6. Clusters (Labels)
        if cluster_labels:
            serialized_clusters = {str(k): str(v) for k, v in cluster_labels.items()}
            zf.writestr("clusters.json", json.dumps(serialized_clusters, indent=2, ensure_ascii=False))

        # Origem de cada rótulo ("ia" | "usuario"). Arquivo separado para que projeto salvo
        # por versão anterior continue abrindo: entrada ausente vira dicionário vazio, e
        # nenhum rótulo é marcado como IA — na dúvida, NÃO marcar (marcar texto do usuário
        # como máquina o faria desconfiar do próprio trabalho).
        if cluster_label_origins:
            zf.writestr("cluster_origins.json",
                        json.dumps({str(k): str(v) for k, v in cluster_label_origins.items()},
                                   indent=2, ensure_ascii=False))


#: Teto do que cada entrada do `.blicsa` pode ocupar DEPOIS de descomprimida.
#:
#: `zf.read(nome)` descomprime a entrada inteira para a memória antes de qualquer validação.
#: Um ZIP de 199 KB com uma entrada de 200 MB de zeros já entrou na RAM num teste da
#: Auditoria 2 — e a mesma técnica escala para gigabytes com um arquivo minúsculo.
#:
#: 400 MB é folgado para um corpus real: o `.blicsa` do dataset de exemplo tem 301 KB, e o
#: dataset ainda vai comprimido em gzip dentro do ZIP.
LIMITE_ENTRADA_BYTES = 400 * 1024 * 1024


def _ler_entrada(zf: zipfile.ZipFile, nome: str) -> bytes:
    """Lê uma entrada do `.blicsa` recusando o que for grande demais para ser corpus.

    O teto é conferido no **cabeçalho** (`ZipInfo.file_size`), antes de descomprimir: checar
    depois de ler seria constatar o estrago em vez de evitá-lo.
    """
    info = zf.getinfo(nome)
    if info.file_size > LIMITE_ENTRADA_BYTES:
        raise ValueError(
            f"entrada '{nome}' declara {info.file_size / 1024 / 1024:.0f} MB descomprimidos, "
            f"acima do teto de {LIMITE_ENTRADA_BYTES / 1024 / 1024:.0f} MB")
    return zf.read(nome)


def load_blicsa_project(path: str) -> dict:
    """Load full Blicsa project from a .blicsa ZIP archive, with version migration hook."""
    result = {
        "df": None,
        "config": {},
        "positions": {},
        "G": None,
        "cluster_labels": {},
        "cluster_label_origins": {},
    }

    with zipfile.ZipFile(path, "r") as zf:
        # Read Manifest
        manifest = json.loads(_ler_entrada(zf, "manifest.json").decode("utf-8"))
        version = manifest.get("version", "1.0")

        # Version Migration Hook
        if version != CURRENT_MANIFEST_VERSION:
            logger.info("[Project] migrando projeto da versão %s para %s",
                        version, CURRENT_MANIFEST_VERSION)

        # Read Config
        if "config.json" in zf.namelist():
            result["config"] = json.loads(_ler_entrada(zf, "config.json").decode("utf-8"))

        # Read Dataset
        if "dataset.json.gz" in zf.namelist():
            import io
            compressed_df = _ler_entrada(zf, "dataset.json.gz")
            df_json = gzip.decompress(compressed_df).decode("utf-8")
            # A normalização vale para QUALQUER versão, não só quando o manifesto diverge:
            # os projetos de 30/07 declaram `version: 3` e mesmo assim vieram com uma coluna
            # só. Confiar no número da versão para decidir se migra é como confiar no
            # rótulo em vez de olhar a caixa.
            result["df"] = normalize_dataframe(
                pd.read_json(io.StringIO(df_json), orient="records"))

        # Read Layout
        if "layout.json" in zf.namelist():
            serialized_pos = json.loads(_ler_entrada(zf, "layout.json").decode("utf-8"))
            result["positions"] = {k: v for k, v in serialized_pos.items()}

        # Read Network (Graph)
        if "network.json" in zf.namelist():
            network_data = json.loads(_ler_entrada(zf, "network.json").decode("utf-8"))
            G = nx.Graph()
            for node in network_data.get("nodes", []):
                G.add_node(node["id"], **node.get("attributes", {}))
            for edge in network_data.get("edges", []):
                G.add_edge(edge["source"], edge["target"], **edge.get("attributes", {}))
            result["G"] = G
            
        # Read Searches
        if "searches.json" in zf.namelist():
            result["searches"] = json.loads(_ler_entrada(zf, "searches.json").decode("utf-8"))
        else:
            result["searches"] = []

        # Read Clusters (Labels)
        if "clusters.json" in zf.namelist():
            serialized_clusters = json.loads(_ler_entrada(zf, "clusters.json").decode("utf-8"))
            # As chaves voltam a inteiro porque é o que o app usa (`dict[int, str]`, ids da
            # partição do Louvain) e a gravação as serializa com `str(k)`.
            #
            # Chave não numérica é preservada como veio em vez de derrubar a carga: `int(k)`
            # sem guarda levantava `ValueError` e o projeto INTEIRO deixava de abrir — dataset,
            # mapa e parâmetros perdidos por causa do rótulo de um cluster.
            def _id_cluster(chave: str):
                try:
                    return int(chave)
                except (TypeError, ValueError):
                    return chave

            result["cluster_labels"] = {_id_cluster(k): v
                                        for k, v in serialized_clusters.items()}

        if "cluster_origins.json" in zf.namelist():
            origens = json.loads(_ler_entrada(zf, "cluster_origins.json").decode("utf-8"))
            result["cluster_label_origins"] = {_id_cluster(k): v for k, v in origens.items()}

    migrar_citacoes_ambiguas(result.get("G"), result.get("df"))
    return result


#: Falha ao abrir/salvar → chave de catálogo. **Nunca** a mensagem da biblioteca.
#:
#: O que o usuário via até 09/08/2026, com a interface em francês, ao abrir um CSV renomeado
#: para `.blicsa`: *"File is not a zip file"*. Em inglês fixo, vindo do `zipfile`, sem dizer o
#: que fazer. Pior ainda no arquivo sem manifesto: *"There is no item named 'manifest.json' in
#: the archive"* — nomeando um arquivo interno do formato, que o usuário não sabe que existe.
#:
#: A ordem importa: `BadZipFile` é subclasse de `Exception` mas não de `OSError`, e
#: `FileNotFoundError`/`PermissionError` são de `OSError` — checar do específico para o geral.
_DIAGNOSTICOS: tuple[tuple[type[BaseException], str], ...] = (
    (zipfile.BadZipFile, "projeto.erro_nao_e_blicsa"),
    (json.JSONDecodeError, "projeto.erro_corrompido"),
    # O ZIP abre, o manifesto lê, e o corpus lá dentro é que está danificado. `BadGzipFile`
    # é subclasse de `OSError` e caía no diagnóstico genérico — precisa vir antes dele.
    (gzip.BadGzipFile, "projeto.erro_corrompido"),
    (KeyError, "projeto.erro_incompleto"),
    (FileNotFoundError, "projeto.erro_sumiu"),
    (PermissionError, "projeto.erro_permissao"),
    (IsADirectoryError, "projeto.erro_e_pasta"),
    (MemoryError, "projeto.erro_memoria"),
)

#: `errno` sem classe própria em Python. Disco cheio é `OSError` genérico.
_DIAGNOSTICOS_ERRNO = {28: "projeto.erro_disco_cheio",   # ENOSPC
                       30: "projeto.erro_somente_leitura"}  # EROFS


def diagnosticar_projeto(erro: BaseException) -> str:
    """Chave de catálogo que explica a falha ao usuário, sem jargão de biblioteca.

    Devolve **chave**, não texto: quem exibe é a UI, que sabe o idioma ativo. Uma função de
    domínio que já devolvesse a frase pronta teria de importar o i18n e escolher o idioma
    sozinha — e `core/` não decide apresentação.
    """
    if isinstance(erro, OSError) and getattr(erro, "errno", None) in _DIAGNOSTICOS_ERRNO:
        return _DIAGNOSTICOS_ERRNO[erro.errno]
    for tipo, chave in _DIAGNOSTICOS:
        if isinstance(erro, tipo):
            return chave
    return "projeto.erro_desconhecido"


#: Nós cujo `citations_mean` vale exatamente zero. Só eles são ambíguos.
def _nos_com_citacao_zero(G) -> set:
    return {n for n, d in G.nodes(data=True) if d.get("citations_mean") == 0}


def migrar_citacoes_ambiguas(G, df) -> int:
    """Desfaz a ambiguidade do `citations_mean: 0.0` de projeto antigo. Devolve quantos nós
    foram recalculados.

    ## O que era ambíguo

    Até 09/08/2026 o escritor gravava `0.0` em duas situações **diferentes**:

    - o termo aparece em documentos com **zero citação** (valor verdadeiro), e
    - o termo aparece em documentos **sem dado de citação** (valor desconhecido).

    O leitor tratava os dois como "não sei", e o efeito era um corpus recente inteiro cinza no
    overlay. Hoje o escritor grava `None` para desconhecido — mas **o arquivo já salvo não tem
    como ser lido**: `0.0` sozinho não diz qual dos dois casos era.

    ## Por que dá para migrar

    O `.blicsa` guarda o **dataset inteiro**, com a coluna `citations`. A ambiguidade só existe
    no grafo derivado; a fonte está ali do lado. Recalcular do dataset responde a pergunta que o
    grafo não responde.

    A migração é por **conteúdo, não por número de versão**: o `normalize_dataframe` acima
    existe porque projetos de 30/07 declaravam `version: 3` e vinham com uma coluna só. Confiar
    no rótulo em vez de olhar a caixa já custou um bug neste arquivo.

    ## Por que só os nós com zero

    `compute_overlay_scores` é O(nós × documentos) — 36 s para 5.000 nós. Recalcular o grafo
    inteiro faria toda abertura de projeto pagar o preço de uma ambiguidade que costuma atingir
    poucos nós. Nó com valor diferente de zero é idêntico nos dois escritores, e nó já com
    `None` é de projeto novo.

    É idempotente: rodar sobre projeto novo recalcula os mesmos valores.
    """
    if G is None or df is None or getattr(df, "empty", True):
        return 0
    ambiguos = _nos_com_citacao_zero(G)
    if not ambiguos:
        return 0

    try:
        from core.matrix_builders import NetworkGenerator
    except Exception as e:                       # pragma: no cover - só sem dependências
        logger.warning("[Project] migração de citações indisponível: %s", e)
        return 0

    gen = NetworkGenerator(df)
    gen.G = G
    try:
        gen.compute_overlay_scores(apenas=ambiguos)
    except Exception as e:
        # Projeto que abre com métrica velha é melhor do que projeto que não abre. A carga
        # inteira já foi perdida uma vez por causa do rótulo de um cluster (`_id_cluster`).
        logger.warning("[Project] migração de citações falhou, mantendo valores antigos: %s", e)
        return 0

    recalculados = len(ambiguos)
    logger.info("[Project] citações recalculadas do dataset em %d nó(s) ambíguo(s)",
                recalculados)
    return recalculados

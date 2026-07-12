import json
import re
import math
import networkx as nx
from pyvis.network import Network
import pandas as pd
from collections import Counter
from itertools import combinations
import community as community_louvain

from .nlp import extract_ngrams, apply_thesaurus

CLUSTER_PALETTE = ['#DF3117', '#1E4DA0', '#F5BE00', '#141414', '#7A9E7E', '#B65CA2', '#5CB0B8', '#C97B2D']


def _apply_clustering(G: nx.Graph, algorithm: str = "louvain", resolution: float = 1.0) -> dict[str, int]:
    if G.number_of_nodes() == 0:
        return {}
        
    if algorithm == "leiden":
        try:
            import igraph as ig
            import leidenalg
            
            nodelist = list(G.nodes())
            node_index = {name: i for i, name in enumerate(nodelist)}
            
            g_ig = ig.Graph(len(nodelist))
            g_ig.vs["name"] = nodelist
            
            edges = []
            weights = []
            for u, v, data in G.edges(data=True):
                edges.append((node_index[u], node_index[v]))
                weights.append(data.get("weight", 1.0))
                
            g_ig.add_edges(edges)
            g_ig.es["weight"] = weights
            
            partition_leiden = leidenalg.find_partition(
                g_ig,
                leidenalg.RBConfigurationVertexPartition,
                weights=g_ig.es["weight"],
                resolution_parameter=resolution,
                seed=42
            )
            
            partition = {}
            for cluster_idx, nodes_in_cluster in enumerate(partition_leiden):
                for node_idx in nodes_in_cluster:
                    node_name = g_ig.vs[node_idx]["name"]
                    partition[node_name] = cluster_idx
                    
            nx.set_node_attributes(G, partition, "group")
            return partition
        except ImportError:
            print("[Blicsa] igraph ou leidenalg não instalados. Usando Louvain como fallback.")
            
    partition = community_louvain.best_partition(G, weight="weight", resolution=resolution, random_state=42)
    nx.set_node_attributes(G, partition, "group")
    return partition


def _color_nodes(G: nx.Graph, partition: dict[str, int]):
    for node, grp in partition.items():
        if node in G.nodes:
            G.nodes[node]["color"] = CLUSTER_PALETTE[grp % len(CLUSTER_PALETTE)]


def _relevance_scores(
    term_counts: Counter,
    term_doc_freq: Counter,
    total_docs: int,
) -> dict[str, float]:
    """TF-IDF-style: freq × log(N / df). Higher = more specific to a cluster."""
    scores: dict[str, float] = {}
    for term, freq in term_counts.items():
        df = term_doc_freq.get(term, 1)
        scores[term] = freq * math.log((total_docs + 1) / (df + 1))
    return scores


def _normalize_association_strength(G: nx.Graph, term_counts: Counter):
    """Replace raw co-occurrence weights with association strength.

    s(i,j) = c(i,j) / (count_i × count_j)
    Keeps weight_raw for CSV export.
    """
    total = max(sum(term_counts.values()), 1)
    for u, v, data in G.edges(data=True):
        ci = term_counts.get(u, 1)
        cj = term_counts.get(v, 1)
        raw = data.get("weight", 1)
        G[u][v]["weight_raw"] = raw
        G[u][v]["weight"] = round(raw / (ci * cj / total), 6) if ci * cj else raw


def _extract_term_lists(
    df: pd.DataFrame,
    field: str,
    thesaurus: dict[str, str],
    extra_stop_words: set[str] | None,
) -> list[list[str]]:
    """Build per-document term lists from the chosen field."""
    result: list[list[str]] = []

    if field == "keywords":
        for kw_str in df["keywords"].dropna():
            if isinstance(kw_str, str) and kw_str.strip():
                sep = ";" if ";" in kw_str else ","
                kws = [
                    apply_thesaurus(k.strip().lower(), thesaurus)
                    for k in kw_str.split(sep) if k.strip()
                ]
                result.append(kws)
    else:
        col_map = {
            "titles":           ["title"],
            "abstracts":        ["abstract"],
            "titles_abstracts": ["title", "abstract"],
        }
        cols = col_map.get(field, ["title"])
        for _, row in df.iterrows():
            text = " ".join(str(row.get(c, "") or "") for c in cols).strip()
            if text:
                grams = extract_ngrams(text, extra_stop_words=extra_stop_words)
                grams = [apply_thesaurus(g, thesaurus) for g in grams]
                result.append(grams)

    return result


class NetworkGenerator:
    def __init__(self, dataframe: pd.DataFrame):
        self.df = dataframe
        self.G = nx.Graph()
        self._term_counts: Counter = Counter()
        self._term_doc_freq: Counter = Counter()
        self._term_scores: dict[str, float] = {}
        self.clustering_algorithm = "louvain"
        self.clustering_resolution = 1.0

    def apply_clustering(self) -> dict[str, int]:
        partition = _apply_clustering(
            self.G, 
            algorithm=self.clustering_algorithm, 
            resolution=self.clustering_resolution
        )
        _color_nodes(self.G, partition)
        return partition

    def compute_overlay_scores(self):
        import re
        for node in self.G.nodes:
            node_lower = str(node).lower().strip()
            matches = pd.DataFrame()
            
            # Match keywords
            if "keywords" in self.df.columns:
                kw_series = self.df["keywords"].fillna("").astype(str).str.lower()
                matches_kw = kw_series.apply(lambda x: any(t.strip() == node_lower for t in re.split(r"[;\n,]", x)))
                if matches_kw.any():
                    matches = self.df[matches_kw]
            
            # Match authors
            if len(matches) == 0 and "authors" in self.df.columns:
                auth_series = self.df["authors"].fillna("").astype(str).str.lower()
                matches_auth = auth_series.apply(lambda x: any(t.strip() == node_lower for t in re.split(r"[;\n,]", x)))
                if matches_auth.any():
                    matches = self.df[matches_auth]
                    
            # Match title
            if len(matches) == 0:
                title_series = self.df["title"].fillna("").astype(str).str.lower()
                matches_title = title_series.str.contains(node_lower, regex=False)
                if matches_title.any():
                    matches = self.df[matches_title]
                else:
                    match_yr = re.search(r'\b(19\d\d|20\d\d)\b', str(node))
                    if match_yr:
                        year_val = int(match_yr.group(1))
                        year_df = self.df[self.df["year"] == year_val]
                        if not year_df.empty:
                            node_cleaned = re.sub(r'\d+', '', str(node)).strip("() ,").lower()
                            matches_yr_auth = year_df["authors"].fillna("").astype(str).str.lower().str.contains(node_cleaned, regex=False)
                            if matches_yr_auth.any():
                                matches = year_df[matches_yr_auth]
            
            if len(matches) > 0:
                years = matches["year"].dropna()
                years = years[years > 0]
                mean_year = float(years.mean()) if not years.empty else 0.0
                
                cits = matches["citations"].dropna()
                mean_cits = float(cits.mean()) if not cits.empty else 0.0
                sum_cits = float(cits.sum()) if not cits.empty else 0.0
                
                self.G.nodes[node]["year_mean"] = round(mean_year, 1)
                self.G.nodes[node]["citations_mean"] = round(mean_cits, 1)
                self.G.nodes[node]["citations_sum"] = int(sum_cits)
            else:
                self.G.nodes[node]["year_mean"] = self.G.nodes[node].get("year_mean", 0.0)
                self.G.nodes[node]["citations_mean"] = self.G.nodes[node].get("citations_mean", 0.0)
                self.G.nodes[node]["citations_sum"] = self.G.nodes[node].get("citations_sum", 0)

    # ------------------------------------------------------------------ #
    #  Pre-computation / preview                                           #
    # ------------------------------------------------------------------ #
    def get_candidate_terms(
        self,
        field: str = "keywords",
        thesaurus: dict[str, str] | None = None,
        extra_stop_words: set[str] | None = None,
    ) -> tuple[int, Counter, Counter, dict[str, float]]:
        """Return (total_papers, term_counts, term_doc_freq, relevance_scores).

        Does NOT build the graph — used to power threshold feedback and
        the verification table.
        """
        th = thesaurus or {}
        term_lists = _extract_term_lists(self.df, field, th, extra_stop_words)
        all_terms = [t for lst in term_lists for t in lst]
        counts: Counter = Counter(all_terms)
        doc_freq: Counter = Counter()
        for lst in term_lists:
            for t in set(lst):
                doc_freq[t] += 1
        scores = _relevance_scores(counts, doc_freq, len(term_lists))
        return len(self.df), counts, doc_freq, scores

    def count_passing_threshold(
        self,
        min_occurrence: int,
        field: str = "keywords",
        thesaurus: dict[str, str] | None = None,
        extra_stop_words: set[str] | None = None,
    ) -> tuple[int, int]:
        """Return (total_unique_terms, terms_that_pass_threshold)."""
        _, counts, _, _ = self.get_candidate_terms(field, thesaurus, extra_stop_words)
        total = len(counts)
        passing = sum(1 for n in counts.values() if n >= min_occurrence)
        return total, passing

    # ------------------------------------------------------------------ #
    #  Keyword / term co-occurrence                                        #
    # ------------------------------------------------------------------ #
    def build_keyword_cooccurrence(
        self,
        min_occurrence: int = 3,
        counting_method: str = "full",      # "full" | "fractional"
        normalize_strength: bool = True,
        field: str = "keywords",            # "keywords" | "titles" | "abstracts" | "titles_abstracts"
        thesaurus: dict[str, str] | None = None,
        max_nodes: int = 0,                 # 0 = unlimited
        allowed_terms: set[str] | None = None,
        extra_stop_words: set[str] | None = None,
    ) -> nx.Graph:
        self.G.clear()
        th = thesaurus or {}
        term_lists = _extract_term_lists(self.df, field, th, extra_stop_words)

        all_terms = [t for lst in term_lists for t in lst]
        counts: Counter = Counter(all_terms)
        doc_freq: Counter = Counter()
        for lst in term_lists:
            for t in set(lst):
                doc_freq[t] += 1

        self._term_counts = counts
        self._term_doc_freq = doc_freq
        self._term_scores = _relevance_scores(counts, doc_freq, len(term_lists))

        valid = {t for t, n in counts.items() if n >= min_occurrence}
        if allowed_terms is not None:
            valid &= allowed_terms
        if max_nodes > 0 and len(valid) > max_nodes:
            valid = set(
                sorted(valid, key=lambda t: self._term_scores.get(t, 0), reverse=True)[:max_nodes]
            )

        # Compute mean year per term for Overlay View
        term_years: dict[str, list[int]] = {t: [] for t in valid}
        for _, row in self.df.iterrows():
            yr = int(row.get("year", 0) or 0)
            if yr == 0:
                continue
            kw_str = str(row.get("keywords", ""))
            if field == "keywords":
                sep = ";" if ";" in kw_str else ","
                row_terms = [
                    apply_thesaurus(k.strip().lower(), th)
                    for k in kw_str.split(sep) if k.strip()
                ]
            else:
                col_map = {
                    "titles": ["title"],
                    "abstracts": ["abstract"],
                    "titles_abstracts": ["title", "abstract"],
                }
                text = " ".join(str(row.get(c, "") or "") for c in col_map.get(field, ["title"]))
                row_terms = [apply_thesaurus(g, th) for g in extract_ngrams(text, extra_stop_words=extra_stop_words)]

            for t in row_terms:
                if t in term_years:
                    term_years[t].append(yr)

        for t in valid:
            yrs = term_years.get(t, [])
            year_mean = round(sum(yrs) / len(yrs), 1) if yrs else 0
            self.G.add_node(
                t,
                size=int(10 + counts[t] * 2),
                title=(
                    f"<b>{t}</b><br>"
                    f"Ocorrências: {counts[t]}<br>"
                    f"Doc. freq.: {doc_freq.get(t, 0)}<br>"
                    f"Ano médio: {year_mean or '—'}"
                ),
                label=t,
                occurrence=counts[t],
                doc_freq=doc_freq.get(t, 0),
                relevance=round(self._term_scores.get(t, 0), 3),
                year_mean=year_mean,
            )

        cooc: Counter = Counter()
        for lst in term_lists:
            flt = list(dict.fromkeys(k for k in lst if k in valid))  # deduplicate per doc
            n_terms = len(flt)
            if n_terms < 2:
                continue
            for a, b in combinations(sorted(flt), 2):
                if counting_method == "fractional":
                    cooc[(a, b)] += 1.0 / n_terms
                else:
                    cooc[(a, b)] += 1

        for (a, b), w in cooc.items():
            self.G.add_edge(a, b, weight=round(w, 4), title=f"Co-ocorrências: {w:.2f}")

        if normalize_strength:
            _normalize_association_strength(self.G, counts)

        partition = self.apply_clustering()
        self.compute_overlay_scores()
        print(
            f"[Engine] {self.G.number_of_nodes()} nós · "
            f"{self.G.number_of_edges()} arestas · "
            f"campo={field} · método={counting_method} · "
            f"strength={'sim' if normalize_strength else 'não'}\n"
        )
        return self.G

    # ------------------------------------------------------------------ #
    #  Co-authorship                                                        #
    # ------------------------------------------------------------------ #
    def build_coauthorship_network(
        self,
        min_publications: int = 2,
        counting_method: str = "full",
    ) -> nx.Graph:
        self.G.clear()
        author_lists: list[list[str]] = []
        for raw in self.df["authors"].dropna():
            if not isinstance(raw, str) or not raw.strip():
                continue
            sep = ";" if ";" in raw else ","
            names = [n.strip() for n in raw.split(sep) if n.strip()]
            author_lists.append(names)

        all_authors = [a for lst in author_lists for a in lst]
        counts: Counter = Counter(all_authors)
        valid = {a for a, n in counts.items() if n >= min_publications}

        for author in valid:
            self.G.add_node(
                author,
                size=int(10 + counts[author] * 3),
                title=f"<b>{author}</b><br>Publicações: {counts[author]}",
                label=author,
            )

        colab: Counter = Counter()
        for lst in author_lists:
            flt = [a for a in lst if a in valid]
            n = len(flt)
            if n < 2:
                continue
            for a, b in combinations(sorted(flt), 2):
                if counting_method == "fractional":
                    colab[(a, b)] += 1.0 / n
                else:
                    colab[(a, b)] += 1

        for (a, b), w in colab.items():
            self.G.add_edge(a, b, weight=round(w, 4), title=f"Coautorias: {w:.2f}")

        partition = self.apply_clustering()
        self.compute_overlay_scores()
        return self.G

    # ------------------------------------------------------------------ #
    #  Co-citation                                                          #
    # ------------------------------------------------------------------ #
    def build_cocitation_network(self, min_cocitations: int = 2) -> nx.Graph:
        self.G.clear()
        ref_col = self._find_ref_col()

        ref_lists: list[list[str]] = []
        for raw in self.df[ref_col].dropna():
            if not isinstance(raw, str) or not raw.strip():
                continue
            refs = [r.strip() for r in raw.split(";") if r.strip()]
            if refs:
                ref_lists.append(refs)

        all_refs = [r for lst in ref_lists for r in lst]
        counts: Counter = Counter(all_refs)
        cooc: Counter = Counter()
        for lst in ref_lists:
            for a, b in combinations(sorted(lst), 2):
                cooc[(a, b)] += 1

        valid_pairs = {pair: w for pair, w in cooc.items() if w >= min_cocitations}

        for (a, b) in valid_pairs:
            for node, label in ((a, a[:40]), (b, b[:40])):
                if node not in self.G:
                    self.G.add_node(
                        node,
                        size=int(8 + counts[node] * 1.5),
                        title=f"<b>{node[:80]}</b><br>Citações: {counts[node]}",
                        label=label,
                    )
            self.G.add_edge(a, b, weight=valid_pairs[(a, b)],
                            title=f"Co-citações: {valid_pairs[(a, b)]}")

        partition = self.apply_clustering()
        self.compute_overlay_scores()
        return self.G

    # ------------------------------------------------------------------ #
    #  Bibliographic Coupling                                              #
    # ------------------------------------------------------------------ #
    def build_bibliographic_coupling(self, min_shared_refs: int = 2) -> nx.Graph:
        """Nodes = papers; edges = number of shared cited references."""
        self.G.clear()
        ref_col = self._find_ref_col()

        doc_refs: list[tuple[str, set[str]]] = []
        for _, row in self.df.iterrows():
            raw = row.get(ref_col, "")
            if not isinstance(raw, str) or not raw.strip():
                continue
            refs = {r.strip() for r in raw.split(";") if r.strip()}
            label = (
                str(row.get("authors", "") or "")[:25].split(";")[0].strip()
                + f" ({row.get('year', '?')})"
            ).strip()
            # Make label unique
            base, i = label, 1
            while any(lbl == label for lbl, _ in doc_refs):
                label = f"{base} #{i}"
                i += 1
            doc_refs.append((label, refs))

        for i in range(len(doc_refs)):
            for j in range(i + 1, len(doc_refs)):
                label_a, refs_a = doc_refs[i]
                label_b, refs_b = doc_refs[j]
                shared = len(refs_a & refs_b)
                if shared >= min_shared_refs:
                    for lbl in (label_a, label_b):
                        if lbl not in self.G:
                            self.G.add_node(lbl, size=12, label=lbl,
                                            title=f"<b>{lbl}</b>")
                    if self.G.has_edge(label_a, label_b):
                        self.G[label_a][label_b]["weight"] += shared
                    else:
                        self.G.add_edge(label_a, label_b, weight=shared,
                                        title=f"Refs. compartilhadas: {shared}")

        for n in self.G.nodes():
            deg = self.G.degree(n, weight="weight")
            self.G.nodes[n]["size"] = int(8 + deg * 0.5)

        partition = self.apply_clustering()
        self.compute_overlay_scores()
        return self.G

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    def _find_ref_col(self) -> str:
        for candidate in ("CR", "References", "Cited References", "references"):
            if candidate in self.df.columns:
                return candidate
        raise ValueError(
            "Coluna de referências não encontrada. "
            "Esperado: 'CR' (WoS) ou 'References' (Scopus)."
        )

    # ------------------------------------------------------------------ #
    #  Direct citation (paper → paper)                                    #
    # ------------------------------------------------------------------ #
    def build_direct_citation_network(self, min_citations: int = 1) -> nx.Graph:
        """Nodes = papers; edges = A cites B (matched by DOI or author+year).

        Works best with Crossref/OpenAlex data that carry reference DOIs.
        Falls back to first-author + year fuzzy matching for WoS/Scopus.
        """
        self.G.clear()

        # Build lookup: doi → label  AND  (surname, year) → label
        doi_map:   dict[str, str] = {}
        fuzzy_map: dict[tuple, str] = {}
        labels_used: set[str] = set()

        for _, row in self.df.iterrows():
            doi = str(row.get("doi", "") or "").strip().lower().replace("https://doi.org/", "")
            yr  = int(row.get("year", 0) or 0)
            raw_auth = str(row.get("authors", "") or "")
            surname = raw_auth.split(";")[0].split(",")[0].strip().lower()

            base = (surname[:15] + f" ({yr})").strip()
            label = base
            suffix = 1
            while label in labels_used:
                label = f"{base} #{suffix}"
                suffix += 1
            labels_used.add(label)

            if doi:
                doi_map[doi] = label
            if surname and yr:
                fuzzy_map[(surname, yr)] = label

        def _resolve_ref(ref_text: str) -> str | None:
            ref_text = ref_text.strip()
            # DOI match
            doi_candidate = ref_text.lower().replace("https://doi.org/", "")
            if doi_candidate in doi_map:
                return doi_map[doi_candidate]
            # Fuzzy: extract year and first word as surname
            m = re.search(r"\b(19|20)\d{2}\b", ref_text)
            if m:
                yr = int(m.group())
                first_word = ref_text.split()[0].rstrip(",").lower() if ref_text else ""
                return fuzzy_map.get((first_word, yr))
            return None

        cite_counts: Counter = Counter()
        label_lookup: dict[str, str] = {}

        for _, row in self.df.iterrows():
            doi = str(row.get("doi", "") or "").strip().lower().replace("https://doi.org/", "")
            yr  = int(row.get("year", 0) or 0)
            raw_auth = str(row.get("authors", "") or "")
            surname = raw_auth.split(";")[0].split(",")[0].strip().lower()

            citing_label = doi_map.get(doi) or fuzzy_map.get((surname, yr))
            if not citing_label:
                continue

            refs_raw = str(row.get("references", "") or "")
            for ref in refs_raw.split(";"):
                cited_label = _resolve_ref(ref)
                if cited_label and cited_label != citing_label:
                    cite_counts[(citing_label, cited_label)] += 1

        for (src, tgt), n in cite_counts.items():
            if n >= min_citations:
                for lbl in (src, tgt):
                    if lbl not in self.G:
                        self.G.add_node(lbl, size=12, label=lbl,
                                        title=f"<b>{lbl}</b>")
                self.G.add_edge(src, tgt, weight=n, title=f"Citações: {n}")

        for n in self.G.nodes():
            self.G.nodes[n]["size"] = int(8 + self.G.degree(n, weight="weight") * 1.5)

        partition = self.apply_clustering()
        self.compute_overlay_scores()
        print(f"[Citação Direta] {self.G.number_of_nodes()} nós · {self.G.number_of_edges()} arestas\n")
        return self.G

    # ------------------------------------------------------------------ #
    #  IPC co-classification (patents)                                     #
    # ------------------------------------------------------------------ #
    def build_ipc_cooccurrence(self, min_occurrence: int = 2) -> nx.Graph:
        """Nodes = IPC codes (truncated to 4 chars = subclass level);
        edges = co-occurrence in same patent.
        Requires 'ipc' column with semicolon-separated codes.
        """
        self.G.clear()
        ipc_col = None
        for candidate in ("ipc", "IPC", "ipc_code", "classification", "Classification"):
            if candidate in self.df.columns:
                ipc_col = candidate
                break
        if ipc_col is None:
            raise ValueError(
                "Coluna de códigos IPC não encontrada. "
                "Esperado: 'ipc' ou 'classification' (semicolon-separated)."
            )

        ipc_lists: list[list[str]] = []
        for raw in self.df[ipc_col].dropna():
            if isinstance(raw, str) and raw.strip():
                codes = [c.strip()[:4].upper() for c in raw.split(";") if c.strip()]
                if codes:
                    ipc_lists.append(codes)

        all_codes = [c for lst in ipc_lists for c in lst]
        counts: Counter = Counter(all_codes)
        valid  = {c for c, n in counts.items() if n >= min_occurrence}

        for code in valid:
            self.G.add_node(
                code,
                size=int(10 + counts[code] * 2),
                title=f"<b>IPC: {code}</b><br>Ocorrências: {counts[code]}",
                label=code,
                occurrence=counts[code],
            )

        cooc: Counter = Counter()
        for lst in ipc_lists:
            flt = list(dict.fromkeys(c for c in lst if c in valid))
            for a, b in combinations(sorted(flt), 2):
                cooc[(a, b)] += 1

        for (a, b), w in cooc.items():
            self.G.add_edge(a, b, weight=w, title=f"Co-ocorrências: {w}")

        partition = self.apply_clustering()
        self.compute_overlay_scores()
        print(f"[IPC] {self.G.number_of_nodes()} códigos · {self.G.number_of_edges()} arestas\n")
        return self.G

    # ------------------------------------------------------------------ #
    #  Temporal evolution                                                   #
    # ------------------------------------------------------------------ #
    def get_temporal_evolution(
        self,
        period_size: int = 5,
        field: str = "keywords",
        min_occurrence: int = 3,
        thesaurus: dict[str, str] | None = None,
    ) -> list[dict]:
        """Slice dataset by year windows and return per-period network stats."""
        if "year" not in self.df.columns:
            return []
        yr_series = self.df["year"].replace(0, None).dropna().astype(int)
        if yr_series.empty:
            return []

        min_y, max_y = int(yr_series.min()), int(yr_series.max())
        results: list[dict] = []
        for start in range(min_y, max_y + 1, period_size):
            end = start + period_size - 1
            slice_df = self.df[self.df["year"].between(start, end)].copy()
            if len(slice_df) < 3:
                continue
            try:
                gen = NetworkGenerator(slice_df)
                gen.build_keyword_cooccurrence(
                    min_occurrence=min_occurrence,
                    field=field,
                    thesaurus=thesaurus,
                )
                stats = gen.get_summary_stats()
                top   = gen.get_top_keywords(5)
                results.append({
                    "period":    f"{start}–{end}",
                    "papers":    int(len(slice_df)),
                    "nodes":     stats["total_nodes"],
                    "edges":     stats["total_edges"],
                    "density":   stats["network_density"],
                    "clusters":  stats["num_clusters"],
                    "top_terms": [k for k, _ in top],
                })
            except Exception:
                pass
        return results

    # ------------------------------------------------------------------ #
    #  HTML export (PyVis)                                                 #
    # ------------------------------------------------------------------ #
    def export_to_html(
        self,
        output_path: str,
        title: str = "Blicsa - Mapeamento Bibliométrico",
    ):
        net = Network(
            height="800px", width="100%",
            bgcolor="#ffffff", font_color="#334155",
            heading=title,
        )
        net.from_nx(self.G)
        net.set_options(json.dumps({
            "nodes": {
                "font": {"size": 13, "strokeWidth": 2, "strokeColor": "#ffffff", "color": "#334155"},
                "borderWidth": 2, "borderWidthSelected": 3, "shadow": True,
            },
            "edges": {
                "color": {"inherit": "both", "opacity": 0.6},
                "smooth": {"enabled": True, "type": "continuous"},
                "shadow": False,
            },
            "physics": {
                "barnesHut": {
                    "gravitationalConstant": -12000, "centralGravity": 0.3,
                    "springLength": 180, "springConstant": 0.04, "damping": 0.09,
                },
                "minVelocity": 0.75, "maxVelocity": 50,
            },
            "interaction": {
                "hover": True, "tooltipDelay": 100,
                "navigationButtons": True, "keyboard": True,
            },
        }))
        net.write_html(output_path)
        
        # Inject VOSviewer style highlights
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                html = f.read()
            
            target = "network = new vis.Network(container, data, options);"
            if target in html:
                js_inject = """network = new vis.Network(container, data, options);

                  // ── VOSviewer style highlights ──────────────────────────────────
                  function hexToRGBA(hex, alpha) {
                      if (!hex) return 'rgba(100,100,100,' + alpha + ')';
                      hex = hex.replace('#', '');
                      if (hex.length === 3) {
                          hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
                      }
                      var r = parseInt(hex.substring(0, 2), 16);
                      var g = parseInt(hex.substring(2, 4), 16);
                      var b = parseInt(hex.substring(4, 6), 16);
                      return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
                  }

                  network.on("hoverNode", function(params) {
                      var hoveredNode = params.node;
                      var connectedNodes = network.getConnectedNodes(hoveredNode);
                      var connectedEdges = network.getConnectedEdges(hoveredNode);
                      
                      var nodeUpdates = [];
                      var edgeUpdates = [];
                      
                      var nodeColor = allNodes[hoveredNode].color;
                      if (typeof nodeColor === 'object' && nodeColor !== null) {
                          nodeColor = nodeColor.background || nodeColor.color;
                      }
                      if (!nodeColor) nodeColor = "#3b82f6";
                      
                      for (var nodeId in allNodes) {
                          var isConnected = (nodeId == hoveredNode) || (connectedNodes.indexOf(nodeId) !== -1);
                          var origCol = allNodes[nodeId].color;
                          if (typeof origCol === 'object' && origCol !== null) {
                              origCol = origCol.background || origCol.color;
                          }
                          nodeUpdates.push({
                              id: nodeId,
                              color: {
                                  background: hexToRGBA(origCol, isConnected ? 1.0 : 0.15),
                                  border: hexToRGBA(origCol, isConnected ? 1.0 : 0.15)
                              },
                              font: {
                                  color: isConnected ? '#1e293b' : 'rgba(148,163,184,0.15)',
                                  strokeColor: isConnected ? '#ffffff' : 'rgba(255,255,255,0.15)'
                              }
                          });
                      }
                      
                      for (var edgeId in allEdges) {
                          var isConnected = connectedEdges.indexOf(edgeId) !== -1;
                          if (isConnected) {
                              edgeUpdates.push({
                                  id: edgeId,
                                  color: {
                                      color: hexToRGBA(nodeColor, 0.85),
                                      highlight: hexToRGBA(nodeColor, 0.95),
                                      hover: hexToRGBA(nodeColor, 0.95),
                                      opacity: 0.85
                                  },
                                  width: (allEdges[edgeId].width || 1) * 2.5
                              });
                          } else {
                              edgeUpdates.push({
                                  id: edgeId,
                                  color: {
                                      color: 'rgba(200,200,200,0.05)',
                                      opacity: 0.05
                                  }
                              });
                          }
                      }
                      
                      nodes.update(nodeUpdates);
                      edges.update(edgeUpdates);
                  });

                  network.on("blurNode", function(params) {
                      var nodeUpdates = [];
                      var edgeUpdates = [];
                      
                      for (var nodeId in allNodes) {
                          var origCol = allNodes[nodeId].color;
                          if (typeof origCol === 'object' && origCol !== null) {
                              origCol = origCol.background || origCol.color;
                          }
                          nodeUpdates.push({
                              id: nodeId,
                              color: {
                                  background: origCol,
                                  border: origCol
                              },
                              font: {
                                  color: '#334155',
                                  strokeColor: '#ffffff'
                              }
                          });
                      }
                      
                      for (var edgeId in allEdges) {
                          var origEdge = allEdges[edgeId];
                          var origColor = origEdge.color || { inherit: 'both', opacity: 0.6 };
                          edgeUpdates.push({
                              id: edgeId,
                              color: origColor,
                              width: origEdge.width || 1
                          });
                      }
                      
                      nodes.update(nodeUpdates);
                      edges.update(edgeUpdates);
                  });"""
                html = html.replace(target, js_inject)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html)
        except Exception as e:
            print(f"[ERRO ao injetar JS] {e}")

    # ------------------------------------------------------------------ #
    #  Graph format exports                                                #
    # ------------------------------------------------------------------ #
    def export_gml(self, output_path: str):
        """GML — compatible with Gephi, Cytoscape, igraph."""
        # GML requires integer/float/string node attrs; sanitize
        G = self.G.copy()
        for n, data in G.nodes(data=True):
            data.pop("title", None)  # HTML strings break some GML parsers
        nx.write_gml(G, output_path)

    def export_pajek(self, output_path: str):
        """Pajek .net format."""
        nx.write_pajek(self.G, output_path)

    def export_gexf(self, output_path: str):
        """GEXF — compatible with Gephi, native Gephi format with full node attributes."""
        G = self.G.copy()
        for n, data in G.nodes(data=True):
            data.pop("title", None)
            data.pop("color", None)
            data["year_mean"] = float(data.get("year_mean", 0.0))
            data["citations_mean"] = float(data.get("citations_mean", 0.0))
            data["citations_sum"] = int(data.get("citations_sum", 0))
        nx.write_gexf(G, output_path)

    def export_vosviewer(self, map_path: str, network_path: str, positions: dict | None = None):
        """Export VOSviewer map and network files (tab-separated txt)."""
        map_rows = []
        map_rows.append("id\tlabel\tx\ty\tcluster\tweight\tscore<mean pub year>\tscore<mean citations>")
        
        pos = positions or {}
        for idx, node in enumerate(self.G.nodes(), 1):
            x, y = 0.0, 0.0
            if node in pos:
                x, y = pos[node][0], pos[node][1]
            cluster = self.G.nodes[node].get("group", 0)
            weight = self.G.nodes[node].get("occurrence", self.G.degree(node, weight="weight"))
            mean_yr = self.G.nodes[node].get("year_mean", 0.0)
            mean_cits = self.G.nodes[node].get("citations_mean", 0.0)
            
            map_rows.append(f"{idx}\t{node}\t{x}\t{y}\t{cluster}\t{weight}\t{mean_yr}\t{mean_cits}")
            
        with open(map_path, "w", encoding="utf-8") as f:
            f.write("\n".join(map_rows))
            
        net_rows = []
        node_ids = {node: i for i, node in enumerate(self.G.nodes(), 1)}
        for u, v, d in self.G.edges(data=True):
            w = d.get("weight", 1.0)
            net_rows.append(f"{node_ids[u]}\t{node_ids[v]}\t{w}")
            
        with open(network_path, "w", encoding="utf-8") as f:
            f.write("\n".join(net_rows))

    def export_excel(self, output_path: str, df_raw=None):
        """Xlsx with Rankings sheet + raw DataFrame sheet."""
        import pandas as pd
        bc = nx.betweenness_centrality(self.G)
        rows = []
        for name, attrs in self.G.nodes(data=True):
            rows.append({
                "Termo / Autor": name,
                "Ocorrências":   attrs.get("occurrence", 0),
                "Grau":          round(self.G.degree(name, weight="weight"), 3),
                "Betweenness":   round(bc.get(name, 0), 4),
                "Cluster":       attrs.get("group", 0),
                "Ano Médio":     round(attrs.get("year_mean", 0) or 0, 1),
                "Relevância":    round(attrs.get("relevance", 0) or 0, 3),
            })
        rank_df = (
            pd.DataFrame(rows)
            .sort_values("Ocorrências", ascending=False)
            .reset_index(drop=True)
        )
        edge_rows = [
            {
                "Source": u, "Target": v,
                "Weight": round(float(d.get("weight", 1)), 4),
                "Weight Raw": round(float(d.get("weight_raw", d.get("weight", 1))), 4),
            }
            for u, v, d in self.G.edges(data=True)
        ]
        edge_df = pd.DataFrame(edge_rows)
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            rank_df.to_excel(writer, sheet_name="Rankings", index=False)
            edge_df.to_excel(writer, sheet_name="Arestas", index=False)
            if df_raw is not None:
                df_raw.to_excel(writer, sheet_name="DataFrame", index=False)

    def export_json_topology(self, output_path: str, positions: dict | None = None):
        """JSON {nodes, edges} for frontend injection (Cytoscape.js / D3.js)."""
        partition = nx.get_node_attributes(self.G, "group")
        raw_sizes = nx.get_node_attributes(self.G, "size")
        nodes_list = list(self.G.nodes())

        # Normalize sizes
        raw = [raw_sizes.get(n, 20) for n in nodes_list]
        mn, mx = min(raw, default=20), max(raw, default=20)
        span = mx - mn if mx != mn else 1

        nodes = []
        for n in nodes_list:
            entry: dict = {
                "id": n,
                "label": n,
                "size": round(10 + 30 * (raw_sizes.get(n, 20) - mn) / span, 2),
                "color": CLUSTER_PALETTE[partition.get(n, 0) % len(CLUSTER_PALETTE)],
                "cluster": partition.get(n, 0),
                "occurrence": self.G.nodes[n].get("occurrence", 0),
                "relevance": self.G.nodes[n].get("relevance", 0),
                "year_mean": self.G.nodes[n].get("year_mean", 0),
            }
            if positions and n in positions:
                entry["x"] = round(float(positions[n][0]), 4)
                entry["y"] = round(float(positions[n][1]), 4)
            nodes.append(entry)

        edges = [
            {
                "source": u,
                "target": v,
                "weight": round(float(d.get("weight", 1)), 4),
                "weight_raw": round(float(d.get("weight_raw", d.get("weight", 1))), 4),
            }
            for u, v, d in self.G.edges(data=True)
        ]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"nodes": nodes, "edges": edges}, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    #  Analytics                                                           #
    # ------------------------------------------------------------------ #
    def get_summary_stats(self) -> dict:
        years = self.df["year"].dropna()
        cits = (
            self.df["citations"].dropna()
            if "citations" in self.df.columns
            else pd.Series(dtype=float)
        )
        return {
            "total_papers":    int(len(self.df)),
            "total_nodes":     int(self.G.number_of_nodes()),
            "total_edges":     int(self.G.number_of_edges()),
            "years_range":     f"{int(years.min())} – {int(years.max())}" if not years.empty else "N/A",
            "top_cited":       int(cits.max()) if not cits.empty else 0,
            "avg_citations":   round(float(cits.mean()), 2) if not cits.empty else 0.0,
            "num_clusters":    int(max(nx.get_node_attributes(self.G, "group").values(), default=-1) + 1),
            "network_density": round(float(nx.density(self.G)), 4) if self.G.number_of_nodes() > 1 else 0.0,
        }

    def get_top_keywords(self, n: int = 20) -> list[tuple[str, int]]:
        all_kws: list[str] = []
        for kw_str in self.df["keywords"].dropna():
            if isinstance(kw_str, str):
                sep = ";" if ";" in kw_str else ","
                all_kws.extend(k.strip().lower() for k in kw_str.split(sep) if k.strip())
        return Counter(all_kws).most_common(n)

    def get_top_authors(self, n: int = 20) -> list[tuple[str, int]]:
        all_authors: list[str] = []
        for raw in self.df["authors"].dropna():
            if isinstance(raw, str):
                sep = ";" if ";" in raw else ","
                all_authors.extend(a.strip() for a in raw.split(sep) if a.strip())
        return Counter(all_authors).most_common(n)

    def get_top_sources(self, n: int = 15) -> list[tuple[str, int]]:
        return Counter(self.df["source"].dropna()).most_common(n)

    def get_author_hindex(self, n: int = 50) -> list[tuple[str, int, int, int, float]]:
        """Return [(author, h_index, g_index, papers, avg_citations)] sorted by h-index desc."""
        import re as _re
        author_cites: dict[str, list[int]] = {}
        for _, row in self.df.iterrows():
            raw = str(row.get("authors", "") or "")
            cit = int(row.get("citations", 0) or 0)
            sep = ";" if ";" in raw else ","
            for a in raw.split(sep):
                a = a.strip()
                if a:
                    author_cites.setdefault(a, []).append(cit)

        results: list[tuple[str, int, int, int, float]] = []
        for author, cite_list in author_cites.items():
            sorted_cites = sorted(cite_list, reverse=True)
            h = sum(1 for i, c in enumerate(sorted_cites, 1) if c >= i)
            
            # g-index calculation
            g = 0
            c_sum = 0
            for i, c in enumerate(sorted_cites, 1):
                c_sum += c
                if c_sum >= i * i:
                    g = i
                    
            avg = sum(cite_list) / len(cite_list)
            results.append((author, h, g, len(cite_list), avg))

        results.sort(key=lambda x: (x[1], x[2], x[4]), reverse=True)
        return results[:n]

    def get_cluster_report(self) -> list[dict]:
        partition = nx.get_node_attributes(self.G, "group")
        if not partition:
            return []
        clusters: dict[int, list[str]] = {}
        for node, grp in partition.items():
            clusters.setdefault(grp, []).append(node)
        report = []
        for grp, nodes in sorted(clusters.items()):
            report.append({
                "cluster_id": grp,
                "color":      CLUSTER_PALETTE[grp % len(CLUSTER_PALETTE)],
                "size":       len(nodes),
                "top_nodes":  sorted(
                    nodes,
                    key=lambda n: self.G.degree(n, weight="weight"),
                    reverse=True,
                )[:5],
            })
        return sorted(report, key=lambda c: c["size"], reverse=True)

    def export_rankings_csv(self, output_path: str):
        bc = nx.betweenness_centrality(self.G)
        rows = []
        for name, attrs in self.G.nodes(data=True):
            rows.append({
                "node":             name,
                "degree":           self.G.degree(name),
                "weighted_degree":  self.G.degree(name, weight="weight"),
                "betweenness":      round(bc.get(name, 0), 4),
                "cluster":          attrs.get("group", -1),
                "color":            attrs.get("color", ""),
                "occurrence":       attrs.get("occurrence", ""),
                "doc_freq":         attrs.get("doc_freq", ""),
                "relevance":        attrs.get("relevance", ""),
                "year_mean":        attrs.get("year_mean", ""),
            })
        (
            pd.DataFrame(rows)
            .sort_values("weighted_degree", ascending=False)
            .to_csv(output_path, index=False, encoding="utf-8-sig")
        )

    def export_edges_csv(self, output_path: str):
        rows = [
            {
                "source":     u,
                "target":     v,
                "weight":     d.get("weight", 1),
                "weight_raw": d.get("weight_raw", d.get("weight", 1)),
            }
            for u, v, d in self.G.edges(data=True)
        ]
        (
            pd.DataFrame(rows)
            .sort_values("weight", ascending=False)
            .to_csv(output_path, index=False, encoding="utf-8-sig")
        )

    def get_thematic_map(self) -> dict:
        """Calculate Callon centrality & density for each cluster."""
        partition = nx.get_node_attributes(self.G, "group")
        if not partition:
            return {}
        clusters: dict[int, list[str]] = {}
        for node, grp in partition.items():
            clusters.setdefault(grp, []).append(node)
            
        data = {}
        for grp, nodes in clusters.items():
            ext_edges = []
            for u in nodes:
                for v in self.G.neighbors(u):
                    if v not in nodes:
                        ext_edges.append(self.G[u][v].get("weight", 1.0))
            centrality = sum(ext_edges)
            
            int_edges = []
            for u in nodes:
                for v in self.G.neighbors(u):
                    if v in nodes:
                        int_edges.append(self.G[u][v].get("weight", 1.0))
            density = (sum(int_edges) / 2.0) / len(nodes) if len(nodes) > 0 else 0.0
            
            top_term = sorted(nodes, key=lambda n: self.G.degree(n, weight="weight"), reverse=True)[0]
            
            data[grp] = {
                "label": top_term,
                "centrality": centrality,
                "density": density,
                "size": len(nodes)
            }
            
        return data

    def get_sankey_data(self, left_field="source", middle_field="authors", right_field="keywords", top_n=10) -> dict:
        """Build flows for three-field Sankey diagram: left -> middle -> right."""
        def get_top_values(field):
            counts = Counter()
            for val in self.df[field].dropna():
                sep = ";" if ";" in str(val) else ","
                parts = [p.strip() for p in str(val).split(sep) if p.strip()]
                counts.update(parts)
            return set(name for name, _ in counts.most_common(top_n))

        left_set = get_top_values(left_field)
        middle_set = get_top_values(middle_field)
        right_set = get_top_values(right_field)

        left_to_middle = Counter()
        middle_to_right = Counter()

        for _, row in self.df.iterrows():
            l_val = str(row.get(left_field, "") or "")
            m_val = str(row.get(middle_field, "") or "")
            r_val = str(row.get(right_field, "") or "")

            l_sep = ";" if ";" in l_val else ","
            m_sep = ";" if ";" in m_val else ","
            r_sep = ";" if ";" in r_val else ","

            l_parts = [p.strip() for p in l_val.split(l_sep) if p.strip() and p.strip() in left_set]
            m_parts = [p.strip() for p in m_val.split(m_sep) if p.strip() and p.strip() in middle_set]
            r_parts = [p.strip() for p in r_val.split(r_sep) if p.strip() and p.strip() in right_set]

            for l in l_parts:
                for m in m_parts:
                    left_to_middle[(l, m)] += 1
            for m in m_parts:
                for r in r_parts:
                    middle_to_right[(m, r)] += 1

        nodes = list(left_set) + list(middle_set) + list(right_set)
        node_indices = {name: i for i, name in enumerate(nodes)}

        sources = []
        targets = []
        values = []

        for (u, v), w in left_to_middle.items():
            sources.append(node_indices[u])
            targets.append(node_indices[v])
            values.append(w)

        for (u, v), w in middle_to_right.items():
            sources.append(node_indices[u])
            targets.append(node_indices[v])
            values.append(w)

        return {
            "nodes": nodes,
            "sources": sources,
            "targets": targets,
            "values": values,
            "raw_flows": {
                "left_to_middle": dict(left_to_middle),
                "middle_to_right": dict(middle_to_right)
            }
        }

import sys
import re
from pathlib import Path

def patch_parsers():
    p = Path("core/parsers.py")
    content = p.read_text(encoding="utf-8")
    if "def load_pdf(self)" not in content:
        pdf_code = """
    # ------------------------------------------------------------------ #
    #  PDF Full-Text                                                       #
    # ------------------------------------------------------------------ #
    def load_pdf(self) -> pd.DataFrame:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber is not installed. Please install it.")
        full_text = ""
        try:
            with pdfplumber.open(self.file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: full_text += t + "\\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        import pandas as pd
        df = pd.DataFrame()
        df["authors"]    = pd.Series([""], dtype=str)
        df["title"]      = pd.Series([self.file_path.name], dtype=str)
        df["year"]       = pd.Series([2024], dtype=int)
        df["source"]     = pd.Series(["PDF File"], dtype=str)
        df["keywords"]   = pd.Series([""], dtype=str)
        df["abstract"]   = pd.Series([full_text], dtype=str)
        df["citations"]  = pd.Series([0], dtype=int)
        df["doi"]        = pd.Series([""], dtype=str)
        df["references"] = pd.Series([""], dtype=str)
        df["origin"]     = "PDF Full-Text"
        self.df = df
        return self.df
"""
        # Inject at the end of class BibliometricParser
        content = content.replace('def load_ris(self) -> pd.DataFrame:', pdf_code + '\n    def load_ris(self) -> pd.DataFrame:')
        p.write_text(content, encoding="utf-8")

def patch_main():
    p = Path("main.py")
    content = p.read_text(encoding="utf-8")
    
    # 1. Add PDF to formats
    if '"pdf":      "load_pdf"' not in content:
        content = content.replace(
            '"ris":      "load_ris",',
            '"ris":      "load_ris",\n                "pdf":      "load_pdf",'
        )
    if 'values=["Scopus (CSV)' in content and 'PDF' not in content:
        content = content.replace(
            'values=["Scopus (CSV)", "Web of Science (TXT)", "BibTeX", "PubMed (TXT)", "OpenAlex (JSON)", "Crossref (JSON)", "RIS"]',
            'values=["Scopus (CSV)", "Web of Science (TXT)", "BibTeX", "PubMed (TXT)", "OpenAlex (JSON)", "Crossref (JSON)", "RIS", "PDF (Full-Text)"]'
        )
    if 'elif val == "RIS": return "ris"' in content and 'PDF' not in content:
        content = content.replace(
            'elif val == "RIS": return "ris"',
            'elif val == "RIS": return "ris"\n        elif val == "PDF (Full-Text)": return "pdf"'
        )
        
    # 2. Add Zotero to search sources
    if '("Zotero", "zotero")' not in content:
        content = content.replace(
            'for lbl, val in [("Todas as Bases", "all"), ("OpenAlex", "openalex"), ("Crossref", "crossref"), ("PubMed", "pubmed")]:',
            'for lbl, val in [("Todas as Bases", "all"), ("OpenAlex", "openalex"), ("Crossref", "crossref"), ("PubMed", "pubmed"), ("Zotero", "zotero")]:'
        )
    
    if '"zotero"' not in content:
        content = content.replace(
            '"pubmed": "PubMed MEDLINE"',
            '"pubmed": "PubMed MEDLINE",\n        "zotero": "Zotero"'
        )
        
    if 'ZoteroProvider' not in content:
        content = content.replace(
            'from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider',
            'from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider\n            from core.sources.zotero import ZoteroProvider'
        )
        content = content.replace(
            'elif src == "pubmed":\n                providers_to_run = [PubMedProvider()]',
            'elif src == "pubmed":\n                providers_to_run = [PubMedProvider()]\n            elif src == "zotero":\n                providers_to_run = [ZoteroProvider()]'
        )

    # 3. Add Semantic Clustering to Analysis Types
    if 'Agrupamento Semântico (Embeddings)' not in content:
        content = content.replace(
            '"Co-classificação IPC (patentes)",',
            '"Co-classificação IPC (patentes)",\n    "Agrupamento Semântico (Embeddings)",'
        )
        
    p.write_text(content, encoding="utf-8")

def create_zotero_provider():
    p = Path("core/sources/zotero.py")
    if not p.exists():
        p.write_text('''
import urllib.parse
import json
import logging
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider

logger = logging.getLogger("ZoteroProvider")

class ZoteroProvider(SearchProvider):
    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        # Zotero user ID can be passed in query. e.g. "475425"
        user_id = query.strip()
        if not user_id.isdigit():
            user_id = "475425" # default public library
            
        base_url = f"https://api.zotero.org/users/{user_id}/items?format=json&limit={min(100, max_results)}"
        import urllib.request
        try:
            req = urllib.request.Request(base_url, headers={'User-Agent': 'Blicsa'})
            with urllib.request.urlopen(req) as res:
                data = json.loads(res.read().decode('utf-8'))
                for i, item in enumerate(data):
                    if cancel_event and cancel_event.is_set(): break
                    d = item.get("data", {})
                    creators = [c.get("lastName", "") + ", " + c.get("firstName", "") for c in d.get("creators", []) if "lastName" in c]
                    yield {
                        "doi": d.get("DOI", ""),
                        "title": d.get("title", "No Title"),
                        "authors": "; ".join(creators),
                        "year": d.get("date", "")[:4] if d.get("date") else None,
                        "source": d.get("publicationTitle", ""),
                        "abstract": d.get("abstractNote", ""),
                        "citations": 0
                    }
                    if progress_cb: progress_cb(i+1, len(data))
        except Exception as e:
            logger.error(f"Zotero API error: {e}")
''', encoding="utf-8")

def patch_matrix_builders():
    p = Path("core/matrix_builders.py")
    content = p.read_text(encoding="utf-8")
    if "Agrupamento Semântico" not in content:
        # Patch map generation
        content = content.replace(
            'def generate(self, network_type: str, field: str, counting_method: str = "full"):',
            '''def generate(self, network_type: str, field: str, counting_method: str = "full"):
        if network_type == "Agrupamento Semântico (Embeddings)":
            self._build_semantic_network(field)
            return
        '''
        )
        
        semantic_code = '''
    def _build_semantic_network(self, field: str):
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            raise RuntimeError("sentence-transformers and scikit-learn are required for this analysis. Please install them.")
        
        self._update_progress("Carregando modelo de NLP...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        texts = []
        indices = []
        for i, row in self.df.iterrows():
            if field == "keywords": t = str(row.get("keywords", ""))
            elif field == "titles": t = str(row.get("title", ""))
            elif field == "abstracts": t = str(row.get("abstract", ""))
            else: t = str(row.get("title", "")) + " " + str(row.get("abstract", ""))
            if len(t) > 10:
                texts.append(t)
                indices.append(i)
                
        if not texts:
            raise ValueError("Não há texto suficiente para criar os embeddings.")
            
        self._update_progress("Gerando embeddings semânticos...")
        embeddings = model.encode(texts)
        sim_matrix = cosine_similarity(embeddings)
        
        self.G = nx.Graph()
        for idx in indices:
            name = str(self.df.at[idx, "title"])[:50] + "..."
            self.G.add_node(name, count=1, original_id=idx)
            
        self._update_progress("Conectando nós similares...")
        threshold = 0.6
        for i in range(len(indices)):
            for j in range(i+1, len(indices)):
                w = float(sim_matrix[i, j])
                if w > threshold:
                    n1 = str(self.df.at[indices[i], "title"])[:50] + "..."
                    n2 = str(self.df.at[indices[j], "title"])[:50] + "..."
                    self.G.add_edge(n1, n2, weight=w, norm_weight=w)
        
        self._detect_communities()
'''
        content = content.replace('def _build_cooccurrence(self, field: str, counting_method: str):', semantic_code + '\n    def _build_cooccurrence(self, field: str, counting_method: str):')
        p.write_text(content, encoding="utf-8")

def patch_init_sources():
    p = Path("core/sources/__init__.py")
    content = p.read_text(encoding="utf-8")
    if 'ZoteroProvider' not in content:
        content += "\\nfrom .zotero import ZoteroProvider\\n"
        p.write_text(content, encoding="utf-8")

def update_requirements():
    p = Path("requirements.txt")
    reqs = p.read_text(encoding="utf-8")
    for r in ["pdfplumber", "sentence-transformers", "scikit-learn"]:
        if r not in reqs:
            reqs += f"\\n{r}"
    p.write_text(reqs, encoding="utf-8")

if __name__ == "__main__":
    patch_parsers()
    patch_main()
    create_zotero_provider()
    patch_matrix_builders()
    patch_init_sources()
    update_requirements()
    print("Agent implementation complete.")

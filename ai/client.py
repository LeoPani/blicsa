import os
import re
from groq import Groq

MODEL = "llama-3.3-70b-versatile"


class GroqBibliometricAnalyst:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.client = Groq(api_key=self.api_key) if self.api_key else None

    def _chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        if not self.client:
            return "Erro: GROQ_API_KEY não configurada."
        resp = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            model=MODEL,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    def generate_insights(
        self,
        top_keywords: list[tuple[str, int]],
        summary_stats: dict,
        cluster_report: list[dict] | None = None,
        year_distribution: dict | None = None,
    ) -> str:
        cluster_txt = ""
        if cluster_report:
            cluster_txt = "\n\nComunidades (clusters) detectados:\n"
            for c in cluster_report[:10]:
                cluster_txt += (
                    f"  Cluster {c['cluster_id']} "
                    f"({c['size']} nós): "
                    f"{', '.join(c['top_nodes'][:5])}\n"
                )

        year_txt = ""
        if year_distribution:
            top_years = sorted(
                year_distribution.items(), key=lambda x: x[1], reverse=True
            )[:5]
            year_txt = f"\n\nAnos com mais publicações: {top_years}"

        prompt = (
            f"Analise os dados bibliométricos abaixo:\n\n"
            f"Estatísticas gerais: {summary_stats}\n"
            f"Top 20 palavras-chave: {top_keywords}"
            f"{cluster_txt}{year_txt}\n\n"
            "Produza a análise em Markdown com as seções:\n"
            "## Frentes de Pesquisa Emergentes\n"
            "## Lacunas Científicas Identificadas\n"
            "## Recomendações para Pesquisa Futura\n"
            "\nUse linguagem técnica acadêmica em português. Seja direto, conciso, objetivo e evite rodeios ou introduções longas. Foque em percepções práticas."
        )
        return self._chat(
            system="Você é especialista em cientometria, análise bibliométrica e mapeamento científico.",
            user=prompt,
        )

    def label_clusters(
        self,
        cluster_report: list[dict],
        context: str = "",
    ) -> dict[int, str]:
        """Return {cluster_id: 'label semântico'} para cada cluster."""
        lines = [
            f"Cluster {c['cluster_id']}: {', '.join(c['top_nodes'][:6])}"
            for c in cluster_report[:12]
        ]
        ctx = f" sobre {context}" if context else ""
        prompt = (
            f"Abaixo estão os clusters de uma rede bibliométrica{ctx}.\n"
            "Cada cluster é representado pelos termos/autores mais centrais.\n\n"
            + "\n".join(lines)
            + "\n\nPara cada cluster, responda SOMENTE no formato:\n"
            "ID: Label conciso em português (2-5 palavras)\n"
            "Exemplo:\n0: Aprendizado de Máquina\n1: Visão Computacional"
        )
        raw = self._chat(
            system=(
                "Você é especialista em análise bibliométrica. "
                "Responda APENAS com as linhas no formato pedido, sem texto adicional."
            ),
            user=prompt,
            temperature=0.1,
        )
        labels: dict[int, str] = {}
        for line in raw.strip().splitlines():
            m = re.match(r"^\s*(\d+)\s*:\s*(.+)$", line)
            if m:
                labels[int(m.group(1))] = m.group(2).strip()
        return labels

    def generate_sankey_insights(self, relations_summary: str) -> str:
        prompt = (
            "Analise as relações de fluxo (Sankey de Três Campos: Autores -> Palavras-Chave -> Periódicos) abaixo:\n\n"
            f"{relations_summary}\n\n"
            "Produza uma análise em Markdown com as seções:\n"
            "## Fluxo de Conhecimento (Sankey)\n"
            "## Principais Atores e Fontes\n"
            "\nUse linguagem técnica acadêmica em português. Seja direto, conciso, objetivo e evite rodeios ou introduções longas. Foque em percepções práticas."
        )
        return self._chat(
            system="Você é especialista em cientometria e mapeamento científico.",
            user=prompt
        )

    def generate_thematic_insights(self, quadrants_summary: str) -> str:
        prompt = (
            "Analise os dados do Mapa Temático (Quadrantes de Callon: Centralidade vs Densidade) abaixo:\n\n"
            f"{quadrants_summary}\n\n"
            "Produza uma análise em Markdown com as seções:\n"
            "## Análise dos Quadrantes Estratégicos\n"
            "## Temas Motores e Especializados\n"
            "## Temas Emergentes e Básicos\n"
            "\nUse linguagem técnica acadêmica em português. Seja direto, conciso, objetivo e evite rodeios ou introduções longas. Foque em percepções práticas."
        )
        return self._chat(
            system="Você é especialista em cientometria e mapeamento científico.",
            user=prompt
        )

    def generate_historiograph_insights(self, citation_paths: str) -> str:
        prompt = (
            "Analise a historiografia de citações diretas entre os principais artigos abaixo:\n\n"
            f"{citation_paths}\n\n"
            "Produza uma análise em Markdown com as seções:\n"
            "## Evolução Histórica (Historiografia)\n"
            "## Marcos Científicos e Artigos Centrais\n"
            "\nUse linguagem técnica acadêmica em português. Seja direto, conciso, objetivo e evite rodeios ou introduções longas. Foque em percepções práticas."
        )
        return self._chat(
            system="Você é especialista em cientometria e mapeamento científico.",
            user=prompt
        )

    def generate_seminal_insights(self, top_references: str) -> str:
        prompt = (
            "A lista a seguir contém os trabalhos e livros mais citados (referências citadas) no conjunto de dados bibliométricos analisado:\n\n"
            f"{top_references}\n\n"
            "Com base nessa lista e no seu conhecimento científico geral:\n"
            "1. Identifique os autores seminais (fundadores ou marcos da área) e suas respectivas obras/livros seminais.\n"
            "2. Forneça uma breve descrição (2-4 frases) explicando do que se trata cada livro ou artigo seminal específico identificado, destacando sua relevância e contribuição teórica para a ciência.\n\n"
            "Produza o relatório em Markdown estruturado por autores seminais. Use linguagem técnica acadêmica em português. Seja direto, conciso, objetivo e evite introduções longas. Foque em descrições práticas."
        )
        return self._chat(
            system="Você é especialista em cientometria, história da ciência e mapeamento científico.",
            user=prompt
        )

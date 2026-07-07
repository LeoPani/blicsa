import os
import re
import json
import urllib.request
import urllib.error
import time

def call_openai_chat(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    timeout: int = 30
) -> str:
    """Make direct HTTP POST to any OpenAI-compatible endpoint with retries and key redaction."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature
    }
    
    redacted_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"[AI Client] Requisitando {base_url}/chat/completions (Model: {model}, Key: {redacted_key})")
    
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Blicsa/1.0 (Python)"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    retries = 3
    delay = 1.0
    while retries > 0:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[AI Client] Limite de requisições (429). Retentando em {delay}s...")
                time.sleep(delay)
                delay *= 2
                retries -= 1
            else:
                # Read response details for better errors if available
                try:
                    err_msg = e.read().decode("utf-8")
                    print(f"[AI Client] HTTP Error {e.code}: {err_msg}")
                except Exception:
                    pass
                raise e
        except Exception as e:
            print(f"[AI Client] Erro na requisição: {e}")
            retries -= 1
            if retries == 0:
                raise e
            time.sleep(delay)
            delay *= 2
    return "Erro ao obter resposta da IA."


def call_openai_chat_history(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    timeout: int = 30
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    redacted_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"[AI Client] Requisitando {base_url}/chat/completions (Model: {model}, Key: {redacted_key})")
    
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Blicsa/1.0 (Python)"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    import json, urllib.request, time
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    retries = 3
    delay = 1.0
    while retries > 0:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data["choices"][0]["message"]["content"]
        except Exception as e:
            retries -= 1
            if retries == 0:
                return f"Erro na requisição: {e}"
            time.sleep(delay)
            delay *= 2
    return "Erro ao obter resposta da IA."

    def chat_history(self, messages: list[dict], temperature: float = 0.7) -> str:
        if not self.api_key:
            return "Erro: API Key não configurada nos Ajustes."
        return call_openai_chat_history(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            messages=messages,
            temperature=temperature
        )

class AIAnalyst:

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("AI_API_KEY", os.environ.get("GROQ_API_KEY"))
        self.base_url = base_url or os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1")
        self.model = model or os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")

    def chat_history(self, messages: list[dict], temperature: float = 0.7) -> str:
        if not self.api_key:
            return 'Erro: API Key não configurada nos Ajustes.'
        return call_openai_chat_history(self.base_url, self.api_key, self.model, messages, temperature)

    def _chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        if not self.api_key:
            return "Erro: API Key não configurada nos Ajustes."
        return call_openai_chat(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            system_prompt=system,
            user_prompt=user,
            temperature=temperature
        )

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

# Backward-compatible alias
class GroqBibliometricAnalyst(AIAnalyst):
    pass

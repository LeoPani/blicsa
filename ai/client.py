import os
import re
import json
import urllib.request
import urllib.error
import time


#: Como o Blicsa se identifica em toda requisição HTTP à API de IA.
#:
#: **Não é cosmético.** O Groq fica atrás de Cloudflare, que responde `403` com `error code:
#: 1010` a cliente sem User-Agent reconhecível — antes de a chave ser sequer avaliada. Toda
#: requisição do app precisa carregá-lo, senão o diagnóstico devolve "chave recusada" para
#: uma chave perfeitamente válida.
USER_AGENT = "Blicsa/1.0 (Python)"

#: Instrução de **registro** das análises — como escrever, não em que língua.
#:
#: A cláusula "em português" vivia aqui, repetida em cinco prompts, e era o que fazia o mapa
#: temático e o Sankey saírem em português para quem usa o app em inglês ou francês. O idioma
#: agora vem do `system` via `diretiva_idioma(get_lang())`, uma vez só, em `_system_com_contexto`.
#:
#: O prompt continua escrito em português de propósito: a diretiva diz ao modelo para responder
#: no idioma da interface *independentemente do idioma deste prompt*. Traduzir os prompts seria
#: multiplicar por três o que precisa ser mantido, sem ganho para o usuário.
ESTILO_ANALISE = ("Use linguagem técnica acadêmica. Seja direto, conciso, objetivo e evite "
                  "rodeios ou introduções longas. Foque em percepções práticas.")

#: Variante das obras seminais, que descrevem obras em vez de apontar percepções. Mantida
#: separada para que esta correção mude só o idioma — a redação de cada prompt fica como estava.
ESTILO_ANALISE_SEMINAL = ("Use linguagem técnica acadêmica. Seja direto, conciso, objetivo e "
                          "evite introduções longas. Foque em descrições práticas.")


def _t(chave: str, padrao: str) -> str:
    """Texto do catálogo, com o português como último recurso.

    `t()` devolve a **própria chave** quando ela não existe em catálogo nenhum, e uma chave
    crua (`ai.sec_fluxo`) virando título de seção no relatório do usuário é pior do que o
    português que esta correção veio tirar. Daí a checagem explícita.
    """
    try:
        from core.i18n import t
        valor = t(chave)
    except Exception:
        return padrao
    return padrao if not valor or valor == chave else valor


# ── Falhas de IA em linguagem de gente (auditoria 2026-09, IA1) ─────────────────────
# Antes, toda falha chegava à tela como "Falha na requisição de IA após 3 tentativas:
# HTTP Error 401: Unauthorized" — inglês técnico, sem dizer o que fazer. E a chave errada
# era tentada 3 vezes (com espera) antes de avisar. O detalhe técnico vai para o log.
_NAO_REPETIR = {400, 401, 403, 404, 422}


def _codigo_http(e: BaseException) -> int | None:
    import urllib.error
    while e is not None:
        if isinstance(e, urllib.error.HTTPError):
            return e.code
        e = e.__cause__ or e.__context__
    return None


def mensagem_de_falha(e: BaseException) -> str:
    """Frase para o usuário explicando a falha de IA e o que fazer."""
    import socket
    import urllib.error
    codigo = _codigo_http(e)
    if codigo in (401, 403):
        return _t("ai.falha_chave", "A chave de IA foi recusada. Confira na aba Credenciais se ela "
                  "foi colada inteira (a do Groq começa com gsk_) ou crie uma nova em "
                  "console.groq.com.")
    if codigo == 429:
        return _t("ai.falha_limite", "O limite gratuito da IA foi atingido. Espere um minuto e "
                  "tente de novo.")
    if codigo == 404:
        return _t("ai.falha_modelo", "O modelo de IA configurado não está disponível no provedor. "
                  "Troque o modelo em Configurações.")
    if codigo in (400, 413, 422):
        return _t("ai.falha_pedido", "O serviço de IA recusou o pedido, provavelmente por ser "
                  "grande demais. Tente com um corpus ou mapa menor.")
    if codigo is not None and codigo >= 500:
        return _t("ai.falha_servidor", "O serviço de IA está fora do ar no momento. Tente de novo "
                  "em alguns minutos.")
    atual = e
    while atual is not None:
        if isinstance(atual, (urllib.error.URLError, socket.timeout, TimeoutError,
                              ConnectionError)):
            return _t("ai.falha_rede", "Sem conexão com o serviço de IA. Verifique a internet e "
                      "tente de novo.")
        atual = atual.__cause__ or atual.__context__
    return _t("ai.falha_resposta", "O serviço de IA respondeu de um jeito inesperado. Tente de "
              "novo; se continuar, veja o detalhe no log do programa.")


def _sem_chave() -> str:
    return _t("ai.falha_sem_chave", "Nenhuma chave de IA configurada. Cole sua chave (por exemplo, "
              "do Groq) na aba Credenciais.")


def _secoes(*pares: tuple[str, str]) -> str:
    """As seções que a análise deve produzir, já no idioma da interface.

    **Título de seção é conteúdo, não instrução.** O modelo copia estes literais para a
    resposta — foi por isso que, medido com chamada real, um relatório com corpo em francês
    saía encabeçado por "Frentes de Pesquisa Emergentes". Pior: o cabeçalho em português
    puxava o corpo junto, e o `system` sozinho perdia a disputa em 4 das 6 análises em inglês.
    """
    return "".join(f"## {_t(chave, padrao)}\n" for chave, padrao in pares)


class AIClientError(Exception):
    """Falha REAL na chamada de IA (rede, auth, quota). PROIBIDO devolver
    string de erro como se fosse conteúdo: quem chama decide como exibir."""

def call_openai_chat(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    timeout: int = 30,
    ao_medir=None,
) -> str:
    """Make direct HTTP POST to any OpenAI-compatible endpoint with retries and key redaction."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    return call_openai_chat_history(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        timeout=timeout,
        ao_medir=ao_medir,
    )


def extrair_uso(resposta: dict) -> dict | None:
    """A contagem de tokens que a resposta traz, ou `None` quando ela não traz nenhuma.

    Duas formas no mesmo ecossistema: o `usage` do padrão OpenAI, e o `x_groq.usage` que o
    Groq manda no ÚLTIMO pedaço do streaming. Como o Blicsa fala com qualquer endpoint
    compatível, as duas são lidas.

    **`None` não é zero.** Provedor que não conta, chamada cortada no meio e resposta sem o
    campo caem todos aqui, e devolver `{}` com zeros faria o relatório de pesquisa afirmar
    um consumo que ninguém mediu — pior do que dizer "não medido".
    """
    if not isinstance(resposta, dict):
        return None
    uso = resposta.get("usage")
    if not uso and isinstance(resposta.get("x_groq"), dict):
        uso = resposta["x_groq"].get("usage")
    if not isinstance(uso, dict) or not uso.get("total_tokens"):
        return None
    return {
        "prompt_tokens": uso.get("prompt_tokens", 0),
        "completion_tokens": uso.get("completion_tokens", 0),
        "total_tokens": uso.get("total_tokens", 0),
    }


def call_openai_chat_history(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    timeout: int = 30,
    ao_medir=None,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    print(f"[AI Client] Requisitando {base_url}/chat/completions (Model: {model})")
    
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    retries = 3
    delay = 1.0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                # A contagem de tokens sai por um callback, e não pelo retorno: cinco
                # chamadores esperam a string da resposta, e mudar o contrato deles para
                # levar uma medida que só o relatório usa espalharia desempacotamento por
                # todo lado. Quem não passa `ao_medir` não vê diferença nenhuma.
                if ao_medir is not None:
                    try:
                        ao_medir(extrair_uso(resp_data))
                    except Exception:
                        pass
                return resp_data["choices"][0]["message"]["content"]
        except Exception as e:
            retries -= 1
            print(f"[AI Client] falha: {type(e).__name__}: {e}")
            # Chave errada, modelo inexistente, pedido inválido: repetir não adianta.
            if retries == 0 or _codigo_http(e) in _NAO_REPETIR:
                raise AIClientError(mensagem_de_falha(e)) from e
            time.sleep(delay)
            delay *= 2


class AIAnalyst:

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, contexto_pesquisa: str = ""):
        self.api_key = api_key or os.environ.get("AI_API_KEY", os.environ.get("GROQ_API_KEY"))
        self.base_url = base_url or os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1")
        #: `llama-3.3-70b-versatile` era o padrão e foi descontinuado pelo Groq: a API passou
        #: a responder `404 model_not_found`, e o Blink quebrava com a chave CERTA — o erro
        #: não fala em modelo, então parecia problema de chave.
        self.model = model or os.environ.get("AI_MODEL", "openai/gpt-oss-120b")

        #: Contexto de pesquisa do projeto. Fica no ANALISTA, não em cada método, porque a
        #: alternativa era um parâmetro novo em `generate_insights`, `generate_sankey_...`,
        #: `generate_thematic_...`, `generate_historiograph_...`, `generate_seminal_...` e
        #: `label_clusters` — seis lugares para esquecer um, e a próxima análise a ser escrita
        #: nasceria sem contexto. Aqui, todas passam por `_chat` e recebem de graça.
        self.contexto_pesquisa = contexto_pesquisa or ""

        #: Contagem de tokens da ÚLTIMA chamada, ou `None` quando ela não veio medida.
        #: Fica no analista porque quem grava o evento de uso (a camada de tela) só sabe que
        #: a chamada terminou depois de consumir a resposta inteira — no streaming, depois
        #: do último pedaço. Um retorno a mais em cada método obrigaria os onze pontos de IA
        #: a desempacotar uma tupla para levar um número que só o relatório lê.
        self.ultimo_uso: dict | None = None

    def _system_com_contexto(self, papel: str) -> str:
        """Papel da análise + diretiva de idioma + contexto do usuário, na ordem canônica.

        A diretiva vem de `core.research_context.diretiva_idioma`, a **mesma** função que o
        chat do Blink usa — e não de um texto equivalente escrito aqui. Duas cópias da mesma
        regra divergem em silêncio, e o sintoma seria o chat responder em francês enquanto o
        mapa temático responde noutra língua, na mesma janela.

        É o ponto único de idioma das seis análises, pelo mesmo motivo que o contexto de
        pesquisa mora no analista: injetá-lo prompt a prompt seria seis lugares para esquecer
        um, e foi exatamente assim que os cinco prompts ficaram presos ao português.
        """
        from core.research_context import diretiva_idioma, montar_system_prompt

        cabecalho = _t("ai.contexto_prompt",
                       "Contexto de pesquisa informado pelo usuário (leve em conta ao responder):")
        return montar_system_prompt(papel=papel, idioma=diretiva_idioma(self._lang()),
                                    contexto_usuario=self.contexto_pesquisa,
                                    cabecalho_contexto=cabecalho)

    @staticmethod
    def _lang() -> str | None:
        """Idioma da interface, ou `None` (que `diretiva_idioma` lê como inglês)."""
        try:
            from core.i18n import get_lang
            return get_lang()
        except Exception:
            return None

    def _com_lembrete_de_idioma(self, user: str) -> str:
        """A mesma diretiva do `system`, repetida no fim do turno do usuário.

        Não é redundância decorativa — é o que a medição com chamada real exigiu. Só no
        `system`, a diretiva perdia para o corpo do prompt: 7 das 18 análises saíam em
        português, sendo 4 das 6 em inglês. O prompt de cada análise é longo e escrito em
        português, e vem **depois** da diretiva; a última instrução do turno é a que o modelo
        honra.

        Vem de `diretiva_idioma`, a mesma função do `system` e do chat do Blink. Duas
        redações do mesmo pedido, no mesmo prompt, é como se produz um modelo hesitante.
        """
        from core.research_context import diretiva_idioma

        return f"{user}\n\n{diretiva_idioma(self._lang())}"

    def _guardar_uso(self, uso: dict | None):
        self.ultimo_uso = uso

    def chat_history(self, messages: list[dict], temperature: float = 0.7) -> str:
        if not self.api_key:
            raise AIClientError(_sem_chave())
        return call_openai_chat_history(self.base_url, self.api_key, self.model, messages,
                                        temperature, ao_medir=self._guardar_uso)

    def _chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        if not self.api_key:
            raise AIClientError(_sem_chave())
        return call_openai_chat(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            # Ponto único por onde passam TODAS as análises das outras telas. É o que faz o
            # contexto chegar ao Sankey, ao mapa temático, à historiografia e às obras
            # seminais sem que cada um precise lembrar de repassá-lo.
            system_prompt=self._system_com_contexto(system),
            user_prompt=self._com_lembrete_de_idioma(user),
            temperature=temperature,
            ao_medir=self._guardar_uso,
        )

    def chat_history_stream(self, messages: list[dict], temperature: float = 0.7):
        if not self.api_key:
            raise AIClientError(_sem_chave())

        self.ultimo_uso = None
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            # Sem isto o padrão OpenAI manda `usage: null` em todo pedaço e nunca o total:
            # o relatório de pesquisa ficaria sem consumo justamente nas chamadas mais
            # longas, que são as do chat. O Groq já manda `x_groq.usage` no último pedaço
            # sem precisar pedir, e ignora o parâmetro — as duas formas são lidas.
            "stream_options": {"include_usage": True},
        }
        # Modelo de raciocínio manda o rascunho junto da resposta: o `gpt-oss` num campo
        # `reasoning` à parte, outros (qwen) num `<think>…</think>` dentro do próprio
        # `content` — que iria direto para a bolha do chat. `hidden` deixa só a resposta.
        # Só vai para o Groq: é parâmetro dele, e provedor que não conhece devolve 400.
        if "api.groq.com" in self.base_url:
            payload["reasoning_format"] = "hidden"


        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                for line in resp:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            # O pedaço que traz a medida vem com `choices` VAZIO, e é o
                            # último. Ler o uso antes de olhar para `choices` é o que faz
                            # a medida sobreviver ao `if` abaixo.
                            medida = extrair_uso(chunk)
                            if medida:
                                self.ultimo_uso = medida
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                # `.get` com teste de verdade, e não `"content" in delta`:
                                # modelo de raciocínio manda pedaços com `content: null`
                                # enquanto pensa, e `yield None` estoura na concatenação
                                # do chat.
                                if delta.get("content"):
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue
        except AIClientError:
            raise
        except Exception as e:
            # Erro no MEIO do stream também levanta; o chamador decide o que
            # fazer com o parcial já recebido.
            print(f"[AI Client] falha no streaming: {type(e).__name__}: {e}")
            raise AIClientError(mensagem_de_falha(e)) from e

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
            "ID: Label conciso (2-5 palavras)\n"
            # O exemplo ilustra o FORMATO, não a língua — dizê-lo evita que o modelo leia dois
            # rótulos em português como amostra do idioma esperado e contrarie a diretiva do
            # `system`. Deixar "em português" na linha acima era pior: instrução explícita
            # contra instrução explícita, com o resultado dependendo do modelo do dia.
            "Exemplo do formato (os rótulos vão no idioma pedido no system):\n"
            "0: Aprendizado de Máquina\n1: Visão Computacional"
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
            f"Analise as relações de fluxo ({_t('ai.obj_sankey', 'Sankey de Três Campos')}) abaixo:\n\n"
            f"{relations_summary}\n\n"
            "Produza uma análise em Markdown com as seções:\n"
            + _secoes(("ai.sec_fluxo", "Fluxo de Conhecimento (Sankey)"),
                      ("ai.sec_atores", "Principais Atores e Fontes"))
            +
            f"\n{ESTILO_ANALISE}"
        )
        return self._chat(
            system="Você é especialista em cientometria e mapeamento científico.",
            user=prompt
        )

    def generate_thematic_insights(self, quadrants_summary: str) -> str:
        prompt = (
            f"Analise os dados do {_t('ai.obj_tematico', 'Mapa Temático')} abaixo:\n\n"
            f"{quadrants_summary}\n\n"
            "Produza uma análise em Markdown com as seções:\n"
            + _secoes(("ai.sec_quadrantes", "Análise dos Quadrantes Estratégicos"),
                      ("ai.sec_motores", "Temas Motores e Especializados"),
                      ("ai.sec_emergentes", "Temas Emergentes e Básicos"))
            +
            f"\n{ESTILO_ANALISE}"
        )
        return self._chat(
            system="Você é especialista em cientometria e mapeamento científico.",
            user=prompt
        )

    def generate_historiograph_insights(self, citation_paths: str) -> str:
        prompt = (
            f"Analise a {_t('ai.obj_historiografia', 'historiografia de citações diretas')} abaixo:\n\n"
            f"{citation_paths}\n\n"
            "Produza uma análise em Markdown com as seções:\n"
            + _secoes(("ai.sec_evolucao", "Evolução Histórica (Historiografia)"),
                      ("ai.sec_marcos", "Marcos Científicos e Artigos Centrais"))
            +
            f"\n{ESTILO_ANALISE}"
        )
        return self._chat(
            system="Você é especialista em cientometria e mapeamento científico.",
            user=prompt
        )

    def generate_seminal_insights(self, top_references: str) -> str:
        prompt = (
            "A lista a seguir contém referências citadas por artigos do corpus, ordenadas pela frequência no próprio corpus. "
            "Quando há um identificador OpenAlex, os metadados foram obtidos por consulta exata. "
            "As outras linhas são transcrições das referências originais:\n\n"
            f"{top_references}\n\n"
            "Analise SOMENTE as obras desta lista. Não inclua autores, títulos, anos ou contribuições "
            "que não constem dos metadados ou da referência fornecida. Não substitua referências "
            "pouco conhecidas por obras famosas. A contagem significa número de artigos do corpus "
            "que citam a obra, não citações globais da obra.\n"
            "Se as contagens forem baixas ou houver poucas referências com metadados, "
            "diga explicitamente que o corpus não sustenta classificar autores ou obras "
            "como seminais; apresente apenas as referências mais recorrentes.\n"
            "Se houver resumo disponível, descreva a contribuição em até duas frases ancoradas nele. "
            "Sem resumo, diga apenas o tema sugerido pelo título e assinale que a contribuição "
            "não foi verificada. Se autor ou título faltarem, declare 'metadados insuficientes'.\n"
            "Use uma lista numerada simples, com uma entrada por obra e a contagem de artigos "
            "citantes. Evite tabelas, que são difíceis de ler neste painel.\n\n"
            "Produza o relatório em Markdown sob a seção:\n"
            + _secoes(("ai.sec_seminais", "Autores e Obras Seminais"))
            + f"\n{ESTILO_ANALISE_SEMINAL}"
        )
        return self._chat(
            system="Você é especialista em cientometria, história da ciência e mapeamento científico.",
            user=prompt
        )

# Backward-compatible alias
class GroqBibliometricAnalyst(AIAnalyst):
    pass

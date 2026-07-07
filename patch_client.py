import re

with open("ai/client.py", "r") as f:
    c = f.read()

# Replace call_openai_chat to accept messages instead of just prompts, or add a new one
new_call = """
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
        "Content-Type": "application/json"
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
"""

if "def call_openai_chat_history" not in c:
    c = c.replace("class AIAnalyst:", new_call + "\nclass AIAnalyst:\n")
    c = c.replace(
        "def _chat(self, system: str, user: str, temperature: float = 0.3) -> str:",
        "def chat_history(self, messages: list[dict], temperature: float = 0.7) -> str:\n        if not self.api_key:\n            return 'Erro: API Key não configurada nos Ajustes.'\n        return call_openai_chat_history(self.base_url, self.api_key, self.model, messages, temperature)\n\n    def _chat(self, system: str, user: str, temperature: float = 0.3) -> str:"
    )

with open("ai/client.py", "w") as f:
    f.write(c)

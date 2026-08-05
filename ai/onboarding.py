"""Onboarding da chave de IA: o usuário traz a chave dele, e o app torna isso trivial.

**Decisão fechada — não reabrir:** o Blicsa **não** embute chave compartilhada. Três motivos,
registrados aqui para não serem esquecidos:

1. chave distribuída em código aberto vaza em minutos — basta um `grep` no repositório ou no
   binário;
2. limitar consumo por usuário exigiria um servidor do projeto, e não existe servidor do
   projeto: o app é local-first, essa é a promessa feita ao usuário no FAQ;
3. redistribuir acesso a uma chave própria costuma violar os termos do provedor.

O que resta, e é o que este módulo faz: reduzir ao mínimo o atrito de criar a chave própria.

Este módulo é **sem Tk de propósito** — o diagnóstico da chave é testável sem abrir janela.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

#: Onde o usuário cria a chave gratuita. Assertado em teste: um link errado aqui manda o
#: usuário para lugar nenhum e o onboarding inteiro perde a função.
URL_CONSOLE_GROQ = "https://console.groq.com/keys"

BASE_URL_PADRAO = "https://api.groq.com/openai/v1"
MODELO_TESTE = "llama-3.3-70b-versatile"

#: Prefixo das chaves do Groq. Usado só para orientar o usuário, nunca para validar de
#: verdade — quem valida é o provedor.
PREFIXO_GROQ = "gsk_"


@dataclass(frozen=True)
class ResultadoTeste:
    """Diagnóstico de uma tentativa de conexão.

    `status` é o que a UI usa para escolher a mensagem. Cada valor tem uma saída diferente
    para o usuário, então **mensagem genérica não serve**: "deu erro" não distingue "sua
    chave está errada" de "seu wi-fi caiu", e a ação do usuário é oposta nos dois casos.
    """

    status: str                 # "ok" | "vazia" | "invalida" | "sem_internet" | "limite" | "erro"
    chave_i18n: str             # chave da mensagem no catálogo
    modelo: str = ""            # preenchido quando status == "ok"
    detalhe: str = ""           # texto técnico para log — NUNCA contém a chave

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def mascarar(chave: str) -> str:
    """`gsk_abc...xyz9` → `gsk_…xyz9`. Nunca devolve a chave inteira.

    Existe porque a chave aparece na UI depois de salva (o usuário precisa reconhecer qual
    está ativa) e porque capturas de tela da documentação são feitas com o app configurado.
    """
    chave = (chave or "").strip()
    if not chave:
        return ""
    if len(chave) <= 8:
        return "…" + chave[-2:]
    return f"{chave[:4]}…{chave[-4:]}"


def _redigir(texto: str, chave: str) -> str:
    """Tira a chave de qualquer texto que vá para log ou tela.

    Parece redundante — a chave viaja num cabeçalho, não na URL. Mas mensagem de erro de
    biblioteca é território de ninguém: basta uma versão futura do `urllib` incluir o
    cabeçalho no `repr` da exceção para a chave ir parar no log. Redigir custa uma linha;
    descobrir o vazamento depois custa uma chave revogada.
    """
    chave = (chave or "").strip()
    if chave and chave in texto:
        return texto.replace(chave, mascarar(chave))
    return texto


def testar_chave(chave: str, base_url: str = BASE_URL_PADRAO,
                 modelo: str = MODELO_TESTE, timeout: int = 15) -> ResultadoTeste:
    """Chamada mínima ao provedor para dizer, com precisão, o que está acontecendo.

    Mínima de propósito: `max_tokens=1`. O objetivo é saber se a chave autentica, não gerar
    texto — e o usuário não deve gastar cota para configurar o app.
    """
    chave = (chave or "").strip()
    if not chave:
        return ResultadoTeste("vazia", "ai.key_empty")

    corpo = json.dumps({
        "model": modelo,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=corpo,
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8", "replace"))
        return ResultadoTeste("ok", "ai.key_ok", modelo=str(dados.get("model") or modelo))
    except urllib.error.HTTPError as e:
        # O código HTTP é o que separa os casos. Agrupá-los num "erro de API" devolveria ao
        # usuário a mesma frase para problemas com soluções opostas.
        if e.code in (401, 403):
            return ResultadoTeste("invalida", "ai.key_invalid", detalhe=f"HTTP {e.code}")
        if e.code == 429:
            return ResultadoTeste("limite", "ai.key_rate_limit", detalhe="HTTP 429")
        return ResultadoTeste("erro", "ai.key_error", detalhe=f"HTTP {e.code}")
    except urllib.error.URLError as e:
        # DNS, recusa de conexão, timeout: a chave pode estar ótima e o problema é a rede.
        return ResultadoTeste("sem_internet", "ai.key_offline",
                              detalhe=_redigir(str(e.reason), chave)[:120])
    except Exception as e:                                    # pragma: no cover - inesperado
        return ResultadoTeste("erro", "ai.key_error", detalhe=f"{type(e).__name__}")


def tem_chave() -> bool:
    """Há chave configurada? É o que decide entre mostrar o chat ou o onboarding."""
    try:
        from core.settings import get_api_key
        return bool((get_api_key() or "").strip())
    except Exception:
        return False

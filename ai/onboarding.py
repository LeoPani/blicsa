"""Ponte para `core/credenciais.py`, onde o onboarding da chave de IA passou a morar.

**Decisão fechada — não reabrir:** o Blicsa **não** embute chave compartilhada. Três motivos,
registrados aqui para não serem esquecidos:

1. chave distribuída em código aberto vaza em minutos — basta um `grep` no repositório ou no
   binário;
2. limitar consumo por usuário exigiria um servidor do projeto, e não existe servidor do
   projeto: o app é local-first, essa é a promessa feita ao usuário no FAQ;
3. redistribuir acesso a uma chave própria costuma violar os termos do provedor.

O que este módulo fazia — diagnosticar uma chave e dizer com precisão o que houve — agora
vale para as três credenciais do app, não só para a da IA, e por isso subiu para
`core/credenciais.py`. Aqui ficaram os nomes antigos, porque manter **duas implementações**
do mesmo diagnóstico é como a dispersão começou: o painel do Blink testava a conexão, o
diálogo de Ajustes não, e o campo que de fato alimentava as chamadas não fazia nem um nem
outro.

Nada de novo deve ser escrito aqui. Código novo importa de `core.credenciais`.
"""

from __future__ import annotations

from core.credenciais import BASE_URL_GROQ as BASE_URL_PADRAO
from core.credenciais import MODELO_TESTE_GROQ as MODELO_TESTE
from core.credenciais import PROVEDORES_IA, ResultadoTeste, mascarar
from core.credenciais import _redigir  # noqa: F401  (usado por testes de sigilo)
from core.credenciais import testar_ia
from core.credenciais import tem_chave_ia as tem_chave

#: Onde o usuário cria a chave gratuita. Assertado em teste: um link errado aqui manda o
#: usuário para lugar nenhum e o onboarding inteiro perde a função.
URL_CONSOLE_GROQ = PROVEDORES_IA["groq"][0]

#: Prefixo das chaves do Groq. Usado só para orientar o usuário, nunca para validar de
#: verdade — quem valida é o provedor.
PREFIXO_GROQ = "gsk_"

#: Nome antigo do diagnóstico da chave de IA.
testar_chave = testar_ia

__all__ = ["BASE_URL_PADRAO", "MODELO_TESTE", "PREFIXO_GROQ", "URL_CONSOLE_GROQ",
           "ResultadoTeste", "mascarar", "tem_chave", "testar_chave"]

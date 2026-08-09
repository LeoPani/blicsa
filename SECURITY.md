# Política de segurança

O Blicsa é um aplicativo de desktop para análise bibliométrica. Ele roda na máquina do
pesquisador, guarda os dados localmente e fala com a rede apenas para consultar bases
bibliográficas públicas e, se o usuário configurar uma chave, um provedor de IA.

## Versões com suporte

| versão | suporte |
|---|---|
| 2.0.x | sim |
| < 2.0 | não — atualize antes de reportar |

## Como reportar uma vulnerabilidade

**Não abra issue pública.** Escreva para **blicsa.app@gmail.com** com:

- o que acontece e por que é um problema de segurança;
- passos para reproduzir (arquivo de exemplo, requisição, sequência na interface);
- versão do Blicsa e sistema operacional;
- o impacto que você consegue demonstrar.

**Resposta em até 7 dias** confirmando o recebimento e dizendo se conseguimos reproduzir.
Correção e divulgação coordenada em até **90 dias**, ou antes se for simples. Você será
creditado no CHANGELOG, salvo se preferir não ser.

Este é um projeto acadêmico mantido por uma pessoa. Não há programa de recompensa.

## Escopo

**No escopo:**

- **Bridge HTTP local** (`core/bridge.py`, `127.0.0.1:8765`): contorno do token, escrita
  fora dos diretórios do app, negação de serviço que derrube o aplicativo.
- **Importação de arquivos** (`.blicsa`, CSV, RIS, BibTeX, Web of Science): execução de
  código, escrita fora do destino escolhido, esgotamento de memória com arquivo pequeno.
- **Exportação**: conteúdo do corpus que vire código executável no programa que abre o
  arquivo — planilha, navegador ou ferramenta de grafo.
- **Segredos**: chave de IA aparecendo em log, mensagem de erro, relatório ou captura.
- **Servidor local do mapa** (`core/local_server.py`): servir arquivo fora de `~/Blicsa/.serve`.

**Fora do escopo:**

- Ataques que exigem acesso físico à máquina ou uma conta já comprometida. O bridge escuta
  só em `127.0.0.1` e exige token; um atacante que já lê o arquivo de configuração do usuário
  tem o token e muito mais.
- Vulnerabilidades nas bases consultadas (OpenAlex, Crossref, PubMed) ou no provedor de IA.
- Dependências de terceiros — reporte ao projeto de origem; avisaremos aqui se afetar o uso.
- Comportamento de extensão de navegador que o usuário instalou por conta própria.

## O que o Blicsa faz com seus dados

- **Corpus e projetos** ficam em `~/Blicsa/`, no seu computador. Nada é enviado a servidor
  nosso — não existe servidor nosso.
- **A chave de IA** é gravada no chaveiro do sistema operacional (`keyring`), não no
  repositório nem no arquivo do projeto. Sem chaveiro disponível, cai para o arquivo de
  configuração do usuário, fora do diretório do programa.
- **Buscas** vão direto do seu computador para a base escolhida, com o e-mail de contato do
  projeto no parâmetro `mailto` — exigência de etiqueta da API do OpenAlex, não rastreamento.
- **O texto enviado à IA** é o que você vê na tela: o contexto de pesquisa que você escreveu
  e os resumos do corpus. Sem chave configurada, nenhuma requisição de IA acontece.

## Verificações automatizadas

`tests/test_seguranca.py` roda em cada execução da suíte e cobre: token inválido recusado,
comparação de token em tempo constante, payload gigante e JSON profundo rejeitados, limite de
taxa, CORS restrito, zip bomb, travessia de caminho, fórmula em CSV neutralizada, ausência de
`pickle`/`eval`/`exec`/`shell=True`, timeout em toda chamada de rede, TLS nunca desabilitado,
chave ausente de erros e logs, e permissões da extensão.

Achados e decisões estão em `docs/AUDITORIA-SEGURANCA.md`.

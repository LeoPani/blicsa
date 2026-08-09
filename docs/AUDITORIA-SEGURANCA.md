# Auditoria 2 · Fase 1 — segurança

**Data:** 2026-08-09 · **Escopo:** itens 1 a 10 de `audit-2-seguranca-e-limpeza.md`
**Postura:** atacar o próprio software, não confirmar acertos.

> **Veredito:** nenhum achado **crítico**. Não há `pickle`, `eval`, `exec`, `yaml.load`
> inseguro nem `shell=True` em lugar nenhum; TLS nunca é desabilitado; a chave de IA não
> aparece em erro, log ou stdout; a extensão pede três permissões e só fala com `127.0.0.1`.
>
> **Sete achados corrigidos**, sendo o mais grave a **injeção de fórmula no CSV exportado** —
> e o mais instrutivo, o fato de que a primeira correção dele **não corrigia nada**.

---

## 1. Achados por gravidade

| # | achado | vetor | impacto | gravidade | estado |
|---|---|---|---|---|---|
| 1 | Fórmula em CSV exportado | termo do corpus começando com `=`, `+`, `-`, `@` | execução na planilha do pesquisador ao abrir o export | **alta** | corrigido |
| 2 | Bridge sem teto de corpo | POST com `Content-Length` enorme | 60 MB alocados por requisição; memória do app | **média** | corrigido |
| 3 | Entrada de `.blicsa` sem teto | ZIP de 199 KB com entrada de 200 MB | zip bomb: memória esgotada ao abrir projeto | **média** | corrigido |
| 4 | Bridge sem limite de taxa | extensão em laço ou script local com o token | app congelado | **média** | corrigido |
| 5 | `Content-Length` não numérico | cabeçalho `abc` | `ValueError` fora de `try`: 500 e conexão cortada | **baixa** | corrigido |
| 6 | JSON sem limite de profundidade | 60.000 níveis de aninhamento | memória e pilha do processo da interface | **baixa** | corrigido |
| 7 | Token comparado com `==` | temporização local | vazamento incremental do token | **baixa** | corrigido |
| 8 | `urlopen` sem timeout no Zotero | servidor que aceita e não responde | busca pendurada em thread não-matável | **baixa** | corrigido |

### 1.1 Injeção de fórmula no CSV — **alta**

**Vetor.** Um registro bibliográfico cujo campo de palavra-chave contenha
`=HYPERLINK("http://…")` ou `=cmd|'/C calc'!A0`. Não exige nada de especial do atacante: basta
que o registro exista numa base pública, ou num arquivo que o pesquisador importou de um
colega.

**Impacto.** O termo vira nó do grafo, o nó vai para o CSV de rankings ou de arestas, e o
pesquisador abre o arquivo no Excel para conferir os números. A planilha **avalia** a célula.

**Medido antes da correção:** 5 células executáveis no ranking e 14 nas arestas, com um corpus
de 4 documentos.

**Correção.** `core.nlp.neutralizar_formula` prefixa com aspa simples — a convenção do próprio
Excel para "isto é texto". O termo continua legível na célula e volta inteiro para quem lê o
arquivo por programa. Aplicada em `export_rankings_csv`, `export_edges_csv` e no export do
corpus completo.

> **A primeira correção não corrigia nada.** `neutralizar_formulas_no_df` filtrava colunas por
> `dtype == object`, e o pandas 3.0 infere `str` para coluna de texto: a checagem era falsa
> para **todas** as células. O sanitizador rodava e não sanitizava. Só apareceu porque a
> verificação foi refeita sobre o arquivo gerado, em vez de dar a correção por boa.

### 1.2 Bridge HTTP local — quatro achados

`core/bridge.py` é a maior superfície do projeto: escuta em `127.0.0.1:8765` e qualquer
processo da máquina fala com ele. O token (`secrets.token_urlsafe(32)`, 256 bits, persistido
nas configurações e regenerável pela interface) é o que separa a extensão do usuário de
qualquer outro programa. Entropia e geração: **sem achado**.

Atacado com requisições reais:

| ataque | antes | depois |
|---|---|---|
| `Content-Length: abc` | `ValueError`, 500, conexão cortada | **400** |
| corpo de 60 MB | lido inteiro para a memória | **413**, recusado antes de ler |
| JSON com 60.000 níveis | aceito e repassado ao app | **400** |
| 70 pedidos em rajada | todos processados | **429** a partir do 61º |
| token com 1 byte errado | recusado, em tempo variável | recusado com `hmac.compare_digest` |

O limitador não é proteção contra a internet — o servidor é local. É contra **extensão
defeituosa em laço**, que congelaria o aplicativo sem nunca ter má intenção.

### 1.3 Zip bomb no `.blicsa` — **média**

`zf.read(nome)` descomprime a entrada inteira para a memória antes de qualquer validação. Um
ZIP de **199 KB** com uma entrada de **200 MB** de zeros entrou na RAM em 0,1 s, e a mesma
técnica escala para gigabytes com um arquivo minúsculo.

Corrigido com `_ler_entrada`, que confere `ZipInfo.file_size` **no cabeçalho**, antes de
descomprimir — checar depois seria constatar o estrago. Teto de 400 MB por entrada; o
`.blicsa` do dataset de exemplo tem 301 KB.

---

## 2. Verificado e limpo

| item | verificação | resultado |
|---|---|---|
| **Desserialização** (item 4) | varredura de `pickle`, `eval`, `exec`, `yaml.load`, `shell=True`, `os.system` | **nenhuma ocorrência** |
| **TLS** (item 5) | `_create_unverified`, `verify=False`, `CERT_NONE` | **nenhuma ocorrência** |
| **Timeouts** (item 5) | todo `urlopen` em `core/`, `core/sources/`, `ai/` | 1 sem timeout → corrigido |
| **URLs** (item 5) | montagem de parâmetro de consulta | `urlencode`/`quote` nos três provedores |
| **Segredos** (item 6) | erro real provocado com chave configurada | chave **ausente** de mensagem, log e stdout |
| **Travessia no ZIP** (item 3) | entrada `../../invadido.txt` | nada escrito fora; **não há `extractall` no código** |
| **Injeção no mapa** (item 7) | `<script>alert(1)</script>` como termo | pyvis escapa para `<script>`; no Sigma os rótulos vão por `textContent`/canvas |
| **Servidor local** (item 8) | diretório servido | confinado a `~/Blicsa/.serve` (já corrigido em `7c85c3a`) |
| **Extensão** (item 9) | manifesto | `activeTab`, `storage`, `scripting` + `127.0.0.1` nas quatro portas do bridge |

### Justificativa das permissões da extensão (item 9)

| permissão | por quê | veredito |
|---|---|---|
| `activeTab` | ler o registro da aba que o usuário mandou capturar | necessária |
| `storage` | guardar o token do bridge e a porta | necessária |
| `scripting` | injetar o extrator na aba, sob ação do usuário | necessária |
| `host_permissions` | só `127.0.0.1`/`localhost` nas portas 8765–8768 | mínima |

Não há `<all_urls>`, `tabs`, `webRequest` nem `cookies`. Nada a remover.

---

## 3. Riscos aceitos

| risco | por quê é aceito |
|---|---|
| Qualquer extensão de navegador pode **tentar** falar com o bridge (o CORS ecoa qualquer `chrome-extension://`) | sem o token não passa do 401, e restringir a um ID de extensão impediria builds de desenvolvimento e a versão Firefox. Registrado aqui em vez de silenciosamente aceito. |
| O token fica no arquivo de configuração do usuário | quem lê esse arquivo já está dentro da conta do usuário e tem acesso ao corpus inteiro; o token não é a fronteira nesse cenário |
| Sem CSRF token no bridge | os endpoints exigem `Authorization`, que um formulário HTML não consegue enviar entre origens |
| `pip-audit` não executado (item 1) | ver §4 |

---

## 4. Item 1 — dependências: **não executado**

`pip-audit` e `safety` não estão instalados, e o Python deste sistema é **gerenciado
externamente** (PEP 668): instalá-los exigiria `--break-system-packages`, alterando o ambiente
do usuário para produzir um número.

Não foi contornado com uma verificação improvisada. Uma varredura de CVE feita à mão, com base
de dados desatualizada, daria uma tabela com cara de auditoria e valor nenhum.

**Como executar**, em ambiente isolado, antes da submissão:

```bash
python3 -m venv /tmp/audit-venv
/tmp/audit-venv/bin/pip install pip-audit
/tmp/audit-venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt
```

Fica como **pendência declarada** desta auditoria, não como item aprovado.

---

## 5. Testes de segurança

`tests/test_seguranca.py` — **28 testes**, um por vetor testável (o prompt pedia no mínimo 12):

token inválido recusado · token válido aceito (guarda do guarda) · comparação em tempo
constante · payload gigante recusado · `Content-Length` inválido sem derrubar o handler ·
JSON profundo recusado · JSON raso continua passando · limite de taxa dispara · CORS de origem
arbitrária negado · zip bomb recusado · projeto normal continua abrindo · travessia de caminho
bloqueada · ausência de `extractall` · cinco formas de fórmula neutralizadas · export sem
célula executável · neutralização independente do dtype do pandas · chave ausente de erro e
log · nenhuma desserialização perigosa · todo `urlopen` com timeout · TLS nunca desabilitado ·
`<script>` escapado no HTML exportado · `innerHTML` do mapa sem dado do corpus · servidor local
confinado · extensão sem permissão excessiva.

Cada correção tem caso de reinjeção em `scripts/reinject_ia_ux.py`.

## 6. Aceite

- `python3 -m pytest tests/ -q` → **928 passed, 1 xfailed**. ✅
- `python3 scripts/reinject_ia_ux.py` → **99/99 defeitos detectados**. ✅
- `SECURITY.md` na raiz, com política de reporte, escopo e prazos. ✅
- `pip-audit` → **pendência declarada** (§4). ⚠️

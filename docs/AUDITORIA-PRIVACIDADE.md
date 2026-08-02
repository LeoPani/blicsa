# Auditoria de privacidade e segredos — antes de publicar

**Data:** 2026-08-02 · Repositório: `PyBibliomics/blicsa` · Escopo: working tree **e histórico completo**

> ## VEREDITO: **NÃO — ainda não está seguro para publicar**
>
> Nenhuma chave de API real foi encontrada, em lugar nenhum. Mas há **três achados que
> precisam da sua decisão**, e um deles está no histórico (apagar o arquivo agora não
> resolve). Os três estão na seção "Ponto de parada", no fim.

| verificação | resultado |
|---|---|
| Chaves de API reais (working tree e histórico) | **nenhuma** ✓ |
| `.env` / `.blicsa_settings.json` rastreados | **não** ✓ |
| Caminhos `/Users/...` em arquivos rastreados | **zero** ✓ |
| Segredos ou caminhos pessoais em `docs/*.md` | **nenhum** ✓ |
| Imagens analisadas (working tree + histórico) | 130 blobs · **123 OK**, 7 para inspeção |
| Captura de tela cheia **commitada** | **1** ⚠ |
| Arquivos de "evidência" com 0 bytes | **5** ⚠ |
| E-mails de terceiros em fixtures | **46** ⚠ |

---

## Parte 1 — Inventário de imagens

**Método:** `scripts/check_evidence_privacy.py --historico`, que extrai **todos os blobs de
imagem que já existiram** (inclusive versões sobrescritas) com `git cat-file` e analisa cada
um: dimensões, fração de fundo papel `#F6F4EE`, fração de pixels escuros. Reproduzível por
`python3 scripts/check_evidence_privacy.py --historico`.

**Total:** 71 imagens rastreadas no working tree, 71 já adicionadas em algum commit, **nenhuma
apagada** — e 130 blobs distintos ao contar as versões antigas de 6 arquivos que foram
recapturados e commitados de novo.

Resolução de tela cheia nesta máquina: **2940×1912**. Capturas de janela ficam em 2800×1680,
2940×1680 ou 2400×1664.

### Imagens que exigem inspeção humana

| arquivo | onde vive | dimensões | fundo papel | veredito |
|---|---|---|---|---|
| `docs/evidence/bugc_cards_compactos_alinhados.png` | **ambos** (commit `7f44775`) | **2940×1912** | 45,3% | **REPROVADA** |
| `docs/evidence/phase1_home.png` | ambos | 0 bytes | — | SUSPEITA |
| `docs/evidence/phase1_coletar.png` | ambos | 0 bytes | — | SUSPEITA |
| `docs/evidence/phase1_corpus.png` | ambos | 0 bytes | — | SUSPEITA |
| `docs/evidence/phase1_analises.png` | ambos | 0 bytes | — | SUSPEITA |
| `docs/evidence/phase1_exportar.png` | ambos | 0 bytes | — | SUSPEITA |

**Abra para olhar:** `docs/evidence/bugc_cards_compactos_alinhados.png`

O que eu vejo nela: é uma **captura da tela inteira**, não da janela. Aparecem a barra de menu
do macOS com data e hora, **o Dock completo com os seus aplicativos** (WhatsApp, Discord,
Notion, Chrome, Docker, VS Code, Mail, Fotos, entre outros) e, nas bordas, fragmentos de outra
janela aberta atrás. Não há texto pessoal legível — nenhum e-mail, nenhum documento — mas é o
seu ambiente de trabalho, e vai junto para o GitHub público.

Os cinco `phase1_*.png` têm **0 bytes**. Não são risco de privacidade; são evidência falsa —
foram commitados como se fossem capturas, numa sessão em que o `screencapture` estava
bloqueado. Vale remover para o repositório não afirmar o que não tem.

**As outras 124 passaram**, incluindo os 20 quadros do `mapa_animacao.gif` (fundo papel entre
70,3% e 89,5% em todos).

### OCR — NÃO verificado

`tesseract` não está instalado nesta máquina. A classificação acima é por dimensão e cor;
**nenhuma imagem teve o texto lido**. Se quiser essa camada:

```bash
brew install tesseract tesseract-lang
python3 scripts/check_evidence_privacy.py --historico --ocr
```

---

## Parte 2 — Segredos

### Nenhuma chave real, em lugar nenhum

Varredura do histórico completo (`git log --all -p`) por `gsk_`, `sk-`, `Bearer `, `api_key`,
`token`, `secret`, `password`. Os únicos casamentos são **fixtures de teste com valores
sintéticos**, todos evidentemente falsos:

```
tests/…  api_key="gsk_plaintext_123"
tests/…  api_key="sk-testkey1234567890abcdef"
tests/…  api_key="gsk_very_long_secret_key_12345"
```

Busca específica por chaves de formato real (`gsk_` ou `sk-` com 40+ caracteres):
**nenhuma ocorrência**. A chave do Groq vive em `.env` (não rastreado) e a do OpenAlex em
`settings.json` fora do repositório (`~/Library/Application Support/blicsa/`).

**Não há chave a revogar.** Se você tiver colado alguma chave em algum lugar fora deste repo
durante o desenvolvimento, aí sim vale trocar — mas o repositório está limpo.

### `.gitignore`

Cobre `.env*`, `.blicsa_settings.json`, `blicsa_config.json`, `__pycache__`, `dist/`,
`build/`, `reports/`. **Nenhum deles está rastreado** — que é o caso perigoso, e não ocorreu.

**Falta:** `*.log`. Hoje nenhum `.log` está rastreado, então é prevenção, não correção.

### E-mails

| e-mail | ocorrências | situação |
|---|---|---|
| `blicsa.app@gmail.com` | `core/sources/base.py` | contato **do projeto** no User-Agent — intencional |
| `leopaniago2@gmail.com` | `main.py:4359`, `main.py:4387`, `docs/BUGREPORT.md:20` | **seu e-mail pessoal**, em dois User-Agent |
| 46 endereços de pesquisadores | `tests/fixtures/openalex_page2.json`, `page3.json` | **dados de terceiros** |

Dois pontos aqui:

1. **Seu gmail pessoal está no `main.py`**, em duas chamadas de User-Agent, enquanto o projeto
   já tem `blicsa.app@gmail.com` para isso. Trocar é uma linha em cada.
2. **Os 46 e-mails de pesquisadores** vieram da API do OpenAlex junto com os metadados dos
   artigos e foram commitados nas fixtures. São dados pessoais de terceiros — públicos na
   origem, mas republicá-los num repositório é outra coisa. As fixtures somam 8,7 MB e
   existem para os testes rodarem offline; dá para redigir os e-mails sem quebrar teste
   nenhum, porque nenhum teste olha esse campo.

### Metadados dos commits

O histórico tem duas identidades de autor, e elas **ficam públicas junto com os commits**:

```
Leonardo Paniago <leopaniago@outlook.com>
Leonardo Paniago <leopaniago2@gmail.com>
```

Isso é normal em qualquer repositório git e seu nome já está no `CITATION.cff`. Registrado
para você saber, não como problema.

---

## Parte 3 — Relatórios e logs

Varredura de todos os `.md` de `docs/` por `/Users/`, `/home/`, e-mails, tokens e saídas de
comando com dados do ambiente:

- **`/Users/` ou `/home/`: zero ocorrências** em arquivos rastreados (verificado com
  `git grep -clI '/Users/'` sobre o repositório inteiro);
- **tokens e chaves: nenhum**;
- **"Leonardo" aparece em 6 relatórios**, sempre como autor das decisões de produto. Seu nome
  já é público no `CITATION.cff`;
- as queries registradas nos relatórios são profissionais (`empreendedorismo`,
  `bibliometrics`) — nada pessoal.

**Nada a substituir na Parte 3.** O trabalho de higiene de caminhos que o prompt previa não é
necessário: os relatórios já usam caminhos relativos.

---

## Parte 4 — PONTO DE PARADA: sua decisão

Três coisas precisam de você. As duas primeiras estão **no histórico**.

### 1. A captura de tela cheia (decisão obrigatória)

`docs/evidence/bugc_cards_compactos_alinhados.png` foi commitada em **`7f44775`**.

**Remover o arquivo agora não basta.** O git guarda o conteúdo, não só o estado atual: quem
clonar o repositório e rodar `git log -p` ou `git show 7f44775` recebe a imagem inteira, com
o seu Dock e a barra de menu. Um `git rm` num commit novo deixa exatamente isso público.

Três caminhos:

**(a) Recapturar e reescrever o histórico** — mantém o histórico, tira o blob.

```bash
pip install git-filter-repo
git filter-repo --path docs/evidence/bugc_cards_compactos_alinhados.png --invert-paths
```

Reescreve **todos os hashes** a partir do commit afetado. Como o repositório ainda não foi
publicado, não há ninguém com clone para quebrar. Depois é só recapturar a evidência pela
janela (o script já faz isso) e commitar de novo.

**(b) Começar o repositório público do zero** — mais simples, e talvez melhor.

```bash
# no diretório atual, guardando o histórico só localmente:
git branch historico-completo          # preserva tudo aqui na sua máquina
rm -rf .git && git init
git add -A && git commit -m "Blicsa v1.0"
```

Você perde a granularidade dos 20+ commits desta série, mas o repositório público nasce sem
nenhum blob problemático e sem reescrita. Os relatórios em `docs/` já contam a história do
desenvolvimento com muito mais contexto do que as mensagens de commit.

**(c) Publicar como está** — só se você olhar a imagem e concluir que o Dock e a barra de
menu não te incomodam. É uma decisão legítima; só não deve ser tomada sem olhar.

**Minha recomendação: (b).** O repositório ainda não foi publicado, ninguém depende dos
hashes, e é o único caminho que não deixa margem para eu ter deixado passar algum outro blob
nas 130 imagens.

### 2. Os 46 e-mails de pesquisadores (decisão sua)

Estão em `tests/fixtures/openalex_page2.json` e `page3.json`, também **no histórico**. Mesma
mecânica: remover agora não tira do passado.

Se você escolher o caminho (b) acima, isso se resolve junto — e aí vale redigir os e-mails nas
fixtures antes do commit inicial. Posso fazer essa redação (substituir por
`redacted@example.org`) e confirmar que os 407 testes continuam passando; nenhum deles lê esse
campo.

### 3. Seu gmail pessoal no `main.py` (correção simples)

Duas linhas usando `leopaniago2@gmail.com` como User-Agent, onde o projeto já tem
`blicsa.app@gmail.com`. Não é segredo — é escolha sua se quer o e-mail pessoal aparecendo nas
requisições que o app faz. Posso trocar se quiser.

---

## Parte 5 — Prevenção (já aplicada)

- **`scripts/check_evidence_privacy.py`** (novo): reprova imagem de evidência com dimensões de
  tela cheia ou fundo papel abaixo do limiar. Roda sobre o working tree e, com `--historico`,
  sobre todos os blobs que já existiram. Sai com código 1 quando reprova.
- **CI**: passo novo que roda essa verificação e uma varredura de segredos, quebrando o build.
- **`CONTRIBUTING.md`**: a regra escrita — captura de evidência é sempre da janela do app
  (por `CGWindowID`), nunca da tela; e nenhum segredo entra em commit.

O script já teria pego o caso desta auditoria: `bugc_cards_compactos_alinhados.png` sai como
REPROVADA por dimensão de tela cheia.

---

## Aceite

```
$ python3 -m pytest tests/ -q
407 passed, 18 deselected, 1 xfailed

$ python3 scripts/check_evidence_privacy.py
exit 0   (working tree: os 5 arquivos de 0 byte saem como SUSPEITA, não REPROVADA)

$ git log --all --diff-filter=A --name-only --pretty=format: | sort -u | grep -icE '\.(png|jpg|gif)$'
71   (bate com o inventário)
```

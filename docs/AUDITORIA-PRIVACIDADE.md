# Auditoria de privacidade e segredos — antes de publicar

**Data:** 2026-08-02 · **Resolvida em:** 2026-08-03 · Repositório: `github.com/LeoPani/blicsa`
· Escopo: working tree **e histórico completo**

> ## VEREDITO FINAL: **SEGURO PARA PUBLICAR — sim**
>
> Os três achados foram corrigidos e verificados no histórico completo, não só no estado
> atual. Nenhuma chave de API real existia em lugar nenhum — **não há nada a revogar**.
> O que foi feito está na Parte 4; o que **permanece público do passado** está na Parte 6,
> e é a única coisa que este trabalho não pode desfazer.
>
> **Correção de fato:** a versão de 02/08 deste relatório afirmava que o repositório "ainda
> não foi publicado". **Isso estava errado** — `github.com/LeoPani/blicsa` já era público, com
> 74 commits enviados. A recomendação de `rm -rf .git` que decorria desse erro foi descartada;
> ver Parte 4.

| verificação | 02/08 | 03/08 (final) |
|---|---|---|
| Chaves de API reais (working tree e histórico) | nenhuma ✓ | **nenhuma** ✓ |
| `.env` / `.blicsa_settings.json` rastreados | não ✓ | **não** ✓ |
| Caminhos `/Users/...` em arquivos rastreados | zero ✓ | **zero** ✓ |
| Segredos ou caminhos pessoais em `docs/*.md` | nenhum ✓ | **nenhum** ✓ |
| Imagens no histórico completo | 130 blobs · 123 OK, 7 p/ inspeção | **125 blobs · 125 OK, 0** ✓ |
| Captura de tela cheia commitada | 1 ⚠ | **0** ✓ (blob removido) |
| Arquivos de "evidência" com 0 bytes | 5 ⚠ | **0** ✓ |
| E-mails de terceiros em fixtures | 46 ⚠ | **0** ✓ (51 redigidos, 8 arquivos) |
| Testes | 407 passed | **407 passed** ✓ |

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
| e-mail pessoal do autor | `main.py:4359`, `main.py:4387`, `docs/BUGREPORT.md:20` | **corrigido** para o contato do projeto (2026-08-03) |
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
Leonardo Paniago <...@outlook.com>
Leonardo Paniago <...@gmail.com>
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

## Parte 4 — O que foi decidido e executado (03/08)

> **A versão original desta seção partia de uma premissa falsa** — a de que o repositório
> ainda não era público. Ela recomendava (b) `rm -rf .git` com commit único. Leonardo corrigiu
> o fato e decidiu o contrário: **preservar o histórico de desenvolvimento**, porque ele é um
> ativo para a submissão ao JOSS, e **jamais** deletar ou recriar o repositório no GitHub —
> o que preserva URL, estrelas, issues e a futura integração com o Zenodo. O texto original
> das opções fica abaixo, para registro.

**Executado:**

1. **Blob da tela cheia removido cirurgicamente pelo ID**, não pelo caminho:

   ```bash
   git filter-repo --strip-blobs-with-ids /tmp/blobs-remover.txt --force
   ```

   O comando original do plano (`--path … --invert-paths`) apagaria **todas** as versões do
   arquivo, inclusive a recaptura limpa. Removendo por ID, o blob ruim (`9edcdea4`, 1.309.655
   bytes) sai e o bom (`e5f00f28`, 467.997 bytes) fica. 104 commits preservados, 2 objetos a
   menos.

2. **51 e-mails de terceiros redigidos** para `redacted@example.org` em **8 fixtures** — o
   plano previa 2; a auditoria achou mais 6.

3. **E-mail pessoal trocado** por `blicsa.app@gmail.com` em `main.py` e `docs/BUGREPORT.md`.

4. **5 arquivos `phase1_*.png` de 0 byte removidos.**

5. **Publicado por fast-forward**, não force-push:

   ```
   04313fd..e7e86b4  main -> main
   ```

   O blob problemático só existiu em commits **posteriores** ao topo publicado, então a
   reescrita não tocou em nada que já fosse público: `04313fd` sobreviveu com o mesmo hash e
   as duas tags do remoto (`v0.9.0`, `v1.1.1-beta`) batem hash a hash. **Nenhum clone quebrou.**

6. **CI provado com isca** (Parte 5).

### Registro — as opções originais (uma delas baseada em premissa falsa)

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

Reescreve **todos os hashes** a partir do commit afetado. ~~Como o repositório ainda não foi
publicado, não há ninguém com clone para quebrar.~~ **[ERRADO — o repositório era público.
Na prática o commit afetado era posterior ao topo publicado, então nenhum hash público mudou;
mas isso foi sorte da cronologia, não consequência da premissa.]** Depois é só recapturar a
evidência pela janela (o script já faz isso) e commitar de novo.

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

~~**Minha recomendação: (b).** O repositório ainda não foi publicado, ninguém depende dos
hashes, e é o único caminho que não deixa margem para eu ter deixado passar algum outro blob
nas 130 imagens.~~

> **[RECOMENDAÇÃO RETIRADA — 03/08]** Baseava-se na premissa falsa de que o repositório não
> era público. Ele era: 74 commits, com tags e histórico já clonáveis. O (b) teria destruído
> o histórico de desenvolvimento — o ativo que sustenta a submissão ao JOSS — sem sequer
> alcançar o objetivo, já que o conteúdo antigo continuaria nos clones existentes. **Foi
> executado o (a)**, com remoção por ID de blob em vez de por caminho.

### 2. Os 46 e-mails de pesquisadores (decisão sua)

Estão em `tests/fixtures/openalex_page2.json` e `page3.json`, também **no histórico**. Mesma
mecânica: remover agora não tira do passado.

Se você escolher o caminho (b) acima, isso se resolve junto — e aí vale redigir os e-mails nas
fixtures antes do commit inicial. Posso fazer essa redação (substituir por
`redacted@example.org`) e confirmar que os 407 testes continuam passando; nenhum deles lê esse
campo.

### 3. Seu gmail pessoal no `main.py` (correção simples)

Duas linhas usando o e-mail pessoal do autor como User-Agent, onde o projeto já tem
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

### Prova de que o CI reprova de verdade (03/08)

Não basta o script sair com código 1 na minha máquina — o que importa é o build quebrar. Num
branch descartável, commitei uma isca de 2940×1912 (dimensões exatas da tela desta máquina) e
enviei ao GitHub:

```
run 30847246772 · conclusão: failure
  passo 7. Check evidence privacy  ← falhou aqui

  67 imagens analisadas · OCR NÃO verificado (tesseract ausente)
    [REPROVADA] docs/evidence/teste_ci_tela_cheia.png · 2940x1912 · papel 0.0% ·
    dimensões de TELA CHEIA (2940x1912); fundo papel em só 0.0% (mínimo 25%);
    100% de pixels escuros — terminal/navegador?
  66 OK · 1 para inspeção humana
```

Branch e isca apagados em seguida; o remoto tem só `main`.

**A primeira tentativa foi inconclusiva** e revelou outro problema: o build morria em
`Install dependencies`, antes de chegar ao passo 7. Causa: `networkx==3.6.1` exige Python
`>=3.11`, mas a matriz do CI inclui `3.10` e o README anuncia "Python 3.10+". **O CI do `main`
está vermelho desde 21/07 por isso** — quebra pré-existente, não introduzida por esta limpeza.
Contornado apenas no branch descartável (matriz 3.11/3.12) para que o teste alcançasse o alvo.
**Pendente de decisão:** ou os pins passam a aceitar 3.10, ou README, badge e matriz passam a
dizer 3.11+.

---

## Parte 6 — O que esta limpeza NÃO desfaz

Honestidade sobre o alcance: o trabalho corrige o **estado atual** do repositório público e
remove do histórico o blob que nunca chegou a ser publicado. Não alcança o passado já exposto.

| item | esteve público? | desde | situação |
|---|---|---|---|
| Captura de tela cheia (Dock + barra de menu) | **não, nunca** | — | **removida do histórico** ✓ |
| `phase1_*.png` (0 byte) | **sim** | 04/07 | removidos do estado atual; ficam nos clones antigos |
| E-mails de terceiros nas fixtures | **sim** | 12/07 | redigidos no estado atual; ficam nos clones antigos |
| E-mail pessoal em `main.py` e afins | **sim** | 07/07 (commit nº 18) | trocado no estado atual; **permanece nos commits 18/49/54**, que são públicos |
| E-mail pessoal nos metadados de autor | **sim** | — | 1 commit; remover exigiria reescrever autoria |
| `leopaniago@outlook.com` nos metadados de autor | **sim** | — | 103 commits; normal em qualquer repositório git |

Sobre as três últimas linhas: retirá-las exigiria reescrever ~85 commits **já publicados** —
quebrando clones, forks e permalinks que a submissão ao JOSS pode citar. Como o endereço não é
credencial e a exposição já ocorreu, a decisão (Leonardo, 03/08) foi **não** reescrever
histórico público. Quem clonou entre 04/07 e 03/08 mantém a cópia antiga; não há como apagar.

**Rollback:** `/Users/leopani/PyBibliomics-BACKUP-20260803-0050` — 103 commits, com o blob
removido intacto (1.309.655 bytes). Vale notar que a branch `historico-completo-pre-limpeza`
**não** serve de rollback: o `filter-repo` reescreve todas as refs, inclusive ela.

---

## Aceite

```
$ python3 -m pytest tests/ -q
407 passed, 18 deselected, 1 xfailed

$ python3 scripts/check_evidence_privacy.py --historico
125 imagens analisadas · 125 OK · 0 para inspeção humana        (exit 0)

$ python3 scripts/check_secrets.py
Nenhum segredo com formato de credencial real encontrado.        (exit 0)

$ git ls-tree -r --name-only origin/main | grep -c 'phase1_.*png'
0

$ git grep -c 'leopaniago2@gmail.com' origin/main | wc -l
0

$ git grep -lE '@(qq|163|sina)\.com' origin/main -- tests/fixtures/ | wc -l
0

$ git cat-file -s origin/main:docs/evidence/bugc_cards_compactos_alinhados.png
467997   (a recaptura pela janela, não a tela cheia)
```

---

## Reauditoria — 2026-08-09 (Auditoria 2, Fase 2)

Refeita sobre o estado atual, incluindo as **9 capturas novas** geradas desde a passagem
anterior (Auditoria 1, Fase 1).

| verificação | resultado |
|---|---|
| `scripts/check_secrets.py` (working tree + histórico) | nenhum segredo com formato de credencial real |
| chaves `gsk_`/`sk-`/`AIza`/`ghp_` em `git log --all -p` | **nenhuma** |
| `scripts/check_evidence_privacy.py` | **80 imagens · 80 OK · 0 para inspeção humana** |
| arquivo de configuração local rastreado | nenhum (`.env*`, `settings.json` e o chaveiro estão fora) |
| caminho com nome de usuário em código rastreado | **2 achados → corrigidos** |

### Achado: caminho absoluto com o nome do usuário

`scripts/reinject_ia_ux.py` e `scripts/reinject_openalex_limits.py` traziam

```python
RAIZ = pathlib.Path("/Users/leopani/PyBibliomics")
```

Dois problemas num só: o nome de usuário do autor viajava para dentro de um repositório
público, e o script **só rodava na máquina dele** — quem clonasse receberia "trecho não
encontrado" em todos os casos, o que numa submissão ao JOSS lê como matriz de reinjeção que
não funciona. Passou a derivar de `__file__`; verificado rodando de `/tmp`, com os 27 defeitos
da matriz do OpenAlex detectados.

### E-mails que permanecem, com justificativa

| e-mail | onde | decisão |
|---|---|---|
| `blicsa.app@gmail.com` | `SECURITY.md`, `CITATION.cff`, `mailto` das APIs | **público de propósito** — é o contato do projeto |
| `blicsa@leopani.dev` | `extension/manifest.json` | idem |
| `leopaniago@outlook.com`, `leopaniago2@gmail.com` | **apenas** neste relatório e em `RELATORIO-LIMPEZA-REPO.md`, como achado documentado | mantidos: são o autor do commit, presentes nos metadados de 103 commits do git — removê-los do texto do relatório não os removeria do histórico, e o relatório precisa nomear o que auditou |
| `pybibliomics@example.com`, `redacted@example.org` | `docs/BUGREPORT.md` | endereços de exemplo, não existem |

### Veredito

**Seguro para publicar — mantido.** Nenhum achado novo de dado pessoal de terceiro. O único
achado desta passagem era de portabilidade e privacidade do próprio autor, e foi corrigido.

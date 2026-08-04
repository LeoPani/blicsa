# Limpeza do repositório e publicação — relatório

**Data:** 2026-08-03 · **Repositório:** `github.com/LeoPani/blicsa` · **Autor das decisões:** Leonardo

> **Resultado:** repositório limpo e publicado. A reescrita de histórico **não tocou em nenhum
> commit público** — o push foi fast-forward, não force-push. Nenhum clone quebrou, nenhuma
> URL de commit morreu, tags preservadas.
>
> O que a limpeza **não** desfaz está na seção 6, e é o único ponto que exige leitura atenta.

---

## 1. Diagnóstico do remoto (o que mudou o plano)

O plano original partia de um erro de fato: o relatório de auditoria de 02/08 afirmava que o
repositório "ainda não foi publicado". **Ele era público, com 74 commits.** Leonardo corrigiu
isso antes da execução, e a correção mudou tudo — de "reescrever à vontade, ninguém depende
dos hashes" para "cada hash público é um compromisso".

Estado medido antes de qualquer alteração:

| item | estava no remoto? | desde |
|---|---|---|
| Captura de tela cheia (Dock + barra de menu) | **NÃO — só local** | nunca |
| 5 arquivos `phase1_*.png` de 0 byte | sim | 2026-07-04 |
| Fixtures com e-mails de terceiros | sim | 2026-07-12 |
| E-mail pessoal em `main.py` | sim | 2026-07-07 (commit nº 18) |

```
origin/main = 04313fdae71831bf8ebe67e45370a08f13d24820   (74 commits)
27 commits locais nunca enviados
```

**O achado que definiu a estratégia:** o item mais sensível — a captura com o Dock e a barra de
menu — **nunca chegou ao público**. Ele só existia em commits locais posteriores ao topo
publicado.

---

## 2. Salvaguardas antes de mexer

```
/Users/leopani/PyBibliomics-BACKUP-20260803-0050    1,5 GB · git funcional · 103 commits
branch historico-completo-pre-limpeza
```

**Correção importante sobre a branch:** ela **não serve de rollback**. O `git filter-repo`
reescreve **todas** as refs, inclusive ela — verificado depois da execução. O rollback real é
a cópia do diretório, e nela o blob removido continua intacto (1.309.655 bytes).

---

## 3. Correções aplicadas

### 3.1 Dados de terceiros (commit `2c7e331`)

**51 e-mails de pesquisadores** redigidos para `redacted@example.org` em **8 fixtures**. O plano
previa 2 arquivos; a auditoria encontrou mais 6:

```
openalex_page1, openalex_page2, openalex_page3, isoa_true,
rel_bibliometric, rel_entrepreneurship, year_2019_2021, + 3 fixtures do PubMed
```

Nenhum teste lê esse campo — 407 continuaram passando.

### 3.2 E-mail de contato

`leopaniago2@gmail.com` → `blicsa.app@gmail.com` em `main.py` (2 ocorrências) e
`docs/BUGREPORT.md`. O projeto já tinha um endereço próprio para isso.

### 3.3 Evidências inválidas

5 arquivos `docs/evidence/phase1_*.png` com **0 byte** removidos. Não eram risco de
privacidade — eram evidência falsa, commitada numa sessão em que o `screencapture` estava
bloqueado.

### 3.4 A captura de tela cheia

Recapturada pela janela (2800×1686, 467.997 bytes) e o blob antigo removido do histórico.

---

## 4. A reescrita de histórico

### O comando — e a correção que ele exigiu

O plano previa:

```bash
git filter-repo --path docs/evidence/bugc_cards_compactos_alinhados.png --invert-paths
```

**Isso apagaria TODAS as versões do arquivo**, inclusive a recaptura limpa que acabara de ser
feita — o repositório ficaria sem a evidência. A remoção correta é **pelo ID do blob**:

```bash
echo 9edcdea4bf3029e2c9069327e701963539216da3 > /tmp/blobs-remover.txt
git filter-repo --strip-blobs-with-ids /tmp/blobs-remover.txt --force
```

| | antes | depois |
|---|---|---|
| commits | 104 | **104** (nenhum perdido) |
| objetos | 1091 | 1089 |
| blob `9edcdea4` (tela cheia, 1,3 MB) | presente | **removido** |
| blob `e5f00f28` (recaptura, 468 KB) | presente | **preservado** |

### Verificação pós-reescrita

```
$ python3 scripts/check_evidence_privacy.py --historico
125 imagens · 125 OK · 0 para inspeção humana          (era 124 OK · 1 REPROVADA)

$ python3 -m pytest tests/ -q
407 passed, 18 deselected, 1 xfailed

$ python3 scripts/check_secrets.py
Nenhum segredo com formato de credencial real encontrado.
```

**Um critério do plano falhou:** `git log --all -p | grep -c 'leopaniago2@gmail.com'` deu **20**,
não 0. O plano mandava parar e reportar, e foi o que se fez. O motivo: essas ocorrências estão
nos commits nº 18, 49 e 54 — **já públicos e não tocados pela reescrita**. Removê-las exigiria
reescrever ~85 commits publicados. Decisão de Leonardo em 03/08: **não** reescrever histórico
público (seção 6).

---

## 5. A publicação

O `filter-repo` remove o remoto; ele foi reconfigurado, e aí veio o achado que mudou a natureza
do push:

```
$ git merge-base --is-ancestor 04313fda HEAD    →  verdadeiro
```

**O topo publicado sobreviveu com o mesmo hash.** A reescrita só tocou commits nunca enviados,
porque o blob problemático só existia depois de `04313fd`. Consequência: o push é
**fast-forward**, não force-push. As duas tags do remoto (`v0.9.0`, `v1.1.1-beta`) batem hash a
hash.

Um erro no caminho: o primeiro push respondeu `Everything up-to-date`. Todo o trabalho da série
estava em `fix/passo-7-extensao`; o `main` local nunca saíra de `04313fd`. A verificação de
ancestralidade fora feita a partir de `HEAD`, não de `main` — o conteúdo estava certo, o alvo
não. Corrigido com um fast-forward de `main` e novo push:

```
$ git push --force-with-lease=main:04313fdae71831bf8ebe67e45370a08f13d24820 origin main
   04313fd..e7e86b4  main -> main
```

Sem o `+` que marcaria atualização forçada.

### Estado do que está publicado

```
$ git ls-tree -r --name-only origin/main | grep -c 'phase1_.*png'          0
$ git grep -c 'leopaniago2@gmail.com' origin/main | wc -l                  0
$ git grep -lE '@(qq|163|sina)\.com' origin/main -- tests/fixtures/ | wc -l 0
$ git cat-file -s origin/main:docs/evidence/bugc_cards_compactos_alinhados.png
467997   (a recaptura pela janela, não a tela cheia)
```

---

## 6. O que esta limpeza NÃO desfaz

| item | esteve público? | desde | situação |
|---|---|---|---|
| Captura de tela cheia | **não, nunca** | — | **removida do histórico** ✓ |
| `phase1_*.png` | **sim** | 04/07 | removidos do estado atual; ficam nos clones antigos |
| E-mails de terceiros nas fixtures | **sim** | 12/07 | redigidos no estado atual; ficam nos clones antigos |
| E-mail pessoal em `main.py` | **sim** | 07/07 | trocado no estado atual; **permanece nos commits 18/49/54** |
| E-mail pessoal nos metadados de autor | **sim** | — | 1 commit |
| `leopaniago@outlook.com` nos metadados | **sim** | — | 103 commits; normal em git |

**Quem clonou o repositório entre 04/07 e 03/08 mantém a cópia antiga. Não há como apagar
isso.** Retirar as três últimas linhas exigiria reescrever ~85 commits públicos, quebrando
clones, forks e permalinks que a submissão ao JOSS pode citar — e o endereço não é credencial.

**Nenhuma chave de API real foi encontrada em lugar nenhum. Não há nada a revogar.**

---

## 7. Prevenção — e a prova de que funciona

- **`scripts/check_evidence_privacy.py`**: reprova imagem com dimensões de tela cheia ou fundo
  papel abaixo do limiar; roda sobre o working tree e, com `--historico`, sobre todos os blobs.
- **`scripts/check_secrets.py`**: padrões exigem **comprimento real de credencial** (32+), para
  fixture de teste como `gsk_plaintext_123` não quebrar o build. Mascara achados na saída,
  porque o log do CI é público.
- **`CONTRIBUTING.md`**: captura de evidência é sempre da janela (`CGWindowID`), nunca da tela.
- **CI**: os dois passos rodam a cada push.

### A prova (não basta o script sair com código 1 na minha máquina)

Num branch descartável, uma isca de 2940×1912 foi commitada e enviada ao GitHub:

```
run 30847246772 · conclusão: failure
  passo 7. Check evidence privacy  ← falhou aqui

  [REPROVADA] docs/evidence/teste_ci_tela_cheia.png · 2940x1912 · papel 0.0% ·
  dimensões de TELA CHEIA (2940x1912); fundo papel em só 0.0% (mínimo 25%);
  100% de pixels escuros — terminal/navegador?
```

Branch e isca apagados; o remoto tem só `main`.

### Achado não previsto: o CI está vermelho desde 21/07

A primeira tentativa foi **inconclusiva** — o build morria em `Install dependencies`, antes de
chegar ao passo 7. Causa: `networkx==3.6.1` exige Python `>=3.11`, mas a matriz do CI inclui
`3.10` e o README anuncia "Python 3.10+".

**Quebra pré-existente, não introduzida por esta limpeza.** Contornada apenas no branch
descartável para o teste alcançar o alvo. **Pendente de decisão:** ou os pins passam a aceitar
3.10, ou README, badge e matriz passam a dizer 3.11+.

---

## 8. Comandos para reproduzir as verificações

```bash
python3 scripts/check_evidence_privacy.py --historico   # 125 OK · 0 para inspeção
python3 scripts/check_secrets.py                        # nenhum segredo
python3 scripts/check_i18n_parity.py                    # catálogos em paridade
python3 -m pytest tests/ -q                             # suíte completa
git ls-remote origin                                    # estado do remoto
```

**Backup, caso algo precise ser refeito:**
`/Users/leopani/PyBibliomics-BACKUP-20260803-0050` — 103 commits, blob removido intacto.

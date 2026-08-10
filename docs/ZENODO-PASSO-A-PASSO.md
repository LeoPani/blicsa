# Zenodo — passo a passo para o DOI

**Para o Leonardo executar.** É interface web e depende da conta dele; nada aqui pode ser
feito por script.

> ## A regra que governa tudo
>
> **O Zenodo só captura releases publicadas DEPOIS de a integração estar ativa.**
>
> A `v2.0.0` foi publicada em 04/08, antes de a integração existir. Ela não gerou DOI e não
> vai gerar sozinha. Ativar a integração agora **não** volta atrás e captura o que já estava
> lá — por isso a release precisa ser apagada e republicada.

## Ordem — não inverter

```
1. ativar a integração no Zenodo
2. só então apagar e republicar a release v2.0.0
3. o Zenodo deposita e emite o DOI
4. registrar o DOI no repositório
```

Inverter 1 e 2 é o erro que já aconteceu uma vez: republicar antes de ativar produz o mesmo
nada de agosto.

---

## Antes de começar

| verificação | estado |
|---|---|
| backup do repositório fora do diretório de trabalho | ✅ `/Users/leopani/blicsa-backup-20260809.bundle` (25 MB, 17 refs, histórico completo) |
| histórico será alterado? | ❌ **não** — decisão da Fase 4; commits e tag ficam intactos |
| binários da release guardados? | ⚠️ **baixe antes de apagar** — ver passo 2 |

---

## Passo 1 — Ativar a integração (5 minutos)

1. Abra <https://zenodo.org> e entre com **Log in with GitHub**.
   Se for a primeira vez, o GitHub vai pedir autorização — aceite.
2. Vá em **GitHub** no menu do seu nome (ou direto em <https://zenodo.org/account/settings/github/>).
3. Se o repositório não aparecer na lista, clique em **Sync now** (canto superior direito).
4. Encontre **LeoPani/blicsa** e **ligue o interruptor** ao lado.

**Como saber que funcionou:** o interruptor fica verde/ligado. Clicando no nome do
repositório, o Zenodo mostra a instrução de badge e a mensagem de que ainda não há releases
capturadas — é o esperado.

> O que esse interruptor faz: instala um *webhook* no repositório. Daí em diante, **toda**
> release publicada é depositada automaticamente.

---

## Passo 2 — Guardar os binários da release atual

A release tem quatro arquivos que precisam ser reanexados depois. **Baixe antes de apagar:**

```bash
cd ~
mkdir -p blicsa-release-v2.0.0
gh release download v2.0.0 --repo LeoPani/blicsa --dir blicsa-release-v2.0.0
ls -la blicsa-release-v2.0.0
```

Esperado: `Blicsa-linux`, `Blicsa-macos.zip`, `Blicsa.exe`, `SHA256SUMS.txt`.

**Confira os checksums antes de seguir** — se um arquivo baixou corrompido, é melhor
descobrir agora do que depois de apagar o original:

```bash
cd ~/blicsa-release-v2.0.0 && shasum -a 256 -c SHA256SUMS.txt
```

Também vale guardar o texto da release:

```bash
gh release view v2.0.0 --repo LeoPani/blicsa --json body --jq .body > ~/blicsa-release-v2.0.0/notas.md
```

---

## Passo 3 — Apagar e republicar a release

**A tag não é tocada.** Só o objeto *release* do GitHub é recriado; `v2.0.0` continua
apontando para o mesmo commit, e nenhum clone de terceiro é afetado.

```bash
# Apaga a release, MANTENDO a tag (o --cleanup-tag NÃO é usado de propósito)
gh release delete v2.0.0 --repo LeoPani/blicsa --yes

# Confirma que a tag sobreviveu
git ls-remote --tags origin | grep v2.0.0

# Republica, com o texto e os binários guardados no passo 2
gh release create v2.0.0 \
  --repo LeoPani/blicsa \
  --title "Blicsa v2.0.0" \
  --notes-file ~/blicsa-release-v2.0.0/notas.md \
  ~/blicsa-release-v2.0.0/Blicsa-linux \
  ~/blicsa-release-v2.0.0/Blicsa-macos.zip \
  ~/blicsa-release-v2.0.0/Blicsa.exe \
  ~/blicsa-release-v2.0.0/SHA256SUMS.txt
```

> **Se preferir pela interface web:** Releases → v2.0.0 → **Delete** (a caixa pergunta se
> quer apagar a tag junto — **não marque**) → depois **Draft a new release** → escolha a tag
> `v2.0.0` existente → cole as notas → arraste os quatro arquivos → **Publish release**.

---

## Passo 4 — Conferir o depósito e pegar o DOI

O webhook dispara em segundos, mas o Zenodo pode levar alguns minutos.

1. Abra <https://zenodo.org/account/settings/github/> e clique em **LeoPani/blicsa**.
   A release deve aparecer listada com um badge de DOI.
2. Abra o depósito. **Revise antes de considerar pronto** — o Zenodo preenche a partir do
   `CITATION.cff`, mas vale conferir:

| campo | deve dizer |
|---|---|
| Title | Blicsa |
| Authors | Paniago, Leonardo — **e o ORCID, se você já tiver preenchido** |
| Description | o abstract do `CITATION.cff` |
| License | MIT |
| Version | 2.0.0 |
| Language | escolher (o CFF não carrega esse campo) |

3. Anote **os dois DOIs** que o Zenodo emite:

| DOI | o que é | onde usar |
|---|---|---|
| **DOI de conceito** (*"Cite all versions"*) | aponta sempre para a versão mais recente | **este vai no README e no `CITATION.cff`** |
| DOI da versão | fixo na v2.0.0 | usar quando quiser citar exatamente esta versão |

O JOSS aceita os dois, mas o de conceito é o que envelhece bem.

---

## Passo 5 — Registrar o DOI no repositório

Três lugares, todos já preparados com o marcador `XXXXXXX`:

**1. `README.md`** — descomente as duas linhas do badge e troque o número:

```markdown
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
```

**2. `CITATION.cff`** — descomente o bloco `identifiers` e preencha:

```yaml
identifiers:
  - type: doi
    value: "10.5281/zenodo.XXXXXXX"
    description: "Arquivamento permanente da v2.0.0 no Zenodo"
```

**3. `docs/JOSS-CHECKLIST.md`** — item 24 passa de ⏳ para ✅ com o DOI.

Depois:

```bash
python3 -m pytest tests/ -q          # o teste de versão lê o CITATION.cff
git add README.md CITATION.cff docs/JOSS-CHECKLIST.md
git commit -m "docs: DOI do Zenodo registrado no README, CITATION.cff e checklist do JOSS"
git push
```

> **Este commit não altera o histórico** e é posterior ao DOI — o DOI aponta para o
> *snapshot* da tag `v2.0.0`, não para o `main`. Acrescentar o badge depois é o fluxo normal
> e não invalida nada.

---

## O que fica pendente depois disto

O DOI resolve o item 24 da checklist do JOSS. Continuam faltando, e **só você pode resolver**:

| item | o que falta |
|---|---|
| 21 | `paper.md` — o artigo em si, entregável central da submissão |
| 22 | `paper.bib` — as referências já existem em `docs/metodos.md` e podem ser convertidas |
| 25 | **ORCID** — o marcador está comentado no `CITATION.cff`; preencher antes de submeter |
| 26 | Declaração de autoria substancial |

---

## Se algo der errado

| sintoma | causa provável | o que fazer |
|---|---|---|
| A release republicada não aparece no Zenodo | integração ligada **depois** da republicação | apagar e republicar de novo, agora com o interruptor já verde |
| O repositório não aparece na lista do Zenodo | falta sincronizar, ou a autorização do GitHub não cobre o repositório | **Sync now**; se persistir, revisar as permissões do app Zenodo em GitHub → Settings → Applications |
| A tag sumiu junto com a release | marcou a caixa de apagar a tag | recriar do backup: `git push origin v2.0.0` (a tag local intacta) ou restaurar do bundle |
| Os metadados do Zenodo vieram errados | o `CITATION.cff` não foi lido | editar no próprio Zenodo (**Edit** no depósito) — os metadados são editáveis e o DOI não muda |

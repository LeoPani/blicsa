# Relatório da v2.0.0 — documentação, integridade e release

**Data:** 2026-08-04 · **Release:** <https://github.com/LeoPani/blicsa/releases/tag/v2.0.0>

> *O prompt pedia este arquivo como `RELATORIO-V1.md`. Como a versão publicada é a **2.0.0**
> (decisão de Leonardo, para não regredir o número público diante da `v1.1.1-beta` já
> publicada), o nome acompanha a versão real.*

---

## 1. Integridade de projetos — verificação primeiro

### A anomalia dos projetos `version: 3` — esclarecida, **não é corrupção**

O relatório anterior registrou dois projetos de 30/07 declarando `version: 3` com apenas a
coluna `title`. A suspeita era corrupção ativa no caminho de gravação, o que seria prioridade
máxima. **Não é.** As evidências:

| verificação | resultado |
|---|---|
| Algum código escreve `"version": 3` ou `"app": "Blicsa"`? | **não**, em nenhum arquivo do repositório |
| Carimbo de gravação dos dois arquivos | `2026-07-30 10:00:00` — **idêntico e redondo**; o app grava `time.strftime` |
| `git log -S` pelos nomes dos projetos | nada |
| Os 12 projetos gravados pelo app | todos `version=1.0`, `app=PyBibliomics Blicsa`, carimbo real |

O caminho de gravação usa `df.to_json(orient="records")`, que escreve **todas** as colunas —
provado por teste que inspeciona o **byte gravado** dentro do ZIP, não o objeto recarregado
(que passaria pela normalização e mascararia uma perda).

**Conclusão:** os dois arquivos foram fabricados por um script avulso, nunca commitado.

### Teste de ida e volta completo

Projeto com tudo preenchido — dataset com as 13 colunas (acentos, DOI com barra, vazio
legítimo, zero, booleano nos dois estados), grafo com atributos em nós e arestas, posições do
layout, rótulos de cluster, histórico de buscas e todos os parâmetros — gravado, reaberto e
comparado valor a valor. **Nada se perde.** Inclui uma segunda volta seguida, para pegar
degradação por acúmulo.

**Um bug encontrado no caminho:** `int(k)` nos rótulos de cluster levantava `ValueError` e
derrubava a carga **inteira** do projeto quando a chave não era numérica — dataset, mapa e
parâmetros perdidos por causa do rótulo de um cluster. Corrigido: a chave estranha é
preservada como veio.

### Versionamento do formato

A normalização na carga cobre os três formatos que existem em disco, com fixture para cada um:
`1.0` (14/07, cinco colunas), `3` (30/07, só `title`) e o atual. Um teste impede as fixtures
de "envelhecerem" para o schema novo e virarem vácuas.

O ponto que definiu o desenho: **o número da versão não serve para decidir se migra.** Os
arquivos que quebravam declaram `version: 3` — *maior* que o `1.0` que funciona — e têm menos
colunas. Por isso a normalização roda sempre.

### Acessos diretos a `df["year"]`

Os cinco apontados no relatório anterior: três já tinham guarda; os dois do filtro de período
não tinham, e são exatamente o caminho que quebrava. Protegidos, com teste que impede um
acesso novo sem guarda entrar em `main.py`.

---

## 2. Documentação de usuário

| arquivo | conteúdo |
|---|---|
| `docs/index.md` | o que é, para quem, o que resolve, captura da tela principal |
| `docs/instalacao.md` · `installation.md` | três plataformas, três formas de instalar, solução de problemas |
| `docs/uso.md` · `usage.md` | fluxo completo com capturas reais e conjunto de exemplo |
| `docs/mapas.md` | as três visualizações e os controles de qualidade |
| `docs/metodos.md` · `methods.md` | sete métodos com fórmula e citação |
| `docs/limitacoes.md` | dez limitações conhecidas |
| `docs/faq.md` | incluindo "meus dados saem do meu computador?" (não) |
| `docs/JOSS-CHECKLIST.md` | estado item a item |

### Honestidade acadêmica sobre a métrica de relevância

Registrado em `metodos.md`, `methods.md`, `limitacoes.md` e `faq.md`, sem eufemismo: a métrica
usa **divergência KL**, é **inspirada** no conceito de especificidade de termos de van Eck &
Waltman e **não é a fórmula publicada por eles**. Os valores **não são numericamente
comparáveis** aos do VOSviewer, e quem precisa reproduzir resultado publicado com o VOSviewer
deve usar o VOSviewer.

### Duas correções que a documentação exigiu

**O `sample_dataset.csv` tinha 3 registros** — não gera mapa nenhum, logo não servia como
exemplo de ponta a ponta. Refeito com **200 registros reais** do OpenAlex, sem e-mails.

**A captura da tela de busca estava desatualizada:** mostrava *"Página 1 de 12.772"*,
comportamento que a correção do pager eliminou. Recapturada com dado real da API (54.581
resultados), mostrando *"Página 1 de 400 navegáveis"*.

---

## 3. Requisitos formais do JOSS

Estado completo em [`JOSS-CHECKLIST.md`](JOSS-CHECKLIST.md). Resumo:

- **19 de 26 itens atendidos.**
- **Faltava o `LICENSE`** — o README anunciava MIT em badge e seção desde sempre, mas sem o
  arquivo o GitHub não detectava licença nenhuma, o que reprova a submissão. Criado.
- **`CODE_OF_CONDUCT.md`** não existia. Criado, bilíngue.
- **`CITATION.cff`**: autor corrigido para `Paniago, Leonardo` (estava `Pani, Leo`), versão
  `2.0.0`, licença e palavras-chave. **Falta o ORCID**, que só Leonardo pode informar.
- **Cobertura: 69%** em `core/` (4232 comandos, 1307 não cobertos), medida pelo CI, igual em
  3.11 e 3.12. Registrada como medida, sem perseguir número.
- **Pendentes:** `paper.md` e `paper.bib` (decisão de autoria), ORCID, DOI do Zenodo.

---

## 4. Numeração de versão — o bloqueio e a decisão

Havia **cinco** declarações independentes, três dizendo `v3.0` — número que nunca existiu e
que **aparecia nas capturas de tela da documentação**. E a tag `v1.0.0` já existia localmente,
apontando para um commit de 03/07, 105 commits atrás, nunca publicada, enquanto o remoto já
tinha `v1.1.1-beta`.

**Decisão de Leonardo: `v2.0.0`.** Número público não regride, e as mudanças justificam o
salto. A tag obsoleta foi apagada.

| onde | dizia | agora |
|---|---|---|
| `main.py::__version__` | `1.1.0-beta` | **`2.0.0`** — fonte única |
| rodapé, janela "Sobre" (2×), `--version` | `v3.0` | derivados de `__version__` |
| `CHANGELOG.md` | `0.9.0` | `2.0.0` |
| `CITATION.cff` | `2.0-upgrade` | `2.0.0` |

Dois testes impedem a divergência voltar: um recusa literal de versão solto em `main.py`,
outro exige que o `CITATION.cff` concorde com `__version__`.

---

## 5. Release

**Publicada:** <https://github.com/LeoPani/blicsa/releases/tag/v2.0.0>

O workflow montava **só Windows** e nem publicava a release. Agora monta as três plataformas,
roda *smoke test* em cada uma e publica com checksums.

| binário | tamanho | SHA-256 |
|---|---|---|
| `Blicsa.exe` | 138.206.028 | `17eae50118747ea4283831608444e2228e7eb47ccb95305f17ec13531bdbf870` |
| `Blicsa-macos.zip` | 116.369.784 | `f802adeab9198abdc5de9f84509822ceeeda5d10b45da819e16b34fb1e75cb07` |
| `Blicsa-linux` | 162.271.696 | `64e28a079c1ae74e866a44c2cfbab4c4b77f864ffd46e82d867a4d79bb3d117e` |

Run `30960516974`, os quatro jobs verdes. O *smoke test* do Windows deixou de ser
`continue-on-error`: build que não abre não deve virar release.

As notas são escritas para usuário, com o aviso de reclusterização em destaque.

---

## 6. Limitações conhecidas registradas

As dez estão em [`limitacoes.md`](limitacoes.md). As que mais afetam o uso:

1. **PubMed: 9.999 registros por busca** — teto do NCBI que `usehistory=y` **não** remove,
   confirmado contra a API real. Particionamento por data não foi implementado (decisão de
   Leonardo); a saída documentada é fatiar a busca.
2. **OpenAlex: 10.000 na navegação** — a importação por cursor não tem teto.
3. **Extração de frases nominais funciona mal em português** — é a limitação mais sentida pelo
   público brasileiro.
4. **Projetos anteriores à v2.0 podem reclusterizar.**
5. **macOS sem assinatura de código.**

---

## 7. Próximos passos

### Zenodo → DOI

1. Entrar em <https://zenodo.org> com a conta do GitHub.
2. **Settings → GitHub** → ligar a chave do repositório `LeoPani/blicsa`.
3. **Republicar a release** (ou criar a próxima). ⚠️ O Zenodo só captura releases criadas
   **depois** da integração ativa — a v2.0.0 foi publicada **antes**, então **não gerou DOI**.
   Basta apagar e recriar a release, ou publicar uma `v2.0.1`.
4. Preencher no depósito: autores com **ORCID**, licença MIT, palavras-chave, descrição, tipo
   *Software*.
5. Usar o **DOI da versão** (não o de *concept*) no JOSS e no INPI.

### Depois do DOI

- Badge do DOI no README e campo `doi:` no `CITATION.cff`.
- `paper.md` e `paper.bib` — decisão de autoria de Leonardo.
- ORCID no `CITATION.cff`.

### Lembrete registrado

**O DOI e a versão publicada são pré-requisito tanto para a submissão ao JOSS quanto para o
registro de software no INPI pelo NITE/UFOP.** O hash do INPI congela exatamente esta versão —
os SHA-256 da seção 5 são o que identifica o artefato registrado.

---

## Aceite

```
$ python -m pytest tests/ -q
475 passed, 20 deselected, 1 xfailed

$ python scripts/check_evidence_privacy.py
67 OK · 0 para inspeção humana            (exit 0)

$ python scripts/check_i18n_parity.py
All catalogs are in parity.

$ git tag -l v2.0.0
v2.0.0

$ ls docs/index.md docs/instalacao.md docs/uso.md docs/mapas.md \
     docs/metodos.md docs/limitacoes.md docs/faq.md docs/JOSS-CHECKLIST.md
(todos presentes)
```

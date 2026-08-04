# Checklist de submissão ao JOSS

Estado de cada requisito da [checklist de revisão do JOSS](https://joss.readthedocs.io/en/latest/review_checklist.html),
com a evidência. Atualizado em **2026-08-04**, sobre o commit publicado em `origin/main`.

Legenda: **✅ atendido** · **⏳ pendente** · **➖ não aplicável**

---

## Software

| # | requisito | estado | evidência |
|---|---|---|---|
| 1 | O software está disponível num repositório público com controle de versão | ✅ | <https://github.com/LeoPani/blicsa>, git, 100+ commits de desenvolvimento |
| 2 | Licença OSI aprovada, num arquivo `LICENSE` | ✅ | `LICENSE` (MIT) na raiz. **Estava faltando até 04/08**: o README anunciava MIT em badge e seção, mas sem o arquivo o GitHub não detectava licença nenhuma — e o JOSS reprova por isso. O arquivo criado corresponde ao que já estava declarado |
| 2b | Código de conduta presente | ✅ | `CODE_OF_CONDUCT.md`, criado em 04/08 (não existia) |
| 3 | Instruções de instalação claras | ✅ | [`docs/instalacao.md`](instalacao.md) e [`installation.md`](installation.md) — três plataformas, três formas de instalar |
| 4 | Dependências declaradas | ✅ | `requirements-core.txt` (app), `requirements.txt` (com extras), `requirements-dev.txt` (testes) |
| 5 | Exemplo funcional de uso | ✅ | [`docs/uso.md`](uso.md) + `docs/sample_dataset.csv` (200 registros reais do OpenAlex) |
| 6 | Documentação da API / funcionalidade | ✅ | [`docs/index.md`](index.md), [`uso.md`](uso.md), [`mapas.md`](mapas.md) |
| 7 | Testes automatizados | ✅ | 473 testes, `python -m pytest tests/ -q` |
| 8 | Integração contínua | ✅ | GitHub Actions, matriz 3.11/3.12 — [workflow](../../actions/workflows/ci.yml) |
| 9 | Diretrizes de contribuição | ✅ | `CONTRIBUTING.md` |
| 10 | Código de conduta | ✅ | `CODE_OF_CONDUCT.md` (ver item 2b) |
| 11 | Canal para reportar problemas | ✅ | GitHub Issues, descrito no `CONTRIBUTING.md` e no [FAQ](faq.md) |

## Documentação

| # | requisito | estado | evidência |
|---|---|---|---|
| 12 | Declaração de necessidade (*statement of need*) | ✅ | [`docs/index.md`](index.md), seção "O que resolve" |
| 13 | Documentação de instalação | ✅ | item 3 |
| 14 | Exemplo de uso | ✅ | item 5 |
| 15 | Descrição dos métodos com referências | ✅ | [`docs/metodos.md`](metodos.md) — 7 métodos com fórmula e citação |
| 16 | Limitações declaradas | ✅ | [`docs/limitacoes.md`](limitacoes.md) — 10 limitações, incluindo os tetos das APIs |

## Qualidade

| # | requisito | estado | evidência |
|---|---|---|---|
| 17 | Cobertura de testes registrada | ✅ | **69%** em `core/` (4232 comandos, 1307 não cobertos), medido pelo CI no run `30884139087`, igual em 3.11 e 3.12 |
| 18 | Build verde | ✅ | run `30884139087`, `3.11: success`, `3.12: success` |
| 19 | Reprodutibilidade dos resultados | ✅ | clustering com semente fixa (`seed=42`); verificado com 5 execuções sobre o mesmo grafo → 1 partição |

## Requisitos formais da submissão

| # | requisito | estado | observação |
|---|---|---|---|
| 20 | `CITATION.cff` válido | ⏳ | existe, mas declara `version: "2.0-upgrade"` — a **quinta** declaração de versão em desacordo (ver Bloqueio). Também traz o autor como `Pani, Leo`, enquanto os commits usam `Leonardo Paniago`; e falta ORCID |
| 21 | Arquivo `paper.md` com o artigo | ⏳ | **não escrito.** É o entregável central da submissão e depende de decisão de autoria |
| 22 | `paper.bib` com as referências | ⏳ | as referências já estão em [`metodos.md`](metodos.md) e podem ser convertidas |
| 23 | Release versionada com tag | ⏳ | ver "Bloqueio" abaixo |
| 24 | DOI de arquivamento (Zenodo/figshare) | ⏳ | depende do item 23 |
| 25 | ORCID do autor de correspondência | ⏳ | precisa ser informado por Leonardo |
| 26 | Autoria substancial declarada | ⏳ | decisão de Leonardo |

---

## Bloqueio para os itens 23–24: a numeração de versão está inconsistente

A tag `v1.0.0` **já existe localmente**, apontando para `e3b4851` de **2026-07-03**, 105
commits atrás do estado atual, e **nunca foi enviada ao remoto**. Enquanto isso o remoto já
tem `v1.1.1-beta`, que é semanticamente **posterior** à v1.0.0.

Declarações de versão em desacordo no código:

| onde | diz |
|---|---|
| `main.py:7` (`__version__`) | `1.1.0-beta` |
| `main.py:615` (rodapé da barra lateral) | `v3.0 • Blicsa Engine` |
| `main.py:799` (janela "Sobre") | `v3.0` |
| `CHANGELOG.md` (última entrada) | `0.9.0` |
| `CITATION.cff` | `2.0-upgrade` |
| tags locais | `v0.9.0`, `v1.0.0`, `v1.1.0-beta`, `v1.1.1-beta` |
| tags no remoto | `v0.9.0`, `v1.1.1-beta` |

Publicar uma release `v1.0.0` agora exigiria **mover uma tag existente** e **regredir** em
relação à `v1.1.1-beta` já pública. Como o DOI do Zenodo e o hash do INPI congelam exatamente
a versão publicada, a escolha do número é decisão de Leonardo, não do processo de build.

**Opções, para decidir:**

- **(a)** apagar a tag local `v1.0.0` (nunca publicada) e recriá-la no commit atual — assume
  que a numeração recomeça e que as tags `beta` foram experimentos;
- **(b)** publicar como **`v2.0.0`**, respeitando a `v1.1.1-beta` já pública;
- **(c)** publicar como **`v1.2.0`**, tratando as `beta` como a linha corrente.

Em qualquer caso, as quatro declarações de versão no código precisam passar a concordar entre
si e com a tag — inclusive o `v3.0` do rodapé, que não corresponde a nenhuma versão que já
existiu.

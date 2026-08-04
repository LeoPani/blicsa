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
| 8 | Integração contínua | ✅ | GitHub Actions, matriz 3.11/3.12 — [workflow](https://github.com/LeoPani/blicsa/actions/workflows/ci.yml) |
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
| 20 | `CITATION.cff` válido | ✅ | versão `2.0.0`, autor `Paniago, Leonardo`, licença MIT, palavras-chave. Teste automatizado impede divergir de `main.py::__version__`. **Falta o ORCID**, que só Leonardo pode informar |
| 21 | Arquivo `paper.md` com o artigo | ⏳ | **não escrito.** É o entregável central da submissão e depende de decisão de autoria |
| 22 | `paper.bib` com as referências | ⏳ | as referências já estão em [`metodos.md`](metodos.md) e podem ser convertidas |
| 23 | Release versionada com tag | ✅ | `v2.0.0` — decisão de Leonardo em 04/08 (ver "Numeração" abaixo) |
| 24 | DOI de arquivamento (Zenodo/figshare) | ⏳ | integração do Zenodo precisa ser ativada **antes** de publicar a release |
| 25 | ORCID do autor de correspondência | ⏳ | precisa ser informado por Leonardo |
| 26 | Autoria substancial declarada | ⏳ | decisão de Leonardo |

---

## Numeração de versão — resolvida em 04/08

**Decisão: `v2.0.0`.** Número público não regride, e as mudanças justificam o salto maior
(Python 3.11+, clusterização determinística alterando resultados de projetos antigos, busca
reescrita). A tag local obsoleta `v1.0.0` — que apontava para um commit de 03/07, 105 commits
atrás, e nunca fora publicada — foi apagada.

Como estava antes, com **cinco** declarações divergentes:

| onde | diz |
|---|---|
| onde | dizia | agora |
|---|---|---|
| `main.py::__version__` | `1.1.0-beta` | **`2.0.0`** — fonte única |
| rodapé da barra lateral | `v3.0 • Blicsa Engine` | derivado de `__version__` |
| janela "Sobre" (2 pontos) | `v3.0` | derivado de `__version__` |
| `--version` | `v3.0-upgrade` | derivado de `__version__` |
| `CHANGELOG.md` | `0.9.0` | `2.0.0` |
| `CITATION.cff` | `2.0-upgrade` | `2.0.0` |

O `v3.0` não correspondia a nenhuma versão que tivesse existido — e aparecia nas capturas de
tela da documentação. Dois testes automatizados agora impedem a divergência: um recusa
literal de versão solto em `main.py`, outro exige que `CITATION.cff` concorde com
`__version__`.

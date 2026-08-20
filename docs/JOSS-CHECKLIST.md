# Checklist de submissão ao JOSS

Estado de cada requisito da [checklist de revisão do JOSS](https://joss.readthedocs.io/en/latest/review_checklist.html),
com a evidência. Atualizado em **2026-08-09**, depois das Auditorias 1 e 2.

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
| 7 | Testes automatizados | ✅ | **1.054 testes**, `python3 -m pytest tests/ -q`, mais **27 testes `live`** que batem nas APIs reais e ficam fora da execução padrão (`pytest -m live`). Inclui matriz de **reinjeção de defeitos** (`scripts/reinject_ia_ux.py`, 101 casos): cada bug corrigido é reintroduzido e a suíte tem de ficar vermelha. Última execução: **90 dos 101 detectados**, não 101 — a ressalva está em [`RELATORIO-AUDITORIA-2.md`](RELATORIO-AUDITORIA-2.md#8-aceite) |
| 8 | Integração contínua | ✅ | GitHub Actions, matriz 3.11/3.12 — [workflow](https://github.com/LeoPani/blicsa/actions/workflows/ci.yml) |
| 9 | Diretrizes de contribuição | ✅ | `CONTRIBUTING.md` |
| 10 | Código de conduta | ✅ | `CODE_OF_CONDUCT.md` (ver item 2b) |
| 11 | Canal para reportar problemas | ✅ | GitHub Issues, descrito no `CONTRIBUTING.md` e no [FAQ](faq.md) |
| 11b | Política de segurança | ✅ | `SECURITY.md` na raiz — escopo, prazos de resposta e o que o programa faz com os dados do usuário. Criado na Auditoria 2 |

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
| 17 | Cobertura de testes registrada | ✅ | **69%** em `core/` (4232 comandos, 1307 não cobertos), medido pelo CI no run `30884139087`. **Número de 04/08**; a suíte passou de 473 para 1.054 testes desde então, e a próxima execução do CI atualiza o valor |
| 17b | Auditoria de dependências | ✅ | `pip-audit 2.10.1` sobre os cinco arquivos de requisitos (47 pacotes): **zero vulnerabilidades conhecidas**, em 2026-08-10. Comando e ressalva de validade em [`AUDITORIA-SEGURANCA.md`](AUDITORIA-SEGURANCA.md) §4 |
| 17c | Auditoria de segurança | ✅ | [`AUDITORIA-SEGURANCA.md`](AUDITORIA-SEGURANCA.md) — 8 achados corrigidos, 28 testes de segurança, nenhum achado crítico |
| 18 | Build verde | ✅ | run `30884139087`, `3.11: success`, `3.12: success` |
| 19 | Reprodutibilidade dos resultados | ✅ | clusterização **e posições do mapa** com semente fixa. Verificado em **subprocessos com `PYTHONHASHSEED` distinto** — só assim se detecta ordem de iteração de `set`. A Auditoria 1 encontrou que as posições **não** eram reprodutíveis (o ForceAtlas2 sorteava com o `random` global, sem semente) e corrigiu; ver [`AUDITORIA-MAPAS.md`](AUDITORIA-MAPAS.md) §2.1 |
| 19b | Verificação funcional documentada | ✅ | [`AUDITORIA-MAPAS.md`](AUDITORIA-MAPAS.md) (11 corpus adversariais × 3 modos, desempenho medido), [`AUDITORIA-FLUXO.md`](AUDITORIA-FLUXO.md) (percurso do usuário novo cronometrado), [`AUDITORIA-ARQUITETURA.md`](AUDITORIA-ARQUITETURA.md) (métricas e dívida catalogada) |

## Requisitos formais da submissão

| # | requisito | estado | observação |
|---|---|---|---|
| 20 | `CITATION.cff` válido | ✅ | versão `2.0.0`, autor `Paniago, Leonardo Luiz Costa`, ORCID `0009-0006-1663-3349`, contato, licença MIT, palavras-chave. Teste automatizado impede divergir de `main.py::__version__` |
| 21 | Arquivo `paper.md` com o artigo | ✅ | [`paper/paper.md`](../paper/paper.md) — Summary, Statement of Need, Key Features e References, com o cabeçalho YAML que o JOSS exige |
| 22 | `paper.bib` com as referências | ✅ | [`paper/paper.bib`](../paper/paper.bib), em BibTeX, derivado de [`metodos.md`](metodos.md) |
| 23 | Release versionada com tag | ✅ | [`v2.0.0`](https://github.com/LeoPani/blicsa/releases/tag/v2.0.0) — três binários + `SHA256SUMS.txt`, run `30960516974` |
| 24 | DOI de arquivamento (Zenodo/figshare) | ✅ | **DOI de conceito: [`10.5281/zenodo.21866410`](https://doi.org/10.5281/zenodo.21866410)** — resolve sempre para a versão mais recente, e é o que está no badge do README e como identificador principal no `CITATION.cff`. O snapshot da v2.0.0 é [`10.5281/zenodo.21866411`](https://doi.org/10.5281/zenodo.21866411), registrado como segundo identificador. A release precisou ser republicada porque o Zenodo só captura releases publicadas **depois** de a integração estar ativa; tag e histórico ficaram intactos — ver [`ZENODO-PASSO-A-PASSO.md`](ZENODO-PASSO-A-PASSO.md) |
| 25 | ORCID do autor de correspondência | ✅ | `0009-0006-1663-3349`, registrado no [`CITATION.cff`](../CITATION.cff) |
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

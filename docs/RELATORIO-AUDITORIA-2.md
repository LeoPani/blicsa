# Relatório — Auditoria 2/3: segurança, limpeza e preparação para publicação

**Data:** 2026-08-09/10 · **Prompt:** `audit-2-seguranca-e-limpeza.md`
**Commits:** `21938c6` · `08b1869` · `5d8cf9c` · `569c872` · e este

> **Veredito por fase**
>
> | fase | veredito |
> |---|---|
> | 1 — Segurança | **8 achados corrigidos**, nenhum crítico; `pip-audit` limpo |
> | 2 — Privacidade | 1 achado corrigido; veredito "seguro para publicar" mantido |
> | 3 — Limpeza de comentários | **nada a limpar** — e isso mudou a Fase 4 |
> | 4 — Reescrita de histórico | **decidido: não reescrever** |
> | 5 — Execução da reescrita | **cancelada** |
> | 6 — Zenodo e JOSS | preparada; falta o que só o Leonardo pode fazer |

---

## 1. Fase 1 — Segurança

Detalhe completo em [`AUDITORIA-SEGURANCA.md`](AUDITORIA-SEGURANCA.md).

**Nenhum achado crítico.** Zero `pickle`, `eval`, `exec`, `yaml.load` inseguro e `shell=True`;
TLS nunca desabilitado; chave de IA ausente de erro, log e stdout; extensão com três
permissões e só `127.0.0.1`.

| gravidade | achado | estado |
|---|---|---|
| **alta** | injeção de fórmula no CSV exportado | corrigido |
| média | bridge sem teto de corpo (60 MB por requisição) | corrigido |
| média | zip bomb no `.blicsa` (199 KB → 200 MB na RAM) | corrigido |
| média | bridge sem limite de taxa | corrigido |
| baixa | `Content-Length` não numérico derrubava o handler | corrigido |
| baixa | JSON de 60.000 níveis aceito | corrigido |
| baixa | token comparado com `==` | corrigido |
| baixa | `urlopen` do Zotero sem timeout | corrigido |

**`pip-audit` executado** em venv isolado — cinco arquivos de requisitos, 47 pacotes, **zero
vulnerabilidades**. Era a pendência declarada da fase, resolvida a pedido.

**28 testes de segurança** (o prompt pedia 12) e `SECURITY.md` na raiz.

### As duas lições da fase

**A primeira correção da injeção de fórmula não corrigia nada.** O filtro por
`dtype == object` é falso no pandas 3.0, que infere `str` para coluna de texto: o sanitizador
rodava e não sanitizava uma célula sequer. Só apareceu porque a verificação foi refeita sobre
o arquivo gerado.

**E a proteção criou o problema que vinha evitar.** Recusar 413/429 sem drenar o corpo deixa
bytes por subir num socket que o servidor considera reutilizável: a suíte completa passou a
dar `TimeoutError` no bridge. Uma negação de serviço fabricada pela própria defesa. Corrigido
fechando a conexão nas recusas e migrando para `ThreadingHTTPServer` — com uma thread só, uma
requisição lenta bloqueava todas as seguintes.

## 2. Fase 2 — Privacidade

Detalhe em [`AUDITORIA-PRIVACIDADE.md`](AUDITORIA-PRIVACIDADE.md), seção de reauditoria.

Limpo: nenhuma credencial no working tree nem no histórico completo; 80 imagens de evidência,
80 OK; nenhum arquivo de configuração local rastreado.

**Um achado:** os dois scripts de reinjeção traziam
`RAIZ = pathlib.Path("/Users/leopani/PyBibliomics")`. Dois problemas num só — o nome de
usuário viajava para um repositório público, e **os scripts só rodavam na máquina do autor**.
Quem clonasse receberia "trecho não encontrado" em todos os casos, o que numa submissão ao
JOSS lê como matriz de reinjeção que não funciona. Corrigido para derivar de `__file__` e
verificado rodando de `/tmp`.

## 3. Fase 3 — Limpeza de comentários

Detalhe em [`LIMPEZA-COMENTARIOS.md`](LIMPEZA-COMENTARIOS.md).

**O repositório já estava limpo, e esse é o achado.** Zero atribuições a ferramenta de IA em
arquivos rastreados **e nas mensagens dos 133 commits** — doze padrões verificados. Zero
`TODO`/`FIXME`/`HACK`. Zero código morto comentado.

Nada foi removido da categoria "explica por quê", que é a maior do repositório e a que
sustenta a avaliação de documentação do JOSS. Cinco comentários em inglês solto foram
traduzidos para o idioma do arquivo. **Nenhum comentário duvidoso** para decisão.

## 4. Fase 4 — Reescrita de histórico: **não**

Levantamento e decisão em [`FASE4-REESCRITA-HISTORICO.md`](FASE4-REESCRITA-HISTORICO.md).

A fase existia para levantar a remoção de assinaturas de IA das mensagens de commit. **Não há
nenhuma.** A pergunta deixou de ser "como reescrever com segurança" e passou a ser "se ainda
vale reescrever".

**Decisão de Leonardo Paniago, 2026-08-09: não reescrever.** Motivo determinante: os
relatórios de auditoria citam commits por hash, e a reescrita os transformaria em ponteiros
para commits inexistentes — justamente a documentação de processo que será referenciada na
submissão.

**Backup feito mesmo assim**, antes de qualquer operação sobre a release:
`/Users/leopani/blicsa-backup-20260809.bundle` — 25 MB, 17 refs, `git bundle verify` confirma
histórico completo.

## 5. Fase 5 — cancelada

Consequência direta da decisão acima. Nenhum `filter-repo`, nenhum force-push, nenhum hash
alterado.

## 6. Fase 6 — Zenodo e JOSS

### A premissa que precisou ser corrigida

O prompt tratava a recriação da release como algo que "se combina sem custo adicional" com a
reescrita do histórico. Com a reescrita cancelada, poderia parecer que a release também
deixava de precisar ser refeita.

**Não deixa** — o motivo é independente: **o Zenodo só captura releases publicadas depois de
a integração estar ativa.** A `v2.0.0` foi publicada em 04/08, antes de a integração existir.

E a operação é muito menor do que uma reescrita:

| | reescrita | recriar a release |
|---|---|---|
| commits e tag | 133 hashes novos, tag recriada | **intactos** |
| force-push | obrigatório | **nenhum** |
| clones de terceiros | quebrados | **não afetados** |
| hashes citados nos relatórios | apontam para o vazio | **continuam válidos** |

### O que foi preparado

| arquivo | o que mudou |
|---|---|
| `CITATION.cff` | contato acrescentado; marcadores comentados para **ORCID** e para o bloco `identifiers` do DOI |
| `README.md` | badge de DOI comentado, pronto para descomentar; seção **Security** apontando para `SECURITY.md` |
| `docs/JOSS-CHECKLIST.md` | evidência atualizada: 929 testes, `pip-audit`, `SECURITY.md`, auditorias 1 e 2, reprodutibilidade agora incluindo as posições do mapa |
| `docs/ZENODO-PASSO-A-PASSO.md` | **novo** — cinco passos para o Leonardo executar, com a ordem crítica, o resgate dos binários antes de apagar a release, e uma tabela de "se algo der errado" |

### Ordem crítica, revisada

```
limpeza de código ✔ → ativar integração do Zenodo → apagar e republicar a release v2.0.0 → DOI
```

A regra que a motivou permanece: nada que altere o histórico depois do DOI. Com a reescrita
cancelada, nada altera o histórico em momento nenhum.

---

## 7. O que falta, e de quem depende

| # | pendência | de quem depende |
|---|---|---|
| 1 | Ativar o Zenodo e republicar a release | **Leonardo** — interface web, conta dele |
| 2 | **ORCID** no `CITATION.cff` | **Leonardo** — só ele tem |
| 3 | `paper.md` — o artigo | **Leonardo** — entregável central, decisão de autoria |
| 4 | `paper.bib` | derivável de `docs/metodos.md`, mas segue o artigo |
| 5 | Declaração de autoria substancial | **Leonardo** |
| 6 | Reexecutar `pip-audit` antes de submeter | qualquer um — auditoria de dependência vence |
| 7 | Atualizar a cobertura (69% é de 04/08, com 473 testes; hoje são 929) | próxima execução do CI |

## 8. Aceite

- `python3 -m pytest tests/ -q` → **929 passed, 1 xfailed**. ✅
- `python3 scripts/reinject_ia_ux.py` → **101/101 defeitos detectados**. ✅
- `python3 scripts/check_evidence_privacy.py` → **80 imagens · 80 OK**. ✅
- `pip-audit -r` × 5 arquivos → **zero vulnerabilidades**. ✅
- `ls docs/AUDITORIA-SEGURANCA.md docs/LIMPEZA-COMENTARIOS.md SECURITY.md` → presentes. ✅

## 9. Um padrão que atravessou as duas auditorias

Nas duas, a reinjeção reprovou guardas que eu tinha acabado de escrever. Na Auditoria 2 foram
quatro:

1. o guarda da comparação em tempo constante procurava `"compare_digest"` como string e casava
   com o **comentário** que explica o defeito — repetição exata do furo do `pos=None`;
2. o teste de TLS casava com o **próprio padrão** escrito dentro dele, assim que o arquivo
   passou a ser rastreado pelo git: verde isolado, vermelho na suíte completa;
3. o teste do limitador de taxa dependia de 70 conexões em rajada contra um servidor
   compartilhado entre arquivos de teste;
4. um caso de reinjeção cujo trecho não existia no arquivo — `SETUP RUIM` lido como furo.

**Asserção sobre a forma do texto passa; só asserção sobre o efeito protege.** É a mesma frase
do relatório de IA de 08/08, e ela continuou valendo contra quem já a tinha escrito.

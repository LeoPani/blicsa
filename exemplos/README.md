# Corpus fictício para testar o import

Dois arquivos gerados por `scripts/gerar_corpus_ficticio.py`, nos formatos que o Blicsa
importa de verdade:

| Arquivo | Formato | Registros |
|---|---|---|
| `corpus_ficticio_scopus.csv` | export CSV do Scopus (cabeçalho real: `Authors`, `Source title`, `Cited by`, `Author Keywords`, `References`, …) | 69 |
| `corpus_ficticio_wos.txt` | export *plain text* etiquetado do Web of Science (`FN`/`VR`, `AU`/`TI`/`PY`/`DE`/`AB`/`TC`/`DI`/`CR`, `ER`) | 37 |

**Nada aqui é real.** Autores, periódicos, títulos e resumos são inventados; os DOIs usam
o prefixo `10.5555`, reservado para testes, e nenhum resolve.

## Como usar

1. Aba de importação → **Carregar** → selecione um dos dois arquivos (ou os dois).
2. O formato é detectado sozinho: o CSV cai em `scopus` pelo cabeçalho, o TXT cai em `wos`
   pelas linhas `FN`/`VR`. Se quiser exercitar o seletor manual, force outro formato na
   lista da linha do arquivo.
3. Carregue **os dois juntos** para ver o diálogo de deduplicação com casos reais.

## O que o corpus foi construído para exercitar

- **Clusters temáticos** — 4 comunidades de palavras-chave (visão embarcada, tecnologia
  assistiva, interação multimodal, avaliação/políticas), com termos-ponte entre elas, para
  o mapa de co-ocorrência ter estrutura em vez de uma bola de pelo.
- **Coautoria com comunidades** — 28 autores agrupados por área, mais autores-ponte que
  publicam fora do próprio grupo.
- **Série temporal 2014–2025** com volume crescente, para linha do tempo e animação.
- **Cocitação** — cada trabalho cita de 3 a 8 anteriores do corpus (campo `References` no
  Scopus, `CR` no WoS), preferindo o mesmo cluster.
- **Citações plausíveis** — correlacionadas com idade e com quantas vezes o trabalho é
  citado dentro do corpus, não sorteadas.
- **Deduplicação, as três passadas do `find_duplicates`:**
  - 8 trabalhos aparecem nos dois arquivos com o **mesmo DOI** (passada 1);
  - 1 par sem DOI, mesmo ano, título ~96% igual (passada 2);
  - 1 par mesmo primeiro autor + mesmo ano, título ~82% igual (passada 3).

  Carregando os dois arquivos, o esperado é **10 duplicatas** em 106 linhas.
- **Harmonização** — de propósito, os mesmos 28 autores aparecem como `Silva J.M.`
  (Scopus) e `Silva, JM` (WoS), e os mesmos 9 periódicos em *Title Case* e em MAIÚSCULAS.
  Sem harmonizar, o corpus combinado mostra 56 autores e 18 periódicos em vez de 28 e 9.

## Regenerar / variar

```bash
python3 scripts/gerar_corpus_ficticio.py                 # mesma semente, mesmo corpus
python3 scripts/gerar_corpus_ficticio.py --seed 7        # outro corpus
python3 scripts/gerar_corpus_ficticio.py --saida /tmp/x  # outra pasta
```

O volume por ano está no dicionário `POR_ANO` do script; os temas, em `CLUSTERS`.

## Dois achados do parser, encontrados ao montar isto

Nenhum dos dois quebra o corpus acima — ele foi montado contornando os dois —, mas os dois
aparecem com arquivos reais:

1. **Título e resumo do WoS quebram em várias linhas.** `_load_wos_etiquetado` junta linha
   de continuação com `"; "`, o que é correto para `AU`, `DE` e `CR` e errado para `TI` e
   `AB`: um export real do WoS entra no Blicsa com títulos do tipo
   `"Assistive navigation systems; for people with visual impairment"`. Por isso este
   corpus mantém `TI` e `AB` em linha única.
2. **A passada 3 do dedup não cruza Scopus com WoS.** `_first_surname` corta no primeiro
   `,`: `"Silva, JM"` (WoS) vira `silva`, e `"Silva J.M."` (Scopus) vira `silva j.m.`.
   Como as chaves nunca batem, a passada por autor+ano só encontra duplicata dentro da
   mesma base — que é justamente onde ela menos importa. Por isso os pares fuzzy deste
   corpus estão os dois dentro do arquivo do WoS.

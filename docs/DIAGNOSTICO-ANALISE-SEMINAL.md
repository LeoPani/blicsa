# Diagnóstico da análise de autores seminais

Registrado antes da correção em 17/09/2026.

## Reprodução e causas

1. `run_consolidated_from_blicsa.py` tira a pontuação de `authors` antes de separar por `;`. Assim, todos os autores de um artigo viram uma única chave. A busca posterior com `str.contains` aceita coincidências parciais e pode atribuir o mesmo artigo a autores diferentes. O relatório observado repete obras e apresenta autores sem relação com elas.
2. A rotina de consolidação lê todo `project.blicsa` da pasta, inclusive consolidados gerados em execuções anteriores. Reexecutar o script aumenta artificialmente as contagens. Não há deduplicação de artigos entre projetos originais.
3. O schema normalizado não garante `openalex_id` nem `id`; a tabela exporta uma coluna de identificador vazia e corta resumos em 200 caracteres, parecendo descrição completa.
4. Na aba do app, referências do OpenAlex chegam como `https://openalex.org/W...`. O código entrega esses identificadores sem metadados ao modelo e pede que use conhecimento geral para nomear autores e obras. Isso permite respostas plausíveis sem lastro no corpus. A aba usa ainda o renderizador Markdown antigo, que deixa tabelas e outras marcações mal formatadas.

## Critérios de correção

- Consolidar somente projetos de origem e deduplicar registros de obras.
- Separar autores antes de normalizar o nome; associar cada autor apenas às linhas em que aparece como autor completo.
- Chamar citações recebidas pelos artigos do corpus pelo nome correto; contar referências citadas separadamente quando disponíveis.
- Exibir apenas metadados presentes no corpus ou resolvidos por identificador exato; nunca preencher um ID nem uma descrição por palpite.
- Formatar Markdown no painel de forma legível e cobrir cada regressão com teste.

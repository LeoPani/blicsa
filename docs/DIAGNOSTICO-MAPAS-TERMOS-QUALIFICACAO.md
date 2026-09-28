# Diagnóstico dos mapas de termos da qualificação

Registrado em 17/09/2026 antes da revisão da seleção de termos.

## Reprodução

Os PNGs dos três projetos novos em `~/Blicsa/projects/qualificacao-2026-*/exports/termos/mapa.png`
renderizam corretamente, mas a seleção automática dos 70 termos mais frequentes
privilegia fragmentos dos próprios assuntos e palavras genéricas. No corpus DSR,
`design` aparece em 47 documentos, `science` em 46 e a locução `design science`
em 46; os três viram nós distintos. Em Grace Period, `grace`, `period` e
`grace period` também ocupam três nós. Em PatentBERT há `patent`, `patents`,
`language`, `models`, `most`, `over`. Isso comprime o espaço visual e reduz a
capacidade de identificar subtemas.

## Causa e critério de correção

`choose_terms` ordena somente por frequência de documentos com pequeno bônus
para locuções. Não elimina termos de redação científica genérica nem fragmentos
redundantes de expressões mais informativas. Para os mapas exploratórios da
qualificação, excluir uma lista explícita de ruído, preferir locuções e registrar
os parâmetros de seleção. Não remover registros do corpus, nem apresentar o
mapa filtrado como uma análise sem escolhas editoriais. Conferir os PNGs depois.

## Revisão da seleção por projeto

O comando `--name dsr-pi` termina com sucesso sem exportar nada porque o filtro
compara a string `dsr-pi` com o slug `dsr-e-pi`, que não a contém. Selecionar por
uma tabela de nomes exata e testar os três casos, para impedir sucesso silencioso.

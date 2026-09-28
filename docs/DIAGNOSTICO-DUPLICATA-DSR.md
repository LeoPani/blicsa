# Diagnóstico de duplicata no corpus DSR e PI

Registrado em 17/09/2026 antes da correção.

O mapa de termos do projeto DSR e PI mostra um grupo de expressões de uma
pesquisa sobre marca d'água em nuvem. O mesmo trabalho de 2016 aparece duas
vezes no corpus com DOI `10.48550/arxiv.1606.02508`: uma versão tem quebras de
linha representadas como caracteres literais `\\n` no título. A normalização
de título usada na deduplicação transformou `\\n` em uma letra `n`, então as
duas grafias ficaram com chaves distintas. Uma terceira versão de 2015 com
título mais diferente e sem DOI pode ser outro estágio do trabalho; preservá-la
até revisão humana. A duplicata de 2016 dá frequência artificial a frases de
um único resumo e altera o mapa.

Critério: normalizar espaços e sequências literais de quebra de linha antes de
comparar títulos; atualizar a triagem e remover só a duplicata identificada,
preservando a busca bruta e um snapshot anterior. Reexportar o mapa e conferir
visualmente se o grupo artificial desaparece.

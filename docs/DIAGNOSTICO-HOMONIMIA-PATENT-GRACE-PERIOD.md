# Diagnóstico: homonímia de “patent” nos corpora da qualificação

## Sintoma observado

O mapa de coautoria de Grace Period apresentou uma equipe de pesquisa clínica sem
relação aparente com propriedade intelectual. A inspeção do título e do resumo
identificou o uso médico de *patent ductus arteriosus* (persistência do canal
arterial), no qual *patent* significa “aberto”, e não patente de invenção.

## Registros afetados

- Grace Period: `W7154128333`, estudo clínico sobre ibuprofeno e persistência do
  canal arterial.
- PatentBERT: `W7160828580`, detecção por Transformer de persistência do canal
  arterial em vídeos de ultrassonografia.

Os dois registros entraram porque as buscas combinavam `patent` com termos que
também aparecem nos resumos, como `grace period` ou `transformer`.

## Controle aplicado

A triagem passou a excluir registros com vocabulário clínico característico de
*patent ductus arteriosus* quando não houver evidência forte de propriedade
intelectual, por exemplo `intellectual property`, `patent application`,
`patent document`, `patent classification`, `prior art`, `invention`, `filing`,
`inventor`, `patent law` ou `patent office`.

O trabalho `W7166821175`, sobre ligação entre aprovações regulatórias e patentes
de dispositivos cardiovasculares, foi mantido porque o uso de patentes como
objeto documental está explícito.

## Resultado esperado

- Grace Period: 68 para 67 documentos.
- PatentBERT: 256 para 255 documentos.
- Registros brutos preservados nas consultas OpenAlex.
- Motivo da exclusão registrado nas planilhas de triagem.
- Mapas regenerados após a correção.

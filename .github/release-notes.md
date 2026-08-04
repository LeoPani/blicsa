**Blicsa** é um aplicativo de desktop para análise bibliométrica: buscar literatura, montar um
corpus, gerar mapas de conhecimento e extrair estatísticas — tudo na sua máquina.

Esta é a primeira versão estável. Comece pela **[documentação](../../blob/main/docs/index.md)**.

## Instalação

Baixe o arquivo da sua plataforma aqui embaixo. Não precisa de Python instalado.

- **Windows** — `Blicsa.exe`. O SmartScreen vai avisar que o publicador é desconhecido: o
  executável não tem assinatura de código. **Mais informações → Executar assim mesmo**.
- **macOS** — `Blicsa-macos.zip`. Descompacte e, **na primeira vez**, clique com o **botão
  direito → Abrir** (não use duplo clique). O app não é assinado nem notarizado pela Apple, e
  com duplo clique o sistema recusa sem oferecer alternativa. Só é preciso fazer isso uma vez.
- **Linux** — `Blicsa-linux`. `chmod +x Blicsa-linux && ./Blicsa-linux`.

Prefere rodar do código? Precisa de **Python 3.11 ou superior** — veja a
[instalação](../../blob/main/docs/instalacao.md).

Confira o download com o `SHA256SUMS.txt` anexado:

```bash
sha256sum -c SHA256SUMS.txt
```

## ⚠️ Leia antes de atualizar

**Projetos salvos antes desta versão podem mostrar clusters diferentes ao serem reabertos.**
Até agora, a mesma entrada podia produzir agrupamentos distintos entre execuções; a partir
desta versão o resultado é reproduzível. **Seu corpus, suas métricas e as posições salvas não
mudam — só o agrupamento pode diferir.** Se você precisa preservar exatamente um agrupamento
já publicado, guarde a figura exportada antes de reabrir o projeto.

**Python 3.11 passa a ser o mínimo** para quem roda a partir do código.

**Registros antigos deixam de aparecer indevidamente como "Open Access".** Havia um defeito na
leitura desse campo em projetos salvos por versões anteriores.

## O que melhorou

- **Projetos antigos abrem.** Antes, um projeto de julho podia falhar ao gerar o mapa com uma
  mensagem de uma palavra só, que não dizia sequer que o problema era o arquivo.
- **O campo Qtd vazio agora traz tudo mesmo.** Havia um teto escondido de 1.000 registros:
  numa busca com 54 mil resultados, quem não digitava nada recebia 1.000 sem saber por quê.
- **As contagens dizem a verdade.** Quando uma colheita para, o app diz **por que** parou — se
  foi o limite que você pediu, se a base acabou, ou se foi um teto da API.
- **A paginação não promete página que não existe.** Uma busca com 366 mil resultados mostrava
  "Página 1 de 14.678" quando só 400 podiam ser abertas.
- **Documentação de usuário completa**, em português, com instalação, uso e métodos também em
  inglês.

## Limitação conhecida em destaque

**O PubMed entrega no máximo 9.999 registros por busca.** É um teto da API do NCBI, não do
Blicsa, e não há como contorná-lo por paginação. Quando acontece, o app diz. Para cobrir um
conjunto maior, divida a busca em consultas mais estreitas — o Blicsa deduplica ao juntar.

As demais estão em [limitações conhecidas](../../blob/main/docs/limitacoes.md).

---

Changelog completo: [CHANGELOG.md](../../blob/main/CHANGELOG.md)

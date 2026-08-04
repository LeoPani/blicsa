# Métodos

*English version: [methods.md](methods.md)*

O que cada número do Blicsa significa, com a fórmula e a referência. Onde a implementação
**difere** da literatura, isso está dito explicitamente.

---

## Força de associação (*association strength*)

Normaliza o peso da coocorrência pelo que seria esperado se os termos fossem independentes.
É a normalização usada por padrão nos mapas do Blicsa.

$$ s_{ij} = \frac{c_{ij}}{w_i \, w_j} $$

onde $c_{ij}$ é o número de documentos em que $i$ e $j$ coocorrem e $w_i$, $w_j$ são as
ocorrências totais de cada termo. Dois termos raros que aparecem sempre juntos recebem
associação alta; um termo muito frequente não domina o mapa só por ser frequente.

> Van Eck, N. J., & Waltman, L. (2009). How to normalize cooccurrence data? An analysis of
> some well-known similarity measures. *Journal of the American Society for Information
> Science and Technology*, 60(8), 1635–1651.

## Contagem: completa ou fracionada

- **Completa (binária)**: cada documento contribui 1 para cada par de termos que contém.
- **Fracionada**: a contribuição de um documento é dividida pelo número de pares que ele gera,
  de modo que documentos com muitos termos não pesem desproporcionalmente.

> Perianes-Rodriguez, A., Waltman, L., & van Eck, N. J. (2016). Constructing bibliometric
> networks: A comparison between full and fractional counting. *Journal of Informetrics*,
> 10(4), 1178–1195.

## Clustering — Louvain

Maximização gulosa de modularidade, com parâmetro de **resolução** ajustável: valores maiores
produzem mais clusters, menores. A implementação usa `python-louvain` com **semente fixa
(`seed=42`)**, o que torna o resultado **reproduzível**: a mesma entrada devolve sempre a
mesma partição.

> Blondel, V. D., Guillaume, J.-L., Lambiotte, R., & Lefebvre, E. (2008). Fast unfolding of
> communities in large networks. *Journal of Statistical Mechanics*, 2008(10), P10008.

## Layout — ForceAtlas2

Layout dirigido por força, com atração e repulsão ajustáveis na interface. Nós fortemente
conectados se aproximam; comunidades emergem visualmente como regiões densas.

> Jacomy, M., Venturini, T., Heymann, S., & Bastian, M. (2014). ForceAtlas2, a continuous
> graph layout algorithm for handy network visualization. *PLoS ONE*, 9(6), e98679.

## Lei de Bradford

Ordena as fontes por produtividade e as divide em zonas com produção aproximadamente igual. O
número de fontes em cada zona cresce geometricamente — o "núcleo" concentra poucas revistas
com muitos artigos.

> Bradford, S. C. (1934). Sources of information on specific subjects. *Engineering*, 137,
> 85–86.

## Lei de Lotka

Descreve a distribuição de produtividade dos autores: o número de autores com $n$ publicações
é proporcional a $1/n^{\alpha}$, com $\alpha \approx 2$ no caso clássico. O Blicsa estima
$\alpha$ a partir do corpus.

> Lotka, A. J. (1926). The frequency distribution of scientific productivity. *Journal of the
> Washington Academy of Sciences*, 16(12), 317–323.

## Detecção de *bursts*

Identifica termos cuja frequência sobe abruptamente num intervalo, sinalizando temas
emergentes. A implementação compara a frequência de cada termo numa janela recente com sua
frequência histórica no mesmo corpus.

> Kleinberg, J. (2003). Bursty and hierarchical structure in streams. *Data Mining and
> Knowledge Discovery*, 7(4), 373–397.

---

## Relevância de termos — leia com atenção

O Blicsa oferece um controle de **relevância** que mantém os termos mais característicos do
corpus e descarta os genéricos (`estudo`, `análise`, `resultados`).

**A métrica implementada é a divergência de Kullback–Leibler** entre a distribuição de
coocorrência de um termo e a distribuição geral do corpus: termos cuja vizinhança se parece
com "o corpus inteiro" recebem relevância baixa; termos com vizinhança distinta recebem
relevância alta.

$$ \mathrm{rel}(t) = \sum_{j} p(j \mid t) \, \log \frac{p(j \mid t)}{p(j)} $$

> **Declaração de honestidade acadêmica.** Esta métrica é **inspirada no conceito de
> especificidade de termos** discutido por van Eck & Waltman, mas **não é uma implementação da
> fórmula publicada por eles**. O VOSviewer usa um cálculo próprio, descrito em
> Van Eck & Waltman (2011), e os valores produzidos pelo Blicsa **não são numericamente
> comparáveis** aos do VOSviewer. Quem precisar reproduzir resultados publicados com o
> VOSviewer deve usar o VOSviewer.
>
> Van Eck, N. J., & Waltman, L. (2011). Text mining and visualization using VOSviewer.
> *ISSI Newsletter*, 7(3), 50–54.

## Extração de termos

Termos vêm de um destes campos, à sua escolha: palavras-chave, títulos, resumos ou
títulos+resumos. Quando o campo é textual, o Blicsa extrai **frases nominais** e aplica
*stop words* e o thesaurus definido por você.

A extração de frases nominais **funciona bem em inglês e mal em português** — veja
[limitações conhecidas](limitacoes.md).

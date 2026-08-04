# Methods

*Versão em português: [metodos.md](metodos.md)*

What each number in Blicsa means, with the formula and the reference. Where the implementation
**differs** from the literature, that is stated explicitly.

---

## Association strength

Normalises co-occurrence weight by what would be expected if the terms were independent. This
is the default normalisation in Blicsa maps.

$$ s_{ij} = \frac{c_{ij}}{w_i \, w_j} $$

where $c_{ij}$ is the number of documents in which $i$ and $j$ co-occur and $w_i$, $w_j$ are
each term's total occurrences. Two rare terms that always appear together get a high
association; a very frequent term does not dominate the map merely for being frequent.

> Van Eck, N. J., & Waltman, L. (2009). How to normalize cooccurrence data? An analysis of
> some well-known similarity measures. *Journal of the American Society for Information
> Science and Technology*, 60(8), 1635–1651.

## Counting: full or fractional

- **Full (binary)**: each document contributes 1 to every pair of terms it contains.
- **Fractional**: a document's contribution is divided by the number of pairs it generates, so
  documents with many terms do not weigh disproportionately.

> Perianes-Rodriguez, A., Waltman, L., & van Eck, N. J. (2016). Constructing bibliometric
> networks: A comparison between full and fractional counting. *Journal of Informetrics*,
> 10(4), 1178–1195.

## Clustering — Louvain

Greedy modularity maximisation with an adjustable **resolution** parameter: higher values
produce more, smaller clusters. The implementation uses `python-louvain` with a **fixed seed
(`seed=42`)**, which makes the result **reproducible**: the same input always yields the same
partition.

> Blondel, V. D., Guillaume, J.-L., Lambiotte, R., & Lefebvre, E. (2008). Fast unfolding of
> communities in large networks. *Journal of Statistical Mechanics*, 2008(10), P10008.

## Layout — ForceAtlas2

Force-directed layout with attraction and repulsion adjustable in the interface. Strongly
connected nodes move closer together, and communities emerge visually as dense regions.

> Jacomy, M., Venturini, T., Heymann, S., & Bastian, M. (2014). ForceAtlas2, a continuous
> graph layout algorithm for handy network visualization. *PLoS ONE*, 9(6), e98679.

## Bradford's law

Ranks sources by productivity and splits them into zones of roughly equal output. The number
of sources in each zone grows geometrically — the "core" concentrates few journals carrying
many articles.

> Bradford, S. C. (1934). Sources of information on specific subjects. *Engineering*, 137,
> 85–86.

## Lotka's law

Describes the distribution of author productivity: the number of authors with $n$ publications
is proportional to $1/n^{\alpha}$, with $\alpha \approx 2$ in the classic case. Blicsa
estimates $\alpha$ from the corpus.

> Lotka, A. J. (1926). The frequency distribution of scientific productivity. *Journal of the
> Washington Academy of Sciences*, 16(12), 317–323.

## Burst detection

Identifies terms whose frequency rises abruptly within an interval, signalling emerging
topics. The implementation compares each term's frequency in a recent window against its
historical frequency in the same corpus.

> Kleinberg, J. (2003). Bursty and hierarchical structure in streams. *Data Mining and
> Knowledge Discovery*, 7(4), 373–397.

---

## Term relevance — please read carefully

Blicsa offers a **relevance** control that keeps the terms most characteristic of the corpus
and discards generic ones (`study`, `analysis`, `results`).

**The implemented metric is the Kullback–Leibler divergence** between a term's co-occurrence
distribution and the corpus-wide distribution: terms whose neighbourhood looks like "the whole
corpus" get low relevance; terms with a distinctive neighbourhood get high relevance.

$$ \mathrm{rel}(t) = \sum_{j} p(j \mid t) \, \log \frac{p(j \mid t)}{p(j)} $$

> **Academic honesty statement.** This metric is **inspired by the concept of term
> specificity** discussed by van Eck & Waltman, but it is **not an implementation of the
> formula they published**. VOSviewer uses its own calculation, described in Van Eck & Waltman
> (2011), and the values produced by Blicsa are **not numerically comparable** to VOSviewer's.
> Anyone needing to reproduce results published with VOSviewer should use VOSviewer.
>
> Van Eck, N. J., & Waltman, L. (2011). Text mining and visualization using VOSviewer.
> *ISSI Newsletter*, 7(3), 50–54.

## Term extraction

Terms come from one of these fields, at your choice: keywords, titles, abstracts, or
titles+abstracts. When the field is free text, Blicsa extracts **noun phrases** and applies
stop words and the thesaurus you define.

Noun-phrase extraction **works well in English and poorly in Portuguese** — see
[known limitations](limitacoes.md).

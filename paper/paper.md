---
title: 'Blicsa: local-first bibliometrics from literature search to knowledge map'
tags:
  - Python
  - bibliometrics
  - scientometrics
  - science mapping
  - OpenAlex
authors:
  - name: Leonardo Luiz Costa Paniago
    orcid: 0009-0006-1663-3349
    affiliation: 1
affiliations:
  - name: Graduate Program in Entrepreneurship and Innovation, Universidade Federal de Ouro Preto, Brazil
    index: 1
date: 20 August 2026
bibliography: paper.bib
---

# Summary

Blicsa is a free desktop application for bibliometric analysis. It covers
literature retrieval, corpus assembly, knowledge mapping, and bibliometric
statistics in a single workflow that runs on the user's own machine. Records are
retrieved through the OpenAlex, Crossref, and PubMed APIs, and can be imported
from Scopus, Web of Science, Zotero, and standard bibliographic file formats.
Maps are rendered in WebGL as network, overlay, and density views, and the
available analyses include the Bradford and Lotka distributions, co-authorship,
co-citation, and burst detection. Blicsa runs on Windows, macOS, and Linux,
stores all data locally, and requires no account, no server, and no
subscription.

# Statement of need

Bibliometric analysis is now a common method across research fields, but the
tools that support it are fragmented, and each one covers only part of the
process. Moving from a literature search to a finished knowledge map typically
requires chaining several programs together, converting files between
incompatible formats, and depending on at least one paid service. This
fragmentation raises the cost of entry, and the cost falls most heavily on
students and on institutions that cannot afford commercial subscriptions.

Blicsa closes the pipeline in a single free application that runs locally. A
researcher can query a database, filter and deduplicate the results, build a
project, generate a map, and export it without leaving the program and without
transmitting any data to a remote server. The intended users are researchers and
graduate students who perform science mapping or systematic reviews, and in
particular those who have no access to paid databases or to programming
environments.

# State of the field

The established tools each solve one part of the problem. VOSviewer produces
high-quality visualizations but does not retrieve literature, so the corpus must
be assembled elsewhere and imported [@vanEck2010]. Bibliometrix is comprehensive
and well maintained, but it requires R, which excludes users without programming
experience [@Aria2017]. CiteSpace offers advanced detection of emerging trends,
at the cost of a heavier and less approachable configuration [@Chen2006]. Scopus
and Web of Science provide curated data, but behind institutional subscriptions
that many researchers do not have.

None of these tools combines retrieval, analysis, and visualization in a single
free program that runs without programming. Blicsa targets that intersection.
Retrieval defaults to OpenAlex, an open scholarly index created as a replacement
for the discontinued Microsoft Academic Graph [@Priem2022], which allows the
entire workflow to operate without a paid data source. Scopus and Web of Science
remain available through file import, so users who do have institutional access
are not excluded.

# Software design

Blicsa is written in Python and distributed as a standalone binary for the three
major platforms, so no Python installation is required. This matters for the
intended audience: the leading alternatives require installing the R environment
or a Java runtime before any analysis can begin, which is the main barrier for
researchers without a computing background. The interface is built with
CustomTkinter, and maps are rendered by Sigma.js on a WebGL canvas embedded
through pywebview. The rendering library is vendored, so mapping works without an
internet connection. Projects are stored as self-contained files that hold the
corpus, the map, the parameters, and the search history, which makes a study
straightforward to archive and to share.

The correctness of the software was assessed by a stricter criterion than the
size of the test suite. The suite contains 1,054 tests, plus 27 live tests that
call the real APIs and are excluded from the default run. Its ability to detect
faults was measured by reinjecting defects that had previously been found and
fixed: each defect is deliberately reintroduced into the code, and the suite must
fail. All 101 reinjected defects are detected. This procedure is a variant of
mutation analysis [@DeMillo1978] that uses real historical faults rather than
synthetic mutants, an approach motivated by evidence that real faults are the
more demanding reference for evaluating test suites [@Just2014].

The exercise is itself audited. A recent refactor silently broke ten cases, which
reported as failures until they were repointed, and one further case was found to
target a test that the injected defect could not reach. Both were corrected, and
the matrix records the sequence rather than only the final figure. Claims about
layout and rendering are verified against captures of the running application
window rather than against simulated objects.

# Research impact

Blicsa lowers the cost of entry to science mapping for researchers who have no
access to paid bibliographic databases, a constraint that is common in
institutions outside high-income countries, and for researchers who have no
programming background. Because the application is local-first, it is also usable
where institutional policy or ethical review restricts the transmission of
research data to third-party servers. The software is released under the MIT
license, with binaries for Windows, macOS, and Linux, and each release is
permanently archived with a DOI [@Paniago2026].

# AI usage disclosure

AI coding assistants were used during part of the development, under the
direction and review of the author. Their output was not accepted on the grounds
that it looked correct: every substantive claim about the behavior of the program
was verified against the running software. The defect reinjection described above
was applied to tests that originated from AI assistance as well as to the rest of
the suite, and some of those tests were rejected as inadequate. Behavior that
depends on the interface language was verified through real calls to the model
rather than through inspection of the prompt, after a case in which the language
tests passed while a substantial share of the analyses still returned text in the
wrong language. The author is responsible for all content of the software and of
this paper.

# Acknowledgements

The author thanks the Graduate Program in Entrepreneurship and Innovation
(Propei) of the Universidade Federal de Ouro Preto.

# References

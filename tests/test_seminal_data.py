"""Regressões dos resultados repetidos e atribuições incorretas no relatório seminal."""

import json

import networkx as nx
import pandas as pd

from core.seminal import (ranked_corpus_authors, reference_metadata_consistent,
                          top_references)


def test_autores_sao_separados_antes_da_normalizacao_e_obra_pertence_ao_autor():
    df = pd.DataFrame([
        {"authors": "Ana Silva; Bruno Costa", "title": "Obra conjunta", "year": 2020,
         "citations": 12},
        {"authors": "Ana Silva", "title": "Obra de Ana", "year": 2021,
         "citations": 30},
        {"authors": "Ana Silveira", "title": "Obra de outra pessoa", "year": 2022,
         "citations": 100},
    ])

    by_name = {row["author"]: row for row in ranked_corpus_authors(df)}

    assert by_name["Ana Silva"]["citations"] == 42
    assert by_name["Ana Silva"]["top_title"] == "Obra de Ana"
    assert by_name["Bruno Costa"]["top_title"] == "Obra conjunta"
    assert by_name["Ana Silveira"]["top_title"] == "Obra de outra pessoa"
    assert len(by_name) == 3


def test_referencias_contadas_por_artigo_e_ids_equivalentes_agrupados():
    df = pd.DataFrame({"references": [
        "https://openalex.org/W123; W123; Freire P, 1968, Livro",
        "W123; FREIRE P, 1968, LIVRO",
        "10.1234/Test; doi:10.1234/test",
    ]})
    assert top_references(df) == [
        ("https://openalex.org/W123", 2),
        ("Freire P, 1968, Livro", 2),
        ("10.1234/Test", 1),
    ]


def test_consolidacao_ignora_consolidados_e_deduplica_obras(tmp_path, monkeypatch):
    import run_consolidated_from_blicsa as script

    for folder in ("patentbert", "grace-period", "seminario-consolidado-local-blicsa"):
        d = tmp_path / folder
        d.mkdir()
        (d / "project.blicsa").touch()

    records = {
        "patentbert": pd.DataFrame([
            {"title": "Obra única", "doi": "https://doi.org/10.1234/A", "citations": 7,
             "authors": "Ana Silva", "references": ""}]),
        "grace-period": pd.DataFrame([
            {"title": "Obra única", "doi": "10.1234/a", "citations": 8,
             "authors": "Ana Silva", "references": "W123"},
            {"title": "Outra obra", "doi": "", "citations": 2,
             "authors": "Bruno Costa", "references": "W456"}]),
        "seminario-consolidado-local-blicsa": pd.DataFrame([
            {"title": "Obra única", "doi": "10.1234/a", "citations": 8,
             "authors": "Ana Silva", "references": "W123"}]),
    }
    read = []

    def fake_load(path):
        read.append(path.parent.name)
        return records[path.parent.name]

    monkeypatch.setattr(script, "load_blicsa_dataframe", fake_load)
    result = script.gather_all_data(tmp_path)

    assert len(result) == 2
    assert read == ["grace-period", "patentbert"]
    assert result.loc[result["title"] == "Obra única", "citations"].iloc[0] == 8
    assert result.loc[result["title"] == "Obra única", "references"].iloc[0] == "W123"


def test_relatorio_separa_citacoes_recebidas_de_referencias_citadas():
    import run_consolidated_from_blicsa as script

    df = pd.DataFrame([
        {"authors": "Ana Silva; Bruno Costa", "title": "Estudo A", "year": 2020,
         "citations": 10, "references": "W123", "keywords": "patente"},
        {"authors": "Ana Silva", "title": "Estudo B", "year": 2021,
         "citations": 20, "references": "W123", "keywords": "patente"},
    ])
    original_columns = list(df.columns)
    text = script.build_insights(df, nx.Graph(), nx.Graph())

    assert "Ana Silva** — 30 citações em 2 artigo(s)" in text
    assert "Bruno Costa** — 10 citações em 1 artigo(s)" in text
    assert "Obra no corpus: Estudo B" in text
    assert "W123 — citado por 2 artigo(s)" in text
    assert "OpenAlex ID |" not in text
    assert list(df.columns) == original_columns


def test_id_openalex_resolvido_por_endpoint_exato(monkeypatch):
    from core.sources.openalex import OpenAlexProvider

    provider = OpenAlexProvider(api_key="")
    urls = []

    def fake_fetch(url, **kwargs):
        urls.append(url)
        return json.dumps({"id": "https://openalex.org/W123", "title": "Obra verificada",
                           "publication_year": 2021,
                           "authorships": [{"author": {"display_name": "Ana Silva"}}]})

    monkeypatch.setattr(provider, "fetch_url", fake_fetch)
    record = provider.get_by_id("https://openalex.org/W123")

    assert urls == [f"https://api.openalex.org/works/W123?mailto={provider.mailto}"]
    assert record["title"] == "Obra verificada"
    assert record["authors"] == "Ana Silva"
    assert provider.get_by_id("W123; lixo") is None
    assert len(urls) == 1


def test_ids_sem_metadados_nao_chegam_ao_modelo(monkeypatch):
    import main
    from core.sources.openalex import OpenAlexProvider

    monkeypatch.setattr(OpenAlexProvider, "get_by_id", lambda self, ref: None)
    evidence, unresolved = main.BlicsaApp._preparar_referencias_seminais(
        [("https://openalex.org/W123", 3)])

    assert evidence == ""
    assert unresolved == 1


def test_titulo_e_ano_contraditorios_no_doi_sao_omitidos(monkeypatch):
    import main
    from core.sources.openalex import OpenAlexProvider
    from core.sources.crossref import CrossrefProvider

    monkeypatch.setattr(OpenAlexProvider, "get_by_id", lambda self, ref: {
        "title": "Health supplement pipeline", "year": 2018,
        "doi": "10.4230/lipics.cosit.2022.18", "authors": "A. Author",
    })
    monkeypatch.setattr(CrossrefProvider, "get_by_doi", lambda self, doi: {
        "title": "Qualitative spatial question answering", "year": 2022,
    })
    evidence, unresolved = main.BlicsaApp._preparar_referencias_seminais(
        [("https://openalex.org/W2896457183", 21)])

    assert evidence == ""
    assert unresolved == 1
    assert not reference_metadata_consistent(
        {"title": "Health supplement pipeline", "year": 2018},
        {"title": "Qualitative spatial question answering", "year": 2022},
    )


def test_variantes_de_titulo_do_mesmo_doi_sao_aceitas():
    assert reference_metadata_consistent(
        {"title": "Patent Classification: Using BERT", "year": 2020},
        {"title": "Patent classification using BERT", "year": 2021},
    )


def test_datacite_impede_mistura_de_metadados_quando_crossref_nao_tem_doi(monkeypatch):
    import main
    from core.sources.openalex import OpenAlexProvider
    from core.sources.crossref import CrossrefProvider

    monkeypatch.setattr(OpenAlexProvider, "get_by_id", lambda self, ref: {
        "title": "HISTORIAE, History of Socio-Cultural Transformation",
        "year": 2019, "doi": "10.4230/LIPIcs.CP.2025.31", "authors": "Wrong Author",
    })
    monkeypatch.setattr(CrossrefProvider, "get_by_doi", lambda self, doi: None)
    monkeypatch.setattr("core.sources.datacite.get_by_doi", lambda doi: {
        "title": "Transformer-Based Feature Learning for Algorithm Selection",
        "year": 2025,
    })

    evidence, unresolved = main.BlicsaApp._preparar_referencias_seminais(
        [("https://openalex.org/W2965373594", 13)])

    assert evidence == ""
    assert unresolved == 1


def test_doi_sem_registro_conferivel_nao_e_entregue_a_ia(monkeypatch):
    import main
    from core.sources.openalex import OpenAlexProvider
    from core.sources.crossref import CrossrefProvider

    monkeypatch.setattr(OpenAlexProvider, "get_by_id", lambda self, ref: {
        "title": "Título aparentemente plausível", "year": 2020,
        "doi": "10.9999/sem-registro", "authors": "Autor Incerto",
    })
    monkeypatch.setattr(CrossrefProvider, "get_by_doi", lambda self, doi: None)
    monkeypatch.setattr("core.sources.datacite.get_by_doi", lambda doi: None)

    evidence, unresolved = main.BlicsaApp._preparar_referencias_seminais(
        [("https://openalex.org/W123", 9)])

    assert evidence == ""
    assert unresolved == 1

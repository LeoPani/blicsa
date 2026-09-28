"""A ampliação metodológica não pode admitir ruído nem buscas pela metade."""

import json

import pytest

from scripts.atualizar_patentbert import load_extra, screen
from scripts.importar_rebuscas import dedup_key
from scripts.refazer_qualificacao import PATENT_EXTRA_QUERIES


def work(title, abstract="", kind="article", source="Journal"):
    return {"title": title, "abstract": abstract,
            "document_type": kind, "source": source}


def test_treinamento_mascarado_de_patentes_pertence_ao_corpus():
    assert screen(work("Patent Language Model Pretraining with ModernBERT",
                       "We pretrain domain-specific masked language models for patents"),
                  "patent-masked") == ""


def test_metodo_de_adaptacao_sem_patentes_nao_entra_no_mapa_aplicado():
    assert screen(work("Domain-adaptive pretraining for biology",
                       "masked language models for clinical notes"),
                  "patent-adaptation")


def test_busca_mascarada_rejeita_pre_treinamento_que_nao_usa_mascara():
    assert screen(work("Patent model pretraining with generative AI"), "patent-masked")


def test_busca_semantica_de_patentes_precisa_de_modelo():
    assert screen(work("Semantic similarity in patent legislation"), "patent-semantic")
    assert screen(work("Dense retrieval of patent prior art with BERT"),
                  "patent-semantic") == ""


def test_consulta_incompleta_impede_ampliacao(tmp_path):
    for family, query in PATENT_EXTRA_QUERIES.items():
        (tmp_path / f"{family}.json").write_text(json.dumps({
            "query": query, "announced": 2, "records": [{}],
        }), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Consulta incompleta"):
        load_extra(tmp_path)


def test_titulo_com_quebra_literal_nao_foge_da_deduplicacao():
    assert dedup_key({"title": "Rightful Ownership\\n Protection in the Cloud"}) == \
           dedup_key({"title": "Rightful Ownership Protection in the Cloud"})

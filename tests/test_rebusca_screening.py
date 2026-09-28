from scripts.importar_rebuscas import screening_reason


def record(title: str, abstract: str = "") -> dict:
    return {"title": title, "abstract": abstract, "document_type": "article"}


def test_patentbert_excludes_medical_patent_ductus() -> None:
    reason = screening_reason(
        "patentbert",
        record(
            "Automated Detection of Patent Ductus Arteriosus Using a Transformer Model",
            "Pediatric Doppler ultrasonography in preterm infants.",
        ),
    )
    assert reason.startswith("homonímia médica")


def test_grace_period_excludes_medical_patent_ductus() -> None:
    reason = screening_reason(
        "grace-period",
        record(
            "Ibuprofen for patent ductus arteriosus in preterm infants",
            "A clinical grace period was used for neonatal treatment.",
        ),
    )
    assert reason.startswith("homonímia médica")


def test_medical_context_with_real_patents_is_kept() -> None:
    reason = screening_reason(
        "patentbert",
        record(
            "From Regulatory Approvals to Patents: Cardiovascular Device Traceability",
            "A language model links device approvals to intellectual property documents.",
        ),
    )
    assert reason == ""

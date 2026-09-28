"""O mapa deve preservar expressões temáticas sem repetir fragmentos genéricos."""

from scripts.exportar_mapas_rebusca import choose_terms, selected_projects


class FakeGenerator:
    def get_candidate_terms(self, **kwargs):
        freq = {"design": 47, "science": 46, "design science": 46,
                "innovation management": 20, "intellectual property": 14,
                "technology transfer": 8, "most": 12, "only": 10}
        return [], [], freq, []


def test_mapa_dsr_prioriza_expressoes_em_vez_de_fragmentos_redundantes():
    terms = choose_terms(FakeGenerator(), maximum=6,
                         slug="qualificacao-2026-dsr-e-pi-rebusca")

    assert "design science" in terms
    assert "innovation management" in terms
    assert "intellectual property" in terms
    assert "technology transfer" in terms
    assert not {"design", "science", "most", "only"} & terms


def test_exportacao_pelo_nome_dsr_e_pi_seleciona_projeto_existente():
    assert selected_projects("dsr-pi") == (
        ("qualificacao-2026-dsr-e-pi-rebusca", 1),
    )

"""Fase 2 — Modo Importação: aviso de volume, estimativa, cancelamento e trilha.

Fixtures adversariais: limite vazio/lixo/negativo, total zero, taxa desconhecida, lote vazio,
cancelamento no primeiro lote, erro de rede persistente, registros sem DOI e sem título.

Cada guarda é testada dos DOIS lados: o caso protegido e o caso normal que tem de continuar
funcionando (limitar não pode virar "nunca baixar tudo"; avisar não pode virar "avisar sempre").
"""
import time

import pytest

from core.import_job import (
    LIMIAR_AVISO,
    ImportJob,
    ImportProgress,
    RateEstimator,
    decide_volume,
    format_eta,
    merge_without_duplicates,
    parse_limit,
)


def _recs(n, inicio=0, com_doi=True):
    return [{"title": f"Artigo {i}", "doi": f"10.1/{i}" if com_doi else "",
             "year": 2020, "citations": i}
            for i in range(inicio, inicio + n)]


def _lotes(total, tam=25, com_doi=True):
    for i in range(0, total, tam):
        yield _recs(min(tam, total - i), inicio=i, com_doi=com_doi)


class Relogio:
    """Relógio sintético: a estimativa fica determinística."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avanca(self, s):
        self.t += s


# ─────────────────────────── limite ───────────────────────────

@pytest.mark.parametrize("entrada", ["", "   ", None, "0", "-5", "abc", 0, -3])
def test_empty_or_invalid_limit_means_unlimited(entrada):
    """Limite vazio = ilimitado (o padrão pedido). Lixo e negativo também."""
    assert parse_limit(entrada) is None


@pytest.mark.parametrize("entrada,esperado", [("1000", 1000), (2500, 2500), ("10.000", 10000)])
def test_valid_limit_is_parsed(entrada, esperado):
    """O outro lado: um número válido tem de ser respeitado."""
    assert parse_limit(entrada) == esperado


def test_unlimited_downloads_everything_without_artificial_cut():
    """Sem limite não existe corte artificial — o alvo é o total encontrado."""
    job = ImportJob(total_encontrado=137, limite=None)
    assert job.limite is None and job.alvo == 137
    baixados = job.consume(_lotes(137))
    assert len(baixados) == 137 and job.baixados == 137
    assert "limite" not in job.trail()


def test_explicit_limit_downloads_exactly_that_many():
    job = ImportJob(total_encontrado=50_000, limite=10_000)
    baixados = job.consume(_lotes(50_000))
    assert len(baixados) == 10_000, f"esperava exatamente 10.000, veio {len(baixados)}"
    assert job.reached_limit is True
    assert "de 10.000 (limite)" in job.trail()


def test_limit_that_is_not_a_multiple_of_the_batch_is_still_exact():
    """Limite que cai no MEIO de um lote tem de cortar o lote.

    Com limite 10.000 e lotes de 25 a fronteira é exata, e o teste acima passava mesmo sem o
    corte — cada lote inteiro cabia e o clamp do progresso disfarçava. A matriz de reinjeção
    expôs isso; um limite não-múltiplo é o caso que discrimina.
    """
    job = ImportJob(total_encontrado=50_000, limite=10_007)
    baixados = job.consume(_lotes(50_000, tam=25))
    assert len(baixados) == 10_007, (
        f"o último lote deveria ser cortado no limite, veio {len(baixados)}")
    assert job.baixados == 10_007


# ─────────────────────────── aviso de volume ───────────────────────────

def test_large_volume_triggers_the_warning_with_the_real_number():
    d = decide_volume(total=319_300, limite=None, taxa_por_segundo=200.0)
    assert d.warn is True
    assert d.total == 319_300, "o diálogo mostra o número REAL, não um arredondado"
    assert d.suggested_limit == 10_000
    assert d.eta_seconds == pytest.approx(319_300 / 200.0)


def test_small_volume_does_not_trigger_the_warning():
    """O outro lado da guarda: abaixo do limiar não incomoda o usuário."""
    assert decide_volume(total=500, limite=None).warn is False
    assert decide_volume(total=LIMIAR_AVISO, limite=None).warn is False, "no limiar, não avisa"
    assert decide_volume(total=LIMIAR_AVISO + 1, limite=None).warn is True


def test_a_small_limit_on_a_huge_universe_does_not_warn():
    """Quem já limitou não precisa ser avisado — o que conta é o que SERÁ baixado."""
    d = decide_volume(total=319_300, limite=500)
    assert d.warn is False, "com limite de 500 não há volume grande para avisar"


def test_volume_decision_without_a_known_rate_has_no_eta():
    d = decide_volume(total=50_000, limite=None, taxa_por_segundo=None)
    assert d.warn is True and d.eta_seconds is None
    assert format_eta(None) == "—"


def test_zero_results_never_warns():
    d = decide_volume(total=0, limite=None)
    assert d.warn is False and d.total == 0


# ─────────────────────────── estimativa de tempo ───────────────────────────

def test_eta_comes_from_the_observed_rate():
    """Taxa sintética conhecida → estimativa esperada, sem depender de relógio real."""
    rel = Relogio()
    est = RateEstimator(relogio=rel)
    est.update(0)
    rel.avanca(10.0)
    est.update(1000)              # 100 registros/s

    assert est.rate == pytest.approx(100.0)
    assert est.eta(restantes=5000) == pytest.approx(50.0)
    assert format_eta(est.eta(5000)) == "~50 s"
    assert format_eta(1680) == "~28 min"


def test_eta_is_unknown_before_two_samples():
    est = RateEstimator(relogio=Relogio())
    assert est.rate is None and est.eta(100) is None
    est.update(10)
    assert est.rate is None, "uma amostra só não dá taxa"


def test_eta_uses_a_sliding_window_not_the_cold_start():
    """As primeiras páginas são lentas; a janela deslizante impede que arrastem a estimativa."""
    rel = Relogio()
    est = RateEstimator(janela=3, relogio=rel)
    est.update(0)
    rel.avanca(20.0)
    est.update(10)                # começo frio: 0,5 reg/s
    for _ in range(3):            # depois acelera: 100 reg/s
        rel.avanca(1.0)
        est.update(est._marcas[-1][1] + 100)

    assert est.rate > 50, f"a janela deveria refletir o ritmo atual, deu {est.rate:.1f}/s"


def test_eta_is_zero_when_nothing_is_left():
    est = RateEstimator(relogio=Relogio())
    assert est.eta(0) == 0.0


# ─────────────────────────── progresso ───────────────────────────

def test_progress_never_regresses_nor_exceeds_one_hundred():
    job = ImportJob(total_encontrado=100, limite=None)
    job.advance(30)
    p1 = job.progress()
    job.advance(-10)                      # tentativa de regredir
    p2 = job.progress()
    job.advance(500)                      # tentativa de estourar
    p3 = job.progress()

    assert p1.percent == 30
    assert p2.downloaded == 30, "o progresso não pode regredir"
    assert p3.percent == 100 and p3.fraction == 1.0, "não pode passar de 100%"
    assert job.baixados == 100


def test_progress_with_unknown_target_does_not_invent_a_percentage():
    p = ImportProgress(downloaded=500, target=0)
    assert p.fraction == 0.0 and p.percent == 0, (
        "sem alvo a barra fica indeterminada em vez de mentir uma porcentagem")


def test_progress_fraction_is_monotonic_across_batches():
    job = ImportJob(total_encontrado=250, limite=None)
    fracoes = []
    job.consume(_lotes(250), on_batch=lambda _: fracoes.append(job.progress().fraction))
    assert fracoes == sorted(fracoes), f"a fração regrediu: {fracoes}"
    assert fracoes[-1] == 1.0


# ─────────────────────────── cancelamento ───────────────────────────

def test_cancelling_preserves_the_partial_and_says_so_in_the_trail():
    job = ImportJob(total_encontrado=1000, limite=None)

    def lotes():
        for i in range(0, 1000, 25):
            if i >= 100:
                job.cancel()
            yield _recs(25, inicio=i)

    parcial = job.consume(lotes())
    assert 0 < len(parcial) < 1000, f"o parcial deveria ser preservado, veio {len(parcial)}"
    assert job.cancelado is True
    assert "cancelado pelo usuário" in job.trail()
    assert "resultados parciais" in job.trail()


def test_cancelling_before_the_first_batch_yields_nothing_without_crashing():
    job = ImportJob(total_encontrado=1000, limite=None)
    job.cancel()
    assert job.consume(_lotes(1000)) == []
    assert job.baixados == 0 and "cancelado" in job.trail()


def test_not_cancelling_downloads_everything():
    """O outro lado: sem cancelamento, nada é interrompido."""
    job = ImportJob(total_encontrado=300, limite=None)
    assert len(job.consume(_lotes(300))) == 300
    assert "cancelado" not in job.trail()


# ─────────────────────────── erro de rede ───────────────────────────

def test_persistent_network_error_leaves_partial_and_warns_in_the_trail():
    """Regressão do bug já corrigido: parada por rede nunca é silenciosa."""
    job = ImportJob(total_encontrado=5000, limite=None)

    def lotes():
        yield _recs(25)
        yield _recs(25, inicio=25)
        job.erro_rede = "HTTP 429 após 3 tentativas"

    parcial = job.consume(lotes())
    assert len(parcial) == 50
    trilha = job.trail()
    assert "⚠ interrompido por erro de rede" in trilha
    assert "resultados parciais" in trilha
    assert "HTTP 429" in trilha, "a trilha deveria dizer o motivo"


def test_clean_run_has_no_warning_in_the_trail():
    job = ImportJob(total_encontrado=50, limite=None)
    job.consume(_lotes(50))
    assert "⚠" not in job.trail()


# ─────────────────────────── deduplicação e trilha ───────────────────────────

def test_trail_reports_dedup_and_language_filter_counts():
    job = ImportJob(total_encontrado=1000, limite=None)
    job.consume(_lotes(1000))
    job.filtrados_idioma = 37
    trilha = job.trail(after_dedup=940)

    assert "Encontrados 1.000" in trilha
    assert "baixados 1.000" in trilha
    assert "após deduplicação 940" in trilha
    assert "filtrados por idioma 37" in trilha
    assert job.deduplicados == 60


def test_trail_omits_dedup_when_nothing_was_removed():
    job = ImportJob(total_encontrado=10, limite=None)
    job.consume(_lotes(10))
    assert "deduplicação" not in job.trail(after_dedup=10)


def test_reimporting_the_same_query_does_not_duplicate():
    """Reimportar é comum (refinar filtro e importar de novo) — o corpus não pode dobrar."""
    corpus = _recs(100)
    juntos, ignorados = merge_without_duplicates(corpus, _recs(100))
    assert len(juntos) == 100 and ignorados == 100, "todos já estavam no corpus"

    juntos2, ignorados2 = merge_without_duplicates(corpus, _recs(50, inicio=90))
    assert len(juntos2) == 140 and ignorados2 == 10, "só os 10 repetidos são ignorados"


def test_merge_falls_back_to_title_when_there_is_no_doi():
    corpus = [{"title": "Um Estudo", "doi": ""}]
    juntos, ignorados = merge_without_duplicates(corpus, [{"title": "  um   estudo ", "doi": ""}])
    assert len(juntos) == 1 and ignorados == 1, "mesmo título normalizado é o mesmo registro"

    # Registro sem DOI e sem título não vira entrada fantasma.
    juntos2, _ = merge_without_duplicates([], [{"title": "", "doi": ""}])
    assert juntos2 == []


# ─────────────────────────── memória ───────────────────────────

def test_fifty_thousand_records_do_not_blow_memory(capsys):
    """50.000 registros sintéticos: pico de memória medido e registrado.

    Método: `tracemalloc` em volta do consumo dos lotes, medindo o pico do processo durante
    a importação. Reproduzível por `pytest tests/test_import_job.py -k fifty -s`.
    """
    import tracemalloc

    TOTAL = 50_000
    tracemalloc.start()
    job = ImportJob(total_encontrado=TOTAL, limite=None)
    registros = job.consume(_lotes(TOTAL, tam=500))
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    pico_mb = pico / (1024 * 1024)

    with capsys.disabled():
        print(f"\n[perf] 50.000 registros · pico {pico_mb:.1f} MB · "
              f"{len(registros)} acumulados · progresso {job.progress().percent}%")

    assert len(registros) == TOTAL
    assert job.progress().percent == 100
    assert pico_mb < 200, f"pico de {pico_mb:.1f} MB para 50.000 registros"

"""
Nível 2 — VELOCIDADE real de cada base. TODOS os testes são @pytest.mark.live
(medem rede real). Sem threshold de reprovação por lentidão — os números viram
baseline no relatório. Exceção: timeout duro de 120s para 100 records = falha real.

Rodar: pytest -m live tests/test_search_speed.py -s
(-s para ver os números impressos.)
"""
import statistics
import threading
import time

import pytest

from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider

PROVIDERS = [
    ("OpenAlex", OpenAlexProvider),
    ("Crossref", CrossrefProvider),
    ("PubMed", PubMedProvider),
]
QUERY = "bibliometric analysis"
HARD_TIMEOUT_S = 120.0


def _fetch_n(cls, n):
    """Retorna (records, elapsed_s) para uma busca fresca (cache limpo por instância)."""
    prov = cls()
    t0 = time.perf_counter()
    recs = list(prov.search(QUERY, max_results=n))
    return recs, time.perf_counter() - t0


@pytest.mark.live
@pytest.mark.parametrize("name,cls", PROVIDERS, ids=[p[0] for p in PROVIDERS])
def test_throughput_100_records_median(name, cls):
    """3 repetições buscando 100 records; reporta mediana e records/s."""
    times, counts = [], []
    for _ in range(3):
        recs, dt = _fetch_n(cls, 100)
        assert dt < HARD_TIMEOUT_S, f"{name}: {dt:.1f}s > timeout duro de {HARD_TIMEOUT_S}s"
        times.append(dt)
        counts.append(len(recs))
    med = statistics.median(times)
    n = statistics.median(counts)
    rps = n / med if med > 0 else float("inf")
    print(f"\n[SPEED] {name:9} | 100 records | mediana={med:6.2f}s | "
          f"n={int(n):3d} | {rps:6.1f} rec/s | tempos={[round(t,2) for t in times]}")
    assert n > 0, f"{name} não retornou registros"


@pytest.mark.live
@pytest.mark.parametrize("name,cls", PROVIDERS, ids=[p[0] for p in PROVIDERS])
def test_first_record_latency(name, cls):
    """Latência até o PRIMEIRO record chegar (útil para percepção de resposta)."""
    prov = cls()
    t0 = time.perf_counter()
    gen = prov.search(QUERY, max_results=100)
    first = next(gen, None)
    latency = time.perf_counter() - t0
    # drena o resto para fechar conexões de forma limpa
    for _ in gen:
        pass
    print(f"\n[SPEED] {name:9} | latência 1º record = {latency:6.2f}s "
          f"({'ok' if first else 'VAZIO'})")
    assert first is not None, f"{name} não entregou nenhum record"
    assert latency < HARD_TIMEOUT_S


@pytest.mark.live
@pytest.mark.parametrize("name,cls", PROVIDERS, ids=[p[0] for p in PROVIDERS])
def test_cancellation_stops_fast_and_clean(name, cls):
    """
    Dispara busca de 500 results; seta cancel_event após a 1ª página (via
    progress_cb) → a busca deve parar em < 5s sem corromper estado (records
    coletados até ali continuam válidos).
    """
    cancel_event = threading.Event()
    collected = []
    cancel_ts = []

    def progress(current, total):
        # após a primeira página conhecida, pede cancelamento
        cancel_ts.append(time.perf_counter())
        cancel_event.set()

    prov = cls()
    t0 = time.perf_counter()
    try:
        for r in prov.search(QUERY, max_results=500,
                             progress_cb=progress, cancel_event=cancel_event):
            collected.append(r)
    except InterruptedError:
        pass  # cancelamento cooperativo é o esperado
    end = time.perf_counter()
    elapsed = end - t0
    # Responsividade do cancelamento = tempo do PEDIDO de cancelamento até parar,
    # isolando a latência (variável, de rede) da primeira página.
    responsiveness = (end - cancel_ts[0]) if cancel_ts else elapsed

    print(f"\n[SPEED] {name:9} | 1ª página em {elapsed:5.2f}s | parou "
          f"{responsiveness:5.2f}s após pedir cancelamento | "
          f"{len(collected)} records coletados")
    assert responsiveness < 5.0, \
        f"{name}: parou {responsiveness:.1f}s após cancelar (>5s)"
    # estado não-corrompido: o que veio antes do cancel é bem-formado
    for r in collected:
        assert isinstance(r.get("title"), str)
        assert isinstance(r.get("year"), int)
    # não deve ter chegado perto dos 500 (parou cedo)
    assert len(collected) < 500

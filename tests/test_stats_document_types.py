"""A aba Estatísticas expõe as contagens de tipos preservadas no corpus."""

from types import SimpleNamespace

import pandas as pd

import main


class _Box:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        pass

    def delete(self, *args):
        self.text = ""

    def insert(self, _where, text):
        self.text += text


def test_stats_show_journal_conference_and_unknown_source(monkeypatch):
    labels = {
        "stats.types_header": "TYPES",
        "stats.journal_total": "Journal papers: {n}",
        "stats.type.article": "Journal article",
        "stats.type.review": "Journal review",
        "stats.type.conference-paper": "Conference paper",
        "stats.source_unknown": "(unknown source)",
    }
    monkeypatch.setattr(main, "t", lambda key, **kw: labels.get(key, key).format(**kw))
    df = pd.DataFrame([
        {"title": "A", "authors": "Alice", "year": 2024,
         "citations": 2, "source": "", "keywords": "", "document_type": "article"},
        {"title": "B", "authors": "Bob", "year": 2025,
         "citations": 0, "source": "Journal B", "keywords": "", "document_type": "review"},
        {"title": "C", "authors": "Carol", "year": 2025,
         "citations": 0, "source": "", "keywords": "", "document_type": "conference-paper"},
    ])
    box = _Box()
    view = SimpleNamespace(_dataframe=df, _generator=None, _stats_box=box)

    main.BlicsaApp._update_stats_tab(view)

    assert "Journal papers: 2" in box.text
    assert "Journal article" in box.text
    assert "Conference paper" in box.text
    assert "(unknown source)" in box.text

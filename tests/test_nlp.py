import pytest
from core.nlp import extract_ngrams

def test_extract_ngrams_portuguese_stop_words():
    # A typical title/abstract in Portuguese with a lot of stop words
    text = "Neste estudo nós propomos uma nova abordagem para a análise dos efeitos significativos do empreendedorismo em pequenas empresas. Os resultados indicam um grande impacto."
    
    ngrams = extract_ngrams(text, min_n=1, max_n=1)
    
    # Check that stop words were removed:
    # "Neste", "estudo", "nós", "uma", "nova", "abordagem", "para", "a", "análise", "dos", "efeitos", "significativos", "do", "em", "pequenas", "Os", "resultados", "indicam", "um", "grande", "impacto"
    
    # "estudo", "nova", "abordagem", "análise", "efeitos", "significativos", "resultados", "grande" were added/present in stop words
    # Therefore, the valid ngrams should primarily just be "propomos", "empreendedorismo", "empresas", "indicam", "impacto"
    
    assert "empreendedorismo" in ngrams
    assert "empresas" in ngrams
    assert "impacto" not in ngrams
    assert "significativos" in ngrams
    
    # Should NOT be in the output
    assert "estudo" not in ngrams
    assert "nova" not in ngrams
    assert "abordagem" not in ngrams
    assert "análise" not in ngrams
    assert "efeitos" not in ngrams
    assert "resultados" not in ngrams

def test_extract_ngrams_english_stop_words():
    text = "In this study we present a novel approach to the analysis of significant effects of entrepreneurship. The results show a large impact."
    
    ngrams = extract_ngrams(text, min_n=1, max_n=1)
    
    assert "entrepreneurship" in ngrams
    assert "impact" in ngrams
    
    assert "study" not in ngrams
    assert "novel" not in ngrams
    assert "approach" not in ngrams
    assert "analysis" not in ngrams
    assert "effects" not in ngrams
    assert "results" not in ngrams

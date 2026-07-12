# Relatório — Validação automatizada (i18n piloto + pendências)

**Data:** 2026-07-12 · **Natureza:** 100% verificação (nenhum código de produção alterado).
Ambiente: macOS Aqua, GUI real, `GROQ_API_KEY` presente. Tkinter/CustomTkinter inicializam
headless (medição de fonte e render de mapa via `savefig` funcionam **sem** captura de tela).

> ## ⚠️ BLOQUEIO: capturas de tela do app estão PENDENTES DE PERMISSÃO
> `screencapture` falha com `could not create image from display` (todas as variações,
> exit 1, nenhum arquivo). A sessão É Aqua (7 processos com janela), então **não é falta de
> GUI** — é a permissão de **Gravação de Tela** do macOS para o Terminal.
> **Conceder:** Ajustes do Sistema → Privacidade e Segurança → **Gravação de Tela** →
> habilitar **Terminal** (ou iTerm) → reabrir o Terminal → me reinvocar.
> Só então gero `i18n_ajustes_{lang}.png` e `i18n_blink_{lang}.png` REAIS.
> **Nenhuma imagem mock foi gerada.**

## Tabela única de resultados

| Item | Método | Resultado | Evidência |
|---|---|---|---|
| **A.1** Chaves i18n faltantes (3 idiomas) | script: `t()` em 14 chaves × 3 idiomas, captura de `[i18n] Warning` | **PASSOU** (0 warnings em pt_BR/en/fr) | saída abaixo |
| **A.2** Truncamento (largura fixa) | `CTkFont`/`font.measure` real vs largura do widget | **REVISAR** (2 casos apertados) | tabela abaixo |
| **A.3** Blink no idioma certo (sem API) | `tests/test_blink_i18n.py` (6 testes) | **PASSOU** (6 passed) | pytest |
| **A.4** Blink responde no idioma da UI | live via `AIAnalyst`+GROQ, `langdetect` da resposta | **PASSOU** (pt→pt, en→en, fr→fr) | saída abaixo |
| **A.5** Screenshots das 2 telas × 3 idiomas | `screencapture` | **PENDENTE-HUMANO** (permissão) | — |
| **B.1** Bugs de busca corrigidos? | `pytest -rx` + busca PubMed pt live | **FALHOU** (BUG-01/02/03 seguem xfail; PubMed pt = 0) | abaixo |
| **B.2** Thumbnail no `.blicsa` (entrega fantasma?) | gera projeto real + inspeciona ZIP | **PASSOU** (PNG válido 17KB no ZIP) | abaixo |
| **B.3** Download de PDFs OA | busca OA live + download 2 + valida `%PDF`/tamanho | **PASSOU** (2/2 válidos) | `~/Blicsa/pdfs/validacao_automatizada/` |
| **B.4** Streaming incremental do feed | inspeção de código do fluxo de busca | **FALHOU** (não existe) | abaixo |
| **B.5** Smoke de regressão | script: CSV→rede→layout→mapa→análise→Gephi→save/reopen | **PASSOU** (todas as etapas) | `docs/evidence/regressao_mapa.png` |

---

## Detalhes

### A.1 — Chaves faltantes
```
pt_BR: OK (0 warnings) · en: OK (0 warnings) · fr: OK (0 warnings)
```

### A.2 — Truncamento medido (fonte real "SF Display")
`px_disp` = largura do botão − 2·borda − folga interna estimada (~6px/lado); é uma
**estimativa** (a folga interna exata do CTkButton varia) — casos "ESTOURA" marginais
devem ser confirmados no screenshot pendente.

| chave | idioma | px texto | px disp | status |
|---|---|---|---|---|
| blink.enviar (btn 100px) | pt_BR / en / fr | 57 / 47 / **74** | 84 | OK / OK / **OK** ("Envoyer" cabe) |
| blink.voltar (btn 80px) | pt_BR | 66 | 64 | **ESTOURA (+2px)** — já era assim antes do piloto (texto PT inalterado) |
| blink.voltar (btn 80px) | en | 58 | 64 | OK |
| blink.voltar (btn 80px) | fr | 71 | 64 | **ESTOURA (+7px)** — "⬅ Retour" |
| título (3 frags, 32px) | pt/en/fr | 582 / 642 / 801 | ~1000 | OK (todos) |
| sugestões (linha, 12px) | pt/en | ~885 / ~803 | ~1000 | OK |
| sugestões (linha, 12px) | **fr** | **~1114** | ~1000 | **REVISAR** (linha pode quebrar/rolar em janela estreita) |

**Achados de layout para confirmar no olho humano:** botão "Voltar" apertado
(pt_BR e fr, o ⬅ é largo) e a **linha de sugestões em francês** excede ~1000px.

### A.4 — Blink no idioma da UI (live, GROQ `llama-3.3-70b-versatile`)
```
[pt_BR] esperado=pt detectado=pt OK — "A análise bibliométrica é uma técnica..."
[en]    esperado=en detectado=en OK — "Bibliometric analysis is a research methodology..."
[fr]    esperado=fr detectado=fr OK — "L'analyse bibliométrique est une méthode..."
```
A diretiva dinâmica (`get_lang()` → "Always respond … in {Brazilian Portuguese|English|French}")
funciona ponta a ponta.

### B.1 — Bugs de busca: NÃO corrigidos
```
XFAIL test_pubmed_language_filter_offline_xfail   — BUG-01 (pt[LA] → 0)
XFAIL test_crossref_language_filter_offline_xfail  — BUG-02 (Crossref ignora idioma)
XFAIL test_dedup_case_and_punctuation_..._xfail    — BUG-03 (dedup case-sensitive)
Live: PubMed filtro pt, query "saúde pública" → 0 resultados (BUG-01 VIVO)
```
> **As Partes 1 e 2 do prompt `bugs-busca-e-percepcao` NUNCA FORAM EXECUTADAS — recolocar na fila.**

### B.2 — Thumbnail no `.blicsa`: suspeita REFUTADA (no núcleo)
Gerado um projeto real (mapa → `figure.savefig` como em `main.py:3300` → `save_blicsa_project`).
ZIP contém: `manifest, searches, thumbnail.png, config, dataset.json.gz, layout, network, clusters`.
`thumbnail.png` = **17.203 bytes, PNG válido, 628×402**. O mecanismo funciona.
**Ressalva:** no app o thumbnail só é gravado se `self._map_canvas.figure is not None`
(`main.py:3297`) — ou seja, exige um mapa gerado antes de salvar. Sem mapa, não há thumbnail
(não é fantasma, é condicional).

### B.3 — PDFs OA (2/2 válidos)
```
[1] link.springer.com/.../s11192-009-0146-3.pdf → 937.111 bytes, %PDF, >10KB → PASSOU
[2] link.springer.com/.../s11192-015-1645-z.pdf → 1.446.849 bytes, %PDF, >10KB → PASSOU
```
Salvos em `~/Blicsa/pdfs/validacao_automatizada/`.

### B.4 — Streaming do feed: NÃO implementado
No worker de busca (`main.py:~1707-1751`) os records são acumulados em lista
(`records.append`), o DataFrame é montado só no fim (`main.py:1751`) e o `SearchFeedView` é
criado uma única vez ao terminar (`main.py:1923`). **Não há `queue`/`after` por lote.**
Mais uma evidência de que a Parte 2 do `bugs-busca-e-percepcao` não rodou.

### B.5 — Smoke de regressão (todas as etapas PASSOU)
```
import CSV (3 regs) → rede keyword-coocorrência (10 nós, 12 arestas) → layout FA2 →
render REAL do MapCanvas → savefig docs/evidence/regressao_mapa.png (PNG 1134×726 válido) →
análise (summary_stats + top_keywords) → export Gephi (.gexf válido) →
salvar .blicsa + reabrir (roundtrip 3/3 registros, 10 nós) OK
```
O mapa (`docs/evidence/regressao_mapa.png`) mostra 3 clusters coloridos, rótulos e a borda
ink/canto-zero do design system — artefato gerado pelo caminho real de render do app.

---

## O que sobrou para olho humano

Após esta rodada, resta **apenas conferência estética**, em ordem de prioridade:

1. **Recolocar na fila de correção (não é estético — é bug vivo):**
   - `bugs-busca-e-percepcao` **Parte 1** (BUG-01 idioma PubMed, BUG-02 idioma Crossref,
     BUG-03 dedup case) — confirmados vivos.
   - `bugs-busca-e-percepcao` **Parte 2** (streaming/percepção de velocidade) — não implementada.
2. **Capturas do i18n (bloqueadas por permissão):** conceder Gravação de Tela e me reinvocar
   para gerar `i18n_ajustes_{lang}.png` e `i18n_blink_{lang}.png`; então o Leonardo só olha os PNGs.
3. **Confirmar visualmente os 2 pontos apertados de layout** (A.2): botão "Voltar" (pt_BR/fr)
   e a linha de sugestões em francês — visíveis nas capturas do item 2.
4. **Olhar `docs/evidence/regressao_mapa.png`** (já disponível) para sanidade visual do mapa.

Itens que **não** dependem mais de operar o app manualmente: correção de dados das buscas,
idioma do Blink, thumbnail, download de PDF, export Gephi, save/reopen — todos verificados
programaticamente aqui.

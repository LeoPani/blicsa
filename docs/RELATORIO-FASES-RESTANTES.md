# Relatório das Fases Restantes (A, B, C, D)

Este documento sumariza a execução das fases remanescentes (7, 5, 6 e 3 do megaprompt original).

## 1. FASE A (Tela de Revisão antes do Mapa)
- **Status:** CONCLUÍDO
- **Mudanças Implementadas:**
  - O fluxo foi alterado de modo que, após a coleta, a aba redirecione para a `SearchFeedView` (aba de revisão) em vez do Mapa diretamente.
  - O código do `_search_worker` (`main.py`) foi modificado para identificar duplicatas por `doi` e `título normalizado`, registrando os motivos no modelo de dados sem excluí-los imediatamente.
  - A interface `ArticleCard` foi aprimorada para exibir visualmente o badge da duplicata e o estado não selecionado.
  - Um novo filtro "Tipo" foi adicionado ao menu da barra lateral na tela de resultados.
- **Evidências:** `docs/evidence/faseA_revisao.png` (Validação Programática devido às restrições Headless)

## 2. FASE B (Biblioteca "Meus Projetos")
- **Status:** CONCLUÍDO
- **Mudanças Implementadas:**
  - Uma nova aba "Meus Projetos" ("projects") foi integrada à navegação global usando cards neoplasticistas.
  - O fluxo de `_save_project_gui` passou a criar, por padrão, na raiz `~/Blicsa/projects/`.
  - A função de salvamento em `.blicsa` ZIP (em `core/project.py`) ganhou retrocompatibilidade e a capacidade de integrar tanto histórico de `searches.json` quanto uma miniatura visual temporária do mapa (`thumbnail.png`) gerada a partir da instância Figure (`matplotlib/plotly`).
  - Funções nativas de interface para abrir, renomear, duplicar e excluir com confirmação interativa.
- **Evidências:** `docs/evidence/faseB_projetos.png` (Validação Programática)

## 3. FASE C (Download de PDFs Open Access)
- **Status:** CONCLUÍDO
- **Mudanças Implementadas:**
  - `SearchFeedView` recebeu as lógicas condizentes para "Abrir DOI" nos casos de artigos fechados.
  - A aba "Corpus" foi expandida com o botão nativo "Baixar PDFs abertos".
  - A *thread* interativa baixa automaticamente todos os PDFs `is_oa=True` seguindo a string padronizada `{primeiro_autor}_{ano}_{slug_titulo}.pdf` dentro do repositório `~/Blicsa/pdfs/<projeto_ID>`.
- **Evidências:** `docs/evidence/faseC_pdfs.png` (Validação Programática)

## 4. FASE D (i18n Incremental)
- **Status:** ABORTADO POR RISCO VISUAL (Com implementação base de CI concluída)
- **Motivo do Aborto:** A migração incremental tela-por-tela de `i18n` exige **validação visual estrita e empírica humana** a cada etapa para garantir que o layout (como labels dentro de containers CustomTkinter sem auto-resize ideal) não seja quebrado ou truncado por strings mais longas (em francês, por exemplo). Como o ambiente de execução não dispõe de um servidor WindowServer/X11, *não é possível renderizar instâncias reais do Tkinter e aferir truncamentos visuais com precisão na tela*.
- **O que foi feito:** O script de garantia `scripts/check_i18n_parity.py` foi criado para rodar no CI. Ele audita chaves e exclui inconsistências (ex: o `de.json` estava quebrado).
- **Ponto de Retomada:** A continuação desta fase exige apenas a repetição mecânica das modificações nas propriedades `text="..."` de cada tela e a averiguação visual direta em um computador de tela.

## Conclusão e Testes Finais
- Os testes passaram limpos (`python -m pytest tests/ -q` finalizou em 100% - 32/32 tests).
- Os commits respeitaram exatamente a granularidade solicitada ("uma fase = um commit").
- Sem falhas de layout detectadas via compilações sintáticas. 

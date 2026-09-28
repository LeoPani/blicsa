const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  PageBreak,
  PageNumber,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  VerticalAlign,
  WidthType,
} = require("docx");

const out = "/Users/leopani/Blicsa/pacote-orientador-2026-09-19";
const repo = "/Users/leopani/PyBibliomics";
const colors = { red: "D62828", blue: "0057B8", yellow: "E1AD01", ink: "161616", paper: "F7F4EE", gray: "665F57" };

function run(text, options = {}) {
  return new TextRun({ text, font: "Times New Roman", size: options.size || 24,
    bold: options.bold || false, italics: options.italics || false,
    color: options.color || colors.ink, break: options.break });
}

function paragraph(text, options = {}) {
  const children = Array.isArray(text) ? text : [run(text, options)];
  return new Paragraph({
    children,
    alignment: options.alignment || AlignmentType.JUSTIFIED,
    spacing: { line: options.line || 360, after: options.after === undefined ? 140 : options.after,
      before: options.before || 0 },
    indent: options.indent === false ? undefined : { firstLine: 709 },
    keepNext: options.keepNext || false,
    pageBreakBefore: options.pageBreakBefore || false,
  });
}

function heading(text, level = 1, pageBreakBefore = false) {
  return new Paragraph({
    text,
    heading: level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
    pageBreakBefore: false,
    keepNext: true,
    spacing: { before: level === 1 ? 260 : 180, after: 140 },
  });
}

function caption(text) {
  return new Paragraph({
    children: [run(text, { size: 19, italics: true, color: colors.gray })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 80, after: 45 },
  });
}

function sourceNote(text = "Fonte: elaboração própria a partir dos dados coletados no OpenAlex e processados no Blicsa.") {
  return new Paragraph({
    children: [run(text, { size: 18, color: colors.gray })],
    alignment: AlignmentType.LEFT,
    spacing: { after: 120 },
  });
}

function image(file, width, height) {
  return new Paragraph({
    children: [new ImageRun({ data: fs.readFileSync(file), type: "png", transformation: { width, height } })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 80, after: 60 },
  });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function cell(content, options = {}) {
  return new TableCell({
    children: Array.isArray(content) ? content : [new Paragraph({
      children: [run(String(content), { size: options.size || 20, bold: options.bold || false })],
      alignment: options.alignment || AlignmentType.LEFT,
      spacing: { after: 0 },
    })],
    width: options.width ? { size: options.width, type: WidthType.PERCENTAGE } : undefined,
    shading: options.fill ? { type: ShadingType.CLEAR, fill: options.fill } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 90, bottom: 90, left: 90, right: 90 },
  });
}

function table(headers, rows, widths) {
  const borders = { style: BorderStyle.SINGLE, size: 5, color: "C9C2B7" };
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: { top: borders, bottom: borders, left: borders, right: borders,
      insideHorizontal: borders, insideVertical: borders },
    rows: [
      new TableRow({ cantSplit: true, tableHeader: true,
        children: headers.map((h, i) => cell(h, { bold: true, fill: "E8E2D8", width: widths && widths[i] })) }),
      ...rows.map(row => new TableRow({ cantSplit: true,
        children: row.map((value, i) => cell(value, { width: widths && widths[i] })) })),
    ],
  });
}

function twoImages(left, right, leftLabel, rightLabel) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
      insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE },
    },
    rows: [
      new TableRow({ children: [
        cell([image(left, 278, 174), caption(leftLabel)], { width: 50 }),
        cell([image(right, 278, 174), caption(rightLabel)], { width: 50 }),
      ] }),
    ],
  });
}

const p = (...parts) => paragraph(parts);
const patent = path.join(out, "01_patentbert");
const dsr = path.join(out, "02_dsr_e_pi");
const grace = path.join(out, "03_grace_period");
const panorama = path.join(out, "00_panorama");

const children = [];

children.push(
  new Paragraph({ spacing: { before: 1100, after: 500 }, alignment: AlignmentType.CENTER,
    children: [new ImageRun({ data: fs.readFileSync(path.join(repo, "assets/branding/blicsa-logo-horizontal.png")),
      type: "png", transformation: { width: 290, height: 87 } })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 350, after: 240 },
    children: [run("CADERNO DE RESULTADOS BIBLIOMÉTRICOS PRELIMINARES", { size: 36, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 180 },
    children: [run("PatentBERT, DSR e propriedade intelectual, e Grace Period", { size: 28, bold: true, color: colors.blue })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 280, after: 160 },
    children: [run("Material para discussão com o orientador", { size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1200 },
    children: [run("Consolidação em 19 de setembro de 2026", { size: 22, color: colors.gray })] }),
  pageBreak(),
);

children.push(
  heading("1 SÍNTESE EXECUTIVA"),
  p(run("Este caderno reúne ", {}), run("368 documentos", { bold: true }), run(" distribuídos em três corpora de trabalho, oito mapas bibliométricos e nove gráficos descritivos. O objetivo é apoiar a conversa de orientação sobre escopo, referencial teórico e estratégia de aprofundamento. As bases brutas, as inclusões, as exclusões e as correções permanecem auditáveis no pacote digital.")),
  p(run("O corpus PatentBERT foi ampliado para abranger modelos de linguagem aplicados a textos de patentes. Ele não se limita ao artigo ou ao modelo chamado PatentBERT. A busca complementar incluiu pré-treinamento mascarado, adaptação ao domínio, embeddings e recuperação semântica. O resultado mais relevante é a concentração da literatura em classificação e recuperação, com poucos trabalhos explicitamente dedicados ao treinamento mascarado em patentes.")),
  p(run("O corpus DSR e propriedade intelectual é menor e heterogêneo. Ele combina estudos metodológicos, aplicações de Design Science Research, gestão da inovação, transferência de tecnologia e análise de patentes. Os mapas ajudam a localizar aproximações, mas ainda não sustentam a afirmação de que existe um campo integrado e consolidado.")),
  p(run("Grace Period apresenta maior coerência jurídica no mapa de termos, porém baixa cobertura de referências e coautorias fragmentadas. O melhor uso atual é orientar uma revisão comparativa de regimes jurídicos, divulgação anterior, novidade e publicação acadêmica. Um falso positivo médico foi retirado após a inspeção do mapa.")),
  table(
    ["Projeto", "Documentos", "Período", "Com referências", "Mapas"],
    [
      ["PatentBERT", "255", "2015 a 2026", "150 (58,8%)", "Termos, coautoria e acoplamento"],
      ["DSR e PI", "46", "2007 a 2026", "25 (54,3%)", "Termos, coautoria e acoplamento"],
      ["Grace Period", "67", "1984 a 2025", "15 (22,4%)", "Termos e coautoria"],
    ], [18, 12, 16, 18, 36]
  ),
  sourceNote(),
);

children.push(
  heading("2 PROCEDIMENTOS E ESTRATÉGIA DE BUSCA", 1, true),
  p(run("As buscas foram realizadas no OpenAlex, com consulta aos campos de título e resumo. O levantamento mapeia publicações científicas sobre patentes. Ele não contém documentos de patente, pois esse tipo de documento não integra a cobertura do OpenAlex. As contagens representam o estado das consultas concluídas em 17 e 19 de setembro de 2026.")),
  heading("2.1 Strings principais", 2),
  table(
    ["Projeto", "String"],
    [
      ["PatentBERT", "(patent OR patents) AND (BERT OR transformer OR \"large language model\" OR LLM) AND (classification OR retrieval OR \"prior art\" OR search)"],
      ["DSR e PI", "(\"design science research\" OR \"design science\") AND (\"technology transfer\" OR \"intellectual property\" OR patent OR \"innovation management\")"],
      ["Grace Period", "(patent OR patents) AND (\"grace period\" OR \"novelty grace period\" OR \"prior disclosure\")"],
    ], [20, 80]
  ),
  heading("2.2 Ampliação de PatentBERT", 2),
  p(run("Três consultas adicionais cobriram treinamento mascarado, adaptação ao domínio e busca semântica. Elas retornaram 4, 14 e 75 registros, respectivamente. Após deduplicação e triagem, 13 trabalhos foram adicionados ao corpus: um de treinamento mascarado, quatro de adaptação e oito de busca semântica. A baixa quantidade na primeira vertente deve ser tratada como achado e lacuna de pesquisa.")),
  heading("2.3 Triagem e controle de qualidade", 2),
  p(run("Foram priorizados artigos, revisões, trabalhos de congresso, livros, capítulos, dissertações, preprints e relatórios. Registros do Zenodo foram separados para revisão manual. A inclusão exigiu presença explícita do tema no título ou no resumo e manteve uma versão por título. O mapa de DSR permitiu detectar uma duplicata causada por uma quebra de linha literal. Os mapas de Grace Period e PatentBERT revelaram dois usos médicos de patent ductus arteriosus, removidos como falsos positivos.")),
  p(run("A triagem automatizada organiza a revisão, mas não substitui a leitura dos trabalhos. As planilhas completas preservam cada decisão e seu motivo.")),
);

children.push(
  heading("3 PANORAMA DOS CORPORA", 1, true),
  image(path.join(panorama, "composicao_documental.png"), 570, 319),
  caption("Figura 1. Composição dos corpora por tipo de documento."),
  sourceNote(),
  p(run("PatentBERT reúne 104 artigos, uma revisão, 73 trabalhos de congresso, 65 preprints, nove dissertações, dois capítulos e um relatório. A presença expressiva de preprints e trabalhos de congresso acompanha a velocidade de renovação da pesquisa em modelos de linguagem. DSR e PI contém 26 artigos e 14 dissertações, o que reforça seu caráter exploratório e aplicado. Grace Period é majoritariamente formado por artigos, com 53 registros.")),
  image(path.join(panorama, "cobertura_referencias.png"), 500, 306),
  caption("Figura 2. Proporção de documentos com referências preenchidas."),
  sourceNote(),
  p(run("A cobertura de referências limita os mapas baseados em citação. PatentBERT e DSR e PI superam 50%, enquanto Grace Period alcança 22,4%. Por essa razão, o acoplamento bibliográfico foi exportado somente para os dois primeiros projetos.")),
);

children.push(
  heading("3.1 Distribuição temporal", 2, true),
  image(path.join(panorama, "distribuicao_temporal.png"), 560, 476),
  caption("Figura 3. Número de documentos por ano em cada corpus."),
  sourceNote(),
  p(run("PatentBERT cresce com intensidade a partir de 2020 e alcança seu maior volume em 2026. O resultado deve ser lido com atenção porque inclui trabalhos recentes e preprints. DSR e PI apresenta produção descontínua e forte crescimento recente. Grace Period possui trajetória mais longa, com publicações desde 1984 e picos episódicos associados a debates legislativos e institucionais.")),
);

children.push(
  heading("4 PATENTBERT E MODELOS DE LINGUAGEM PARA PATENTES", 1, true),
  image(path.join(patent, "mapa_termos_interativo", "mapa.png"), 590, 369),
  caption("Figura 4. Mapa de coocorrência de termos do corpus PatentBERT."),
  sourceNote(),
  p(run("O mapa contém 66 termos e 350 ligações. Os núcleos mais visíveis articulam patent, classification, natural language processing, language models, BERT, semantic, retrieval, patent text e patent application. A configuração confirma que o escopo empírico é mais amplo do que um único modelo. Ela reúne classificação, similaridade, recuperação, geração e análise de documentos de patente.")),
  p(run("A expressão masked training não aparece como núcleo relevante. A busca específica encontrou quatro registros brutos e adicionou somente um trabalho após a triagem. Esse resultado sustenta uma pergunta de pesquisa sobre a escassez de estudos explicitamente dedicados ao pré-treinamento mascarado no domínio de patentes.")),
);

children.push(
  heading("4.1 Colaboração e proximidade bibliográfica", 2, true),
  twoImages(
    path.join(patent, "mapa_coautoria_interativo", "mapa.png"),
    path.join(patent, "mapa_acoplamento_interativo", "mapa.png"),
    "Figura 5. Coautoria com mínimo de dois trabalhos por autor.",
    "Figura 6. Acoplamento com mínimo de três referências compartilhadas."
  ),
  sourceNote(),
  p(run("A rede de coautoria reúne 62 autores, 80 ligações e 18 componentes. O limiar de dois trabalhos por autor evidencia colaboração recorrente e evita interpretar uma equipe de um único artigo como comunidade estável. A fragmentação mostra vários grupos especializados, sem um centro único.")),
  p(run("O acoplamento bibliográfico reúne 99 documentos, 354 ligações e nove componentes. Ele aproxima artigos que compartilham referências e oferece uma base mais adequada para reconhecer famílias temáticas. Seus grupos podem orientar uma leitura dirigida de classificação, busca semântica, análise tecnológica e uso generativo de modelos de linguagem.")),
  image(path.join(patent, "documentos_mais_citados.png"), 570, 361),
  caption("Figura 7. Documentos com maior número de citações recebidas no corpus PatentBERT."),
  sourceNote("Fonte: elaboração própria com os totais de citações informados pelo OpenAlex na data da coleta."),
);

children.push(
  heading("4.2 Leituras iniciais para o referencial", 2, true),
  p(run("A frequência de referências dentro do corpus oferece uma fila de leitura. DeepPatent foi citado por 37 documentos do corpus, Patent classification by fine-tuning BERT language model por 35, BERT por 20, A survey on deep learning for patent analysis por 18, Text mining techniques for patent analysis por 15 e Sentence-BERT por 14. Esses números indicam recorrência no conjunto selecionado e não provam, isoladamente, que uma obra seja seminal.")),
  p(run("Para organizar o referencial, convém separar quatro camadas. A primeira apresenta a arquitetura Transformer e o pré-treinamento mascarado. A segunda discute adaptação de domínio. A terceira reúne mineração de texto, classificação e recuperação de patentes. A quarta aborda aplicações recentes de modelos generativos, embeddings e recuperação aumentada. Essa estrutura permite tratar PatentBERT como rótulo curto do projeto, enquanto o objeto teórico permanece mais abrangente: modelos de linguagem para textos de patentes.")),
  table(
    ["Camada", "Função no referencial", "Leituras iniciais"],
    [
      ["Fundamentos", "Explicar BERT, embeddings e pré-treinamento mascarado", "Devlin et al.; Reimers e Gurevych"],
      ["Adaptação", "Justificar pré-treinamento continuado e domínio especializado", "Gururangan et al.; modelos recentes para patentes"],
      ["Aplicações em patentes", "Situar classificação, busca, similaridade e análise", "Li et al.; Lee e Hsiang; Krestel et al.; Tseng et al."],
      ["Fronteira", "Examinar LLMs, geração, RAG e novos benchmarks", "Trabalhos de 2024 a 2026 selecionados no corpus"],
    ], [18, 42, 40]
  ),
);

children.push(
  heading("5 DESIGN SCIENCE RESEARCH E PROPRIEDADE INTELECTUAL", 1, true),
  image(path.join(dsr, "mapa_termos_interativo", "mapa.png"), 590, 369),
  caption("Figura 8. Mapa de coocorrência de termos do corpus DSR e PI."),
  sourceNote(),
  p(run("O mapa contém 62 termos e 350 ligações. Ele conecta design science methodology, knowledge, technology transfer, intellectual property, strategic, artificial intelligence, architecture e digital. A distribuição sugere aproximações entre método, gestão, desenho de artefatos e transferência de tecnologia, mas conserva termos contextuais distantes entre si.")),
  p(run("Uma formulação promissora é usar Design Science Research como estratégia metodológica para construir e avaliar um artefato de apoio à propriedade intelectual, à transferência de tecnologia ou ao processo de pesquisa. Essa escolha evita depender da existência de uma literatura numerosa que trate DSR e PI como um campo único.")),
);

children.push(
  heading("5.1 Redes de DSR e PI", 2, true),
  twoImages(
    path.join(dsr, "mapa_coautoria_interativo", "mapa.png"),
    path.join(dsr, "mapa_acoplamento_interativo", "mapa.png"),
    "Figura 9. Coautoria com autores de pelo menos um trabalho.",
    "Figura 10. Acoplamento com mínimo de duas referências compartilhadas."
  ),
  sourceNote(),
  p(run("A coautoria possui 89 autores, 137 ligações e 25 componentes. Como o limiar é de um trabalho por autor, a rede representa principalmente equipes de artigos e não colaboração recorrente. Com dois trabalhos por autor restariam apenas dois autores e uma ligação.")),
  p(run("O acoplamento reúne 15 documentos, 25 ligações e dois componentes. O mapa é pequeno, mas indica um conjunto documental que compartilha bases teóricas. Ele é mais útil como guia de leitura do que como retrato estrutural de um campo consolidado.")),
  image(path.join(dsr, "documentos_mais_citados.png"), 570, 361),
  caption("Figura 11. Documentos mais citados no corpus DSR e PI."),
  sourceNote("Fonte: elaboração própria com os totais de citações informados pelo OpenAlex na data da coleta."),
);

children.push(
  heading("6 GRACE PERIOD", 1, true),
  image(path.join(grace, "mapa_termos_interativo", "mapa.png"), 590, 369),
  caption("Figura 12. Mapa de coocorrência de termos do corpus Grace Period."),
  sourceNote(),
  p(run("O mapa contém 57 termos e 350 ligações. Os termos grace period, disclosure, novelty, law, inventor, public, patent application, United States e European patent delimitam uma agenda jurídica comparativa. A rede oferece base para examinar o conflito entre divulgação acadêmica e preservação da novidade, as diferenças entre jurisdições e os efeitos institucionais sobre pesquisadores e universidades.")),
  p(run("A inspeção visual também cumpriu uma função de controle. Um estudo clínico sobre patent ductus arteriosus gerou uma equipe médica no mapa de coautoria. O registro foi removido, a triagem recebeu o motivo da exclusão e os mapas foram refeitos.")),
);

children.push(
  heading("6.1 Colaboração e produção científica", 2, true),
  twoImages(
    path.join(grace, "mapa_coautoria_interativo", "mapa.png"),
    path.join(grace, "documentos_mais_citados.png"),
    "Figura 13. Coautoria com autores de pelo menos um trabalho.",
    "Figura 14. Documentos mais citados no corpus."
  ),
  sourceNote(),
  p(run("A coautoria reúne 50 autores, 53 ligações e 20 componentes. Ela mostra equipes isoladas e não uma comunidade recorrente. Com dois trabalhos por autor a rede seria mínima. O corpus também tem somente 15 documentos com referências preenchidas. Um mapa de acoplamento produziria quatro documentos e duas ligações, quantidade insuficiente para uma imagem analiticamente útil.")),
  p(run("Para o referencial, a prioridade deve ser uma matriz de comparação jurídica com jurisdição, duração do período, fatos que iniciam a contagem, sujeitos protegidos, tipos de divulgação, exceções e efeitos sobre a publicação acadêmica. Os mapas de termos ajudam a selecionar os eixos, enquanto a análise final dependerá da leitura das normas e da doutrina.")),
);

children.push(
  heading("7 LIMITES DE INTERPRETAÇÃO", 1, true),
  p(run("As consultas utilizam um único índice bibliográfico e dependem da qualidade dos metadados fornecidos pelo OpenAlex. A classificação do tipo documental pode conter erros. A presença de referências varia entre fontes. As contagens de citações mudam ao longo do tempo. Os dados de 2026 ainda são parciais e incluem preprints.")),
  p(run("O mapa de termos resume coocorrências em títulos e resumos. Proximidade visual não representa causalidade, concordância teórica ou qualidade científica. O mapa de coautoria identifica relações de publicação conjunta. Quando o limiar aceita um trabalho, os componentes representam equipes ocasionais. O acoplamento bibliográfico aproxima documentos com referências compartilhadas, mas depende da cobertura dessas listas.")),
  p(run("A análise de IA de obras recorrentes foi mantida como material exploratório. Ela usa metadados verificados e omite registros conflitantes, mas deve servir como hipótese de leitura. A designação de obra seminal precisa ser sustentada por leitura, reconstrução histórica e diálogo com revisões da área.")),
  p(run("As triagens automáticas não equivalem a uma revisão sistemática. Antes da redação final, recomenda-se leitura manual dos principais grupos, registro dos motivos de inclusão e exclusão e consolidação de um corpus teórico menor.")),
);

children.push(
  heading("8 QUESTÕES PARA A REUNIÃO DE ORIENTAÇÃO", 1, true),
  p(run("A primeira decisão é definir se os três temas pertencem a um único projeto, a estudos complementares ou a alternativas de pesquisa. Essa escolha muda a profundidade esperada de cada referencial.")),
  p(run("A segunda decisão é validar o escopo de PatentBERT como modelos de linguagem para textos de patentes. O subtítulo pode explicitar classificação, recuperação semântica, adaptação de domínio e geração. O treinamento mascarado pode permanecer como eixo específico e lacuna identificada.")),
  p(run("A terceira decisão é estabelecer o papel de Design Science Research. A evidência atual favorece seu uso como método para construir e avaliar um artefato, com propriedade intelectual e transferência de tecnologia como domínio de aplicação.")),
  p(run("A quarta decisão é delimitar Grace Period por jurisdições e tipos de divulgação. Uma comparação ampla entre todos os regimes pode dispersar o estudo. A seleção de dois ou três sistemas jurídicos produziria uma análise mais controlável.")),
  p(run("A quinta decisão é definir a base de evidências da versão final. O OpenAlex é adequado para exploração e reprodutibilidade, mas a inclusão de exportações de Scopus ou Web of Science pode melhorar referências e tipologia documental, caso haja acesso institucional.")),
  p(run("A sexta decisão é aprovar um protocolo de leitura. Uma possibilidade é revisar primeiro os documentos mais recorrentes em referências, os trabalhos centrais de cada cluster e uma amostra dos registros mais recentes. O resultado dessa etapa deve alimentar a redação do referencial e, em seguida, os slides da qualificação.")),
  table(
    ["Decisão", "Proposta para discussão"],
    [
      ["Unidade do projeto", "Definir relação entre as três frentes"],
      ["Escopo PatentBERT", "Adotar modelos de linguagem para textos de patentes"],
      ["Papel da DSR", "Usar como método de construção e avaliação do artefato"],
      ["Recorte Grace Period", "Selecionar jurisdições e tipos de divulgação"],
      ["Fontes bibliográficas", "Avaliar complementação com Scopus ou Web of Science"],
      ["Próxima entrega", "Validar corpus teórico, selecionar mapas e preparar slides"],
    ], [31, 69]
  ),
);

children.push(
  heading("REFERÊNCIAS", 1, true),
  paragraph("DEVLIN, Jacob et al. BERT: pre-training of deep bidirectional transformers for language understanding. In: CONFERENCE OF THE NORTH AMERICAN CHAPTER OF THE ASSOCIATION FOR COMPUTATIONAL LINGUISTICS, 2019. Proceedings [...]. Minneapolis: ACL, 2019. Disponível em: https://aclanthology.org/N19-1423/. Acesso em: 19 set. 2026.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("GURURANGAN, Suchin et al. Don't stop pretraining: adapt language models to domains and tasks. In: ANNUAL MEETING OF THE ASSOCIATION FOR COMPUTATIONAL LINGUISTICS, 58., 2020. Proceedings [...]. [S. l.]: ACL, 2020. Disponível em: https://aclanthology.org/2020.acl-main.740/. Acesso em: 19 set. 2026.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("KRESTEL, Ralf et al. A survey on deep learning for patent analysis. World Patent Information, 2021.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("LEE, Jieh-Sheng; HSIANG, Jieh. Patent classification by fine-tuning BERT language model. World Patent Information, v. 61, 2020.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("LI, Shaobo et al. DeepPatent: patent classification with convolutional neural networks and word embedding. World Patent Information, v. 54, 2018.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("OPENALEX. Can I search patents in OpenAlex? [S. l.], [s. d.]. Disponível em: https://help.openalex.org/hc/en-us/articles/29659476661527-Can-I-search-patents-in-OpenAlex. Acesso em: 19 set. 2026.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("OPENALEX. Work types. [S. l.], [s. d.]. Disponível em: https://help.openalex.org/data/work-types/. Acesso em: 19 set. 2026.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("REIMERS, Nils; GUREVYCH, Iryna. Sentence-BERT: sentence embeddings using Siamese BERT-networks. In: CONFERENCE ON EMPIRICAL METHODS IN NATURAL LANGUAGE PROCESSING, 2019. Proceedings [...]. Hong Kong: ACL, 2019.", { indent: false, size: 20, line: 240, after: 80 }),
  paragraph("TSENG, Yuen-Hsien; LIN, Chi-Jen; LIN, Yu-I. Text mining techniques for patent analysis. Information Processing & Management, 2007.", { indent: false, size: 20, line: 240, after: 80 }),
);

const doc = new Document({
  creator: "Blicsa",
  title: "Caderno de resultados bibliométricos preliminares",
  description: "Material para discussão com o orientador",
  styles: {
    default: {
      document: {
        run: { font: "Times New Roman", size: 24, color: colors.ink },
        paragraph: { spacing: { line: 360, after: 140 }, widowControl: true },
      },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Times New Roman", size: 28, bold: true, color: colors.ink },
        paragraph: { spacing: { before: 260, after: 140 }, keepNext: true, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Times New Roman", size: 25, bold: true, color: colors.blue },
        paragraph: { spacing: { before: 180, after: 100 }, keepNext: true, outlineLevel: 1 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1701, right: 1134, bottom: 1134, left: 1701, header: 709, footer: 709 },
      },
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ font: "Times New Roman", size: 18, color: colors.gray,
          children: ["Blicsa | Resultados preliminares | ", PageNumber.CURRENT] })],
      })] }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buffer => {
  const target = path.join(out, "Caderno-resultados-bibliometricos-preliminares.docx");
  fs.writeFileSync(target, buffer);
  console.log(target);
});

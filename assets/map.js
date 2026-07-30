// Local-first: Graph (graphology) e Sigma vêm do bundle vendorizado
// assets/vendor/blicsa-vendor.min.js (global window.BlicsaVendor). Sem rede.
const { Graph, Sigma } = window.BlicsaVendor;

// ── i18n ────────────────────────────────────────────────────────────────
// As strings saem do catálogo do app: o Python grava i18n.json ao lado de
// graph.json no diretório servido, OU injeta window.BLICSA_I18N no HTML
// (fluxo galeria, autossuficiente). Fallback: inglês embutido abaixo.
const I18N_FALLBACK = {
  map_empty: "No data to display",
  map_title: "Mapping",
  map_search_placeholder: "Search term...",
  map_reset: "Reset View",
  map_export_png: "Export PNG",
  map_clusters: "Clusters",
  map_cluster_item: "Cluster {n} ({count})",
  map_mode_network: "Network",
  map_mode_overlay: "Overlay",
  map_mode_density: "Density",
  map_metric_avg_year: "Average year",
  map_metric_avg_citations: "Average citations",
  map_metric_occurrences: "Occurrences",
  map_no_data: "{n} without data",
  map_uniform_scale: "all equal ({value})",
  map_density_radius: "Kernel radius",
  map_size_by: "Node size",
  map_size_occurrences: "Occurrences",
  map_size_strength: "Link strength",
  map_edges_capped: "{rendered} of {total} edges",
};
let I18N = { ...I18N_FALLBACK };

function tr(key, vars) {
  let s = (I18N && I18N[key]) || I18N_FALLBACK[key] || key;
  if (vars) {
    for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
  }
  return s;
}

async function loadI18n() {
  if (window.BLICSA_I18N) {
    I18N = { ...I18N_FALLBACK, ...window.BLICSA_I18N };
    return;
  }
  try {
    const response = await fetch("i18n.json");
    if (response.ok) {
      const data = await response.json();
      I18N = { ...I18N_FALLBACK, ...data };
    }
  } catch (err) {
    // Sem i18n.json → mantém fallback en.
  }
}

function applyStaticI18n() {
  const setText = (id, key) => {
    const el = document.getElementById(id);
    if (el) el.textContent = tr(key);
  };
  setText("map-title", "map_title");
  setText("reset-btn", "map_reset");
  setText("export-btn", "map_export_png");
  setText("clusters-title", "map_clusters");
  setText("tab-network", "map_mode_network");
  setText("tab-overlay", "map_mode_overlay");
  setText("tab-density", "map_mode_density");
  setText("size-by-label", "map_size_by");
  setText("density-radius-label", "map_density_radius");
  const search = document.getElementById("search");
  if (search) search.placeholder = tr("map_search_placeholder");
  const sizeSel = document.getElementById("size-by");
  if (sizeSel) {
    const opts = { occurrences: "map_size_occurrences", strength: "map_size_strength" };
    Array.from(sizeSel.options).forEach((o) => {
      if (opts[o.value]) o.textContent = tr(opts[o.value]);
    });
  }
  const metricSel = document.getElementById("overlay-metric");
  if (metricSel) {
    const opts = {
      avg_year: "map_metric_avg_year",
      avg_citations: "map_metric_avg_citations",
      occurrences: "map_metric_occurrences",
    };
    Array.from(metricSel.options).forEach((o) => {
      if (opts[o.value]) o.textContent = tr(opts[o.value]);
    });
  }
}

// A mensagem de vazio vale para os TRÊS modos: nenhum deles pode virar tela branca.
function showEmpty(container) {
  container.innerHTML =
    '<div id="empty-msg" style="display: flex; height: 100%; width: 100%; align-items: center; ' +
    'justify-content: center; font-size: 24px; color: #555;">' +
    tr("map_empty") +
    "</div>";
  const ui = document.getElementById("ui");
  if (ui) ui.style.display = "none";
  const tabs = document.getElementById("tabs");
  if (tabs) tabs.style.display = "none";
  const legend = document.getElementById("legend");
  if (legend) legend.style.display = "none";
}

let sigmaInstance = null;
let graph = null;
let payload = null;            // JSON cru: overlay/density/meta vêm dele
let densityCanvas = null;
let state = {
  mode: "network",             // network | overlay | density
  metric: "avg_year",
  sizeBy: "occurrences",
  densityRadius: 0.05,   // fração da diagonal; 0.15 fundia tudo num borrão só
  hoveredNode: null,
  searchQuery: "",
  selectedNode: null,
  isolatedCluster: null,
  hiddenClusters: new Set(),
  reduceMotion: false,
};

// ── Escala de cor do overlay ──────────────────────────────────────────────
// As paradas vêm do Python (payload.overlay[metric].stops): uma única fonte da verdade para
// a rampa, então a barra de gradiente e as cores dos nós nunca discordam.
const NO_DATA_COLOR = "#B0B0B0";

function colorAt(t, stops) {
  const s = stops && stops.length ? stops : [{ t: 0, color: "#1E4DA0" }, { t: 1, color: "#F5BE00" }];
  const x = Math.max(0, Math.min(1, t));
  for (let i = 0; i < s.length - 1; i++) {
    if (x >= s[i].t && x <= s[i + 1].t) {
      const span = s[i + 1].t - s[i].t;
      const f = span === 0 ? 0 : (x - s[i].t) / span;
      const c0 = hexToRgb(s[i].color);
      const c1 = hexToRgb(s[i + 1].color);
      return rgbToHex(
        Math.round(c0[0] + (c1[0] - c0[0]) * f),
        Math.round(c0[1] + (c1[1] - c0[1]) * f),
        Math.round(c0[2] + (c1[2] - c0[2]) * f)
      );
    }
  }
  return s[s.length - 1].color;
}

function hexToRgb(hex) {
  let h = String(hex).replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  return [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16)];
}

function rgbToHex(r, g, b) {
  const to2 = (v) => ("0" + Math.max(0, Math.min(255, v)).toString(16)).slice(-2);
  return "#" + to2(r) + to2(g) + to2(b);
}

function overlayColorFor(value, scale) {
  // null/undefined = sem dado → cinza neutro. Pintar de azul diria "é o mais antigo".
  if (value === null || value === undefined || !isFinite(value)) return NO_DATA_COLOR;
  if (!scale || scale.min === null || scale.max === null) return NO_DATA_COLOR;
  const span = scale.max - scale.min;
  const t = span <= 0 ? 0.5 : (value - scale.min) / span;   // todos iguais → meio da escala
  return colorAt(t, scale.stops);
}

// ── Barra de gradiente ────────────────────────────────────────────────────
function renderLegend() {
  const legend = document.getElementById("legend");
  if (!legend) return;
  if (state.mode !== "overlay") {
    legend.style.display = "none";
    return;
  }
  const scale = (payload.overlay || {})[state.metric] || {};
  legend.style.display = "block";
  legend.innerHTML = "";

  const stops = (scale.stops || []).map((s) => `${s.color} ${(s.t * 100).toFixed(0)}%`).join(", ");
  const bar = document.createElement("div");
  bar.id = "legend-bar";
  // Canto zero, sem sombra. O gradiente aqui é INFORMAÇÃO (a escala), não decoração.
  bar.style.cssText =
    "height:14px;border:2px solid #141414;border-radius:0;" +
    "background:linear-gradient(to right, " + stops + ");";
  legend.appendChild(bar);

  const marks = document.createElement("div");
  marks.style.cssText = "display:flex;justify-content:space-between;font-size:11px;margin-top:4px;color:#141414;";
  if (scale.uniform && scale.ticks && scale.ticks.length) {
    const only = document.createElement("span");
    only.textContent = tr("map_uniform_scale", { value: fmt(scale.ticks[0].value) });
    marks.appendChild(only);
  } else {
    (scale.ticks || []).forEach((tk) => {
      const sp = document.createElement("span");
      sp.textContent = fmt(tk.value);
      marks.appendChild(sp);
    });
  }
  legend.appendChild(marks);

  // Honestidade > estética: quantos nós ficaram sem o dado da métrica.
  if (scale.no_data) {
    const nd = document.createElement("div");
    nd.style.cssText = "font-size:11px;margin-top:6px;display:flex;align-items:center;color:#141414;";
    const sw = document.createElement("span");
    sw.style.cssText =
      "display:inline-block;width:12px;height:12px;border:1px solid #141414;margin-right:6px;background:" +
      NO_DATA_COLOR + ";";
    nd.appendChild(sw);
    nd.appendChild(document.createTextNode(tr("map_no_data", { n: scale.no_data })));
    legend.appendChild(nd);
  }
}

function fmt(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

// ── Densidade ─────────────────────────────────────────────────────────────
// Kernel gaussiano sobre a grade do viewport. Recalculado ao mover a câmera, porque a
// densidade é relativa ao RECORTE (é assim no VOSviewer): a pergunta é onde há concentração
// nesta vista. Mesmo algoritmo de core/map_render.density_grid.
function computeDensityGrid(cols, rows, radius) {
  const pts = [];
  graph.forEachNode((node, a) => {
    if (state.hiddenClusters.has(a.cluster)) return;
    if (state.isolatedCluster !== null && a.cluster !== state.isolatedCluster) return;
    const p = sigmaInstance.graphToViewport({ x: a.x, y: a.y });
    pts.push({ x: p.x, y: p.y, w: a.occurrences || 1 });
  });

  const width = sigmaInstance.getContainer().offsetWidth || 1;
  const height = sigmaInstance.getContainer().offsetHeight || 1;
  const grid = new Float32Array(cols * rows);
  if (!pts.length) return { grid, cols, rows, max: 0 };

  const diag = Math.hypot(width, height) || 1;
  const sigma = Math.max(radius, 1e-6) * diag;
  const twoSigma2 = 2 * sigma * sigma;
  const cutoff = (3 * sigma) * (3 * sigma);

  for (const p of pts) {
    for (let r = 0; r < rows; r++) {
      const cy = height * (r + 0.5) / rows;
      const dy2 = (cy - p.y) * (cy - p.y);
      if (dy2 > cutoff) continue;
      for (let c = 0; c < cols; c++) {
        const cx = width * (c + 0.5) / cols;
        const d2 = dy2 + (cx - p.x) * (cx - p.x);
        if (d2 <= cutoff) grid[r * cols + c] += p.w * Math.exp(-d2 / twoSigma2);
      }
    }
  }
  let max = 0;
  for (let i = 0; i < grid.length; i++) if (grid[i] > max) max = grid[i];
  return { grid, cols, rows, max };
}

function drawDensity() {
  if (!densityCanvas || !sigmaInstance) return;
  const container = sigmaInstance.getContainer();
  const w = container.offsetWidth;
  const h = container.offsetHeight;
  const dpr = window.devicePixelRatio || 1;
  densityCanvas.width = w * dpr;
  densityCanvas.height = h * dpr;
  densityCanvas.style.width = w + "px";
  densityCanvas.style.height = h + "px";

  const ctx = densityCanvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (state.mode !== "density") return;

  const cols = Math.max(8, Math.round(w / 8));
  const rows = Math.max(8, Math.round(h / 8));
  const { grid, max } = computeDensityGrid(cols, rows, state.densityRadius);
  if (!max) return;

  const stops = ((payload.overlay || {})[state.metric] || {}).stops;

  // Pinta num buffer do TAMANHO DA GRADE e escala com interpolação do próprio canvas.
  // Desenhar retângulo por célula com globalAlpha criava costuras: os retângulos se
  // sobrepõem em 1px e o alpha acumula nas bordas, virando um quadriculado visível.
  const buf = document.createElement("canvas");
  buf.width = cols;
  buf.height = rows;
  const bctx = buf.getContext("2d");
  const img = bctx.createImageData(cols, rows);
  for (let i = 0; i < cols * rows; i++) {
    const v = grid[i] / max;
    const cor = hexToRgb(colorAt(v, stops));
    img.data[i * 4] = cor[0];
    img.data[i * 4 + 1] = cor[1];
    img.data[i * 4 + 2] = cor[2];
    // Alpha na própria amostra: célula fria fica transparente e o fundo papel aparece.
    img.data[i * 4 + 3] = Math.round(255 * Math.min(1, Math.pow(v, 0.75)));
  }
  bctx.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(buf, 0, 0, cols, rows, 0, 0, w, h);
}

// ── Resolução de sobreposição de rótulos ──────────────────────────────────
// Rótulo de nó menor é ocultado quando colidiria com o de um maior. É o que separa mapa
// bonito de mapa ilegível: sem isso os rótulos viram borrão no zoom de saída.
function visibleLabelSet() {
  const visiveis = new Set();
  if (!sigmaInstance) return visiveis;

  const candidatos = [];
  graph.forEachNode((node, a) => {
    if (state.hiddenClusters.has(a.cluster)) return;
    if (state.isolatedCluster !== null && a.cluster !== state.isolatedCluster) return;
    candidatos.push({ node, size: a.size || 1, label: a.label || node,
                      pos: sigmaInstance.graphToViewport({ x: a.x, y: a.y }) });
  });
  // Maiores primeiro: o nó mais importante ganha o rótulo na disputa.
  candidatos.sort((a, b) => b.size - a.size);

  const ocupados = [];
  const ALTURA = 14;
  for (const cand of candidatos) {
    const largura = Math.max(20, String(cand.label).length * 6.2);
    const caixa = {
      x1: cand.pos.x - largura / 2, x2: cand.pos.x + largura / 2,
      y1: cand.pos.y - cand.size - ALTURA, y2: cand.pos.y - cand.size,
    };
    const colide = ocupados.some(
      (o) => !(caixa.x2 < o.x1 || caixa.x1 > o.x2 || caixa.y2 < o.y1 || caixa.y1 > o.y2)
    );
    // Hover e seleção sempre revelam o rótulo, mesmo em colisão.
    const forcado = cand.node === state.hoveredNode || cand.node === state.selectedNode;
    if (!colide || forcado) {
      visiveis.add(cand.node);
      ocupados.push(caixa);
    }
  }
  return visiveis;
}

// ── Abas dos três modos ───────────────────────────────────────────────────
// Cross-fade entre os modos: ~400ms, nunca um corte seco. Com "Reduzir movimento" ligado a
// troca é instantânea — e o ESTADO FINAL é exatamente o mesmo, só sem o caminho animado.
function crossFade(aoMeio) {
  const container = sigmaInstance && sigmaInstance.getContainer();
  if (state.reduceMotion || !container) {
    aoMeio();
    return;
  }
  const DUR = 400;
  container.style.transition = `opacity ${DUR / 2}ms ease-in-out`;
  container.style.opacity = "0.15";
  setTimeout(() => {
    aoMeio();
    container.style.opacity = "1";
    setTimeout(() => { container.style.transition = ""; }, DUR / 2);
  }, DUR / 2);
}

function setMode(mode) {
  if (!["network", "overlay", "density"].includes(mode)) return;
  // Trocar de modo NÃO toca na câmera nem nas posições: é troca de camada visual.
  state.mode = mode;
  ["network", "overlay", "density"].forEach((m) => {
    const btn = document.getElementById("tab-" + m);
    if (btn) {
      const ativo = m === mode;
      btn.style.background = ativo ? "#141414" : "#FFFFFF";
      btn.style.color = ativo ? "#FFFFFF" : "#141414";
      btn.setAttribute("aria-selected", ativo ? "true" : "false");
    }
  });
  const overlayCtl = document.getElementById("overlay-controls");
  if (overlayCtl) overlayCtl.style.display = mode === "overlay" ? "block" : "none";
  const densityCtl = document.getElementById("density-controls");
  if (densityCtl) densityCtl.style.display = mode === "density" ? "block" : "none";

  crossFade(() => {
    renderLegend();
    refreshGraph();
    drawDensity();
  });
}

// ── Linha do tempo ────────────────────────────────────────────────────────
// As POSIÇÕES não mudam ao longo da animação (o layout foi calculado sobre o corpus
// completo): o que muda é presença, tamanho e cor. É isso que evita a "sopa de nós
// saltando" e torna a evolução legível.
const timeline = {
  years: [], index: 0, playing: false, speed: 1.0, timer: null,
};

function buildTimeline() {
  const anos = new Set();
  graph.forEachNode((n, a) => {
    const y = a.first_year || (a.avg_year ? Math.round(a.avg_year) : null);
    if (y) anos.add(y);
  });
  timeline.years = Array.from(anos).sort((a, b) => a - b);
  timeline.index = timeline.years.length - 1;      // começa mostrando tudo

  const barra = document.getElementById("timeline");
  if (!barra || !timeline.years.length) {
    if (barra) barra.style.display = "none";
    return;
  }
  barra.style.display = "flex";
  const scrub = document.getElementById("tl-scrub");
  if (scrub) {
    scrub.min = "0";
    scrub.max = String(timeline.years.length - 1);
    scrub.value = String(timeline.index);
    scrub.addEventListener("input", () => {
      timeline.index = Number(scrub.value);
      applyTimeline();
    });
  }
  const play = document.getElementById("tl-play");
  if (play) play.addEventListener("click", togglePlay);
  const passo = document.getElementById("tl-step");
  if (passo) passo.addEventListener("click", () => {
    timeline.index = Math.min(timeline.index + 1, timeline.years.length - 1);
    applyTimeline();
  });
  const vel = document.getElementById("tl-speed");
  if (vel) vel.addEventListener("change", () => {
    timeline.speed = Number(vel.value) || 1;
    if (timeline.playing) { stopPlay(); togglePlay(); }
  });
  applyTimeline();
}

function currentYear() {
  return timeline.years.length ? timeline.years[timeline.index] : null;
}

function applyTimeline() {
  const ano = currentYear();
  const rotulo = document.getElementById("tl-year");
  if (rotulo) rotulo.textContent = ano === null ? "" : String(ano);
  const scrub = document.getElementById("tl-scrub");
  if (scrub) scrub.value = String(timeline.index);
  refreshGraph();
  drawDensity();
}

function togglePlay() {
  if (timeline.playing) { stopPlay(); return; }
  if (!timeline.years.length) return;
  timeline.playing = true;
  const btn = document.getElementById("tl-play");
  if (btn) btn.textContent = "⏸";
  const intervalo = Math.max(120, 900 / (timeline.speed || 1));
  timeline.timer = setInterval(() => {
    timeline.index += 1;
    if (timeline.index >= timeline.years.length) {
      timeline.index = timeline.years.length - 1;
      stopPlay();
    }
    applyTimeline();
  }, intervalo);
}

function stopPlay() {
  timeline.playing = false;
  if (timeline.timer) clearInterval(timeline.timer);
  timeline.timer = null;
  const btn = document.getElementById("tl-play");
  if (btn) btn.textContent = "▶";
}

function nodeVisibleAtCurrentYear(attrs) {
  const ano = currentYear();
  if (ano === null) return true;
  const estreia = attrs.first_year || (attrs.avg_year ? Math.round(attrs.avg_year) : null);
  if (!estreia) return true;             // sem ano: sempre visível (não se inventa data)
  return estreia <= ano;
}

async function init() {
  await loadI18n();
  applyStaticI18n();

  state.reduceMotion =
    (window.BLICSA_REDUCE_MOTION === true) ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  const container = document.getElementById("container");

  let data;
  try {
    const response = await fetch("graph.json");
    if (!response.ok) throw new Error("Failed to fetch graph.json");
    data = await response.json();
  } catch (err) {
    showEmpty(container);
    return;
  }

  if (!data.nodes || data.nodes.length === 0) {
    showEmpty(container);
    return;
  }

  payload = data;
  graph = new Graph();
  graph.import(data);

  // Canvas da densidade ATRÁS do canvas do Sigma (mesma caixa, sem interferir no ponteiro).
  densityCanvas = document.createElement("canvas");
  densityCanvas.id = "density-canvas";
  densityCanvas.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:1;";
  container.style.position = "relative";
  container.appendChild(densityCanvas);

  sigmaInstance = new Sigma(graph, container, {
    minCameraRatio: 0.05,
    maxCameraRatio: 20,
    renderEdgeLabels: false,
    defaultNodeType: "circle",
    defaultEdgeType: "line",
    labelFont: "Archivo, Inter, system-ui, sans-serif",
    labelSize: 12,
    labelWeight: "600",
    labelColor: { color: "#141414" },
    // Halo sólido (contorno chapado), nunca sombra difusa — regra do design system.
    labelRenderedSizeThreshold: 0,
  });

  buildClustersUi();
  wireInteractions();
  buildTimeline();
  setMode("network");
  staggerEntrance();

  // Densidade é relativa ao viewport: mover a câmera recalcula.
  sigmaInstance.getCamera().on("updated", () => {
    if (state.mode === "density") drawDensity();
    refreshGraph();
  });
  window.addEventListener("resize", () => drawDensity());

  const meta = payload.meta || {};
  const edgeInfo = document.getElementById("edge-info");
  if (edgeInfo && meta.edges_capped) {
    edgeInfo.textContent = tr("map_edges_capped", {
      rendered: meta.edges_rendered, total: meta.edges_total,
    });
  }
}

function buildClustersUi() {
  const clusters = new Map();
  graph.forEachNode((node, attr) => {
    if (attr.cluster !== undefined) {
      if (!clusters.has(attr.cluster)) clusters.set(attr.cluster, { color: attr.color, count: 0 });
      clusters.get(attr.cluster).count++;
    }
  });
  const clustersDiv = document.getElementById("clusters");
  if (!clustersDiv) return;
  clustersDiv.innerHTML = "";
  Array.from(clusters.entries()).sort((a, b) => a[0] - b[0]).forEach(([cluster, info]) => {
    const div = document.createElement("div");
    div.className = "cluster-item";
    const swatch = document.createElement("div");
    swatch.className = "cluster-color";
    swatch.style.backgroundColor = info.color;
    const span = document.createElement("span");
    span.textContent = tr("map_cluster_item", { n: cluster, count: info.count });
    div.appendChild(swatch);
    div.appendChild(span);
    div.onclick = () => {
      if (state.hiddenClusters.has(cluster)) {
        state.hiddenClusters.delete(cluster);
        div.style.opacity = "1";
      } else {
        state.hiddenClusters.add(cluster);
        div.style.opacity = "0.5";
      }
      refreshGraph();
      drawDensity();
    };
    clustersDiv.appendChild(div);
  });
}

function wireInteractions() {
  ["network", "overlay", "density"].forEach((m) => {
    const btn = document.getElementById("tab-" + m);
    if (btn) btn.addEventListener("click", () => setMode(m));
  });

  const metricSel = document.getElementById("overlay-metric");
  if (metricSel) {
    metricSel.addEventListener("change", () => {
      state.metric = metricSel.value;
      renderLegend();
      refreshGraph();
    });
  }

  const sizeSel = document.getElementById("size-by");
  if (sizeSel) {
    sizeSel.addEventListener("change", () => {
      state.sizeBy = sizeSel.value;
      refreshGraph();
    });
  }

  const radius = document.getElementById("density-radius");
  if (radius) {
    radius.addEventListener("input", () => {
      state.densityRadius = Number(radius.value) / 100;
      drawDensity();
    });
  }

  sigmaInstance.on("enterNode", ({ node }) => { state.hoveredNode = node; refreshGraph(); });
  sigmaInstance.on("leaveNode", () => { state.hoveredNode = null; refreshGraph(); });
  sigmaInstance.on("clickNode", ({ node }) => {
    state.selectedNode = node === state.selectedNode ? null : node;
    refreshGraph();
  });
  sigmaInstance.on("doubleClickNode", ({ node }) => {
    const c = graph.getNodeAttribute(node, "cluster");
    state.isolatedCluster = state.isolatedCluster === c ? null : c;
    refreshGraph();
    drawDensity();
  });
  sigmaInstance.on("clickStage", () => { state.selectedNode = null; refreshGraph(); });

  document.addEventListener("keydown", (e) => {
    // F: modo apresentação (só o mapa, para projetar numa banca).
    if ((e.key === "f" || e.key === "F") && !e.metaKey && !e.ctrlKey &&
        document.activeElement && document.activeElement.tagName !== "INPUT") {
      document.body.classList.toggle("presentation");
      return;
    }
    if (e.key === "Escape") {
      document.body.classList.remove("presentation");
      state.selectedNode = null;
      state.isolatedCluster = null;
      state.searchQuery = "";
      const s = document.getElementById("search");
      if (s) s.value = "";
      refreshGraph();
      drawDensity();
    }
  });

  const searchInput = document.getElementById("search");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.searchQuery = searchInput.value.toLowerCase();
      if (state.searchQuery) {
        const node = graph.findNode((n, a) => String(a.label).toLowerCase().includes(state.searchQuery));
        if (node) {
          state.selectedNode = node;
          const alvo = {
            x: graph.getNodeAttribute(node, "x"),
            y: graph.getNodeAttribute(node, "y"),
            ratio: 0.5,
          };
          if (state.reduceMotion) sigmaInstance.getCamera().setState(alvo);
          else sigmaInstance.getCamera().animate(alvo, { duration: 500 });
        } else {
          state.selectedNode = null;
        }
      } else {
        state.selectedNode = null;
      }
      refreshGraph();
    });
  }

  const reset = document.getElementById("reset-btn");
  if (reset) {
    reset.addEventListener("click", () => {
      if (state.reduceMotion) sigmaInstance.getCamera().setState({ x: 0.5, y: 0.5, ratio: 1, angle: 0 });
      else sigmaInstance.getCamera().animatedReset({ duration: 500 });
    });
  }

  const exportBtn = document.getElementById("export-btn");
  if (exportBtn) exportBtn.addEventListener("click", () => exportPng(2));
}

// Entrada escalonada dos nós ao gerar o mapa (~600ms, dos maiores para os menores): dá a
// sensação de "o mapa se construindo". Com "Reduzir movimento" o mapa já nasce pronto.
function staggerEntrance() {
  if (state.reduceMotion || !graph) return;
  const ordem = graph.nodes().sort(
    (a, b) => graph.getNodeAttribute(b, "size") - graph.getNodeAttribute(a, "size"));
  const total = 600;
  const visiveis = new Set();
  const passo = Math.max(1, Math.round(ordem.length / 24));

  sigmaInstance.setSetting("nodeReducer", (node, data) => (
    visiveis.has(node) ? { ...data } : { ...data, hidden: true }));
  sigmaInstance.refresh();

  let i = 0;
  const timer = setInterval(() => {
    for (let k = 0; k < passo && i < ordem.length; k++, i++) visiveis.add(ordem[i]);
    sigmaInstance.refresh();
    if (i >= ordem.length) {
      clearInterval(timer);
      refreshGraph();      // devolve o reducer normal
    }
  }, total / 24);
}

// Export PNG em alta resolução: compõe densidade + grafo num canvas só.
function exportPng(escala) {
  sigmaInstance.refresh();
  const container = sigmaInstance.getContainer();
  const w = container.offsetWidth;
  const h = container.offsetHeight;
  const out = document.createElement("canvas");
  out.width = w * escala;
  out.height = h * escala;
  const ctx = out.getContext("2d");
  ctx.fillStyle = "#F6F4EE";
  ctx.fillRect(0, 0, out.width, out.height);
  if (state.mode === "density" && densityCanvas) {
    ctx.drawImage(densityCanvas, 0, 0, out.width, out.height);
  }
  container.querySelectorAll("canvas").forEach((cv) => {
    if (cv.id === "density-canvas") return;
    ctx.drawImage(cv, 0, 0, out.width, out.height);
  });
  const link = document.createElement("a");
  link.download = "mapa_blicsa.png";
  link.href = out.toDataURL("image/png");
  link.click();
}

function refreshGraph() {
  if (!sigmaInstance || !graph) return;

  const searchStr = state.searchQuery;
  const highlightNode = state.selectedNode || state.hoveredNode;
  const neighbors = new Set();
  if (highlightNode) graph.forEachNeighbor(highlightNode, (n) => neighbors.add(n));

  const escala = (payload.overlay || {})[state.metric] || {};
  const rotulos = visibleLabelSet();

  sigmaInstance.setSetting("nodeReducer", (node, data) => {
    const res = { ...data };

    if (state.hiddenClusters.has(data.cluster)) { res.hidden = true; return res; }
    if (state.isolatedCluster !== null && data.cluster !== state.isolatedCluster) {
      res.hidden = true; return res;
    }
    // Linha do tempo: o nó só aparece a partir do ano da sua estreia. A POSIÇÃO nunca muda.
    if (!nodeVisibleAtCurrentYear(data)) { res.hidden = true; return res; }

    // Tamanho: ocorrências (padrão) ou força de ligação.
    if (state.sizeBy === "strength" && isFinite(data.strength)) {
      const s = (payload.meta || {}).strength_max || 0;
      res.size = 3 + 15 * (s > 0 ? data.strength / s : 0.5);
    }

    // Modo densidade: o mapa de calor é a informação, mas os RÓTULOS ficam (é assim no
    // VOSviewer — sem eles não se sabe o que está concentrado). O círculo do nó encolhe
    // a um ponto para não competir com o calor.
    if (state.mode === "density") {
      res.size = 1.2;
      res.color = "#141414";
      if (!rotulos.has(node)) res.label = "";
      return res;
    }

    if (state.mode === "overlay") {
      res.color = overlayColorFor(data[state.metric], escala);
    }

    // Rótulo só aparece se ganhou a disputa de colisão (ou está em hover/seleção).
    if (!rotulos.has(node)) res.label = "";

    if (searchStr && !String(data.label).toLowerCase().includes(searchStr)) {
      res.color = "#E0E0E0";
      res.zIndex = 0;
    } else {
      res.zIndex = 1;
    }

    if (highlightNode) {
      if (node === highlightNode || neighbors.has(node)) {
        res.highlighted = true;
        res.zIndex = 2;
        res.label = data.label;
      } else {
        res.color = "#E0E0E0";
        res.label = "";
        res.zIndex = 0;
      }
    }
    return res;
  });

  sigmaInstance.setSetting("edgeReducer", (edge, data) => {
    const res = { ...data };
    const [source, target] = graph.extremities(edge);

    // Densidade não tem arestas (é o padrão do VOSviewer).
    if (state.mode === "density") { res.hidden = true; return res; }

    // No overlay a informação é a COR do nó; a malha de arestas só atrapalha a leitura da
    // escala. Fica bem apagada em vez de sumir, para o desenho do campo não se perder.
    if (state.mode === "overlay" && !highlightNode) {
      res.color = "rgba(20,20,20,0.02)";
    }

    const cs = graph.getNodeAttribute(source, "cluster");
    const ct = graph.getNodeAttribute(target, "cluster");
    if (state.hiddenClusters.has(cs) || state.hiddenClusters.has(ct)) { res.hidden = true; return res; }
    // A aresta só existe quando as DUAS pontas já estrearam naquele recorte temporal.
    if (!nodeVisibleAtCurrentYear(graph.getNodeAttributes(source)) ||
        !nodeVisibleAtCurrentYear(graph.getNodeAttributes(target))) {
      res.hidden = true; return res;
    }
    if (state.isolatedCluster !== null && (cs !== state.isolatedCluster || ct !== state.isolatedCluster)) {
      res.hidden = true; return res;
    }

    if (highlightNode) {
      if (source === highlightNode || target === highlightNode) {
        res.color = "#1E4DA0";
        res.size = (data.size || 1) * 1.5;
        res.zIndex = 2;
      } else {
        res.hidden = true;
      }
    }
    return res;
  });

  // `setSetting` sozinho não repinta com o reducer novo: o Sigma v3 reaproveita os dados de
  // exibição já indexados, então a troca de modo saía sem efeito (os nós continuavam com a
  // cor de cluster no overlay). O refresh explícito força a reindexação.
  sigmaInstance.refresh();

  if (state.mode === "density") drawDensity();
}

// Exposto para os testes e para o Python (captura de evidência): permite trocar de modo
// sem clicar, e conferir que as posições não mudaram.
window.BlicsaMap = {
  setMode: (m) => setMode(m),
  getMode: () => state.mode,
  setMetric: (m) => { state.metric = m; renderLegend(); refreshGraph(); },
  getPositions: () => {
    const out = {};
    if (graph) graph.forEachNode((n, a) => { out[n] = [a.x, a.y]; });
    return out;
  },
  exportPng: (escala) => exportPng(escala || 2),
  state: () => ({ ...state, hiddenClusters: Array.from(state.hiddenClusters) }),
  // Linha do tempo, para a captura de evidência e os testes.
  timeline: () => ({ years: timeline.years.slice(), index: timeline.index,
                     year: currentYear(), playing: timeline.playing }),
  setYearIndex: (i) => {
    timeline.index = Math.max(0, Math.min(Number(i) || 0, timeline.years.length - 1));
    applyTimeline();
    return currentYear();
  },
  visibleNodeCount: () => {
    if (!graph) return 0;
    let n = 0;
    graph.forEachNode((_, a) => { if (nodeVisibleAtCurrentYear(a)) n++; });
    return n;
  },
  setPresentation: (on) => document.body.classList.toggle("presentation", !!on),
  setReduceMotion: (on) => { state.reduceMotion = !!on; },
  // Introspecção para a captura de evidência: o que o reducer realmente devolveu para um nó.
  debugNode: (chave) => {
    if (!graph) return null;
    const n = chave || graph.nodes()[0];
    const attrs = graph.getNodeAttributes(n);
    const escala = (payload.overlay || {})[state.metric] || {};
    const reducer = sigmaInstance.getSetting("nodeReducer");
    return {
      node: n,
      mode: state.mode,
      metric: state.metric,
      raw_metric: attrs[state.metric],
      raw_color: attrs.color,
      scale_min: escala.min,
      scale_max: escala.max,
      computed: reducer ? reducer(n, attrs) : null,
    };
  },
};

window.addEventListener("DOMContentLoaded", init);

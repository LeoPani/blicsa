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
  const title = document.getElementById("map-title");
  if (title) title.textContent = tr("map_title");
  const search = document.getElementById("search");
  if (search) search.placeholder = tr("map_search_placeholder");
  const reset = document.getElementById("reset-btn");
  if (reset) reset.textContent = tr("map_reset");
  const exp = document.getElementById("export-btn");
  if (exp) exp.textContent = tr("map_export_png");
  const clustersTitle = document.getElementById("clusters-title");
  if (clustersTitle) clustersTitle.textContent = tr("map_clusters");
}

function showEmpty(container) {
  container.innerHTML =
    '<div style="display: flex; height: 100%; width: 100%; align-items: center; ' +
    'justify-content: center; font-size: 24px; color: #555;">' +
    tr("map_empty") +
    "</div>";
  const ui = document.getElementById("ui");
  if (ui) ui.style.display = "none";
}

let sigmaInstance = null;
let graph = null;
let state = {
  hoveredNode: null,
  searchQuery: "",
  selectedNode: null,
  hiddenClusters: new Set()
};

async function init() {
  await loadI18n();
  applyStaticI18n();

  const container = document.getElementById("container");

  // Load graph data
  let data;
  try {
    const response = await fetch("graph.json");
    if (!response.ok) throw new Error("Failed to fetch graph.json");
    data = await response.json();
  } catch (err) {
    showEmpty(container);
    return;
  }

  graph = new Graph();
  graph.import(data);

  // Setup Sigma
  if (!data.nodes || data.nodes.length === 0) {
    showEmpty(container);
    return;
  }

  sigmaInstance = new Sigma(graph, container, {
    minCameraRatio: 0.1,
    maxCameraRatio: 10,
    renderEdgeLabels: true,
    defaultNodeType: "circle",
    defaultEdgeType: "line",
  });

  // Build clusters UI
  const clusters = new Map();
  graph.forEachNode((node, attr) => {
    if (attr.cluster !== undefined) {
      if (!clusters.has(attr.cluster)) {
        clusters.set(attr.cluster, { color: attr.color, count: 0 });
      }
      clusters.get(attr.cluster).count++;
    }
  });

  const clustersDiv = document.getElementById("clusters");
  Array.from(clusters.entries()).sort((a,b) => a[0] - b[0]).forEach(([cluster, info]) => {
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
    };
    clustersDiv.appendChild(div);
  });

  // Hover & selection logic
  sigmaInstance.on("enterNode", ({ node }) => {
    state.hoveredNode = node;
    refreshGraph();
  });
  sigmaInstance.on("leaveNode", () => {
    state.hoveredNode = null;
    refreshGraph();
  });
  sigmaInstance.on("clickNode", ({ node }) => {
    state.selectedNode = node === state.selectedNode ? null : node;
    refreshGraph();
  });
  sigmaInstance.on("clickStage", () => {
    state.selectedNode = null;
    refreshGraph();
  });

  // Search
  const searchInput = document.getElementById("search");
  searchInput.addEventListener("input", () => {
    state.searchQuery = searchInput.value.toLowerCase();
    if (state.searchQuery) {
      // Find exact or partial match to jump
      const node = graph.findNode((n, a) => a.label.toLowerCase().includes(state.searchQuery));
      if (node) {
        state.selectedNode = node;
        sigmaInstance.getCamera().animate({
          x: graph.getNodeAttribute(node, "x"),
          y: graph.getNodeAttribute(node, "y"),
          ratio: 0.5
        }, { duration: 500 });
      } else {
          state.selectedNode = null;
      }
    } else {
      state.selectedNode = null;
    }
    refreshGraph();
  });

  // Reset
  document.getElementById("reset-btn").addEventListener("click", () => {
    sigmaInstance.getCamera().animatedReset({ duration: 500 });
  });

  // Export
  document.getElementById("export-btn").addEventListener("click", () => {
      sigmaInstance.refresh();
      const canvas = document.querySelector("#container canvas");
      if (canvas) {
          const link = document.createElement('a');
          link.download = 'mapa_blicsa.png';
          link.href = canvas.toDataURL('image/png');
          link.click();
      }
  });

  refreshGraph();
}

function refreshGraph() {
  if (!sigmaInstance || !graph) return;

  const searchStr = state.searchQuery;
  const hovered = state.hoveredNode;
  const selected = state.selectedNode;

  const highlightNode = selected || hovered;
  const neighbors = new Set();

  if (highlightNode) {
    graph.forEachNeighbor(highlightNode, (neighbor) => {
      neighbors.add(neighbor);
    });
  }

  sigmaInstance.setSetting("nodeReducer", (node, data) => {
    const res = { ...data };

    if (state.hiddenClusters.has(data.cluster)) {
      res.hidden = true;
      return res;
    }

    if (searchStr && !data.label.toLowerCase().includes(searchStr)) {
      res.color = "#E0E0E0";
      res.zIndex = 0;
    } else {
      res.zIndex = 1;
    }

    if (highlightNode) {
      if (node === highlightNode || neighbors.has(node)) {
        res.highlighted = true;
        res.zIndex = 2;
      } else {
        res.color = "#E0E0E0";
        res.zIndex = 0;
      }
    }

    return res;
  });

  sigmaInstance.setSetting("edgeReducer", (edge, data) => {
    const res = { ...data };
    const [source, target] = graph.extremities(edge);

    if (state.hiddenClusters.has(graph.getNodeAttribute(source, "cluster")) ||
        state.hiddenClusters.has(graph.getNodeAttribute(target, "cluster"))) {
      res.hidden = true;
      return res;
    }

    if (highlightNode) {
      if (source === highlightNode || target === highlightNode) {
        res.color = "#1E4DA0";
        res.size = data.size * 1.5;
        res.zIndex = 2;
      } else {
        res.hidden = true;
      }
    }
    return res;
  });
}

window.addEventListener("DOMContentLoaded", init);

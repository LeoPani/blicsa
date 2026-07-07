import Graph from "https://esm.sh/graphology@0.25.4";
import Sigma from "https://esm.sh/sigma@3.0.0-beta.18";

let sigmaInstance = null;
let graph = null;
let state = {
  hoveredNode: null,
  searchQuery: "",
  selectedNode: null,
  hiddenClusters: new Set()
};

async function init() {
  const container = document.getElementById("container");
  
  // Load graph data
  let data;
  try {
    const response = await fetch("graph.json");
    if (!response.ok) throw new Error("Failed to fetch graph.json");
    data = await response.json();
  } catch (err) {
    container.innerHTML = '<div style="display: flex; height: 100%; width: 100%; align-items: center; justify-content: center; font-size: 24px; color: #555;">Nenhum dado para exibir</div>';
    document.getElementById("ui").style.display = 'none';
    return;
  }
  
  graph = new Graph();
  graph.import(data);
  
  // Setup Sigma
  if (!data.nodes || data.nodes.length === 0) {
    container.innerHTML = '<div style="display: flex; height: 100%; width: 100%; align-items: center; justify-content: center; font-size: 24px; color: #555;">Nenhum dado para exibir</div>';
    document.getElementById("ui").style.display = 'none';
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
    div.innerHTML = `
      <div class="cluster-color" style="background-color: ${info.color}"></div>
      <span>Cluster ${cluster} (${info.count})</span>
    `;
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

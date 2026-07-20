# Vendors locais do mapa (local-first)

O mapa temático usa **graphology** + **sigma** carregados de um único bundle
local — sem nenhum import remoto em runtime. Sem isto o mapa não renderiza sem
internet, violando o princípio local-first do Blicsa.

## `blicsa-vendor.min.js`

| item | valor |
|------|-------|
| sigma | **3.0.3** (estável — não beta) |
| graphology | **0.25.4** |
| formato | IIFE (`window.BlicsaVendor = { Graph, Sigma }`) |
| bundler | esbuild 0.24.0 (`--bundle --minify --format=iife`) |
| tamanho | 172481 bytes |
| sha256 | `2b41622148a7efda496778b64c073dc69ebb0fc7ca8d786b6479ffd7ec1ff51d` |

### Origem (npm registry)
- https://registry.npmjs.org/sigma/-/sigma-3.0.3.tgz
- https://registry.npmjs.org/graphology/-/graphology-0.25.4.tgz

### Como reproduzir o bundle
```sh
npm install sigma@3.0.3 graphology@0.25.4 esbuild@0.24.0
printf 'export { default as Graph } from "graphology";\nexport { default as Sigma } from "sigma";\n' > entry.js
esbuild entry.js --bundle --minify --format=iife \
  --global-name=BlicsaVendor --legal-comments=inline \
  --outfile=blicsa-vendor.min.js
```

## Migração beta.18 → 3.0.3 estável
A API pública usada por `assets/map.js` é idêntica entre a beta.18 e a 3.0.3
estável: construtor `new Sigma(graph, container, settings)`; settings
`minCameraRatio`, `maxCameraRatio`, `renderEdgeLabels`, `defaultNodeType`,
`defaultEdgeType`; eventos `enterNode`/`leaveNode`/`clickNode`/`clickStage`;
`getCamera().animate()` / `animatedReset()`; e os reducers via
`setSetting("nodeReducer"|"edgeReducer", fn)`. **Nenhuma mudança de API foi
necessária** — a troca foi só o import ESM externo → global local. Verificado
renderizando o mapa com o Wi-Fi desligado (docs/evidence/passo5_mapa_offline.png).

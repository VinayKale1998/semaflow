/* Shared helpers for the walkthrough pages.
   Reads window.WALKTHROUGH_DATA (set by data/walkthrough_data.js).
   No framework, no network. */

const DATA = window.WALKTHROUGH_DATA;

const PAGES = [
  ["index.html", "Overview"],
  ["01_corpus.html", "1. Corpus"],
  ["02_chunking.html", "2. Chunking"],
  ["03_embedding.html", "3. Embedding"],
  ["04_vector_search.html", "4. Vector"],
  ["05_bm25.html", "5. BM25"],
  ["06_rrf.html", "6. RRF"],
  ["07_reranker.html", "7. Reranker"],
  ["08_full_pipeline.html", "8. Pipeline"],
];

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function tag(docType) {
  return `<span class="tag ${docType}">${esc(docType)}</span>`;
}

function currentFile() {
  const parts = location.pathname.split("/");
  return parts[parts.length - 1] || "index.html";
}

function renderChrome(stepLabel) {
  const here = currentFile();
  const header = document.createElement("header");
  header.className = "site";
  header.innerHTML = `<div class="inner">
    <div class="brand"><a href="index.html">SemaFlow RAG walkthrough</a></div>
    <div class="step">${esc(stepLabel || "")}</div>
  </div>`;
  document.body.prepend(header);

  const nav = document.getElementById("nav");
  if (nav) {
    nav.className = "pages";
    nav.innerHTML = PAGES.map(([href, label]) => {
      const active = href === here ? " class=\"active\"" : "";
      return `<a href="${href}"${active}>${esc(label)}</a>`;
    }).join("");
  }
}

const DOC_COLORS = {
  data_dictionary: "#2f6fb0",
  policy: "#3f9163",
  category_def: "#cc7a30",
};

// Render the PCA scatter of all chunks as inline SVG.
// opts: { query: {x,y}, neighborIds: Set, points override }
function scatterSVG(opts) {
  opts = opts || {};
  const pts = DATA.projection_2d.chunks;
  const q = opts.query;
  const W = 760, H = 460, pad = 30;

  let xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  if (q) { xs = xs.concat(q.x); ys = ys.concat(q.y); }
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const sx = (x) => pad + (x - minX) / (maxX - minX) * (W - 2 * pad);
  const sy = (y) => H - pad - (y - minY) / (maxY - minY) * (H - 2 * pad);

  let svg = `<svg class="viz" viewBox="0 0 ${W} ${H}" width="100%" role="img">`;

  // neighbour lines from query to highlighted points
  if (q && opts.neighborIds) {
    pts.forEach((p) => {
      if (opts.neighborIds.has(p.chunk_id)) {
        svg += `<line x1="${sx(q.x)}" y1="${sy(q.y)}" x2="${sx(p.x)}" y2="${sy(p.y)}" stroke="#d23c3c" stroke-width="1" stroke-opacity="0.45"/>`;
      }
    });
  }

  // chunk points
  pts.forEach((p) => {
    const hl = opts.neighborIds && opts.neighborIds.has(p.chunk_id);
    const r = hl ? 5.5 : 3.2;
    const op = opts.neighborIds ? (hl ? 1 : 0.35) : 0.8;
    svg += `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${r}" fill="${DOC_COLORS[p.doc_type]}" fill-opacity="${op}"${hl ? ' stroke="#1c2128" stroke-width="0.8"' : ""}><title>${esc(p.source)}</title></circle>`;
  });

  // query point
  if (q) {
    svg += `<circle cx="${sx(q.x)}" cy="${sy(q.y)}" r="7" fill="#d23c3c" stroke="#fff" stroke-width="1.5"><title>query</title></circle>`;
    svg += `<text x="${sx(q.x) + 11}" y="${sy(q.y) + 4}" font-size="12" fill="#d23c3c">query</text>`;
  }
  svg += "</svg>";
  return svg;
}

function scatterLegend(withQuery) {
  const items = [
    ["data_dictionary", "data dictionary"],
    ["policy", "policy"],
    ["category_def", "category def"],
  ].map(([cls, label]) => `<span><span class="swatch ${cls}"></span>${label}</span>`);
  if (withQuery) items.push(`<span><span class="swatch query"></span>query</span>`);
  return `<div class="legend">${items.join("")}</div>`;
}

// Build a results table from a list of row objects and a column spec.
// columns: [{key, label, cls, fmt}]
function resultsTable(rows, columns, targetSource) {
  const head = "<tr><th class=\"rank\">#</th>" +
    columns.map((c) => `<th class="${c.cls || ""}">${esc(c.label)}</th>`).join("") +
    "</tr>";
  const body = rows.map((r, i) => {
    const isTarget = targetSource && r.source === targetSource;
    const cells = columns.map((c) => {
      const raw = c.fmt ? c.fmt(r[c.key], r) : r[c.key];
      return `<td class="${c.cls || ""}">${raw == null ? "" : raw}</td>`;
    }).join("");
    return `<tr class="${isTarget ? "target" : ""}"><td class="rank">${i + 1}</td>${cells}</tr>`;
  }).join("");
  return `<table>${head}${body}</table>`;
}

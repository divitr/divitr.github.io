// constellation.js — Post Constellation Visualizer

(function () {
  'use strict';

  // ── Config ────────────────────────────────────────────────────────────────────

  const COLORS     = ['#7a8fa6', '#a07060', '#6a9a7a', '#8a7aaa', '#a09060'];
  const W = 700, H = 420, PAD = 60;
  const KNOWN_TAGS = ['ml', 'math', 'physics', 'stats', 'misc'];

  const STOP = new Set([
    'the','a','an','and','or','but','in','on','at','to','for','of','with',
    'we','our','is','are','was','were','be','been','being','have','has','had',
    'do','does','did','will','would','could','should','may','might','shall',
    'not','no','nor','as','by','from','into','through','before','after',
    'here','there','when','where','how','all','each','some','such','only',
    'same','so','than','too','very','just','can','now','also','this','that',
    'these','those','it','its','if','which','who','what','i','you','he','she',
    'they','us','them','my','your','their','while','about','between','any',
    'let','use','used','using','given','thus','then','since','note','see',
    'well','like','get','way','give','show','shows','gives','makes','make',
    'one','two','three','consider','define','defined','assume','write','take',
    'following','first','second','next','both','more','most','other','where',
    'each','over','under','again','such','even','new','result','results',
    'case','form','follows','hence','clearly','simply','write','written','call',
    'function','functions','space','paper','model','models','training','data',
    'work','works','working','approach','need','needs','point','points',
    'prove','proof','proofs','proven','shown','where','there','here','that',
  ]);

  // ── SVG helpers ───────────────────────────────────────────────────────────────

  const NS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs = {}) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  }

  // ── Post extraction ───────────────────────────────────────────────────────────

  function extractPosts() {
    return Array.from(document.querySelectorAll('.blog-post-item')).map(el => {
      const link = el.querySelector('h3 a');
      const href = link?.getAttribute('href') ?? '';
      return {
        slug:  href.replace(/^\/posts\//, '').replace(/\/$/, ''),
        title: link?.textContent?.replace(/\s*\([^)]*\)\s*$/, '').trim() ?? '',
        desc:  el.querySelector('.post-description')?.textContent?.trim() ?? '',
        date:  el.querySelector('.post-date')?.textContent?.trim() ?? '',
        tags:  (el.getAttribute('data-tags') ?? '').split(',').map(t => t.trim()).filter(Boolean),
        emoji: el.getAttribute('data-emoji') ?? '',
        href,
      };
    });
  }

  // ── Fetch + parse ─────────────────────────────────────────────────────────────

  async function fetchMdtx(slug) {
    try {
      const r = await fetch(`/posts/src/${slug}.mdtx`);
      return r.ok ? await r.text() : '';
    } catch { return ''; }
  }

  function stripMdtx(raw) {
    return raw
      .replace(/^(req|title|date|desc|tags|emoji|visibility):.*/mg, '')
      .replace(/\{[^}]{0,300}\}/g, ' ')
      .replace(/^(#+|list\[.*?\]|end\s+\w+[\s;]*|example:|content:|image:).*/mg, '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/\[\^[^\]]*\]/g, '')
      .replace(/[*_`~#>[\]\\]/g, ' ');
  }

  function tokenize(text) {
    return text.toLowerCase().split(/[^a-z]+/).filter(w => w.length > 3 && !STOP.has(w));
  }

  // Extends tokenize with bigrams and trigrams so phrases like
  // "kernel_ridge", "neural_tangent_kernel", "heat_equation", "optimal_transport"
  // become single high-IDF features — much more discriminative than unigrams alone.
  function ngramTokenize(text) {
    const words = tokenize(text);
    const bi  = words.slice(0, -1).map((w, i) => w + '_' + words[i + 1]);
    const tri = words.slice(0, -2).map((w, i) => w + '_' + words[i + 1] + '_' + words[i + 2]);
    return [...words, ...bi, ...tri];
  }

  // ── TF-IDF ────────────────────────────────────────────────────────────────────
  // minDf=1: keep all terms (unique per-post terms have highest IDF → most discriminative).
  // minDf=2: keep only shared terms.

  function tfidf(corpus, minDf = 1) {
    const n = corpus.length;
    const tfs = corpus.map(tokens => {
      const freq = {};
      for (const t of tokens) freq[t] = (freq[t] ?? 0) + 1;
      const len = tokens.length || 1;
      for (const t in freq) freq[t] /= len;
      return freq;
    });
    const df = {};
    for (const freq of tfs) for (const t in freq) df[t] = (df[t] ?? 0) + 1;
    const vocab = Object.keys(df).filter(t => df[t] >= minDf && df[t] < n);
    if (!vocab.length) return tfs.map(() => []);
    const idf = Object.fromEntries(vocab.map(t => [t, Math.log((n + 1) / df[t])]));
    return tfs.map(freq => {
      const row  = vocab.map(t => (freq[t] ?? 0) * (idf[t] ?? 0));
      const norm = Math.sqrt(row.reduce((s, x) => s + x * x, 0)) || 1;
      return row.map(x => x / norm);
    });
  }

  // ── Feature construction ──────────────────────────────────────────────────────
  // Three signals, squared-weight blend:
  //   Tags (W=2):  one-hot over personal tags — pulls same-tagged posts together
  //   Desc (W=2):  title+desc TF-IDF, minDf=1 — unique summary keywords per post
  //   Body (W=1):  prose TF-IDF, minDf=1 — now keeps discriminative rare terms
  //
  // Relative cosine weight = W²: so tags:desc:body = 4:4:1.

  function buildFeatures(posts, bodies) {
    const W_TAG = 2, W_DESC = 2, W_BODY = 1;

    // Tag one-hot, L2-normalized per post
    const tagVecs = posts.map(p => {
      const v    = KNOWN_TAGS.map(t => p.tags.includes(t) ? 1 : 0);
      const norm = Math.sqrt(v.reduce((s, x) => s + x * x, 0)) || 1;
      return v.map(x => x / norm);
    });

    // Description TF-IDF with bigrams+trigrams (minDf=1)
    // Phrases like "neural_tangent", "heat_equation", "category_theory" are highly discriminative
    const descVecs = tfidf(
      posts.map(p => ngramTokenize([p.title, p.title, p.title, p.desc, p.desc].join(' '))),
      1
    );

    // Body TF-IDF with bigrams+trigrams (minDf=1)
    // "kernel_ridge_regression", "optimal_transport", "markov_jump_process" etc.
    const bodyVecs = tfidf(
      posts.map((p, i) => ngramTokenize(p.title + ' ' + p.desc + ' ' + stripMdtx(bodies[i]))),
      1
    );

    return posts.map((_, i) => {
      const combined = [
        ...tagVecs[i].map(x => x * W_TAG),
        ...(descVecs[i] ?? []).map(x => x * W_DESC),
        ...(bodyVecs[i] ?? []).map(x => x * W_BODY),
      ];
      const norm = Math.sqrt(combined.reduce((s, x) => s + x * x, 0)) || 1;
      return combined.map(x => x / norm);
    });
  }

  // ── Linear algebra ────────────────────────────────────────────────────────────

  const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
  function mvMul(A, v) { return A.map(row => dot(row, v)); }
  function normalized(v) { const n = Math.sqrt(dot(v, v)) || 1; return v.map(x => x / n); }
  function deflate(A, v, lam) { return A.map((row, i) => row.map((x, j) => x - lam * v[i] * v[j])); }

  function powerIter(A, seed, maxIter = 1000, tol = 1e-11) {
    let v = normalized(seed), lam = 0;
    for (let i = 0; i < maxIter; i++) {
      const w = mvMul(A, v), newL = dot(v, w), newV = normalized(w);
      if (Math.abs(newL - lam) < tol) return { v: newV, lam: newL };
      v = newV; lam = newL;
    }
    return { v, lam };
  }

  // ── Laplacian Eigenmaps ───────────────────────────────────────────────────────
  // Spectral embedding that explicitly minimizes inter-cluster connections.
  // This is the continuous relaxation of the graph min-cut problem:
  // clusters emerge as the natural low-energy modes of the affinity graph.
  //
  // Algorithm:
  //   1. Build Gaussian affinity matrix W from cosine similarities
  //   2. Compute normalized graph Laplacian L_sym = I - D^{-1/2} W D^{-1/2}
  //   3. Shift: M = λ_max·I - L_sym  (so smallest eigenvalues of L become largest of M)
  //   4. Power-iterate M to find top 3 eigenvectors
  //   5. Skip trivial eigenvector (≈ 0 of L); use next two as 2D coordinates

  function lapEmbed2d(X) {
    const n = X.length;
    if (n < 3) return X.map((_, i) => [i, 0]);

    const BETA = 4; // affinity sharpness: exp(-β·(1−cos))

    // Gaussian affinity on cosine similarity (all cosines ≥ 0 for our non-neg features)
    const W = X.map((xi, i) => X.map((xj, j) => {
      if (i === j) return 0;
      return Math.exp(-BETA * (1 - dot(xi, xj)));
    }));

    // Degree row-sums
    const d        = W.map(row => row.reduce((s, x) => s + x, 0));
    const invSqrtD = d.map(di => di > 0 ? 1 / Math.sqrt(di) : 0);

    // Normalized Laplacian: L = I − D^{-½} W D^{-½}
    const L = W.map((row, i) =>
      row.map((w, j) => (i === j ? 1 : 0) - invSqrtD[i] * w * invSqrtD[j])
    );

    // λ_max of L (all eigenvalues in [0,2] for normalized Laplacian)
    const { lam: lmax } = powerIter(L, L.map((_, i) => Math.sin(i * 1.7 + 0.3)));

    // Shift M = λ_max·I − L  →  largest eigenvectors of M = smallest of L
    const M = L.map((row, i) => row.map((x, j) => (i === j ? lmax : 0) - x));

    // Top 3 eigenvectors of M (= bottom 3 of L)
    const { v: u1, lam: m1 } = powerIter(M, M.map((_, i) => Math.sin(i * 1.3 + 0.7)));
    const M2 = deflate(M, u1, m1);
    const { v: u2, lam: m2 } = powerIter(M2, M2.map((_, i) => Math.cos(i * 2.1 + 0.4)));
    const M3 = deflate(M2, u2, m2);
    const { v: u3 }          = powerIter(M3, M3.map((_, i) => Math.sin(i * 3.7 + 1.2)));

    // u1 ≈ trivial (constant) eigenvector; u2, u3 give the meaningful 2D embedding
    return u1.map((_, i) => [u2[i], u3[i]]);
  }

  // ── K-means ───────────────────────────────────────────────────────────────────

  function dist2(a, b) { return a.reduce((s, x, i) => s + (x - b[i]) ** 2, 0); }
  function euclid(a, b) { return Math.sqrt(dist2(a, b)); }

  function kmeans2d(pts, k, runs = 40) {
    const n = pts.length;
    if (n <= k) return pts.map((_, i) => i);
    let bestLabels = null, bestInertia = Infinity;
    for (let run = 0; run < runs; run++) {
      const taken = new Set();
      const ci    = [Math.floor(Math.random() * n)];
      taken.add(ci[0]);
      while (ci.length < k) {
        const d     = pts.map((p, i) => taken.has(i) ? 0 : Math.min(...ci.map(c => dist2(p, pts[c]))));
        const total = d.reduce((s, x) => s + x, 0);
        let r = Math.random() * total;
        for (let i = 0; i < n; i++) {
          r -= d[i];
          if (r <= 0 && !taken.has(i)) { ci.push(i); taken.add(i); break; }
        }
        if (ci.length < run + 2)
          for (let i = 0; i < n; i++) if (!taken.has(i)) { ci.push(i); taken.add(i); break; }
      }
      const cents  = ci.map(i => [...pts[i]]);
      const labels = new Array(n).fill(0);
      for (let iter = 0; iter < 300; iter++) {
        let changed = false;
        for (let i = 0; i < n; i++) {
          let best = 0, bd = Infinity;
          for (let j = 0; j < k; j++) { const d = dist2(pts[i], cents[j]); if (d < bd) { bd = d; best = j; } }
          if (labels[i] !== best) { labels[i] = best; changed = true; }
        }
        if (!changed) break;
        for (let j = 0; j < k; j++) {
          const g = pts.filter((_, i) => labels[i] === j);
          if (g.length) cents[j] = [0, 1].map(d => g.reduce((s, p) => s + p[d], 0) / g.length);
        }
      }
      const inertia = pts.reduce((s, p, i) => s + dist2(p, cents[labels[i]]), 0);
      if (inertia < bestInertia) { bestInertia = inertia; bestLabels = labels.slice(); }
    }
    return bestLabels;
  }

  // ── Silhouette-based auto-k ────────────────────────────────────────────────────

  function silhouette(pts, labels) {
    const k = Math.max(...labels) + 1, n = pts.length;
    let total = 0;
    for (let i = 0; i < n; i++) {
      const ci   = labels[i];
      const same  = pts.filter((_, j) => j !== i && labels[j] === ci);
      const a     = same.length ? same.reduce((s, p) => s + euclid(pts[i], p), 0) / same.length : 0;
      let b       = Infinity;
      for (let c = 0; c < k; c++) {
        if (c === ci) continue;
        const other = pts.filter((_, j) => labels[j] === c);
        if (other.length) b = Math.min(b, other.reduce((s, p) => s + euclid(pts[i], p), 0) / other.length);
      }
      total += b === Infinity ? 0 : (b - a) / Math.max(a, b);
    }
    return total / n;
  }

  function autoK(pts, kMin = 2, kMax = 5) {
    let bestK = kMin, bestScore = -Infinity;
    for (let k = kMin; k <= Math.min(kMax, pts.length - 1); k++) {
      const score = silhouette(pts, kmeans2d(pts, k, 20));
      if (score > bestScore) { bestScore = score; bestK = k; }
    }
    return bestK;
  }

  // ── No singleton clusters ─────────────────────────────────────────────────────
  // Iteratively merges any size-1 cluster into the spatially nearest other cluster.

  function fixSingletons(pts, labels) {
    let cur = [...labels];
    let changed = true;
    while (changed) {
      changed = false;
      const counts = {};
      for (const l of cur) counts[l] = (counts[l] ?? 0) + 1;
      const lone = Object.keys(counts).map(Number).find(c => counts[c] === 1);
      if (lone === undefined) break;
      const idx    = cur.indexOf(lone);
      const others = [...new Set(cur)].filter(l => l !== lone);
      // Find nearest cluster centroid in 2D
      let best = others[0], bd = Infinity;
      for (const l of others) {
        const members = pts.filter((_, i) => cur[i] === l);
        const cx = members.reduce((s, p) => s + p[0], 0) / members.length;
        const cy = members.reduce((s, p) => s + p[1], 0) / members.length;
        const d  = dist2(pts[idx], [cx, cy]);
        if (d < bd) { bd = d; best = l; }
      }
      cur[idx] = best;
      changed = true;
    }
    // Renormalize labels to 0…k-1
    const unique = [...new Set(cur)].sort((a, b) => a - b);
    const remap  = Object.fromEntries(unique.map((v, i) => [v, i]));
    return cur.map(l => remap[l]);
  }

  // ── Point repulsion ───────────────────────────────────────────────────────────

  function repulse(pts, minPx = 52, iters = 200, strength = 0.3) {
    const p = pts.map(c => [...c]);
    for (let it = 0; it < iters; it++) {
      const forces = p.map(() => [0, 0]);
      for (let i = 0; i < p.length; i++)
        for (let j = i + 1; j < p.length; j++) {
          const dx = p[j][0] - p[i][0], dy = p[j][1] - p[i][1];
          const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
          if (d < minPx) {
            const f = (minPx - d) * strength;
            forces[i][0] -= (dx / d) * f; forces[i][1] -= (dy / d) * f;
            forces[j][0] += (dx / d) * f; forces[j][1] += (dy / d) * f;
          }
        }
      for (let i = 0; i < p.length; i++) {
        p[i][0] = Math.max(PAD, Math.min(W - PAD, p[i][0] + forces[i][0]));
        p[i][1] = Math.max(PAD, Math.min(H - PAD, p[i][1] + forces[i][1]));
      }
    }
    return p;
  }

  // ── Global random rotation (for visual variety, geometry preserved) ─────────
  function randomRotate2d(embed2d) {
    const n = embed2d.length;
    if (n < 2) return embed2d;
    const mx = embed2d.reduce((s, p) => s + p[0], 0) / n;
    const my = embed2d.reduce((s, p) => s + p[1], 0) / n;
    const a = Math.random() * 2 * Math.PI;
    const c = Math.cos(a), s = Math.sin(a);
    return embed2d.map(([x, y]) => {
      const dx = x - mx, dy = y - my;
      return [mx + c * dx - s * dy, my + s * dx + c * dy];
    });
  }

  // ── MST per cluster (constellation lines) ─────────────────────────────────────

  function clusterMSTs(pts, labels) {
    const k = Math.max(...labels) + 1, edges = [];
    for (let c = 0; c < k; c++) {
      const idxs = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      if (idxs.length < 2) continue;

      const inTree = new Set([idxs[0]]);
      while (inTree.size < idxs.length) {
        let best = null, bd = Infinity;
        for (const u of inTree)
          for (const v of idxs)
            if (!inTree.has(v)) { const d = dist2(pts[u], pts[v]); if (d < bd) { bd = d; best = [u, v]; } }
        if (!best) break;
        inTree.add(best[1]); edges.push(best);
      }
    }
    return edges;
  }

  // ── Date → opacity ────────────────────────────────────────────────────────────

  function dateOpacities(posts) {
    const ms    = posts.map(p => { const d = new Date(p.date); return isNaN(d) ? null : d.getTime(); });
    const valid = ms.filter(Boolean);
    if (!valid.length) return posts.map(() => 0.85);
    const lo = Math.min(...valid), hi = Math.max(...valid), range = hi - lo || 1;
    return ms.map(m => m == null ? 0.65 : 0.3 + 0.7 * ((m - lo) / range));
  }

  // ── Per-cluster random rotation + mild aspect stretch ─────────────────────────
  // Each cluster gets an independent random rotation and a small random stretch
  // along one axis, giving each group a distinct "constellation shape" while
  // keeping points near their semantically-correct positions.

  function jitterClusters(coords, labels) {
    const result = coords.map(c => [...c]);
    const k = Math.max(...labels) + 1;
    for (let c = 0; c < k; c++) {
      const idxs = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      if (idxs.length < 2) continue;

      // Cluster centroid
      const cx = idxs.reduce((s, i) => s + result[i][0], 0) / idxs.length;
      const cy = idxs.reduce((s, i) => s + result[i][1], 0) / idxs.length;

      // Random rotation angle per cluster (up to ±60 degrees)
      const angle = (Math.random() - 0.5) * Math.PI * 2 / 3;
      const cos   = Math.cos(angle), sin = Math.sin(angle);

      // Random mild stretch (0.7 to 1.4) along the rotated x-axis
      const stretch = 0.7 + Math.random() * 0.7;

      for (const i of idxs) {
        let dx = result[i][0] - cx, dy = result[i][1] - cy;
        // Rotate
        const rx = cos * dx - sin * dy;
        const ry = sin * dx + cos * dy;
        // Stretch along one axis
        result[i][0] = cx + rx * stretch;
        result[i][1] = cy + ry;
      }
    }
    return result;
  }

  // ── Scale to SVG viewport ─────────────────────────────────────────────────────

  function scaleCoords(coords) {
    const xs = coords.map(c => c[0]), ys = coords.map(c => c[1]);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const xR = xMax - xMin || 1, yR = yMax - yMin || 1;
    return coords.map(([x, y]) => [
      PAD + ((x - xMin) / xR) * (W - 2 * PAD),
      PAD + ((y - yMin) / yR) * (H - 2 * PAD),
    ]);
  }

  function pointSegDist2(p, a, b) {
    const vx = b[0] - a[0], vy = b[1] - a[1];
    const wx = p[0] - a[0], wy = p[1] - a[1];
    const c1 = vx * wx + vy * wy;
    if (c1 <= 0) return dist2(p, a);
    const c2 = vx * vx + vy * vy;
    if (c2 <= c1) return dist2(p, b);
    const t = c1 / c2;
    const proj = [a[0] + t * vx, a[1] + t * vy];
    return dist2(p, proj);
  }

  function chooseClusterLabelPos(cx, cy, r, idxs, pts, clusterEdges) {
    const step = Math.max(18, Math.min(34, r * 0.45));
    const cands = [
      [cx, cy],
      [cx, cy - step], [cx, cy + step],
      [cx - step, cy], [cx + step, cy],
      [cx - 0.75 * step, cy - 0.75 * step], [cx + 0.75 * step, cy - 0.75 * step],
      [cx - 0.75 * step, cy + 0.75 * step], [cx + 0.75 * step, cy + 0.75 * step],
    ].map(([x, y]) => [
      Math.max(14, Math.min(W - 14, x)),
      Math.max(14, Math.min(H - 14, y)),
    ]);

    let best = cands[0], bestScore = -Infinity;
    for (const p of cands) {
      const dPt = Math.min(...idxs.map(i => euclid(p, pts[i])));
      let dEdge = Infinity;
      for (const [u, v] of clusterEdges) dEdge = Math.min(dEdge, Math.sqrt(pointSegDist2(p, pts[u], pts[v])));
      const score = Math.min(dPt, dEdge * 0.9);
      if (score > bestScore) { bestScore = score; best = p; }
    }
    return best;
  }

  // ── Cluster keyword labels ────────────────────────────────────────────────────

  function clusterKeywords(posts, labels) {
    const k = Math.max(...labels) + 1;
    const GENERIC = new Set([
      'posts', 'post', 'notes', 'note', 'paper', 'small', 'quick', 'rough', 'view', 'using',
      'some', 'more', 'less', 'cool', 'bits', 'things', 'picture', 'problem', 'models', 'model',
    ]);
    const TAG_FALLBACK = { ml: 'learning', math: 'theory', physics: 'dynamics', stats: 'inference', misc: 'ideas' };

    function low(word) { return (word ?? 'ideas').toLowerCase(); }

    return Array.from({ length: k }, (_, c) => {
      const idxs = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      if (!idxs.length) return 'ideas';

      const freq = {};
      const tagFreq = {};
      for (const i of idxs) {
        for (const t of tokenize(`${posts[i].title} ${posts[i].desc}`)) {
          if (GENERIC.has(t)) continue;
          freq[t] = (freq[t] ?? 0) + 1;
        }
        for (const t of posts[i].tags) tagFreq[t] = (tagFreq[t] ?? 0) + 1;
      }

      const topWord = Object.entries(freq)
        .sort((a, b) => b[1] - a[1] || b[0].length - a[0].length || a[0].localeCompare(b[0]))[0]?.[0];
      if (topWord) return low(topWord);

      const topTag = Object.entries(tagFreq).sort((a, b) => b[1] - a[1])[0]?.[0];
      return low(TAG_FALLBACK[topTag] ?? topTag ?? 'ideas');
    });
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  function render(svgContainer, tooltipEl, posts, embed2d, labels) {
    const opacities = dateOpacities(posts);
    const scaled    = repulse(scaleCoords(jitterClusters(embed2d, labels)));
    const edges     = clusterMSTs(scaled, labels);
    const words     = clusterKeywords(posts, labels);
    const k         = Math.max(...labels) + 1;

    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', style: 'display:block' });
    root.appendChild(svg('rect', { x: 0, y: 0, width: W, height: H, fill: '#fafafa', rx: 3 }));

    // Constellation lines (MST per cluster)
    const lg = svg('g');
    for (const [i, j] of edges)
      lg.appendChild(svg('line', {
        x1: scaled[i][0], y1: scaled[i][1], x2: scaled[j][0], y2: scaled[j][1],
        stroke: COLORS[labels[i] % COLORS.length], 'stroke-width': 1, opacity: 0.3,
      }));
    root.appendChild(lg);

    // Cluster hover regions + one-word labels
    const hoverLayer = svg('g');
    const clusterMeta = [];
    const labelLayer = svg('g', { 'pointer-events': 'none' });
    for (let c = 0; c < k; c++) {
      const idxs = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      if (!idxs.length) continue;

      const cx = idxs.reduce((s, i) => s + scaled[i][0], 0) / idxs.length;
      const cy = idxs.reduce((s, i) => s + scaled[i][1], 0) / idxs.length;
      const r0 = Math.max(...idxs.map(i => euclid(scaled[i], [cx, cy])));
      const r  = Math.max(34, Math.min(95, r0 + 22));
      const clusterEdges = edges.filter(([u, v]) => labels[u] === c && labels[v] === c);
      const [lx, ly] = chooseClusterLabelPos(cx, cy, r, idxs, scaled, clusterEdges);

      const zone = svg('circle', { cx, cy, r, fill: '#000', opacity: 0.001, style: 'cursor:default' });
      const lbl = svg('text', {
        x: lx, y: ly, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
        'font-size': 11, 'letter-spacing': '0.05em',
        fill: COLORS[c % COLORS.length], 'font-family': 'Charter, Georgia, serif', 'font-style': 'italic',
        stroke: '#fafafa', 'stroke-width': 3.5, 'paint-order': 'stroke',
        opacity: 0,
      });
      lbl.textContent = words[c];
      clusterMeta.push({ c, cx, cy, r, lbl });

      zone.addEventListener('mouseenter', () => { lbl.setAttribute('opacity', '0.92'); });
      zone.addEventListener('mouseleave', () => { lbl.setAttribute('opacity', '0'); });

      hoverLayer.appendChild(zone);
      labelLayer.appendChild(lbl);
    }
    root.appendChild(hoverLayer);

    // Dots
    for (let i = 0; i < posts.length; i++) {
      const [x, y] = scaled[i];
      const color  = COLORS[labels[i] % COLORS.length];
      const op     = opacities[i];
      const g      = svg('g', { style: 'cursor:pointer' });
      const halo   = svg('circle', { cx: x, cy: y, r: 12, fill: color, opacity: 0 });
      const dot    = svg('circle', { cx: x, cy: y, r: 5, fill: color, opacity: op });
      g.appendChild(halo); g.appendChild(dot);
      g.addEventListener('mouseenter', e => {
        dot.setAttribute('r', 7); dot.setAttribute('opacity', 1); halo.setAttribute('opacity', 0.12);
        showTooltip(tooltipEl, posts[i], e);
      });
      g.addEventListener('mousemove', e => moveTooltip(tooltipEl, e));
      g.addEventListener('mouseleave', () => {
        dot.setAttribute('r', 5); dot.setAttribute('opacity', op); halo.setAttribute('opacity', 0);
        hideTooltip(tooltipEl);
      });
      g.addEventListener('click', () => { window.location.href = posts[i].href; });
      root.appendChild(g);
    }
    root.appendChild(labelLayer);

    // Robust cluster-hover detection (works even when hovering over points/lines).
    function showClusterLabel(idx) {
      for (const m of clusterMeta)
        m.lbl.setAttribute('opacity', m.c === idx ? '0.92' : '0');
    }
    root.addEventListener('mousemove', e => {
      const rect = root.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / (rect.width || 1)) * W;
      const y = ((e.clientY - rect.top) / (rect.height || 1)) * H;
      let best = null, bestScore = Infinity;
      for (const m of clusterMeta) {
        const d = euclid([x, y], [m.cx, m.cy]);
        if (d <= m.r) {
          const score = d / m.r;
          if (score < bestScore) { bestScore = score; best = m.c; }
        }
      }
      showClusterLabel(best);
    });
    root.addEventListener('mouseleave', () => showClusterLabel(null));

    // Legend
    const legend = svg('text', {
      x: W - PAD + 10, y: H - 6, 'text-anchor': 'end', 'font-size': 10,
      fill: '#c0c0bc', 'font-family': 'Charter, Georgia, serif', 'font-style': 'italic',
      'pointer-events': 'none',
    });
    legend.textContent = 'opacity indicates recency';
    root.appendChild(legend);

    svgContainer.innerHTML = '';
    svgContainer.appendChild(root);
  }

  // ── Tooltip ───────────────────────────────────────────────────────────────────

  function showTooltip(el, post, e) {
    el.innerHTML = `
      <div style="display:flex;align-items:baseline;gap:0.35rem;margin-bottom:0.15rem">
        <span style="font-size:0.95rem;line-height:1">${post.emoji}</span>
        <a href="${post.href}" style="color:#4a4a4a;text-decoration:none;font-weight:500;font-size:0.88rem;line-height:1.3"
           onmouseenter="this.style.textDecoration='underline'" onmouseleave="this.style.textDecoration='none'"
        >${post.title}</a>
      </div>
      <div style="color:#aaa;font-size:0.76rem;margin-bottom:0.2rem">${post.date}</div>
      <div style="color:#666;font-size:0.81rem;line-height:1.4">${post.desc}</div>
      <div style="margin-top:0.3rem">${post.tags.map(t =>
        `<span style="color:#bbb;font-size:0.73rem;margin-right:0.3rem">#${t}</span>`).join('')}</div>`;
    el.style.opacity = '1'; el.style.pointerEvents = 'none';
    moveTooltip(el, e);
  }

  function moveTooltip(el, e) {
    const parent = el.offsetParent;
    const parentRect = parent?.getBoundingClientRect() ?? { left: 0, top: 0, right: 800, bottom: 500 };
    const plotSvg = parent?.querySelector('#constellation-svg svg');
    const plotRect = plotSvg?.getBoundingClientRect() ?? parentRect;

    const pad = 8;
    const bounds = {
      left: plotRect.left - parentRect.left + pad,
      top: plotRect.top - parentRect.top + pad,
      right: plotRect.right - parentRect.left - pad,
      bottom: plotRect.bottom - parentRect.top - pad,
    };

    const tw = el.offsetWidth || 240;
    const th = el.offsetHeight || 130;
    const gap = 14;
    const mx = e.clientX - parentRect.left;
    const my = e.clientY - parentRect.top;

    const candidates = [
      [mx + gap, my + gap],           // down-right
      [mx - tw - gap, my + gap],      // down-left
      [mx + gap, my - th - gap],      // up-right
      [mx - tw - gap, my - th - gap], // up-left
    ];

    const fits = ([x, y]) =>
      x >= bounds.left &&
      y >= bounds.top &&
      x + tw <= bounds.right &&
      y + th <= bounds.bottom;

    let [tx, ty] = candidates.find(fits) ?? candidates[0];
    tx = Math.min(Math.max(tx, bounds.left), bounds.right - tw);
    ty = Math.min(Math.max(ty, bounds.top), bounds.bottom - th);

    el.style.left = tx + 'px';
    el.style.top = ty + 'px';
  }

  function hideTooltip(el) { el.style.opacity = '0'; }

  // ── Main ──────────────────────────────────────────────────────────────────────

  async function buildViz() {
    const statusEl  = document.getElementById('constellation-status');
    const svgEl     = document.getElementById('constellation-svg');
    const tooltipEl = document.getElementById('constellation-tooltip');
    if (!statusEl || !svgEl || !tooltipEl) return;

    const posts = extractPosts();
    if (!posts.length) { statusEl.textContent = 'no posts found.'; return; }

    statusEl.style.display = 'block';
    statusEl.textContent = 'fetching…';
    const texts = await Promise.all(posts.map(p => fetchMdtx(p.slug)));

    statusEl.textContent = 'computing…';
    const X = buildFeatures(posts, texts);
    if (!X.length || !X[0].length) { statusEl.textContent = 'not enough data.'; return; }

    const embed2d  = randomRotate2d(lapEmbed2d(X));         // random global orientation
    const k        = autoK(embed2d);                     // silhouette-optimal k
    let labels     = fixSingletons(embed2d, kmeans2d(embed2d, k));  // no lone posts
    const kShown   = Math.max(...labels) + 1;

    statusEl.style.display = 'none';
    render(svgEl, tooltipEl, posts, embed2d, labels);

    if (!document.getElementById('constellation-caption')) {
      const cap = document.createElement('p');
      cap.id = 'constellation-caption';
      cap.className = 'constellation-caption';

      const lnk = `text-decoration:none;color:#bbb`;
      const paperLnk = `text-decoration:underline`;
      const shortHtml = `Embedded via TF-IDF + <a href="https://proceedings.neurips.cc/paper_files/paper/2001/file/f106b7f99d2cb30c3db1c3cc0fde9ccb-Paper.pdf" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Laplacian eigenmaps</a>, clustered by k-means. <a id="cap-expand" href="#" style="${lnk}">(more)</a>`;
      const longHtml  = `Each post is embedded as a weighted TF-IDF vector over unigrams, bigrams, and trigrams extracted from one-hot vectors over available tags, title/description text, and body prose (stripped of math). These are concatenated and \\(L^2\\)-normalized so weights reflect relative cosine influence. Pairwise cosine similarities are passed through a Gaussian kernel, giving an affinity graph. The 2D layout is computed via <a href="https://proceedings.neurips.cc/paper_files/paper/2001/file/f106b7f99d2cb30c3db1c3cc0fde9ccb-Paper.pdf" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Laplacian eigenmaps</a>. The second and third smallest eigenvectors of the normalized graph Laplacian define a 2D embedding (globally randomly rotated for display). \\(k \\in \\{2,\\ldots,5\\}\\) is chosen to maximize silhouette score, then singleton clusters are merged. Cluster labels are generated from the most frequent non-generic token in that cluster's titles and descriptions. Lines are a minimum spanning tree within each cluster. <a id="cap-collapse" href="#" style="${lnk}">(less)</a>`;

      function setShort() {
        cap.innerHTML = shortHtml;
        if (window.MathJax?.typesetPromise) window.MathJax.typesetPromise([cap]);
        cap.querySelector('#cap-expand').addEventListener('click', e => { e.preventDefault(); setLong(); });
      }
      function setLong() {
        cap.innerHTML = longHtml;
        if (window.MathJax?.typesetPromise) window.MathJax.typesetPromise([cap]);
        cap.querySelector('#cap-collapse').addEventListener('click', e => { e.preventDefault(); setShort(); });
      }

      setShort();
      svgEl.appendChild(cap);
    }
  }

  // ── Toggle + penguin ──────────────────────────────────────────────────────────

  function setup() {
    const btn       = document.getElementById('viz-toggle');
    const container = document.getElementById('constellation-container');
    if (!btn || !container) return;

    let built = false;
    const isOpen = () => container.style.display !== 'none';

    btn.addEventListener('mouseenter', () => { btn.textContent = '🐧 (analysis)'; });
    btn.addEventListener('mouseleave', () => { btn.textContent = isOpen() ? '🐧 (analysis)' : '🐧'; });

    btn.addEventListener('click', () => {
      if (isOpen()) {
        container.style.display = 'none';
        btn.classList.remove('active');
        btn.textContent = '🐧';
      } else {
        container.style.display = 'block';
        btn.classList.add('active');
        btn.textContent = '🐧 (analysis)';
        if (!built) { built = true; buildViz(); }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', setup);
})();

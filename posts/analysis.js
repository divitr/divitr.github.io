// analysis.js — Post Analysis Visualizer (Constellation + Phase Portrait)
// lot of design help from claude code lol

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

  function strippedText(el) {
    if (!el) return '';
    const clone = el.cloneNode(true);
    clone.querySelectorAll('.katex-mathml').forEach(e => e.remove());
    return clone.textContent;
  }

  function extractPosts() {
    return Array.from(document.querySelectorAll('.blog-post-item')).map(el => {
      const link = el.querySelector('h3 a');
      const href = link?.getAttribute('href') ?? '';
      return {
        slug:  href.replace(/^\/posts\//, '').replace(/\/$/, ''),
        title: strippedText(link).replace(/\s*\([^)]*\)\s*$/, '').trim(),
        desc:  strippedText(el.querySelector('.post-description')).trim(),
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
  //
  // lapEmbedFull returns { coords: [u2, u3] pairs, fiedler: u2 }
  // The Fiedler vector u2 is the second eigenvector of the normalized graph Laplacian
  // (the first non-trivial one) — the most discriminative 1D projection.

  function lapEmbedFull(X) {
    const n = X.length;
    if (n < 3) return { coords: X.map((_, i) => [i, 0]), fiedler: X.map((_, i) => i) };

    const BETA = 4; // affinity sharpness: exp(-β·(1−cos))

    // Gaussian affinity on cosine similarity (all cosines ≥ 0 for our non-neg features)
    const Wmat = X.map((xi, i) => X.map((xj, j) => {
      if (i === j) return 0;
      return Math.exp(-BETA * (1 - dot(xi, xj)));
    }));

    // Degree row-sums
    const d        = Wmat.map(row => row.reduce((s, x) => s + x, 0));
    const invSqrtD = d.map(di => di > 0 ? 1 / Math.sqrt(di) : 0);

    // Normalized Laplacian: L = I − D^{-½} W D^{-½}
    const L = Wmat.map((row, i) =>
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
    // u2 is the Fiedler vector — the most discriminative 1D projection of the affinity graph
    return {
      coords:  u1.map((_, i) => [u2[i], u3[i]]),
      fiedler: u2,
    };
  }

  // ── K-means ───────────────────────────────────────────────────────────────────

  function dist2(a, b) { return a.reduce((s, x, i) => s + (x - b[i]) ** 2, 0); }
  function euclid(a, b) { return Math.sqrt(dist2(a, b)); }

  function kmeans2d(pts, k, runs = 100) {
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
      const SIZE_REG = 0.08; // small bias against very large clusters (relative to n)
      for (let iter = 0; iter < 300; iter++) {
        let changed = false;
        const sizes = new Array(k).fill(0);
        for (const l of labels) sizes[l]++;
        for (let i = 0; i < n; i++) {
          let best = 0, bd = Infinity;
          for (let j = 0; j < k; j++) { const d = dist2(pts[i], cents[j]) + SIZE_REG * (sizes[j] / n); if (d < bd) { bd = d; best = j; } }
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
    // Small parsimony penalty per extra cluster — prevents over-splitting on small datasets
    // where k=5 with two 2-post clusters can outscore k=3 on silhouette alone.
    let bestK = kMin, bestScore = -Infinity;
    for (let k = kMin; k <= Math.min(kMax, pts.length - 1); k++) {
      const score = silhouette(pts, kmeans2d(pts, k)) - 0.01 * (k - kMin) ** 2;
      if (score > bestScore) { bestScore = score; bestK = k; }
    }
    return bestK;
  }

  // ── No singleton clusters ─────────────────────────────────────────────────────
  // Iteratively merges any cluster with fewer than 3 posts into the spatially nearest other cluster.

  function fixSingletons(pts, labels) {
    let cur = [...labels];
    let changed = true;
    while (changed) {
      changed = false;
      const counts = {};
      for (const l of cur) counts[l] = (counts[l] ?? 0) + 1;
      const lone = Object.keys(counts).map(Number).find(c => counts[c] < 3);
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

  // ── Merge all-misc clusters ───────────────────────────────────────────────────
  // Misc posts are content-diverse by nature so k-means splits them into small
  // clusters that share no vocabulary and fall back to the "ideas" label.
  // This merges every cluster whose members are ALL tagged misc into one.

  function mergeMiscClusters(posts, labels) {
    const k = Math.max(...labels) + 1;
    const miscClusters = [];
    for (let c = 0; c < k; c++) {
      const idxs = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      if (idxs.length && idxs.every(i => posts[i].tags.includes('misc'))) miscClusters.push(c);
    }
    if (miscClusters.length <= 1) return labels;
    const target = miscClusters[0];
    const merged = labels.map(l => miscClusters.includes(l) ? target : l);
    const unique = [...new Set(merged)].sort((a, b) => a - b);
    const remap  = Object.fromEntries(unique.map((v, i) => [v, i]));
    return merged.map(l => remap[l]);
  }

  // ── Date → opacity ────────────────────────────────────────────────────────────

  function dateOpacities(posts) {
    const ms    = posts.map(p => { const d = new Date(p.date); return isNaN(d) ? null : d.getTime(); });
    const valid = ms.filter(Boolean);
    if (!valid.length) return posts.map(() => 0.85);
    const lo = Math.min(...valid), hi = Math.max(...valid), range = hi - lo || 1;
    return ms.map(m => m == null ? 0.65 : 0.3 + 0.7 * ((m - lo) / range));
  }

  // ── Dot radii by post length ──────────────────────────────────────────────────

  function normLengths(posts) {
    const lens = posts.map(p => p.wordCount ?? 0);
    const lo = Math.min(...lens), hi = Math.max(...lens);
    const range = hi - lo || 1;
    return lens.map(l => 4 + 2 * ((l - lo) / range)); // [4, 6]
  }

  // ── Cluster keyword labels ────────────────────────────────────────────────────

  function clusterKeywords(posts, labels) {
    const k = Math.max(...labels) + 1;
    const TAG_FALLBACK = null; // use tag name directly

    // Uni+bigram token set and bag per post
    function postTokenSet(i) {
      const words = tokenize(`${posts[i].title} ${posts[i].desc}`);
      const bi    = words.slice(0, -1).map((w, j) => w + '_' + words[j + 1]);
      return new Set([...words, ...bi]);
    }
    function postTokenBag(i) {
      const words = tokenize(`${posts[i].title} ${posts[i].desc}`);
      const bi    = words.slice(0, -1).map((w, j) => w + '_' + words[j + 1]);
      return [...words, ...bi];
    }

    const clusterIdxs = Array.from({ length: k }, (_, c) =>
      labels.reduce((a, l, i) => (l === c ? [...a, i] : a), [])
    );

    // Within-cluster doc frequency: how many posts in this cluster contain each term
    const withinDf = clusterIdxs.map(idxs =>
      idxs.reduce((acc, i) => {
        for (const t of postTokenSet(i)) acc[t] = (acc[t] ?? 0) + 1;
        return acc;
      }, {})
    );

    // TF per cluster (raw count / total tokens)
    const tfs = clusterIdxs.map(idxs => {
      const freq = {};
      for (const i of idxs) for (const t of postTokenBag(i)) freq[t] = (freq[t] ?? 0) + 1;
      const len = Object.values(freq).reduce((s, x) => s + x, 0) || 1;
      for (const t in freq) freq[t] /= len;
      return freq;
    });

    // IDF across clusters (each cluster = one doc)
    const df = {};
    for (const freq of tfs) for (const t in freq) df[t] = (df[t] ?? 0) + 1;

    // Bigram penalty: score bigrams at 80% to bias toward unigrams when competitive
    const BIGRAM_BIAS = 0.8;

    // Score ranked candidates per cluster (before deduplication)
    const allCandidates = clusterIdxs.map((idxs, c) => {
      if (!idxs.length) return [];
      const minSupport = Math.min(2, idxs.length);
      const wdf = withinDf[c];
      const freq = tfs[c];
      return Object.entries(freq)
        .filter(([t]) => (wdf[t] ?? 0) >= minSupport)
        .map(([t, tf]) => {
          const isBigram = t.includes('_');
          const tfidf = tf * Math.log((k + 1) / df[t]);
          return [t, isBigram ? tfidf * BIGRAM_BIAS : tfidf];
        })
        .sort((a, b) => b[1] - a[1]);
    });

    // Greedy deduplication: assign labels in order of confidence (highest top score first),
    // each cluster picks its best unclaimed term.
    const assigned = new Array(k).fill(null);
    const used = new Set();
    const order = allCandidates
      .map((cands, c) => [c, cands[0]?.[1] ?? -Infinity])
      .sort((a, b) => b[1] - a[1])
      .map(([c]) => c);

    for (const c of order) {
      const idxs = clusterIdxs[c];
      if (!idxs.length) { assigned[c] = 'misc'; continue; }

      const top = allCandidates[c].find(([t]) => !used.has(t))?.[0];
      if (top) { assigned[c] = top.replace(/_/g, ' '); used.add(top); continue; }

      // Fallback to dominant tag
      const tagFreq = {};
      for (const i of idxs) for (const t of posts[i].tags) tagFreq[t] = (tagFreq[t] ?? 0) + 1;
      const topTag = Object.entries(tagFreq).sort((a, b) => b[1] - a[1])[0]?.[0];
      assigned[c] = (topTag ?? 'misc').toLowerCase();
    }

    return assigned;
  }

  // ── Shared dot renderer ───────────────────────────────────────────────────────
  // Renders all dots into root SVG element. Each dot: halo, filled circle, emoji.
  // On hover: dot fades out, emoji fades in, other-cluster dots dim to 12%.
  // Returns dotMeta array { dot, emo, halo, op, cluster }.

  function renderDots(root, tooltipEl, posts, scaled, labels, radii, opacities, plotSvgEl) {
    const dotMeta = [];
    for (let i = 0; i < posts.length; i++) {
      const [x, y] = scaled[i];
      const color  = COLORS[labels[i] % COLORS.length];
      const op     = opacities[i];
      const r      = radii[i];
      const g      = svg('g', { style: 'cursor:pointer' });
      const halo   = svg('circle', { cx: x, cy: y, r: r + 7, fill: color, opacity: 0, style: 'transition:opacity 0.45s ease-in-out' });
      const dot    = svg('circle', { cx: x, cy: y, r, fill: color, opacity: op, style: 'transition:opacity 0.45s ease-in-out' });
      const emo    = svg('text', {
        x, y, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
        'font-size': 13, opacity: 0, style: 'pointer-events:none;user-select:none;transition:opacity 0.45s ease-in-out',
      });
      emo.textContent = posts[i].emoji;
      g.appendChild(halo); g.appendChild(dot); g.appendChild(emo);
      dotMeta.push({ dot, emo, halo, op, cluster: labels[i] });

      g.addEventListener('mouseenter', e => {
        dot.setAttribute('opacity', 0); emo.setAttribute('opacity', 1); halo.setAttribute('opacity', 0.12);
        // dim dots outside this cluster
        for (const m of dotMeta)
          if (m.cluster !== labels[i]) { m.dot.setAttribute('opacity', m.op * 0.12); m.emo.setAttribute('opacity', 0); }
        showTooltip(tooltipEl, posts[i], e, plotSvgEl);
      });
      g.addEventListener('mousemove', e => moveTooltip(tooltipEl, e, plotSvgEl));
      g.addEventListener('mouseleave', () => {
        dot.setAttribute('opacity', op); emo.setAttribute('opacity', 0); halo.setAttribute('opacity', 0);
        // restore all dots
        for (const m of dotMeta) m.dot.setAttribute('opacity', m.op);
        hideTooltip(tooltipEl);
      });
      g.addEventListener('click', () => { window.location.href = posts[i].href; });
      root.appendChild(g);
    }
    return dotMeta;
  }

  // ── Tooltip ───────────────────────────────────────────────────────────────────

  function showTooltip(el, post, e, plotSvgEl) {
    el.innerHTML = `
      <div style="margin-bottom:0.15rem">
        <a href="${post.href}" style="color:#4a4a4a;text-decoration:none;font-weight:500;font-size:0.88rem;line-height:1.3"
           onmouseenter="this.style.textDecoration='underline'" onmouseleave="this.style.textDecoration='none'"
        >${post.title}</a>
      </div>
      <div style="color:#aaa;font-size:0.76rem;margin-bottom:0.2rem">${post.date}</div>
      <div style="color:#666;font-size:0.81rem;line-height:1.4">${post.desc}</div>
      <div style="margin-top:0.3rem">${post.tags.map(t =>
        `<span style="color:#bbb;font-size:0.73rem;margin-right:0.3rem">#${t}</span>`).join('')}</div>`;
    el.style.opacity = '1'; el.style.pointerEvents = 'none';
    moveTooltip(el, e, plotSvgEl);
  }

  function moveTooltip(el, e, plotSvgEl) {
    const parent = el.offsetParent;
    const parentRect = parent?.getBoundingClientRect() ?? { left: 0, top: 0, right: 800, bottom: 500 };
    const plotRect = plotSvgEl?.getBoundingClientRect() ?? parentRect;

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

  // ── Caption injector ──────────────────────────────────────────────────────────
  // Injects an expand/collapse caption paragraph below the SVG container.
  // Checks for existing element by id to avoid double-inject.

  function injectCaption(container, id, shortHtml, longHtml) {
    if (document.getElementById(id)) return;
    const cap = document.createElement('p');
    cap.id = id;
    cap.className = 'constellation-caption';

    const renderMath = el => {
      if (window.renderMathInElement) {
        renderMathInElement(el, { delimiters: [
          { left: '\\(', right: '\\)', display: false },
          { left: '\\[', right: '\\]', display: true },
        ]});
      }
    };
    function setShort() {
      cap.innerHTML = shortHtml;
      renderMath(cap);
      const expander = cap.querySelector('[data-expand]');
      if (expander) expander.addEventListener('click', e => { e.preventDefault(); setLong(); });
    }
    function setLong() {
      cap.innerHTML = longHtml;
      renderMath(cap);
      const collapser = cap.querySelector('[data-collapse]');
      if (collapser) collapser.addEventListener('click', e => { e.preventDefault(); setShort(); });
    }

    setShort();
    container.appendChild(cap);
  }

  // ── Constellation-specific helpers ────────────────────────────────────────────

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

  // ── Gravitational settling ────────────────────────────────────────────────────
  // Each node has a "mass" = radius × opacity (length × recency).
  // Heavy posts are gently pulled toward the mass-weighted centroid;
  // light / old posts drift slightly outward. Strength ≈ 0.07 keeps it invisible
  // to a casual eye but gives the layout a subtle organic density gradient.

  function applyGravity(coords, labels, radii, opacities, strength = 0.07) {
    const masses = radii.map((r, i) => r * opacities[i]);
    const k      = Math.max(...labels) + 1;

    // Mass-weighted centroid per cluster
    const centroids = Array.from({ length: k }, (_, c) => {
      const idxs  = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      const totalM = idxs.reduce((s, i) => s + masses[i], 0) || 1;
      return [
        idxs.reduce((s, i) => s + coords[i][0] * masses[i], 0) / totalM,
        idxs.reduce((s, i) => s + coords[i][1] * masses[i], 0) / totalM,
      ];
    });

    const clusterMeanM = Array.from({ length: k }, (_, c) => {
      const idxs = labels.reduce((a, l, i) => (l === c ? [...a, i] : a), []);
      return idxs.reduce((s, i) => s + masses[i], 0) / (idxs.length || 1);
    });

    return coords.map(([x, y], i) => {
      const [cx, cy] = centroids[labels[i]];
      const pull     = strength * (masses[i] / clusterMeanM[labels[i]]);
      return [x + pull * (cx - x), y + pull * (cy - y)];
    });
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

  // ── Render: Constellation ─────────────────────────────────────────────────────

  function renderConstellation(svgContainer, tooltipEl, posts, embed2d, labels) {
    const opacities = dateOpacities(posts);
    const radii     = normLengths(posts);
    const scaled    = repulse(applyGravity(scaleCoords(jitterClusters(embed2d, labels)), labels, radii, opacities));
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

    // Dots (via shared renderer, before labelLayer so labels render on top)
    const dotMeta = renderDots(root, tooltipEl, posts, scaled, labels, radii, opacities, root);

    // Label layer on top of dots
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
    legend.textContent = 'opacity indicates recency, size indicates length';
    root.appendChild(legend);

    svgContainer.innerHTML = '';
    svgContainer.appendChild(root);
  }

  // ── Tag ordering via co-occurrence Fiedler vector ────────────────────────────
  // Build a 5×5 tag co-occurrence matrix, compute its normalized graph Laplacian,
  // and take the Fiedler vector (smallest non-trivial eigenvector) as the 1D
  // ordering. Tags that frequently co-occur end up adjacent on the axis.
  // Returns { tag → [0,1] } with math-family tags oriented toward 0 (top).

  function computeTagOrdering(posts) {
    const tags = KNOWN_TAGS; // ['ml','math','physics','stats','misc']
    const n    = tags.length;
    const C    = Array.from({ length: n }, () => new Array(n).fill(0));
    for (const p of posts) {
      const idxs = p.tags.map(t => tags.indexOf(t)).filter(i => i >= 0);
      for (const i of idxs) for (const j of idxs) if (i !== j) C[i][j]++;
    }
    // Small regularisation so isolated tags are still connected
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if (i !== j) C[i][j] += 0.1;
    const deg      = C.map(row => row.reduce((s, x) => s + x, 0));
    const invSqrtD = deg.map(d => d > 0 ? 1 / Math.sqrt(d) : 0);
    const L        = C.map((row, i) => row.map((w, j) => (i === j ? 1 : 0) - invSqrtD[i] * w * invSqrtD[j]));
    const { lam: lmax } = powerIter(L, tags.map((_, i) => Math.sin(i * 1.7 + 0.3)));
    const M              = L.map((row, i) => row.map((x, j) => (i === j ? lmax : 0) - x));
    const { v: u1, lam: m1 } = powerIter(M, tags.map((_, i) => Math.sin(i * 1.3 + 0.7)));
    const M2             = deflate(M, u1, m1);
    const { v: u2 }      = powerIter(M2, tags.map((_, i) => Math.cos(i * 2.1 + 0.4)));
    // Normalise to [0,1], orient so math < misc (theoretical at top)
    const lo = Math.min(...u2), hi = Math.max(...u2), range = hi - lo || 1;
    let norm = u2.map(v => (v - lo) / range);
    if (norm[tags.indexOf('math')] > norm[tags.indexOf('misc')]) norm = norm.map(v => 1 - v);
    return Object.fromEntries(tags.map((t, i) => [t, norm[i]]));
  }

  // ── Catmull-Rom spline → SVG path ────────────────────────────────────────────

  function catmullRomPath(pts) {
    if (pts.length < 2) return '';
    if (pts.length === 2) return `M ${pts[0][0]},${pts[0][1]} L ${pts[1][0]},${pts[1][1]}`;
    // Phantom endpoints
    const p = [
      [2*pts[0][0] - pts[1][0], 2*pts[0][1] - pts[1][1]],
      ...pts,
      [2*pts[pts.length-1][0] - pts[pts.length-2][0], 2*pts[pts.length-1][1] - pts[pts.length-2][1]],
    ];
    let d = `M ${p[1][0].toFixed(2)},${p[1][1].toFixed(2)}`;
    for (let i = 1; i < p.length - 2; i++) {
      const cp1x = p[i][0] + (p[i+1][0] - p[i-1][0]) / 6;
      const cp1y = p[i][1] + (p[i+1][1] - p[i-1][1]) / 6;
      const cp2x = p[i+1][0] - (p[i+2][0] - p[i][0]) / 6;
      const cp2y = p[i+1][1] - (p[i+2][1] - p[i][1]) / 6;
      d += ` C ${cp1x.toFixed(2)},${cp1y.toFixed(2)} ${cp2x.toFixed(2)},${cp2y.toFixed(2)} ${p[i+1][0].toFixed(2)},${p[i+1][1].toFixed(2)}`;
    }
    return d;
  }

  // ── Shared KDE computation ────────────────────────────────────────────────────

  function computeKDEs(posts, tagsOrdered) {
    const times = posts.map(p => new Date(p.date).getTime()).filter(t => t > 0 && !isNaN(t));
    if (!times.length) return null;
    const tMin = Math.min(...times), tMax = Math.max(...times);

    function silverman(ts) {
      const n = ts.length;
      if (n < 2) return (tMax - tMin) / 2 || 1e12;
      const m = ts.reduce((a, b) => a + b) / n;
      const s = Math.sqrt(ts.reduce((acc, t) => acc + (t - m) ** 2, 0) / n);
      const sorted = [...ts].sort((a, b) => a - b);
      const q1 = sorted[Math.floor(n * 0.25)], q3 = sorted[Math.floor(n * 0.75)];
      const iqr = (q3 - q1) || s;
      return 0.9 * Math.min(s, iqr / 1.34) * n ** (-0.2);
    }

    const globalBW = silverman(times);
    const pad_t = globalBW * 1.2;
    const gMin = tMin - pad_t, gMax = tMax + pad_t;
    const GRID = 300;
    const grid = Array.from({ length: GRID }, (_, i) => gMin + (i / (GRID - 1)) * (gMax - gMin));

    const kdes = {}, tagBW = {}, tagN = {};
    let globalPeak = 0;
    for (const tag of tagsOrdered) {
      const ts = posts
        .filter(p => p.tags.includes(tag))
        .map(p => new Date(p.date).getTime())
        .filter(t => t > 0 && !isNaN(t));
      tagN[tag] = ts.length;
      if (!ts.length) { kdes[tag] = grid.map(() => 0); tagBW[tag] = globalBW; continue; }
      const h = Math.max(silverman(ts), globalBW * 0.5);
      tagBW[tag] = h;
      const norm = ts.length * h * Math.sqrt(2 * Math.PI);
      kdes[tag] = grid.map(t => ts.reduce((s, ti) => s + Math.exp(-0.5 * ((t - ti) / h) ** 2), 0) / norm);
      globalPeak = Math.max(globalPeak, ...kdes[tag]);
    }

    return { kdes, tagBW, tagN, grid, gMin, gMax, tMin, tMax, globalPeak, globalBW };
  }

  // ── Render: Temporal Drift (ridgeline KDE) ───────────────────────────────────
  // Per-tag Gaussian KDE over publication time, ordered by Fiedler vector.
  // CM thread colored by instantaneous Shannon entropy — dark = focused, light = diffuse.
  // Faint uncertainty bands show ±1σ of the GP posterior around each KDE curve.

  function renderPhase(svgContainer, tooltipEl, posts, _unused, _labels, tagY) {
    const TAGS_ORDERED = Object.entries(tagY).sort((a, b) => a[1] - b[1]).map(([t]) => t);
    const PALETTE = ['#7a8fa6', '#6a9a7a', '#a09060', '#8a7aaa', '#a07060'];
    const TAG_COLOR = Object.fromEntries(TAGS_ORDERED.map((t, i) => [t, PALETTE[i % PALETTE.length]]));

    const kdeData = computeKDEs(posts, TAGS_ORDERED);
    if (!kdeData) return;
    const { kdes, tagBW, tagN, grid, gMin, gMax, tMin, tMax, globalPeak, globalBW } = kdeData;
    const nTags = TAGS_ORDERED.length;
    const GRID  = grid.length;

    // Instantaneous entropy: H(t) = -Σ pₖ log pₖ / log(n), normalized to [0,1]
    const entropy = grid.map((_, gi) => {
      const vals = TAGS_ORDERED.map(tag => kdes[tag][gi]);
      const total = vals.reduce((a, b) => a + b, 0);
      if (total < 1e-30) return 1;
      const ps = vals.map(v => v / total);
      const H  = -ps.reduce((s, p) => s + (p > 0 ? p * Math.log(p) : 0), 0);
      return H / Math.log(nTags);
    });

    // Layout
    const PADL = 62, PADR = 30, PADT = 24, PADB = 44;
    const plotW = W - PADL - PADR;
    const stripH = (H - PADT - PADB) / nTags;
    const peakH  = stripH * 0.88;
    const scale  = globalPeak > 0 ? peakH / globalPeak : 1;

    const sx   = t => PADL + ((t - gMin) / (gMax - gMin)) * plotW;
    const base = i => PADT + (i + 1) * stripH;
    const AXIS_Y = PADT + nTags * stripH + 18;

    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', style: 'display:block' });
    root.appendChild(svg('rect', { x: 0, y: 0, width: W, height: H, fill: '#fafafa', rx: 3 }));

    // ── GP Regression for CM thread ──────────────────────────────────────────────
    // Each post is one observation: (time t_i, mean tag-baseline y_i).
    // The GP posterior mean is the smooth inferred trajectory; posterior std is
    // NARROW near posts (data constrains it) and WIDE between posts (genuine uncertainty).
    const gpObs = posts.map(p => {
      const t  = new Date(p.date).getTime();
      if (!t || isNaN(t)) return null;
      const bs = p.tags.map(tag => { const k = TAGS_ORDERED.indexOf(tag); return k >= 0 ? base(k) : null; }).filter(b => b !== null);
      return bs.length ? [t, bs.reduce((a, b) => a + b) / bs.length] : null;
    }).filter(Boolean);

    const gpN    = gpObs.length;
    const gpT    = gpObs.map(o => o[0]);
    const gpY    = gpObs.map(o => o[1]);
    const gpMu   = gpY.reduce((a, b) => a + b) / gpN;
    const gpSf2  = gpY.reduce((s, y) => s + (y - gpMu) ** 2, 0) / gpN || (stripH * stripH * 0.1);
    const gpSn2  = gpSf2 * 0.05;    // small observation noise
    const gpL    = globalBW;  // SE kernel length scale — smooth, no oscillation

    const gpK = (t1, t2) => gpSf2 * Math.exp(-0.5 * ((t1 - t2) / gpL) ** 2);

    // Build K(T,T) + σ_n² I and invert (n ≈ 14, trivial)
    const Kmat = Array.from({length: gpN}, (_, i) =>
      Array.from({length: gpN}, (_, j) => gpK(gpT[i], gpT[j]) + (i === j ? gpSn2 : 0))
    );
    function matInv(M) {
      const n = M.length;
      const A = M.map((row, i) => [...row, ...Array.from({length: n}, (_, j) => i === j ? 1 : 0)]);
      for (let col = 0; col < n; col++) {
        let mr = col;
        for (let r = col + 1; r < n; r++) if (Math.abs(A[r][col]) > Math.abs(A[mr][col])) mr = r;
        [A[col], A[mr]] = [A[mr], A[col]];
        const piv = A[col][col]; if (Math.abs(piv) < 1e-12) continue;
        for (let j = col; j < 2*n; j++) A[col][j] /= piv;
        for (let r = 0; r < n; r++) { if (r === col) continue; const f = A[r][col]; for (let j = col; j < 2*n; j++) A[r][j] -= f * A[col][j]; }
      }
      return A.map(row => row.slice(n));
    }
    const Kinv  = matInv(Kmat);
    const alpha = Kinv.map(row => row.reduce((s, v, j) => s + v * (gpY[j] - gpMu), 0));

    // Posterior mean + std at each grid point
    const gpPost = grid.map(t => {
      const kstar     = gpT.map(ti => gpK(t, ti));
      const mean      = gpMu + kstar.reduce((s, k, j) => s + k * alpha[j], 0);
      const Kinvk     = Kinv.map(row => row.reduce((s, v, j) => s + v * kstar[j], 0));
      const variance  = Math.max(0, gpSf2 - kstar.reduce((s, k, j) => s + k * Kinvk[j], 0));
      return [sx(t), mean, Math.sqrt(variance)];
    });
    const cmPts = gpPost.map(([x, y]) => [x, y]);

    // Draw strips bottom-to-top
    for (let i = nTags - 1; i >= 0; i--) {
      const tag   = TAGS_ORDERED[i];
      const color = TAG_COLOR[tag];
      const kde   = kdes[tag];
      const by    = base(i);
      const pts   = grid.map((_, gi) => [sx(grid[gi]), by - kde[gi] * scale]);

      // White mask — hides bleed from strips drawn earlier
      root.appendChild(svg('rect', {
        x: PADL, y: by - peakH - 8, width: plotW, height: peakH + 8, fill: '#fafafa',
      }));

      // Main filled area
      const areaD = `M ${PADL},${by} ` +
        pts.map(([x, y]) => `L ${x.toFixed(1)},${y.toFixed(1)}`).join(' ') +
        ` L ${PADL + plotW},${by} Z`;
      root.appendChild(svg('path', { d: areaD, fill: color, opacity: 0.13 }));

      // Curve stroke
      const curveD = 'M ' + pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L ');
      root.appendChild(svg('path', { d: curveD, fill: 'none', stroke: color, 'stroke-width': 1.3, opacity: 0.58 }));

      // Baseline
      root.appendChild(svg('line', { x1: PADL, y1: by, x2: PADL + plotW, y2: by, stroke: '#e4e4e0', 'stroke-width': 0.5 }));

      // Tag label
      const lbl = svg('text', {
        x: PADL - 8, y: by, 'text-anchor': 'end', 'dominant-baseline': 'auto',
        'font-size': 9, fill: color, opacity: 0.8,
        'font-family': 'Charter, Georgia, serif', 'font-style': 'italic', 'letter-spacing': '0.04em',
      });
      lbl.textContent = tag;
      root.appendChild(lbl);

      // Post ticks + hit areas
      for (const p of posts.filter(q => q.tags.includes(tag))) {
        const t = new Date(p.date).getTime();
        if (!t || isNaN(t)) continue;
        const px = sx(t);
        root.appendChild(svg('line', { x1: px, y1: by - 1, x2: px, y2: by + 5, stroke: color, 'stroke-width': 1.2, opacity: 0.5 }));
        const hit = svg('rect', { x: px - 7, y: by - 14, width: 14, height: 24, fill: 'transparent', style: 'cursor:pointer' });
        hit.addEventListener('mouseenter', e => showTooltip(tooltipEl, p, e, svgContainer));
        hit.addEventListener('mousemove',  e => moveTooltip(tooltipEl, e, svgContainer));
        hit.addEventListener('mouseleave',  () => hideTooltip(tooltipEl));
        root.appendChild(hit);
      }
    }

    // GP posterior ±1σ band — narrow near posts, wide in gaps
    const bandD = 'M ' + gpPost.map(([x, y, s]) => `${x.toFixed(1)},${(y - s).toFixed(1)}`).join(' L ') +
      ' L ' + gpPost.slice().reverse().map(([x, y, s]) => `${x.toFixed(1)},${(y + s).toFixed(1)}`).join(' L ') + ' Z';
    root.appendChild(svg('path', { d: bandD, fill: '#888', opacity: 0.13, 'pointer-events': 'none' }));

    // GP posterior mean colored by entropy — rendered as chunked paths (not individual line
    // elements) to avoid seam artifacts at opacity-varying joints. Each chunk of ~12 points
    // shares one averaged entropy color, so adjacent same-color segments merge seamlessly.
    {
      const CHUNK = 12;
      for (let start = 0; start < GRID - 1; start += CHUNK) {
        const end = Math.min(start + CHUNK, GRID - 1);
        const midGi = Math.floor((start + end) / 2);
        const He = entropy[midGi];
        const gray = Math.round(20 + He * 168);
        const gx   = gray.toString(16).padStart(2, '0');
        const op   = 0.88 - He * 0.68;
        const d = 'M ' + gpPost.slice(start, end + 1)
          .map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
        root.appendChild(svg('path', {
          d, fill: 'none', stroke: `#${gx}${gx}${gx}`, 'stroke-width': 1.6,
          opacity: op.toFixed(3), 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
          'pointer-events': 'none',
        }));
      }
    }

    // "opacity indicates entropy" — textPath curved along right tail of CM thread, 5px above.
    // Blur layer: blurred white text creates soft fog; sharp dark text on top for readability.
    // The <path> inside <defs> is correctly invisible (SVG spec); dotted appearance was from
    // segment seams above, now fixed.
    {
      const aS = Math.floor(GRID * 0.55), aE = GRID - 1;
      const annotId    = 'kde-annot-' + Math.random().toString(36).slice(2);
      const blurFiltId = 'kde-blur-'  + Math.random().toString(36).slice(2);
      const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');

      const annotPathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      annotPathEl.setAttribute('id', annotId);
      annotPathEl.setAttribute('d', gpPost.slice(aS, aE + 1)
        .map(([x, y], i) => `${i ? 'L' : 'M'} ${x.toFixed(1)},${(y - 5).toFixed(1)}`).join(' '));
      annotPathEl.setAttribute('fill', 'none');
      annotPathEl.setAttribute('stroke', 'none');
      defs.appendChild(annotPathEl);

      const filt = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
      filt.setAttribute('id', blurFiltId);
      filt.setAttribute('x', '-10%'); filt.setAttribute('y', '-80%');
      filt.setAttribute('width', '120%'); filt.setAttribute('height', '360%');
      const feBlur = document.createElementNS('http://www.w3.org/2000/svg', 'feGaussianBlur');
      feBlur.setAttribute('stdDeviation', '4');
      filt.appendChild(feBlur);
      defs.appendChild(filt);
      root.appendChild(defs);

      const makeTP = (fill, filtUrl) => {
        const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        textEl.setAttribute('font-size', '7.5');
        textEl.setAttribute('fill', fill);
        textEl.setAttribute('font-family', 'Charter, Georgia, serif');
        textEl.setAttribute('font-style', 'italic');
        if (filtUrl) textEl.setAttribute('filter', filtUrl);
        const tp = document.createElementNS('http://www.w3.org/2000/svg', 'textPath');
        tp.setAttribute('href', '#' + annotId);
        tp.setAttribute('startOffset', '96%');
        tp.setAttribute('text-anchor', 'end');
        tp.textContent = 'opacity indicates entropy';
        textEl.appendChild(tp);
        return textEl;
      };
      root.appendChild(makeTP('white', `url(#${blurFiltId})`));  // blurred white fog
      root.appendChild(makeTP('#666', null));                      // sharp dark text
    }

    // X-axis date labels (no tick line)
    const MO = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const yr0 = new Date(tMin).getFullYear(), mo0 = new Date(tMin).getMonth() < 6 ? 0 : 6;
    outer: for (let yr = yr0; yr <= new Date(tMax).getFullYear() + 1; yr++) {
      for (const mo of [0, 6]) {
        if (yr === yr0 && mo < mo0) continue;
        const t = new Date(yr, mo, 1).getTime();
        if (t > tMax + 60 * 24 * 3600000) break outer;
        const px = sx(t);
        if (px < PADL - 1 || px > PADL + plotW + 1) continue;
        const tl = svg('text', { x: px, y: AXIS_Y + 9, 'text-anchor': 'middle', 'font-size': 9, fill: '#c8c8c4', 'font-family': 'Charter, Georgia, serif', 'font-style': 'italic' });
        tl.textContent = `${MO[mo]} ${yr}`;
        root.appendChild(tl);
      }
    }

    svgContainer.innerHTML = '';
    svgContainer.appendChild(root);
  }

  // ── Render: Entropy + Fisher-Rao Speed ───────────────────────────────────────
  // At each moment t the KDE defines a probability distribution p(t) over tags.
  // Shannon entropy H(t) = -Σ pₖ log pₖ / log n measures focus (low = concentrated).
  // Fisher-Rao speed ‖ṗ‖_FR = ‖d√p/dt‖₂ is the velocity in the information-geometric
  // metric on Δ⁴ — the sphere under the Hellinger embedding. Spikes = topic pivots.

  function renderSimplex(svgContainer, tooltipEl, posts, _unused, _labels, tagY) {
    const TAGS_ORDERED = Object.entries(tagY).sort((a, b) => a[1] - b[1]).map(([t]) => t);
    const PALETTE = ['#7a8fa6', '#6a9a7a', '#a09060', '#8a7aaa', '#a07060'];
    const TAG_COLOR = Object.fromEntries(TAGS_ORDERED.map((t, i) => [t, PALETTE[i % PALETTE.length]]));
    const nTags = TAGS_ORDERED.length;

    const kdeData = computeKDEs(posts, TAGS_ORDERED);
    if (!kdeData) return;
    const { kdes, grid, gMin, gMax, tMin, tMax } = kdeData;
    const GRID = grid.length;

    // ── Normalized probabilities + Hellinger coordinates ──────────────────────
    // p_k(t) = KDE_k(t) / Σ KDE_j(t)    h_k(t) = √p_k(t)  (Hellinger embedding)
    const probs = grid.map((_, gi) => {
      const vals = TAGS_ORDERED.map(tag => kdes[tag][gi]);
      const total = vals.reduce((a, b) => a + b, 0);
      return total > 1e-30 ? vals.map(v => v / total) : vals.map(() => 1 / nTags);
    });
    const hellinger = probs.map(p => p.map(v => Math.sqrt(v)));

    // ── Shannon entropy H(t) normalized to [0, 1] ─────────────────────────────
    // H = 1 when attention is uniform across all tags; 0 when fully concentrated.
    const entropy = probs.map(p =>
      -p.reduce((s, pk) => s + (pk > 1e-15 ? pk * Math.log(pk) : 0), 0) / Math.log(nTags)
    );

    // ── Fisher-Rao speed ‖ṗ‖_FR = ‖d√p/dt‖₂ via central differences ─────────
    // The Fisher information metric on Δⁿ⁻¹ is the round metric on the positive
    // orthant of Sⁿ⁻¹ under the Hellinger embedding h_k = √p_k — so Euclidean
    // distance in Hellinger space is the geodesic distance in information geometry.
    const frSpeed = grid.map((_, gi) => {
      const hP = hellinger[Math.min(gi + 1, GRID - 1)];
      const hM = hellinger[Math.max(gi - 1, 0)];
      const sc = (gi === 0 || gi === GRID - 1) ? 1 : 2;
      return Math.sqrt(hM.reduce((s, _, k) => s + ((hP[k] - hM[k]) / sc) ** 2, 0));
    });

    // Normalize speed to [0, 1] over active window
    const giStart = grid.findIndex(t => t >= tMin);
    const giEnd   = grid.reduce((idx, t, i) => t <= tMax ? i : idx, 0);
    const gS = Math.max(0, giStart), gE = Math.min(GRID - 1, giEnd);
    const maxSpeed = frSpeed.slice(gS, gE + 1).reduce((m, s) => Math.max(m, s), 1e-15);
    const normSpeed = frSpeed.map(s => s / maxSpeed);

    // ── Layout ─────────────────────────────────────────────────────────────────
    const PADL = 50, PADR = 32, PADT = 30, PADB = 48;
    const plotW = W - PADL - PADR;
    const plotH = H - PADT - PADB;
    const AXIS_Y = PADT + plotH;
    const sx = t => PADL + ((t - gMin) / (gMax - gMin)) * plotW;
    const sy = v => PADT + (1 - v) * plotH;

    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', style: 'display:block' });
    root.appendChild(svg('rect', { x: 0, y: 0, width: W, height: H, fill: '#fafafa', rx: 3 }));

    // Subtle horizontal gridlines
    for (const yv of [0.25, 0.5, 0.75, 1.0]) {
      root.appendChild(svg('line', {
        x1: PADL, y1: sy(yv).toFixed(1), x2: PADL + plotW, y2: sy(yv).toFixed(1),
        stroke: yv === 1.0 ? '#e0e0dc' : '#ebebeb', 'stroke-width': 0.7,
        'pointer-events': 'none',
      }));
    }
    // Baseline
    root.appendChild(svg('line', {
      x1: PADL, y1: AXIS_Y, x2: PADL + plotW, y2: AXIS_Y,
      stroke: '#ddd', 'stroke-width': 0.8, 'pointer-events': 'none',
    }));

    // ── Entropy curve (filled area + Catmull-Rom stroke) ──────────────────────
    const ENTROPY_COLOR = '#7a8fa6';
    {
      const pts = [];
      for (let gi = gS; gi <= gE; gi++) pts.push([sx(grid[gi]), sy(entropy[gi])]);
      if (pts.length > 1) {
        const first = pts[0], last = pts[pts.length - 1];
        const areaD = `M ${first[0].toFixed(1)},${AXIS_Y} L ${first[0].toFixed(1)},${first[1].toFixed(1)} ` +
          pts.slice(1).map(([x, y]) => `L ${x.toFixed(1)},${y.toFixed(1)}`).join(' ') +
          ` L ${last[0].toFixed(1)},${AXIS_Y} Z`;
        root.appendChild(svg('path', { d: areaD, fill: ENTROPY_COLOR, opacity: '0.10', 'pointer-events': 'none' }));
        root.appendChild(svg('path', {
          d: catmullRomPath(pts), fill: 'none',
          stroke: ENTROPY_COLOR, 'stroke-width': 1.5, opacity: '0.75',
          'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'pointer-events': 'none',
        }));
      }
    }

    // ── Fisher-Rao speed curve (stroke only) ──────────────────────────────────
    const SPEED_COLOR = '#a07060';
    {
      const pts = [];
      for (let gi = gS; gi <= gE; gi++) pts.push([sx(grid[gi]), sy(normSpeed[gi])]);
      if (pts.length > 1) {
        root.appendChild(svg('path', {
          d: catmullRomPath(pts), fill: 'none',
          stroke: SPEED_COLOR, 'stroke-width': 1.3, opacity: '0.70',
          'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'pointer-events': 'none',
        }));
      }
    }

    // ── Curve labels (right margin) ────────────────────────────────────────────
    const labelX = PADL + plotW + 5;
    for (const [val, color, label] of [
      [entropy[gE],    ENTROPY_COLOR, 'H(t)'],
      [normSpeed[gE],  SPEED_COLOR,   '‖ṗ‖'],
    ]) {
      const lbl = svg('text', {
        x: labelX, y: (sy(val) + 3.5).toFixed(1),
        'font-size': 9, fill: color, opacity: '0.85',
        'font-family': 'Charter, Georgia, serif', 'font-style': 'italic',
      });
      lbl.textContent = label;
      root.appendChild(lbl);
    }

    // ── Y-axis labels ──────────────────────────────────────────────────────────
    for (const [v, label] of [[0, '0'], [0.5, '½'], [1, '1']]) {
      const t = svg('text', {
        x: PADL - 6, y: (sy(v) + 3.5).toFixed(1), 'text-anchor': 'end', 'font-size': 8.5,
        fill: '#c8c8c4', 'font-family': 'Charter, Georgia, serif', 'font-style': 'italic',
      });
      t.textContent = label;
      root.appendChild(t);
    }

    // ── Post ticks + hit areas (same style as KDE view) ───────────────────────
    for (const p of posts) {
      const t = new Date(p.date).getTime();
      if (!t || isNaN(t) || t < tMin || t > tMax) continue;
      const px = sx(t);
      const primaryTag = p.tags.find(tg => TAGS_ORDERED.includes(tg)) ?? TAGS_ORDERED[0];
      const color = TAG_COLOR[primaryTag];
      root.appendChild(svg('line', {
        x1: px.toFixed(1), y1: (AXIS_Y + 1).toFixed(1), x2: px.toFixed(1), y2: (AXIS_Y + 6).toFixed(1),
        stroke: color, 'stroke-width': 1.3, opacity: '0.6',
      }));
      const hit = svg('rect', {
        x: (px - 7).toFixed(1), y: (AXIS_Y - 14).toFixed(1), width: 14, height: 24,
        fill: 'transparent', style: 'cursor:pointer',
      });
      hit.addEventListener('mouseenter', e => showTooltip(tooltipEl, p, e, svgContainer));
      hit.addEventListener('mousemove',  e => moveTooltip(tooltipEl, e, svgContainer));
      hit.addEventListener('mouseleave', () => hideTooltip(tooltipEl));
      hit.addEventListener('click', () => { window.location.href = p.href; });
      root.appendChild(hit);
    }

    // ── X-axis date labels ─────────────────────────────────────────────────────
    const MO = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const yr0 = new Date(tMin).getFullYear(), mo0 = new Date(tMin).getMonth() < 6 ? 0 : 6;
    outer: for (let yr = yr0; yr <= new Date(tMax).getFullYear() + 1; yr++) {
      for (const mo of [0, 6]) {
        if (yr === yr0 && mo < mo0) continue;
        const t = new Date(yr, mo, 1).getTime();
        if (t > tMax + 60 * 24 * 3600000) break outer;
        const px = sx(t);
        if (px < PADL - 1 || px > PADL + plotW + 1) continue;
        const tl = svg('text', {
          x: px.toFixed(1), y: AXIS_Y + 16,
          'text-anchor': 'middle', 'font-size': 9, fill: '#c8c8c4',
          'font-family': 'Charter, Georgia, serif', 'font-style': 'italic',
        });
        tl.textContent = `${MO[mo]} ${yr}`;
        root.appendChild(tl);
      }
    }

    svgContainer.innerHTML = '';
    svgContainer.appendChild(root);
  }

  // ── Tab injector ──────────────────────────────────────────────────────────────

  function injectTabs(container, onSwitch) {
    if (document.getElementById('analysis-tabs')) {
      return { setActive() {} };
    }

    const tabsEl = document.createElement('div');
    tabsEl.id = 'analysis-tabs';
    tabsEl.style.cssText = 'display:flex;gap:0.8rem;align-items:baseline;justify-content:flex-end;margin-bottom:0.6rem;padding-top:0.3rem';

    const base = 'font-size:11px;letter-spacing:0.05em;font-family:Charter,Georgia,serif;font-style:italic;background:none;border:none;padding:0;cursor:pointer';

    const btnConst   = document.createElement('button'); btnConst.textContent   = 'map';
    const btnPhase   = document.createElement('button'); btnPhase.textContent   = 'KDE';
    // const btnSimplex = document.createElement('button'); btnSimplex.textContent = 'focus';
    [btnConst, btnPhase].forEach(b => { b.style.cssText = base; });

    function setActive(id) {
      btnConst.style.cssText   = base + `;color:${id==='constellation'?'#666':'#bbb'};font-weight:${id==='constellation'?'600':'normal'}`;
      btnPhase.style.cssText   = base + `;color:${id==='phase'?'#666':'#bbb'};font-weight:${id==='phase'?'600':'normal'}`;
      // btnSimplex.style.cssText = base + `;color:${id==='simplex'?'#666':'#bbb'};font-weight:${id==='simplex'?'600':'normal'}`;
    }

    setActive('constellation');

    btnConst.addEventListener('click',   () => onSwitch('constellation'));
    btnPhase.addEventListener('click',   () => onSwitch('phase'));
    // btnSimplex.addEventListener('click', () => onSwitch('simplex'));

    tabsEl.appendChild(btnConst);
    tabsEl.appendChild(btnPhase);
    // tabsEl.appendChild(btnSimplex);

    container.insertBefore(tabsEl, container.firstChild);

    return { setActive };
  }

  // ── Main ──────────────────────────────────────────────────────────────────────

  async function buildViz() {
    const statusEl  = document.getElementById('constellation-status');
    const svgEl     = document.getElementById('constellation-svg');
    const tooltipEl = document.getElementById('constellation-tooltip');
    const container = document.getElementById('constellation-container');
    if (!statusEl || !svgEl || !tooltipEl || !container) return;

    const posts = extractPosts();
    if (!posts.length) { statusEl.textContent = 'no posts found.'; return; }

    statusEl.style.display = 'block';
    statusEl.innerHTML = 'inspired by <a href="https://www.chartosaur.com/blog" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:underline">chartosaur</a>';
    const texts = await Promise.all(posts.map(p => fetchMdtx(p.slug)));
    posts.forEach((p, i) => { p.wordCount = texts[i].split(/\s+/).filter(Boolean).length; });
    const X = buildFeatures(posts, texts);
    if (!X.length || !X[0].length) { statusEl.textContent = 'not enough data.'; return; }

    const { coords: rawCoords, fiedler } = lapEmbedFull(X);
    const embed2d  = rawCoords;
    const k        = autoK(embed2d);
    const labels   = mergeMiscClusters(posts, fixSingletons(embed2d, kmeans2d(embed2d, k)));

    const tagY = computeTagOrdering(posts);

    statusEl.style.display = 'none';

    // Inject panel divs
    let phaseSvgEl = document.getElementById('phase-svg');
    if (!phaseSvgEl) {
      phaseSvgEl = document.createElement('div');
      phaseSvgEl.id = 'phase-svg';
      phaseSvgEl.style.display = 'none';
      svgEl.insertAdjacentElement('afterend', phaseSvgEl);
    }
    // let simplexSvgEl = document.getElementById('simplex-svg');
    // if (!simplexSvgEl) {
    //   simplexSvgEl = document.createElement('div');
    //   simplexSvgEl.id = 'simplex-svg';
    //   simplexSvgEl.style.display = 'none';
    //   phaseSvgEl.insertAdjacentElement('afterend', simplexSvgEl);
    // }

    // Inject tabs
    const tabs = injectTabs(container, id => {
      tabs.setActive(id);
      svgEl.style.display        = id === 'constellation' ? 'block' : 'none';
      phaseSvgEl.style.display   = id === 'phase'         ? 'block' : 'none';
      // simplexSvgEl.style.display = id === 'simplex'       ? 'block' : 'none';
      hideTooltip(tooltipEl);
    });

    // Render constellation
    renderConstellation(svgEl, tooltipEl, posts, embed2d, labels);

    // Constellation caption
    const lnk = 'text-decoration:none;color:#bbb';
    const paperLnk = 'text-decoration:underline';
    const constShortHtml = `Embedded via TF-IDF and <a href="https://proceedings.neurips.cc/paper_files/paper/2001/file/f106b7f99d2cb30c3db1c3cc0fde9ccb-Paper.pdf" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Laplacian eigenmaps</a>, clustered by k-means. <a href="#" style="${lnk}" data-expand="1">(more)</a>`;
    const constLongHtml  = `Each post is embedded as a weighted TF-IDF vector over unigrams, bigrams, and trigrams extracted from one-hot vectors over available tags, title/description text, and body prose (stripped of math). These are concatenated and \\(L^2\\)-normalized so weights reflect relative cosine influence. Pairwise cosine similarities are passed through a Gaussian kernel, giving an affinity graph. The 2D layout is computed via <a href="https://proceedings.neurips.cc/paper_files/paper/2001/file/f106b7f99d2cb30c3db1c3cc0fde9ccb-Paper.pdf" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Laplacian eigenmaps</a>. The second and third smallest eigenvectors of the normalized graph Laplacian define a 2D embedding. \\(k \\in \\{2,\\ldots,5\\}\\) is chosen to maximize a parsimony-penalized silhouette score, then singleton and all-misc clusters are merged. Cluster labels are the highest cross-cluster TF-IDF unigram or bigram shared by \\(\\geq 2\\) posts in the cluster, deduplicated across clusters. Lines are a minimum spanning tree within each cluster. <a href="#" style="${lnk}" data-collapse="1">(less)</a>`;
    injectCaption(svgEl, 'constellation-caption', constShortHtml, constLongHtml);

    // Render drift view
    renderPhase(phaseSvgEl, tooltipEl, posts, null, labels, tagY);

    // Drift caption
    const phaseShortHtml = `KDE, stacked in <a href="https://en.wikipedia.org/wiki/Algebraic_connectivity" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Fiedler order</a>. CoM thread fit via GPR. <a href="#" style="${lnk}" data-expand="1">(more)</a>`;
    const phaseLongHtml  = `Each tag's activity is modeled by Gaussian kernel density estimation with bandwidth given by Silverman's formula. Tags are stacked in the order dictated by the <a href="https://en.wikipedia.org/wiki/Algebraic_connectivity" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Fiedler vector</a>. The center of mass thread traces the normalized weighted average of the tag-strip baselines over time, with weights given by the instantaneous KDE values. Gaussian process regression fits per-post CoM values, giving the thread and uncertainty band, and thread opacity indicates normalized Shannon entropy across tags. <a href="#" style="${lnk}" data-collapse="1">(less)</a>`;
    injectCaption(phaseSvgEl, 'phase-caption', phaseShortHtml, phaseLongHtml);

    // // Render simplex view
    // renderSimplex(simplexSvgEl, tooltipEl, posts, null, labels, tagY);
    // const simplexShortHtml = `Per-tag KDE normalized to tag-mixture probabilities, projected via PCA. <a href="#" style="${lnk}" data-expand="1">(more)</a>`;
    // const simplexLongHtml = `Per-tag KDE values are normalized to a probability distribution in the 4-simplex \\(\\Delta^4\\). The vertices are pure-tag states; each point represents a convex combination of tags. Points are projected to 2D via PCA, and a <a href="https://en.wikipedia.org/wiki/Catmull%E2%80%93Rom_spline" target="_blank" rel="noopener noreferrer" style="${paperLnk}">Catmull-Rom spline</a> interpolates the points to trace evolution over time. <a href="#" style="${lnk}" data-collapse="1">(less)</a>`;
    // injectCaption(simplexSvgEl, 'simplex-caption', simplexShortHtml, simplexLongHtml);
  }

  // ── Toggle + penguin ──────────────────────────────────────────────────────────

  function setup() {
    const btn       = document.getElementById('viz-toggle');
    const container = document.getElementById('constellation-container');
    if (!btn || !container) return;

    let built = false;
    const isOpen = () => container.style.display !== 'none';

    btn.addEventListener('mouseenter', () => { btn.textContent = isOpen() ? '🐧 analysis' : 'analysis'; });
    btn.addEventListener('mouseleave', () => { btn.textContent = isOpen() ? '🐧 analysis' : 'analysis'; });

    btn.addEventListener('click', () => {
      if (isOpen()) {
        container.style.display = 'none';
        btn.classList.remove('active');
        btn.textContent = 'analysis';
      } else {
        container.style.display = 'block';
        btn.classList.add('active');
        btn.textContent = '🐧 analysis';
        if (!built) { built = true; buildViz(); }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', setup);
})();

// Deterministic motion-graphics engine: everything is a pure function of time t (seconds).
// window.init(job) builds the DOM; window.renderAt(t) sets every style for that instant.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, x) => a + (b - a) * x;
  const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const easeInOut = (x) => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const easeBack = (x) => { x = clamp(x); const c1 = 1.5, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
  const expoOut = (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * clamp(x)));
  const prog = (t, start, dur) => clamp((t - start) / dur);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const norm = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}']/gu, "");

  let J, S = [], words = [], chunks = [];

  function headlineHTML(text, emphasis) {
    const em = new Set((emphasis || []).flatMap((e) => String(e).split(/\s+/)).map(norm).filter(Boolean));
    return String(text || "").split(/\s+/).filter(Boolean)
      .map((w) => `<span class="w"><span class="${em.has(norm(w)) ? "em" : ""}">${esc(w)}</span></span>`).join(" ");
  }

  function fmtNum(v, dec, prefix, suffix) {
    const s = Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    return `${esc(prefix || "")}${s}<span class="sfx">${esc(suffix || "")}</span>`;
  }


  // ---------- diagram ----------
  const NS = "http://www.w3.org/2000/svg";
  function rectExit(hw, hh, dx, dy) { const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L; const k = Math.min(hw / Math.abs(dx || 1e-9), hh / Math.abs(dy || 1e-9)); return [dx * k, dy * k]; }
  function arrowPath(svg, pts) {
    const d = "M" + pts.map((p) => p.map((v) => v.toFixed(1)).join(" ")).join(" L");
    const body = document.createElementNS(NS, "path"); body.setAttribute("d", d); svg.appendChild(body);
    const [x1, y1] = pts[pts.length - 2], [x2, y2] = pts[pts.length - 1];
    const a = Math.atan2(y2 - y1, x2 - x1), h = 22;
    const head = document.createElementNS(NS, "path");
    head.setAttribute("class", "head");
    head.setAttribute("d", `M${x2 - h * Math.cos(a - 0.5)} ${y2 - h * Math.sin(a - 0.5)} L${x2} ${y2} L${x2 - h * Math.cos(a + 0.5)} ${y2 - h * Math.sin(a + 0.5)}`);
    svg.appendChild(head);
    const len = body.getTotalLength();
    body.style.strokeDasharray = `${len} ${len}`; body.style.strokeDashoffset = len; head.style.opacity = 0;
    return { body, head, len };
  }
  function buildDiagram(el, sc) {
    const items = (sc.items || []).slice(0, 5), n = items.length, layout = sc.layout || "flow";
    const box = document.createElement("div"); box.className = `dg ${layout}`; el.appendChild(box);
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "arrows"); box.appendChild(svg);
    const nodes = [], arrows = [];
    const mk = (it, x, y, w, h, cls = "", badge = null) => {
      const d = document.createElement("div"); d.className = `node ${cls}`;
      Object.assign(d.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
      d.innerHTML = (badge ? `<div class="badge">${badge}</div>` : "") + `<div class="nl">${esc(it.label)}</div>` + (it.display ? `<div class="nd">${esc(it.display)}</div>` : "");
      box.appendChild(d); fit(d.querySelector(".nl"), w - 50, h - (it.display ? 70 : 30)); nodes.push(d); return d;
    };
    let H = 640;
    if (layout === "flow") {
      const gap = 60, nh = Math.min(200, (H - gap * (n - 1)) / n); H = n * nh + (n - 1) * gap;
      items.forEach((it, k) => mk(it, 30, k * (nh + gap), 800, nh, "", k + 1));
      for (let k = 0; k < n - 1; k++) arrows.push(arrowPath(svg, [[430, k * (nh + gap) + nh + 6], [430, (k + 1) * (nh + gap) - 8]]));
    } else {
      H = 680; const cx = 430, cy = 340;
      if (layout === "cycle") {
        const rx = 262, ry = 245, w = 290, h = 140;
        const ang = items.map((_, k) => -Math.PI / 2 + (2 * Math.PI * k) / n);
        items.forEach((it, k) => mk(it, cx + rx * Math.cos(ang[k]) - w / 2, cy + ry * Math.sin(ang[k]) - h / 2, w, h, "", k + 1));
        for (let k = 0; k < n; k++) {
          const a0 = ang[k], a1 = ang[k] + (2 * Math.PI) / n, d = Math.min(0.55, (a1 - a0) * 0.33), pts = [];
          for (let j = 0; j <= 24; j++) { const a = lerp(a0 + d, a1 - d, j / 24); pts.push([cx + (rx + 40) * Math.cos(a), cy + (ry + 40) * Math.sin(a)]); }
          arrows.push(arrowPath(svg, pts));
        }
      } else { // hub
        const w0 = 300, h0 = 160, w = 250, h = 130, rx = 268, ry = 255;
        mk(items[0], cx - w0 / 2, cy - h0 / 2, w0, h0, "center");
        const sat = items.slice(1);
        sat.forEach((it, k) => {
          const a = -Math.PI / 2 + (2 * Math.PI * k) / sat.length + (sat.length === 2 ? Math.PI / 2 : 0);
          const x = cx + rx * Math.cos(a), y = cy + ry * Math.sin(a);
          mk(it, x - w / 2, y - h / 2, w, h);
          const [ex0, ey0] = rectExit(w0 / 2 + 10, h0 / 2 + 10, x - cx, y - cy), [ex1, ey1] = rectExit(w / 2 + 12, h / 2 + 12, cx - x, cy - y);
          arrows.push(arrowPath(svg, [[cx + ex0, cy + ey0], [x + ex1, y + ey1]]));
        });
      }
    }
    box.style.height = H + "px";
    return { nodes, arrows, layout };
  }
  function renderDiagram(el, sc, lt, dur) {
    const D = el._dg; if (!D) return;
    const steps = D.nodes.length, span = Math.max(0.8, dur - 1.0);
    D.nodes.forEach((nd, k) => {
      const at = 0.3 + (span * k) / steps, p = easeBack(prog(lt, at, 0.45));
      nd.style.opacity = clamp(p * 1.3); nd.style.transform = `scale(${lerp(0.7, 1, p)})`;
    });
    D.arrows.forEach((a, k) => {
      const from = D.layout === "hub" ? 0 : k;
      const at = 0.3 + (span * from) / steps + 0.35, p = easeInOut(prog(lt, at, 0.5));
      a.body.style.strokeDashoffset = a.len * (1 - p); a.head.style.opacity = p > 0.92 ? 1 : 0;
    });
  }

  // ---------- map ----------
  const ALIAS = { "united states": "united states of america", usa: "united states of america", us: "united states of america",
    uk: "united kingdom", britain: "united kingdom", "great britain": "united kingdom", "czech republic": "czechia",
    "democratic republic of the congo": "dem. rep. congo", drc: "dem. rep. congo", "south korea": "south korea", "ivory coast": "côte d'ivoire",
    "bosnia and herzegovina": "bosnia and herz.", "central african republic": "central african rep.", "dominican republic": "dominican rep.",
    "south sudan": "s. sudan", "eswatini": "eswatini", "north macedonia": "macedonia", "uae": "united arab emirates" };
  let COUNTRIES = null;
  function countries() {
    if (!COUNTRIES && J.world) COUNTRIES = topojson.feature(J.world, J.world.objects.countries).features;
    return COUNTRIES || [];
  }
  function findCountry(name) {
    let n = String(name).toLowerCase().trim(); n = ALIAS[n] || n;
    const cs = countries();
    return cs.find((c) => (c.properties.name || "").toLowerCase() === n) || cs.find((c) => (c.properties.name || "").toLowerCase().startsWith(n.slice(0, 6)));
  }
  function buildMap(el, sc) {
    const W = 860, H = 700;
    const box = document.createElement("div"); box.className = "mapbox"; el.appendChild(box);
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H); box.appendChild(svg);
    const g = document.createElementNS(NS, "g"); svg.appendChild(g);
    const pW = d3.geoMercator().fitExtent([[10, 10], [W - 10, H - 10]], { type: "MultiPoint", coordinates: [[-175, -56], [175, 76]] });
    const path = d3.geoPath(pW);
    const add = (d, cls) => { const e = document.createElementNS(NS, "path"); e.setAttribute("d", d || ""); e.setAttribute("class", cls); e.setAttribute("vector-effect", "non-scaling-stroke"); g.appendChild(e); return e; };
    add(path(d3.geoGraticule().step([15, 15])()), "grat");
    countries().forEach((c) => add(path(c), "land"));
    const regs = (sc.regions || []).map(findCountry).filter(Boolean);
    const hi = regs.map((c) => add(path(c), "hi"));
    const places = (sc.places || []).filter((p) => isFinite(p.lat) && isFinite(p.lon));
    const pts = [];
    places.forEach((p) => { for (const [dx, dy] of [[-7, -5], [7, 5]]) pts.push([p.lon + dx, Math.max(-80, Math.min(84, p.lat + dy))]); });
    const mainland = (f) => {
      if (f.geometry.type !== "MultiPolygon") return f;
      const polys = f.geometry.coordinates.map((c) => ({ type: "Polygon", coordinates: c }));
      return { type: "Feature", geometry: polys.reduce((a, b) => (d3.geoArea(b) > d3.geoArea(a) ? b : a)) };
    };
    const fc = { type: "FeatureCollection", features: [...regs.map(mainland), ...(pts.length ? [{ type: "Feature", geometry: { type: "MultiPoint", coordinates: pts } }] : [])] };
    let pT = pW;
    if (fc.features.length) {
      pT = d3.geoMercator().fitExtent([[110, 120], [W - 110, H - 110]], fc);
      if (pT.scale() / pW.scale() > 30) pT.scale(pW.scale() * 30).translate(pT.translate()); // keep detail reasonable
      if (pT.scale() < pW.scale()) pT = pW;
    }
    const s = pT.scale() / pW.scale(), tW = pW.translate(), tT = pT.translate();
    const tx = tT[0] - s * tW[0], ty = tT[1] - s * tW[1];
    // pins + route in target-screen coordinates (appear after the zoom)
    const pinEls = places.map((p) => {
      const [x, y] = pT([p.lon, p.lat]);
      const d = document.createElement("div"); d.className = "pin" + (x > W * 0.62 ? " left" : "");
      d.style.left = x + "px"; d.style.top = y + "px";
      d.innerHTML = `<div class="ring"></div><div class="dot"></div><div class="tag">${esc(p.label)}</div>`; box.appendChild(d); return d;
    });
    // place labels to avoid overlapping each other and the frame (least-overlap wins)
    const placed = [];
    pinEls.forEach((pin, k) => {
      const tag = pin.querySelector(".tag");
      const x = parseFloat(pin.style.left), y = parseFloat(pin.style.top), w = tag.offsetWidth || 200, h = 56;
      const opts = [[26, -h - 4], [-26 - w, -h - 4], [26, 8], [-26 - w, 8], [-w / 2, -h - 30], [-w / 2, 30], [26, -h - 44], [26, 48], [-26 - w, -h - 44], [-26 - w, 48]];
      if (x > W * 0.62) opts.unshift(opts.splice(1, 1)[0]);
      let best = opts[0], bestCost = Infinity;
      for (const [dx, dy] of opts) {
        const r = [x + dx, y + dy, x + dx + w, y + dy + h];
        let cost = (r[0] < 8 || r[2] > W - 8 || r[1] < 8 || r[3] > H - 8) ? 1e6 : 0;
        for (const q of placed) cost += Math.max(0, Math.min(r[2], q[2]) - Math.max(r[0], q[0])) * Math.max(0, Math.min(r[3], q[3]) - Math.max(r[1], q[1]));
        if (cost < bestCost) { best = [dx, dy]; bestCost = cost; if (!cost) break; }
      }
      placed.push([x + best[0], y + best[1], x + best[0] + w, y + best[1] + h], [x - 18, y - 18, x + 18, y + 18]);
      Object.assign(tag.style, { left: best[0] + "px", top: best[1] + "px", right: "auto" });
    });
    let route = null;
    if (sc.route && places.length >= 2) {
      const P = places.map((p) => pT([p.lon, p.lat]));
      let d = `M${P[0][0]} ${P[0][1]}`;
      for (let k = 1; k < P.length; k++) {
        const [x0, y0] = P[k - 1], [x1, y1] = P[k], mx = (x0 + x1) / 2, my = (y0 + y1) / 2, L = Math.hypot(x1 - x0, y1 - y0);
        let nx = -(y1 - y0) / (L || 1), ny = (x1 - x0) / (L || 1);
        if (ny > 0) { nx = -nx; ny = -ny; } // bow the arc upward
        d += ` Q${mx + nx * L * 0.25} ${my + ny * L * 0.25} ${x1} ${y1}`;
      }
      const rs = document.createElementNS(NS, "svg"); rs.setAttribute("viewBox", `0 0 ${W} ${H}`); rs.setAttribute("width", W); rs.setAttribute("height", H);
      const halo = document.createElementNS(NS, "path"); halo.setAttribute("d", d); halo.setAttribute("class", "routehalo"); rs.appendChild(halo);
      const r = document.createElementNS(NS, "path"); r.setAttribute("d", d); r.setAttribute("class", "routefull"); rs.appendChild(r);
      box.insertBefore(rs, box.querySelector(".pin"));
      const len = r.getTotalLength();
      for (const e of [halo, r]) { e.style.strokeDasharray = `${len} ${len}`; e.style.strokeDashoffset = len; }
      route = { r, halo, len };
    }
    const zoomed = fc.features.length > 0 && s > 1.05;
    return { g, s, tx, ty, hi, pinEls, route, zoomed, W, H };
  }
  function renderMap(el, sc, lt, dur) {
    const M = el._map; if (!M) return;
    const zd = M.zoomed ? Math.min(1.6, dur * 0.35) : 0;
    const p = M.zoomed ? easeInOut(prog(lt, 0.15, zd)) : 1;
    const sc_ = Math.pow(M.s, p);
    // interpolate the world point under the view center for a smooth fly-in
    const cx = M.W / 2, cy = M.H / 2, c1x = (cx - M.tx) / M.s, c1y = (cy - M.ty) / M.s;
    const wx = lerp(cx, c1x, p), wy = lerp(cy, c1y, p);
    M.g.setAttribute("transform", `translate(${cx - sc_ * wx} ${cy - sc_ * wy}) scale(${sc_})`);
    const after = 0.15 + zd;
    M.hi.forEach((h) => { h.style.fillOpacity = 0.45 * easeOut(prog(lt, after - 0.2, 0.5)); });
    const span = Math.max(0.5, dur - after - 0.8);
    M.pinEls.forEach((pin, k) => {
      const at = after + (span * k) / Math.max(1, M.pinEls.length), q = easeBack(prog(lt, at, 0.4));
      pin.style.opacity = clamp(q * 1.5);
      pin.querySelector(".dot").style.transform = `scale(${q})`;
      const tag = pin.querySelector(".tag"); tag.style.opacity = easeOut(prog(lt, at + 0.15, 0.3));
      const rp = ((lt - at) % 1.4) / 1.4; const ring = pin.querySelector(".ring");
      ring.style.transform = `scale(${1 + rp * 2.4})`; ring.style.opacity = lt > at ? (1 - rp) * 0.8 : 0;
    });
    if (M.route) { const off = M.route.len * (1 - easeInOut(prog(lt, after + 0.2, Math.max(0.6, span)))); M.route.r.style.strokeDashoffset = off; M.route.halo.style.strokeDashoffset = off; }
  }

  // ---------- before / after ----------
  function buildBA(el, sc, i) {
    let [a, b] = sc.items;
    if (!(a.image && b.image)) { a = { ...a, image: null }; b = { ...b, image: null }; } // photos on both sides or neither
    const box = document.createElement("div"); box.className = "ba"; el.appendChild(box);
    const myth = /myth|wrong|false|fake|misconception|belief|assum/i.test(a.label || "");
    const side = (it, cls) => `<div class="side ${cls}${it.image ? " withimg" : ""}${cls === "before" && myth ? " myth" : ""}">${it.image ? `<img src="${esc(fileUrl(it.image))}">` : ""}<div class="tagl">${esc(it.label)}</div><div class="big">${esc(it.display || "")}</div></div>`;
    box.innerHTML = side(a, "before") + side(b, "after") + `<div class="handle"></div>`;
    box.querySelectorAll(".big").forEach((e) => fit(e, 760, 200));
    // sweep when the narration reaches its second sentence
    const ws = (J.timeline.scenes[i] || {}).words || [];
    const k = ws.findIndex((w, j) => /[.!?]$/.test(w.w) && j < ws.length - 1);
    const st = J.timeline.scenes[i].start;
    return { after: box.querySelector(".after"), before: box.querySelector(".before"), handle: box.querySelector(".handle"),
             sweepAt: k >= 0 ? ws[k + 1].s - st - 0.25 : null };
  }
  function renderBA(el, sc, lt, dur) {
    const B = el._ba; if (!B) return;
    const at = B.sweepAt ?? dur * 0.45, p = easeInOut(prog(lt, at, 0.8));
    const H = 700, half = (H - 12) / 2;
    B.before.style.height = `${lerp(H, half, p)}px`;
    B.after.style.top = `${H - half}px`; B.after.style.height = `${half}px`;
    B.after.style.clipPath = `inset(${(1 - p) * 100}% 0 0 0 round 0 0 40px 40px)`;
    B.handle.style.top = `${lerp(H, H - half - 6, p)}px`; B.handle.style.opacity = p > 0 && p < 1 ? 1 : 0;
    const bi = B.before.querySelector("img"), ai = B.after.querySelector("img");
    if (bi) bi.style.transform = `scale(${lerp(1.1, 1.0, clamp(lt / dur))})`;
    if (ai) ai.style.transform = `scale(${lerp(1.12, 1.0, clamp(lt / dur))})`;
  }


  // ---------- poster: big drawn pictogram for text-only scenes ----------
  function buildGlyph(nodes) {
    const wrap = document.createElement("div"); wrap.className = "glyph";
    const disc = document.createElement("div"); disc.className = "disc"; wrap.appendChild(disc);
    const ring = document.createElementNS(NS, "svg"); ring.setAttribute("class", "ring"); ring.setAttribute("viewBox", "0 0 100 100");
    ring.innerHTML = `<circle cx="50" cy="50" r="48" pathLength="100"/>`; wrap.appendChild(ring);
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "ico"); svg.setAttribute("viewBox", "0 0 24 24");
    for (const [tag, attrs] of nodes) {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) if (k !== "key") e.setAttribute(k, v);
      e.setAttribute("pathLength", "1");
      svg.appendChild(e);
    }
    wrap.appendChild(svg);
    return wrap;
  }
  function fitGrow(el, maxW, maxH, maxFs) {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    const fits = () => el.scrollWidth <= maxW + 2 && el.offsetHeight <= maxH;
    for (let k = 0; k < 30 && fits() && fs < maxFs; k++) { fs = Math.min(maxFs, fs * 1.05); el.style.fontSize = fs + "px"; }
    for (let k = 0; k < 40 && !fits() && fs > 40; k++) { fs *= 0.95; el.style.fontSize = fs + "px"; }
  }
  function renderGlyph(el, lt, first) {
    const g = el._glyph; if (!g) return;
    const parts = [...g.querySelectorAll(".ico > *")];
    const pd = first ? 1 : easeBack(prog(lt, 0, 0.5));
    g.querySelector(".disc").style.transform = `scale(${lerp(0.6, 1, pd)})`;
    g.querySelector(".disc").style.opacity = clamp(pd);
    parts.forEach((e, k) => {
      const p = first ? 1 : easeInOut(prog(lt, 0.1 + (k * 0.5) / Math.max(1, parts.length), 0.7));
      e.style.strokeDasharray = "1 1"; e.style.strokeDashoffset = 1 - p;
      if (e.getAttribute("fill") && e.getAttribute("fill") !== "none") e.style.fillOpacity = p;
    });
    g.querySelector(".ring").style.transform = `rotate(${lt * 18}deg)`;
    g.querySelector(".ring circle").style.strokeDashoffset = first ? 0 : 100 * (1 - easeOut(prog(lt, 0.05, 0.9)));
    g.querySelector(".ico").style.transform = `translateY(${Math.sin(lt * 1.7) * 7}px) rotate(${Math.sin(lt * 1.1) * 2}deg)`;
  }

  const fileUrl = (p) => (/^(https?|file|data):/.test(p) ? p : "file://" + encodeURI(p));

  function build(sc, i) {
    const el = document.createElement("div");
    el.className = `scene ${sc.type}`;
    const kickTxt = sc.kicker && sc.type !== "hook" && norm(sc.kicker) !== norm(J.series || "") ? sc.kicker : "";
    const kick = kickTxt ? `<div class="kicker"><span>${esc(kickTxt)}</span></div>` : "";
    let h = "";
    switch (sc.type) {
      case "stat":
        h = `${kick}<div class="statnum"></div><div class="statlabel">${esc(sc.label || sc.headline || "")}</div>`;
        break;
      case "compare": {
        const items = (sc.items || []).slice(0, 4);
        const max = Math.max(...items.map((x) => Math.abs(x.value || 0)), 1e-9);
        if (items.length <= 2) el.classList.add("few");
        h = `${kick}<div class="title2 hl">${headlineHTML(sc.headline, sc.emphasis)}</div>` + items.map((x, k) =>
          `<div class="bar" data-r="${Math.max(0.012, Math.abs(x.value || 0) / max)}"><div class="lab"><span>${esc(x.label)}</span><span>${esc(x.display ?? x.value ?? "")}</span></div><div class="trk"><div class="fill"></div></div></div>`).join("");
        break;
      }
      case "list":
        h = `${kick}<div class="title2 hl">${headlineHTML(sc.headline, sc.emphasis)}</div>` + (sc.items || []).slice(0, 5).map((x, k) =>
          `<div class="li"><div class="n">${k + 1}</div><div class="t">${esc(x.label)}</div></div>`).join("");
        break;
      case "timeline":
        h = `${kick}<div class="title2 hl">${headlineHTML(sc.headline, sc.emphasis)}</div><div class="tl"><div class="rail"></div>` + (sc.items || []).slice(0, 5).map((x) =>
          `<div class="ev"><div class="dot"></div><div class="yr">${esc(x.label)}</div><div class="tx">${esc(x.display || "")}</div></div>`).join("") + `</div>`;
        break;
      case "diagram": case "map": case "beforeafter":
        h = `${kick}<div class="title2 hl">${headlineHTML(sc.headline, sc.emphasis)}</div>`;
        break;
      case "outro":
        h = `${kick}<div class="hl">${headlineHTML(sc.headline, sc.emphasis)}</div>` + (!J.handle ? "" :
          `<div class="loop"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.2L3 16M3 21v-5h5"/></svg><span>${esc(J.handle)}</span></div>`);
        break;
      default:
        h = `${kick}<div class="hl">${headlineHTML(sc.headline, sc.emphasis)}</div>`;
    }
    el.innerHTML = h;
    $("#scenes").appendChild(el);
    if (sc.type === "diagram") el._dg = buildDiagram(el, sc);
    if (sc.type === "map") el._map = buildMap(el, sc);
    if (sc.type === "beforeafter") el._ba = buildBA(el, sc, i);
    if (sc.type === "stat" && !sc.image && sc.icon_nodes) {
      el.classList.add("statposter");
      el._glyph = buildGlyph(sc.icon_nodes); el._glyph.classList.add("sm");
      el.insertBefore(el._glyph, el.firstChild);
    }
    if (["hook", "statement", "outro"].includes(sc.type) && !sc.image && sc.icon_nodes) {
      el.classList.add("poster");
      el._glyph = buildGlyph(sc.icon_nodes);
      el.insertBefore(el._glyph, el.firstChild);
      const ph = $(".hl", el);
      if (ph) fitGrow(ph, 860, sc.type === "hook" ? 430 : 400, sc.type === "hook" ? 158 : 140);
    }
    if (sc.image && sc.type !== "beforeafter") {
      const ph = document.createElement("div"); ph.className = "photo";
      ph.innerHTML = `<img src="${esc(fileUrl(sc.image))}">`; $("#photos").appendChild(ph);
      el._photo = ph; el.classList.add("hasphoto");
    }
    // auto-fit headline font size so it never overflows
    const hl = $(".hl:not(.title2)", el);
    if (hl) fit(hl, 860, 620);
    const t2 = $(".title2", el);
    if (t2) fit(t2, 860, ["diagram", "map", "beforeafter"].includes(sc.type) ? 200 : 230);
    const sn = $(".statnum", el);
    if (sn) {
      sn.innerHTML = fmtNum(sc.value ?? 0, sc.decimals || 0, sc.prefix, sc.suffix);
      fit(sn, 860, 330);
    }
    if (sc.type === "stat" && !sc.icon_nodes && !sc.image) {  // no icon: the number itself becomes the poster
      el.classList.add("bigstat");
      fitGrow(sn, 860, 470, 440);
      fitGrow($(".statlabel", el), 860, 230, 78);
    }
    return el;
  }

  function fit(el, maxW, maxH) {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    for (let k = 0; k < 40 && (el.scrollWidth > maxW + 2 || el.scrollHeight > maxH) && fs > 30; k++) {
      fs *= 0.94;
      el.style.fontSize = fs + "px";
    }
  }

  // load the real fonts BEFORE building: every auto-fit measures text, and a fallback font measures narrower
  const FONTS = ['900 100px "Inter Tight"', '800 100px "Inter Tight"', '500 100px "Inter Tight"',
    'italic 400 100px "Instrument Serif"', '700 40px "JetBrains Mono"'];
  window.init = (job) => Promise.all(FONTS.map((f) => document.fonts.load(f))).then(() => initBuild(job));
  function initBuild(job) {
    J = job;
    document.documentElement.dataset.theme = job.spec.theme || "midnight";
    $("#seriesName").textContent = job.series || "";
    const tl = job.timeline.scenes;
    $("#top").innerHTML = tl.map(() => `<div class="seg"><i></i></div>`).join("");
    S = job.spec.scenes.map((sc, i) => ({ sc, el: build(sc, i), start: tl[i].start, end: tl[i].end }));
    // captions: chunks of <= 3 words, break after punctuation
    words = tl.flatMap((s) => s.words);
    chunks = [];
    let cur = [];
    words.forEach((w, k) => {
      cur.push(w);
      const brk = /[.!?,;:—]$/.test(w.w) || cur.length >= 3 || k === words.length - 1;
      if (brk) { chunks.push(cur); cur = []; }
    });
    chunks.forEach((c, k) => { c.s = c[0].s; c.e = k < chunks.length - 1 ? chunks[k + 1][0].s : job.timeline.duration; });
    const imgs = [...document.images].map((im) => im.decode().catch(() => null));
    return Promise.all([document.fonts.ready, ...imgs]).then(() => true);
  }

  let lastChunk = -1;
  function renderCaptions(t) {
    const cap = $("#cap");
    if (J.captions === false) { cap.style.display = "none"; return; }
    const k = chunks.findIndex((c) => t >= c.s - 0.04 && t < c.e);
    if (k !== lastChunk) {
      cap.innerHTML = k < 0 ? "" : chunks[k].map((w) => `<span class="cw">${esc(w.w.replace(/[,;:]$/, ""))}</span>`).join("");
      lastChunk = k;
    }
    if (k < 0) return;
    const c = chunks[k];
    const p = easeBack(prog(t, c.s - 0.04, 0.16));
    cap.style.transform = `translateY(${(1 - p) * 26}px) scale(${lerp(0.92, 1, p)})`;
    cap.style.opacity = clamp(p * 1.4);
    [...cap.children].forEach((el, i) => {
      const w = c[i];
      el.classList.toggle("on", t >= w.s - 0.02 && (i === c.length - 1 ? t < c.e : t < c[i + 1].s));
    });
  }

  function animWords(el, lt, delay = 0, stagger = 0.06, dur = 0.42) {
    el.querySelectorAll(".w > span").forEach((s, i) => {
      const p = expoOut(prog(lt, delay + i * stagger, dur));
      s.style.transform = `translateY(${(1 - p) * 110}%) rotate(${(1 - p) * 4}deg)`;
    });
  }

  function renderScene(o, t, i) {
    const { el, sc, start, end } = o;
    const isLast = i === S.length - 1;
    const enter = i === 0 ? 1 : easeOut(prog(t, start - 0.05, 0.38));
    const exitStart = end - 0.22;
    const exit = isLast ? 0 : easeInOut(prog(t, exitStart, 0.22));
    const visible = (i === 0 || t >= start - 0.06) && (isLast || t < end + 0.01);
    el.style.opacity = visible ? clamp(enter) * (1 - exit) : 0;
    if (el._photo) {
      const ph = el._photo, lt0 = t - start, D0 = end - start;
      ph.style.opacity = visible ? (i === 0 ? 1 : easeOut(prog(t, start - 0.15, 0.5))) * (1 - exit) : 0;
      ph.firstChild.style.transform = `scale(${lerp(1.14, 1.0, easeOut(clamp(lt0 / (D0 + 0.5))))}) translateX(${lerp(-1.5, 1.5, clamp(lt0 / D0))}%)`;
    }
    if (!visible) return;
    const lt = t - start;
    const dur = end - start;
    const drift = lt * 6; // slow push-in
    el.style.transform = `translateY(${(1 - enter) * 70 - exit * 40 - drift * 0.6}px) scale(${lerp(1, 0.96, exit)})`;
    el.style.filter = enter < 1 || exit > 0 ? `blur(${(1 - enter) * 10 + exit * 8}px)` : "none";

    const k = $(".kicker", el);
    if (k) { const p = easeOut(prog(lt, 0, 0.35)); if (i === 0) { k.style.opacity = 1; k.style.transform = "none"; } else { k.style.opacity = p; k.style.transform = `translateX(${(1 - p) * -30}px)`; } }

    switch (sc.type) {
      case "hook": {
        // visible on frame 0 for the swipe decision; tiny settle-in for energy
        const hl = $(".hl", el); hl.style.transform = `scale(${lerp(1.035, 1, easeOut(lt / 1.2))})`; hl.style.transformOrigin = "left center";
        renderGlyph(el, lt, i === 0);
        break;
      }
      case "statement": case "outro":
        animWords($(".hl", el), lt, el._glyph ? 0.25 : 0.05);
        renderGlyph(el, lt, false);
        break;
      case "stat": {
        const p = expoOut(prog(lt, 0.1, Math.min(1.4, dur * 0.6)));
        const v = (sc.value ?? 0) * p;
        $(".statnum", el).innerHTML = fmtNum(v, sc.decimals || 0, sc.prefix, sc.suffix);
        $(".statnum", el).style.transform = `scale(${lerp(0.9, 1, easeBack(prog(lt, 0, 0.5)))})`;
        $(".statnum", el).style.transformOrigin = "left bottom";
        const pl = easeOut(prog(lt, 0.35, 0.5));
        $(".statlabel", el).style.opacity = pl; $(".statlabel", el).style.transform = `translateY(${(1 - pl) * 24}px)`;
        renderGlyph(el, lt, false);
        break;
      }
      case "diagram": animWords($(".title2", el), lt, 0, 0.04); renderDiagram(el, sc, lt, dur); break;
      case "map": animWords($(".title2", el), lt, 0, 0.04); renderMap(el, sc, lt, dur); break;
      case "beforeafter": animWords($(".title2", el), lt, 0, 0.04); renderBA(el, sc, lt, dur); break;
      case "compare": {
        animWords($(".title2", el), lt, 0, 0.04);
        el.querySelectorAll(".bar").forEach((b, j) => {
          const p0 = easeOut(prog(lt, 0.25 + j * 0.3, 0.4));
          b.style.opacity = p0; b.style.transform = `translateX(${(1 - p0) * 40}px)`;
          const pf = expoOut(prog(lt, 0.45 + j * 0.3, 0.9));
          $(".fill", b).style.width = `${pf * parseFloat(b.dataset.r) * 100}%`;
        });
        break;
      }
      case "list": {
        animWords($(".title2", el), lt, 0, 0.04);
        const items = el.querySelectorAll(".li");
        const span = Math.max(0.6, dur - 0.9);
        items.forEach((li, j) => {
          const at = 0.35 + (span * j) / Math.max(1, items.length);
          const p = easeBack(prog(lt, at, 0.42));
          li.style.opacity = clamp(p); li.style.transform = `translateX(${(1 - p) * 60}px)`;
          $(".n", li).style.transform = `scale(${lerp(0.4, 1, p)}) rotate(${(1 - p) * -20}deg)`;
        });
        break;
      }
      case "timeline": {
        animWords($(".title2", el), lt, 0, 0.04);
        const evs = el.querySelectorAll(".ev");
        const span = Math.max(0.6, dur - 0.9);
        const tlEl = $(".tl", el);
        const pr = easeInOut(prog(lt, 0.3, span));
        $(".rail", el).style.height = `${pr * tlEl.offsetHeight}px`;
        evs.forEach((ev, j) => {
          const at = 0.3 + (span * j) / Math.max(1, evs.length);
          const p = easeOut(prog(lt, at, 0.4));
          ev.style.opacity = p; ev.style.transform = `translateY(${(1 - p) * 30}px)`;
          $(".dot", ev).style.transform = `scale(${easeBack(prog(lt, at, 0.35))})`;
        });
        break;
      }
    }
  }


  // ---------- layout QA: run after renderAt(t) at a scene's settled frame ----------
  const SAFE = { top: 150, bottom: 1560, left: 36, right: 1044, railX: 945, railY: 880 };
  function effOpacity(el) { let o = 1; for (let e = el; e && e !== document.body; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; }
  function inter(a, b) { const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top); return w > 0 && h > 0 ? w * h : 0; }
  window.layoutCheck = (si) => {
    const issues = [], o = S[si]; if (!o) return issues;
    const el = o.el, add = (kind, detail) => issues.push({ scene: si, type: o.sc.type, kind, detail });
    const TEXT = ".kicker, .hl, .title2, .statnum, .statlabel, .nl, .nd, .li .t, .ev .yr, .ev .tx, .ba .big, .ba .tagl, .bar .lab, .pin .tag";
    const BOX = ".node, .mapbox, .ba, .bar, .li, .ev, .statbar, .pin .tag, .statnum";
    const label = (e) => (e.textContent || e.className).trim().replace(/\s+/g, " ").slice(0, 40);
    const vis = (e) => effOpacity(e) > 0.6;
    const texts = [...el.querySelectorAll(TEXT)].filter(vis);
    for (const e of texts) {
      if (e.scrollWidth > e.clientWidth + 3) add("overflow", `text wider than its box: "${label(e)}"`);
      const fs = parseFloat(getComputedStyle(e).fontSize) * (e.getBoundingClientRect().height / (e.offsetHeight || 1));
      if (e.textContent.trim() && fs < 32) add("tiny_text", `${fs.toFixed(0)}px text: "${label(e)}"`);
    }
    const boxes = [...el.querySelectorAll(BOX + ", " + TEXT)].filter(vis);
    for (const e of boxes) {
      const r = e.getBoundingClientRect(); if (!r.width || !r.height) continue;
      if (r.left < SAFE.left - 1 || r.right > SAFE.right + 1) add("off_frame", `"${label(e)}" reaches the side edge`);
      if (r.top < SAFE.top || r.bottom > SAFE.bottom) add("ui_zone", `"${label(e)}" under the Shorts top/bottom UI`);
      if (r.right > SAFE.railX && r.bottom > SAFE.railY) add("ui_zone", `"${label(e)}" under the like/comment buttons`);
    }
    // overlaps between sibling cards / labels
    const groups = [".node", ".pin .tag", ".li", ".ev", ".bar"];
    for (const g of groups) {
      const xs = [...el.querySelectorAll(g)].filter(vis).map((e) => [e, e.getBoundingClientRect()]);
      for (let a = 0; a < xs.length; a++) for (let b = a + 1; b < xs.length; b++) {
        const ar = inter(xs[a][1], xs[b][1]), m = Math.min(xs[a][1].width * xs[a][1].height, xs[b][1].width * xs[b][1].height);
        if (ar > 0.04 * m) add("overlap", `"${label(xs[a][0])}" overlaps "${label(xs[b][0])}"`);
      }
    }
    // captions colliding with content
    const caps = [...document.querySelectorAll("#cap .cw")].map((e) => e.getBoundingClientRect());
    if (caps.length) {
      const c = caps.reduce((u, r) => ({ left: Math.min(u.left, r.left), right: Math.max(u.right, r.right), top: Math.min(u.top, r.top), bottom: Math.max(u.bottom, r.bottom) }));
      for (const e of boxes) { const r = e.getBoundingClientRect(); if (inter(c, r) > 0.03 * (r.width * r.height)) { add("caption_overlap", `captions cover "${label(e)}"`); break; } }
      if (c.right > SAFE.railX && c.bottom > SAFE.railY) add("ui_zone", "captions under the like/comment buttons");
      if (c.top < 600 || c.bottom > SAFE.bottom || c.left < SAFE.left - 1 || c.right > SAFE.right + 1) add("caption_position", "captions outside their zone");
      const cfs = parseFloat(getComputedStyle(document.querySelector("#cap .cw")).fontSize);
      if (cfs < 44) add("tiny_text", `captions only ${cfs.toFixed(0)}px`);
    }
    // how much of the content zone (y 330..1370) the scene actually uses
    const rects = [...el.querySelectorAll("*")].filter((e) => !e.closest(".idx") && vis(e)).map((e) => e.getBoundingClientRect()).filter((r) => r.width > 4 && r.height > 4);
    if (el._photo && effOpacity(el._photo) > 0.6) rects.push({ top: 0, bottom: 1000 });
    if (rects.length) {
      const top = Math.max(330, Math.min(...rects.map((r) => r.top))), bottom = Math.min(1370, Math.max(...rects.map((r) => r.bottom)));
      const cov = Math.max(0, bottom - top) / 1040;
      if (cov < 0.45) add("sparse_frame", `content fills only ${(cov * 100).toFixed(0)}% of the frame height`);
    }
    const seen = new Set();
    return issues.filter((x) => { const k = x.kind + x.detail; if (seen.has(k)) return false; seen.add(k); return true; });
  };

  window.renderAt = (t) => {
    const D = J.timeline.duration;
    // background life
    const a = t * 0.18;
    $("#b1").style.transform = `translate(${-200 + Math.sin(a) * 160}px, ${-150 + Math.cos(a * 0.8) * 120}px)`;
    $("#b2").style.transform = `translate(${380 + Math.cos(a * 0.9) * 170}px, ${1150 + Math.sin(a * 1.1) * 150}px)`;
    $("#grid").style.transform = `translateY(${(t * 12) % 90}px)`;
    // progress segments
    const segs = document.querySelectorAll(".seg i");
    S.forEach((o, i) => { segs[i].style.width = `${clamp((t - o.start) / (o.end - o.start)) * 100}%`; });
    // scene-change accent flash
    let fl = 0;
    S.forEach((o, i) => { if (i > 0) fl = Math.max(fl, 0.35 * (1 - clamp(Math.abs(t - o.start) / 0.12))); });
    $("#flash").style.opacity = fl;
    S.forEach((o, i) => renderScene(o, t, i));
    renderCaptions(t);
    return D;
  };
})();

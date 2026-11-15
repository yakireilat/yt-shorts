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

  function build(sc, i) {
    const el = document.createElement("div");
    el.className = `scene ${sc.type}`;
    const kick = sc.kicker ? `<div class="kicker">${esc(sc.kicker)}</div>` : "";
    let h = "";
    switch (sc.type) {
      case "stat":
        h = `${kick}<div class="statnum"></div><div class="statlabel">${esc(sc.label || sc.headline || "")}</div><div class="statbar"><i></i></div>`;
        break;
      case "compare": {
        const items = (sc.items || []).slice(0, 4);
        const max = Math.max(...items.map((x) => Math.abs(x.value || 0)), 1e-9);
        h = `${kick}<div class="title2 hl">${headlineHTML(sc.headline, sc.emphasis)}</div>` + items.map((x, k) =>
          `<div class="bar ${k === 0 ? "" : ""}" data-r="${Math.max(0.012, Math.abs(x.value || 0) / max)}"><div class="lab"><span>${esc(x.label)}</span><span>${esc(x.display ?? x.value ?? "")}</span></div><div class="trk"><div class="fill"></div></div></div>`).join("");
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
      case "outro":
        h = `${kick}<div class="hl">${headlineHTML(sc.headline, sc.emphasis)}</div>` +
          `<div class="loop"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.2L3 16M3 21v-5h5"/></svg><span>${esc(J.handle || J.series)}</span></div>`;
        break;
      default:
        h = `${kick}<div class="hl">${headlineHTML(sc.headline, sc.emphasis)}</div>`;
    }
    el.innerHTML = h + `<div class="idx">${String(i + 1).padStart(2, "0")}</div>`;
    $("#scenes").appendChild(el);
    // auto-fit headline font size so it never overflows
    const hl = $(".hl:not(.title2)", el);
    if (hl) fit(hl, 860, 620);
    const t2 = $(".title2", el);
    if (t2) fit(t2, 860, 230);
    const sn = $(".statnum", el);
    if (sn) {
      sn.innerHTML = fmtNum(sc.value ?? 0, sc.decimals || 0, sc.prefix, sc.suffix);
      fit(sn, 860, 330);
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

  window.init = (job) => {
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
    return document.fonts.ready.then(() => true);
  };

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
    if (!visible) return;
    const lt = t - start;
    const dur = end - start;
    const drift = lt * 6; // slow push-in
    el.style.transform = `translateY(${(1 - enter) * 70 - exit * 40 - drift * 0.6}px) scale(${lerp(1, 0.96, exit)})`;
    el.style.filter = enter < 1 || exit > 0 ? `blur(${(1 - enter) * 10 + exit * 8}px)` : "none";

    const ix = $(".idx", el);
    ix.style.transform = `translateY(${(1 - enter) * 120 - lt * 14}px)`;
    const k = $(".kicker", el);
    if (k) { const p = easeOut(prog(lt, 0, 0.35)); if (i === 0) { k.style.opacity = 1; k.style.transform = "none"; } else { k.style.opacity = p; k.style.transform = `translateX(${(1 - p) * -30}px)`; } }

    switch (sc.type) {
      case "hook": {
        // visible on frame 0 for the swipe decision; tiny settle-in for energy
        const hl = $(".hl", el); hl.style.transform = `scale(${lerp(1.035, 1, easeOut(lt / 1.2))})`; hl.style.transformOrigin = "left center";
        break;
      }
      case "statement": case "outro":
        animWords($(".hl", el), lt, 0.05);
        break;
      case "stat": {
        const p = expoOut(prog(lt, 0.1, Math.min(1.4, dur * 0.6)));
        const v = (sc.value ?? 0) * p;
        $(".statnum", el).innerHTML = fmtNum(v, sc.decimals || 0, sc.prefix, sc.suffix);
        $(".statnum", el).style.transform = `scale(${lerp(0.9, 1, easeBack(prog(lt, 0, 0.5)))})`;
        $(".statnum", el).style.transformOrigin = "left bottom";
        const pl = easeOut(prog(lt, 0.35, 0.5));
        $(".statlabel", el).style.opacity = pl; $(".statlabel", el).style.transform = `translateY(${(1 - pl) * 24}px)`;
        const pct = /%/.test(sc.suffix || "") ? clamp((sc.value || 0) / 100) : 1;
        $(".statbar i", el).style.width = `${p * pct * 100}%`;
        break;
      }
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

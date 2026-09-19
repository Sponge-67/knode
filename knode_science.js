/* knode_science.js — scientific layer for the knode editor.
 *
 * Adds: template library palette (Tab / double-click), fixed-step simulation,
 * plot panel (time series, phase portraits, arrays, CSV/PNG export), graph
 * analysis (cycles, critical path, centrality heat-maps, lint), parameter sweeps,
 * Monte-Carlo uncertainty + sensitivity, examples, result overlays on nodes,
 * parameter editing, autosave and real HDF5 export (when h5py is installed).
 *
 * It relies on globals of the main script: graph, renderer, BACKEND_URL,
 * saveState, restoreSnapshot, addDebugEntry, executionLogs, updateLiveState,
 * updatePropertiesPanel, escapeHtml.
 */
(function () {
  'use strict';

  const KS = window.KnodeSci = {
    library: null, byId: {}, examples: [], health: null,
    results: {},        // node id -> {status, outputs, error, ms}
    lastRun: null, lastSim: null, sweep: null,
    heat: null,         // {metric, values: {id: 0..1}, raw: {id: number}}
    plotSel: null, busy: false, abort: null,
    mouse: { x: 0, y: 0 },
  };
  // The backend address is read at call time (BACKEND_URL may be switched by the Backend Manager).
  const PALETTE = ['#4ecdc4', '#ff6b6b', '#feca57', '#a29bfe', '#1dd1a1', '#ff9f43', '#54a0ff', '#ff9ff3', '#c8d6e5', '#ee5a24'];
  const ENUMS = { scheme: ['complementary', 'triadic', 'analogous', 'split', 'tetradic', 'monochrome'], init: ['single', 'random'] };
  const LONG_TEXT = /^(expr|equations|text|objective|template|constants|points|f|pattern)$/;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (s) => escapeHtml(s === undefined ? '' : s);

  // ------------------------------------------------------------------ styles
  const css = `
  .ks-sep{width:1px;height:16px;background:#444;margin:0 3px}
  .ks-num{width:58px;padding:2px 4px;background:#1a1a1a;border:1px solid #444;border-radius:3px;color:#c8c8c8;font-size:10px}
  .ks-lbl{font-size:9px;color:#777}
  .ks-dot{width:8px;height:8px;border-radius:50%;background:#555;display:inline-block;margin-left:4px;cursor:help}
  .header-actions select.ks-sel{background:#333;border:1px solid #444;color:#c8c8c8;font-size:10px;padding:2px 4px;border-radius:3px;max-width:150px}
  .header-actions button.ks-accent{background:#2d3a66;border-color:#445599}
  .header-actions button.ks-accent:hover{background:#3a4a80}
  .ks-modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:2000}
  .ks-modal.active{display:flex}
  .ks-box{background:#222;border:1px solid #3a3a3a;border-radius:8px;box-shadow:0 10px 40px rgba(0,0,0,.6);color:#c8c8c8;font-size:11px;display:flex;flex-direction:column;max-height:86vh}
  .ks-box h2{font-size:13px;font-weight:600;color:#ddd;margin:0}
  .ks-head{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid #333;gap:10px}
  .ks-body{padding:12px 14px;overflow:auto}
  .ks-x{background:none;border:none;color:#888;font-size:14px;cursor:pointer}
  .ks-input,.ks-box select,.ks-box textarea{background:#1a1a1a;border:1px solid #3a3a3a;border-radius:4px;color:#ddd;padding:4px 6px;font-size:11px}
  .ks-box textarea{font-family:ui-monospace,Menlo,Consolas,monospace;width:100%;resize:vertical}
  .ks-btn{background:#333;border:1px solid #444;color:#ddd;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px}
  .ks-btn:hover{background:#444}.ks-btn.pri{background:#3a4a80;border-color:#5566aa}
  .ks-chips{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0}
  .ks-chip{padding:2px 8px;border-radius:10px;border:1px solid #444;cursor:pointer;font-size:10px;color:#aaa}
  .ks-chip.on{color:#111;font-weight:600}
  .ks-pal{display:flex;gap:12px;min-height:340px}
  .ks-list{flex:1;overflow:auto;max-height:52vh;border:1px solid #333;border-radius:4px}
  .ks-item{padding:5px 8px;cursor:pointer;border-left:3px solid transparent;display:flex;justify-content:space-between;gap:8px}
  .ks-item:hover,.ks-item.sel{background:#2c2c2c}
  .ks-item small{color:#777}
  .ks-prev{width:300px;overflow:auto;max-height:52vh;line-height:1.45}
  .ks-prev code,.ks-mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10px}
  .ks-tag{display:inline-block;padding:0 5px;border-radius:3px;background:#333;margin:1px;font-size:9px}
  table.ks-t{border-collapse:collapse;width:100%;font-size:10px}
  table.ks-t td,table.ks-t th{padding:3px 6px;border-bottom:1px solid #2e2e2e;text-align:left}
  table.ks-t th{color:#888;font-weight:500}
  .ks-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
  .ks-kpi{background:#1b1b1b;border:1px solid #2e2e2e;border-radius:4px;padding:6px}
  .ks-kpi b{display:block;font-size:14px;color:#eee}.ks-kpi span{font-size:9px;color:#777}
  .ks-err{color:#e74c3c}.ks-warn{color:#f39c12}.ks-ok{color:#2ecc71}
  .ks-link{color:#8fa6ff;cursor:pointer;text-decoration:underline dotted}
  #ksPlot{position:absolute;right:12px;top:12px;width:560px;height:360px;min-width:320px;min-height:220px;resize:both;overflow:hidden;
          background:rgba(24,24,24,.97);border:1px solid #3a3a3a;border-radius:6px;display:none;flex-direction:column;z-index:50;box-shadow:0 6px 24px rgba(0,0,0,.5)}
  #ksPlot.active{display:flex}
  #ksPlot .ks-ph{display:flex;align-items:center;gap:6px;padding:4px 8px;border-bottom:1px solid #333;cursor:move;font-size:10px;color:#aaa;flex-wrap:wrap}
  #ksPlot .ks-pb{flex:1;display:flex;min-height:0}
  #ksPlot .ks-ps{width:150px;overflow:auto;border-right:1px solid #2e2e2e;font-size:10px;padding:4px}
  #ksPlot .ks-ps label{display:flex;gap:4px;align-items:center;white-space:nowrap;cursor:pointer;padding:1px 0}
  #ksPlot .ks-ps i{width:10px;height:3px;display:inline-block;flex-shrink:0}
  #ksPlot .ks-pc{flex:1;position:relative;min-width:0}
  #ksPlot canvas{position:absolute;inset:0;width:100%;height:100%}
  #ksPlot select,#ksPlot button{background:#2a2a2a;border:1px solid #444;color:#ccc;font-size:10px;border-radius:3px;padding:1px 5px}
  .ks-group{border:1px solid #2f3a55;border-radius:5px;padding:6px;margin-bottom:8px;background:#1e2230}
  .ks-group label{display:block;font-size:9px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#8a93a8;margin:4px 0 2px}
  .ks-group .ks-desc{font-size:10px;color:#999;line-height:1.4;margin:3px 0 6px}
  .ks-prow{display:flex;align-items:center;gap:6px;margin:3px 0}
  .ks-prow>span{width:84px;font-size:10px;color:#9aa;overflow:hidden;text-overflow:ellipsis;flex-shrink:0}
  .ks-prow input,.ks-prow select,.ks-prow textarea{flex:1;min-width:0;background:#141414;border:1px solid #333;border-radius:3px;color:#ddd;font-size:10px;padding:2px 4px}
  .ks-prow textarea{font-family:ui-monospace,Menlo,Consolas,monospace;min-height:34px;resize:vertical}
  .ks-out{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:9px;background:#141414;border-radius:3px;padding:4px;max-height:140px;overflow:auto;white-space:pre-wrap;word-break:break-all}
  .ks-bar{height:8px;border-radius:2px;display:inline-block;vertical-align:middle}
  .ks-prow.ks-block{flex-direction:column;align-items:stretch}
  .ks-prow.ks-block>span{width:auto}
  .ks-prow textarea.ks-code{min-height:44px;line-height:1.45;font-size:10.5px;tab-size:4;white-space:pre;overflow:auto}
  .ks-unit{font-style:normal;color:#6c7488;margin-left:3px;font-size:9px}
  .ks-hint{font-size:9px;color:#6c7488;white-space:pre-wrap;margin:-1px 0 5px;line-height:1.35}
  .ks-prow input[type=range]{accent-color:#7c8cff;padding:0;border:none;background:transparent}
  .ks-prow input.ks-expr{color:#ffd479;font-family:ui-monospace,Menlo,monospace;border-color:#6b5a2a!important}
  `;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ------------------------------------------------------------------ helpers
  async function api(path, body, signal) {
    const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal };
    let res;
    try { res = await fetch(BACKEND_URL + path, opt); }
    catch (e) {
      if (e.name === 'AbortError') throw e;
      setHealth(null);
      throw new Error('backend offline — start it with:  python server.py');
    }
    const data = await res.json().catch(() => ({ success: false, error: 'invalid JSON from server' }));
    if (!res.ok && data.success !== false) data.success = false;
    return data;
  }

  /** Show a message (HTML allowed) in the status bar at the bottom of the window. */
  function status(html) { const el = $('#status'); if (el) el.innerHTML = html; }
  /**
   * Compact human-readable formatting for any output value: 4 significant digits, exponents for very
   * small/large numbers, [n] or [r×c] for arrays, {keys…} for objects, quoted short strings.
   */
  function fmt(v, d) {
    d = d || 4;
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      if (!isFinite(v)) return String(v);
      const a = Math.abs(v);
      return (a !== 0 && (a < 1e-3 || a >= 1e5)) ? v.toExponential(d - 1) : String(+v.toPrecision(d));
    }
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (typeof v === 'string') return v.length > 24 ? JSON.stringify(v.slice(0, 22) + '…') : JSON.stringify(v);
    if (Array.isArray(v) && v.length && Array.isArray(v[0])) return '[' + v.length + '×' + v[0].length + ']';
    if (Array.isArray(v)) return '[' + v.length + ']' + (v.length && typeof v[0] === 'number' ? ' ' + fmt(v[0], 3) + '…' : '');
    if (typeof v === 'object') return '{' + Object.keys(v).slice(0, 3).join(',') + (Object.keys(v).length > 3 ? ',…' : '') + '}';
    return String(v);
  }
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const nodeName = (id) => (graph.nodes[id] ? graph.nodes[id].name : '#' + id);
  const numericArray = (v) => Array.isArray(v) && v.length > 1 && v.every(x => typeof x === 'number' || x === null);

  /**
   * Open (creating on first use) a modal dialog with the given id, title and width; returns its body element.
   * Clicking the backdrop, ✕ or Esc closes it.
   */
  function modal(id, title, width) {
    let m = document.getElementById(id);
    if (!m) {
      m = document.createElement('div');
      m.id = id; m.className = 'ks-modal';
      m.innerHTML = `<div class="ks-box" style="width:${width || 640}px"><div class="ks-head"><h2></h2><button class="ks-x">✕</button></div><div class="ks-body"></div></div>`;
      document.body.appendChild(m);
      m.addEventListener('mousedown', e => { if (e.target === m) m.classList.remove('active'); });
      $('.ks-x', m).onclick = () => m.classList.remove('active');
    }
    $('h2', m).textContent = title;
    m.classList.add('active');
    return $('.ks-body', m);
  }

  // ------------------------------------------------------------------ serialisation
  function serializeNode(n) {
    const props = n.properties || {};
    const tpl = props.template ? KS.byId[props.template] : null;
    return {
      name: n.name, code: n.code,
      inputs: n.inputs.filter(p => p.enabled && !p.isDummy).map(p => p.name),
      outputs: n.outputs.filter(p => p.enabled && !p.isDummy).map(p => p.name),
      params: props.params || {}, template: props.template || null,
      stateful: tpl ? !!tpl.stateful : undefined,
      subgraph: props.subgraph || undefined,
      bypass: props.bypass || undefined, frozen: props.frozen || undefined,
      break_if: props.break_if || undefined, cache: props.cache === false ? false : undefined,
    };
  }
  /**
   * Convert the editor graph into the engine payload: enabled ports by name, params, template, flags,
   * group subgraphs, and enabled data wires (dummy-port wires become 'relation' edges).
   */
  function serialize() {
    const nodes = {}, connections = [];
    for (const id in graph.nodes) nodes[id] = serializeNode(graph.nodes[id]);
    for (const id in graph.wires) {
      const w = graph.wires[id];
      if (!w.enabled) continue;
      const fp = w.fromPortObj, tp = w.toPortObj;
      if ((fp && !fp.enabled) || (tp && !tp.enabled)) continue;
      connections.push({ id: +id, from: String(w.from), to: String(w.to),
        fromPort: fp ? fp.name : w.fromPort, toPort: tp ? tp.name : w.toPort,
        kind: w.wireClass === 'dummy' ? 'relation' : 'data' });
    }
    return { nodes, connections };
  }

  // ------------------------------------------------------------------ templates
  // Port rules shared with knode_universal.derive_ports (Python)
  function derivePorts(tpl, params) {
    if (!tpl || !tpl.ports) return [tpl ? tpl.inputs.slice() : [], tpl ? tpl.outputs.slice() : []];
    const txt = v => String(v === undefined || v === null ? '' : v);
    const names = t => txt(t).replace(/\n/g, ',').split(',').map(x => x.trim()).filter(Boolean);
    const lhs = t => { const o = []; for (const l of txt(t).replace(/;/g, '\n').split('\n')) { const m = l.split('#')[0].match(/^\s*([A-Za-z_]\w*)\s*=(?!=)/); if (m && !o.includes(m[1])) o.push(m[1]); } return o; };
    const species = t => { const o = []; for (const l of txt(t).split('\n')) { const line = l.split('#')[0]; if (!line.includes('->')) continue;
      for (const side of line.split(',')[0].split('->')) for (const tok of side.split('+')) { const m = tok.match(/^\s*\d*\s*([A-Za-z_]\w*)\s*$/); if (m && !o.includes(m[1])) o.push(m[1]); } } return o; };
    const smout = t => { const o = []; for (const l of txt(t).split('\n')) { const m = l.split('#')[0].match(/^\s*(\*|[A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*=(?!=)/); if (m && !o.includes(m[2])) o.push(m[2]); } return o; };
    return ['inputs', 'outputs'].map(side => {
      const out = [];
      for (const tok of (tpl.ports[side] || [])) {
        const i = tok.indexOf(':'), kind = tok.slice(0, i), arg = tok.slice(i + 1);
        let add = [];
        if (kind === 'list') add = names(params[arg]);
        else if (kind === 'lhs') add = lhs(params[arg]);
        else if (kind === 'species') add = species(params[arg]);
        else if (kind === 'smout') add = smout(params[arg]);
        else if (kind === 'const') add = arg.split(',').filter(Boolean);
        else if (kind === 'suffix') { const j = arg.indexOf(':'); add = names(params[arg.slice(0, j)]).map(n => n + arg.slice(j + 1)); }
        for (const n of add) if (!out.includes(n)) out.push(n);
      }
      return out;
    });
  }

  // Make a node's ports match the given names; wires on kept ports survive, wires on removed ports are deleted.
  function syncPorts(node, ins, outs) {
    const fix = (arr, want, isInput) => {
      for (const p of [...arr]) {
        if (p.isDummy || want.includes(p.name)) continue;
        for (const wid of [...p.connections]) if (graph.wires[wid]) graph.removeWire(wid);
        arr.splice(arr.indexOf(p), 1);
      }
      for (const n of want) if (!arr.some(p => p.name === n)) isInput ? node.addInput(n, 4) : node.addOutput(n, 16);
      arr.sort((a, b) => want.indexOf(a.name) - want.indexOf(b.name));
    };
    fix(node.inputs, ins, true);
    fix(node.outputs, outs, false);
    node._updateHeight();
  }

  /**
   * Create a node from a library template at (x, y): ports derived from the (merged) parameters,
   * template code (locked against regeneration), description and category colour.
   */
  function createFromTemplate(tpl, x, y, params, name) {
    const node = graph.addNode(name || tpl.name, Math.round(x), Math.round(y), 'standard');
    node.properties = { template: tpl.id, params: tpl.open_params && params && Object.keys(params).length ? clone(params) : Object.assign(clone(tpl.params), params || {}) };
    node.inputs = []; node.outputs = [];
    const [ins, outs] = derivePorts(tpl, node.properties.params);
    for (const p of ins) node.addInput(p, 4);
    for (const p of outs) node.addOutput(p, 16);
    node.code = tpl.code;
    node.description = tpl.description;
    node.setLineColor(tpl.color);
    node._updateHeight();
    return node;
  }

  /** Convert client (screen) coordinates to canvas world coordinates, respecting pan and zoom. */
  function worldAtScreen(cx, cy) {
    const r = renderer.canvas.getBoundingClientRect();
    return renderer.viewport.toWorld(cx - r.left, cy - r.top);
  }
  /** World coordinates of the centre of the visible canvas. */
  function viewCenter() {
    const r = renderer.canvas.getBoundingClientRect();
    return worldAtScreen(r.left + r.width / 2, r.top + r.height / 2);
  }

  /** Add a template node at a world position (or the view centre), select it and record undo. Returns the node. */
  function addTemplateAt(tid, world) {
    const tpl = KS.byId[tid];
    if (!tpl) return;
    const p = world || viewCenter();
    const node = createFromTemplate(tpl, p.x - 85, p.y - 30);
    if (KS.noteRecent) KS.noteRecent(tid);                 // "Recent" list in the context menu
    graph.selectedNodes = [node.id]; graph.selectedWires = [];
    renderer.render(); updateLiveState(); updateStatus(); updatePropertiesPanel(node);
    status(`Added <b>${esc(tpl.name)}</b> — ${esc(tpl.description)}`);
    addDebugEntry('Added template node "' + tpl.name + '" (ID ' + node.id + ')', 'node');
    saveState();
    return node;
  }

  // ------------------------------------------------------------------ palette
  let palState = { q: '', cat: null, sel: 0, items: [], at: null };
  /**
   * Open the searchable node library. opts.filter(template) restricts the list; opts.onPick(node) runs after
   * the node is created (used by link-drag search to auto-connect).
   */
  function openPalette(world, opts) {
    opts = opts || {};
    palState.filter = opts.filter || null; palState.onPick = opts.onPick || null;
    if (!KS.library) { status('<span class="ks-err">Library unavailable — start the backend (python server.py)</span>'); loadLibrary(); return; }
    palState.at = world || null;
    const body = modal('ksPalette', 'Node library — ' + KS.library.templates.length + ' models', 820);
    body.innerHTML = `
      <input class="ks-input" id="ksQ" placeholder="Search models, domains, equations… (↑↓ to move, Enter to add)" style="width:100%">
      <div class="ks-chips" id="ksCats"></div>
      <div class="ks-pal"><div class="ks-list" id="ksList"></div><div class="ks-prev" id="ksPrev"></div></div>`;
    const cats = $('#ksCats', body);
    cats.innerHTML = `<span class="ks-chip ${palState.cat ? '' : 'on'}" data-c="" style="${palState.cat ? '' : 'background:#ccc'}">All</span>` +
      Object.entries(KS.library.categories).map(([c, col]) =>
        `<span class="ks-chip ${palState.cat === c ? 'on' : ''}" data-c="${esc(c)}" style="border-color:${col};${palState.cat === c ? 'background:' + col : ''}">${esc(c)}</span>`).join('');
    cats.onclick = e => { const c = e.target.dataset.c; if (c === undefined) return; palState.cat = c || null; palState.sel = 0; openPalette(palState.at); };
    const q = $('#ksQ', body);
    q.value = palState.q;
    q.oninput = () => { palState.q = q.value; palState.sel = 0; renderPalList(); };
    q.onkeydown = e => {
      if (e.key === 'ArrowDown') { palState.sel = Math.min(palState.items.length - 1, palState.sel + 1); renderPalList(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { palState.sel = Math.max(0, palState.sel - 1); renderPalList(); e.preventDefault(); }
      else if (e.key === 'Enter' && palState.items[palState.sel]) { pickPalette(palState.items[palState.sel].id); }
      else if (e.key === 'Escape') { $('#ksPalette').classList.remove('active'); }
    };
    renderPalList();
    setTimeout(() => { q.focus(); q.select(); }, 0);        // typing replaces the previous query
  }
  /** Re-render palette results for the current query/category and the preview of the highlighted template. */
  function renderPalList() {
    const terms = palState.q.toLowerCase().split(/\s+/).filter(Boolean);
    palState.items = KS.library.templates.filter(t => {
      if (palState.cat && t.category !== palState.cat) return false;
      if (palState.filter && !palState.filter(t)) return false;
      const hay = (t.name + ' ' + t.category + ' ' + t.description + ' ' + t.id + ' ' + t.inputs.join(' ') + ' ' + t.outputs.join(' ')).toLowerCase();
      return terms.every(w => hay.includes(w));
    });
    const list = $('#ksList');
    list.innerHTML = palState.items.map((t, i) =>
      `<div class="ks-item ${i === palState.sel ? 'sel' : ''}" data-i="${i}" style="border-left-color:${t.color}">
        <span>${esc(t.name)}${t.stateful ? ' <span class="ks-tag" title="stateful: evolves over simulation steps">⟳ dynamic</span>' : ''}</span><small>${esc(t.category)}</small></div>`).join('')
      || '<div style="padding:10px;color:#777">No matches</div>';
    list.onmousemove = e => { const it = e.target.closest('.ks-item'); if (it && +it.dataset.i !== palState.sel) { palState.sel = +it.dataset.i; renderPalList(); } };
    list.onclick = e => { const it = e.target.closest('.ks-item'); if (it) pickPalette(palState.items[+it.dataset.i].id); };
    const sel = list.querySelector('.sel'); if (sel) sel.scrollIntoView({ block: 'nearest' });
    const t = palState.items[palState.sel];
    $('#ksPrev').innerHTML = t ? `
      <div style="font-size:13px;color:#eee;margin-bottom:4px">${esc(t.name)}</div>
      <div style="color:${t.color};font-size:10px;margin-bottom:6px">${esc(t.category)}${t.stateful ? ' · dynamic (use ▶▶ Simulate)' : ''}</div>
      <div style="margin-bottom:8px">${esc(t.description)}</div>
      <div><b style="color:#888">in</b> ${t.inputs.map(p => `<span class="ks-tag">${esc(p)}</span>`).join('') || '—'}</div>
      <div><b style="color:#888">out</b> ${t.outputs.map(p => `<span class="ks-tag">${esc(p)}</span>`).join('')}</div>
      <div style="margin-top:6px"><b style="color:#888">params</b><div class="ks-mono">${Object.entries(t.params).map(([k, v]) => esc(k) + ' = ' + esc(JSON.stringify(v))).join('<br>') || '—'}</div></div>
      ${t.refs.length ? `<div style="margin-top:6px;color:#888">Refs: ${t.refs.map(esc).join('; ')}</div>` : ''}` : '';
  }
  /** Create the chosen template at the palette's anchor position and fire the onPick callback. */
  function pickPalette(tid) {
    $('#ksPalette').classList.remove('active');
    const node = addTemplateAt(tid, palState.at);
    if (palState.onPick && node) palState.onPick(node);
    palState.onPick = null; palState.filter = null;
  }

  // ------------------------------------------------------------------ results & overlays
  function applyResults(rep, sim) {
    if (KS.levelView) rep = KS.levelView(rep);
    KS.results = {};
    const prof = rep.profile || {};
    for (const id in graph.nodes) {
      const st = (rep.status || {})[id];
      if (!st) continue;
      KS.results[id] = { status: st, outputs: (rep.outputs || {})[id], error: (rep.errors || {})[id], ms: prof[id] ? prof[id].mean_ms : null };
    }
    renderer.render();
    const sel = graph.selectedNodes.length === 1 ? graph.nodes[graph.selectedNodes[0]] : null;
    if (sel) updatePropertiesPanel(sel);
  }

  /**
   * Write a run/simulation report into the State panel: per-node outputs, errors with tracebacks,
   * stdout, loop convergence and warnings.
   */
  function logReport(rep, title) {
    const ok = rep.success;
    let h = `<div class="${ok ? 'ks-ok' : 'ks-err'}">${ok ? '✓' : '✗'} ${esc(title)}${rep.wall_ms != null ? ` · ${rep.wall_ms} ms` : ''}${rep.stopped ? ` · stopped: ${esc(rep.stopped)}` : ''}</div>`;
    if (rep.cycles && rep.cycles.length) h += `<div class="ks-warn" style="font-size:8px">↻ feedback loops: ${rep.cycles.map(c => c.map(nodeName).map(esc).join('→')).join(' | ')}${rep.mode === 'simulate' ? ' (one-step delay at back edge)' : ''}</div>`;
    for (const l of rep.loops || []) h += `<div style="font-size:8px;color:${l.converged ? '#2ecc71' : '#e74c3c'}">algebraic loop ${l.converged ? 'converged' : 'did NOT converge'} in ${l.iterations} iterations</div>`;
    for (const id in rep.status || {}) {
      const st = rep.status[id];
      if (st === 'ok') {
        const o = (rep.outputs || {})[id] || {};
        h += `<div style="font-size:8px;padding-left:8px;color:#c8c8c8">${esc(nodeName(id))}: ${esc(Object.entries(o).map(([k, v]) => k + '=' + fmt(v)).join(', '))}</div>`;
      } else if (st === 'error') {
        const e = rep.errors[id];
        h += `<div class="ks-err" style="font-size:8px;padding-left:8px">✗ ${esc(nodeName(id))}${e.line ? ' (line ' + e.line + ')' : ''}: ${esc(e.error)}</div>`;
        if (e.traceback) h += `<div style="font-size:7px;color:#777;white-space:pre-wrap;padding-left:16px">${esc(e.traceback)}</div>`;
      } else h += `<div style="font-size:8px;padding-left:8px;color:#666">· ${esc(nodeName(id))}: ${esc(st)} (upstream error)</div>`;
      const so = (rep.stdout || {})[id];
      if (so) h += `<div style="font-size:7px;color:#f39c12;white-space:pre-wrap;padding-left:16px">${esc(so.trim().slice(0, 2000))}</div>`;
    }
    for (const w of rep.warnings || []) h += `<div class="ks-warn" style="font-size:8px">⚠ ${esc(w)}</div>`;
    executionLogs.push(h);
    updateLiveState();
  }

  /** Perceptual blue→green→yellow colour for a value in [0, 1] (viridis-like); used by heat-maps and gauges. */
  function heatColor(v) {           // perceptual-ish blue→yellow→red ramp
    const stops = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
    const x = Math.max(0, Math.min(1, v)) * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(x)), f = x - i;
    const c = stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  /**
   * Normalised sparkline for a trace: a Float32Array [x0, y0, x1, y1, …] in 0..1, ≤ 2×75 points.
   * Cached per trace array and its length (0.5). In 0.4 every frame re-filtered and min/max-scanned
   * the full trace of every node — ~1 M values per frame for 200 nodes × 5 000 steps.
   * The cache stays valid in live mode because it is re-validated by length as traces grow.
   * Each of the 75 buckets contributes its min and max, so spikes are never lost.
   */
  const sparkCache = new WeakMap();
  function sparkPoints(arr) {
    const hit = sparkCache.get(arr);
    if (hit && hit.len === arr.length) return hit.pts;
    let lo = Infinity, hi = -Infinity, n = 0;
    for (const v of arr) if (v !== null) { if (v < lo) lo = v; if (v > hi) hi = v; n++; }
    if (n < 2) return null;
    if (hi === lo) { hi += 1; lo -= 1; }
    const B = Math.min(75, arr.length), pts = [];
    for (let b = 0; b < B; b++) {
      const i0 = Math.floor(b * arr.length / B), i1 = Math.max(i0 + 1, Math.floor((b + 1) * arr.length / B));
      let mn = Infinity, mx = -Infinity, imn = i0, imx = i0;
      for (let i = i0; i < i1; i++) { const v = arr[i]; if (v === null) continue; if (v < mn) { mn = v; imn = i; } if (v > mx) { mx = v; imx = i; } }
      if (mn === Infinity) continue;
      const first = imn <= imx ? [imn, mn] : [imx, mx], second = imn <= imx ? [imx, mx] : [imn, mn];
      pts.push(first[0] / (arr.length - 1), (first[1] - lo) / (hi - lo), second[0] / (arr.length - 1), (second[1] - lo) / (hi - lo));
    }
    const out = Float32Array.from(pts);
    sparkCache.set(arr, { len: arr.length, pts: out });
    return out;
  }

  /**
   * Canvas overlay drawn after the nodes (world coordinates): centrality heat-map halos, group-card
   * outlines, error/blocked outlines, output values under each node and sparklines of their traces.
   */
  KS.drawOverlays = function (ctx) {
    const traces = KS.lastSim && !KS.inGroup && KS.lastSim.traces;
    for (const id in graph.nodes) {
      const n = graph.nodes[id];
      const x = n.x, y = n.y, w = n.width, h = n.height;
      if (n.properties && n.properties.template === 'reroute') continue;   // wire dots carry no labels
      if (KS.heat && KS.heat.values[id] !== undefined) {
        ctx.save();
        ctx.strokeStyle = heatColor(KS.heat.values[id]); ctx.lineWidth = 3;
        ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 10;
        renderer.roundRect(ctx, x - 4, y - 4, w + 8, h + 8, 8); ctx.stroke();
        ctx.restore();
        ctx.fillStyle = heatColor(KS.heat.values[id]);
        ctx.font = '7px "Segoe UI", Arial, sans-serif'; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
        ctx.fillText(KS.heat.metric + ' ' + fmt(KS.heat.raw[id], 3), x + w, y - 6);
      }
      if (n.properties && n.properties.subgraph) {          // group nodes: stacked-card outline
        ctx.save(); ctx.strokeStyle = '#9aa4b8'; ctx.globalAlpha = 0.55; ctx.lineWidth = 1;
        renderer.roundRect(ctx, x + 4, y - 4, w, h, 7); ctx.stroke();
        renderer.roundRect(ctx, x + 8, y - 8, w, h, 8); ctx.globalAlpha = 0.3; ctx.stroke(); ctx.restore();
      }
      const r = KS.results[id];
      if (!r) continue;
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      if (r.status === 'error') {
        ctx.save(); ctx.strokeStyle = '#e74c3c'; ctx.lineWidth = 1.5; renderer.roundRect(ctx, x - 2, y - 2, w + 4, h + 4, 7); ctx.stroke(); ctx.restore();
        ctx.fillStyle = '#e74c3c'; ctx.font = '7px "Segoe UI", Arial, sans-serif';
        const msg = (r.error.line ? 'line ' + r.error.line + ': ' : '') + r.error.error;
        ctx.fillText('✗ ' + (msg.length > 48 ? msg.slice(0, 46) + '…' : msg), x, y + h + 3);
        continue;
      }
      if (r.status === 'blocked') {
        ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = '#666'; renderer.roundRect(ctx, x - 2, y - 2, w + 4, h + 4, 7); ctx.stroke(); ctx.restore();
        continue;
      }
      const outs = r.outputs || {};
      if (renderer.viewport.zoom < 0.35) continue;          // level of detail: labels unreadable when zoomed far out
      const keys = Object.keys(outs).slice(0, 3);
      ctx.font = '7px ui-monospace, Menlo, Consolas, monospace';
      keys.forEach((k, i) => {
        ctx.fillStyle = '#8a9bb0';
        ctx.fillText(k + ' = ' + fmt(outs[k]), x + 2, y + h + 3 + i * 9);
      });
      // sparkline of the first traced numeric output
      if (traces) {
        const k = (n.outputs || []).map(p => id + '.' + p.name).find(key => traces[key]);
        const sp = k && sparkPoints(traces[k]);
        if (sp) {
          const sy = y + h + 5 + keys.length * 9, sh = 16;
          ctx.strokeStyle = n.lineColor; ctx.lineWidth = 1; ctx.globalAlpha = 0.85; ctx.beginPath();
          for (let i = 0; i < sp.length; i += 2) {
            const px = x + sp[i] * w, py = sy + sh - sp[i + 1] * sh;
            i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
          }
          ctx.stroke(); ctx.globalAlpha = 1;
        }
      }
    }
  };

  // ------------------------------------------------------------------ properties panel
  KS.decorateProperties = function (node, container) {
    if (!node || graph.selectedNodes.length !== 1) return;
    const props = node.properties || (node.properties = {});
    const tpl = props.template ? KS.byId[props.template] : null;
    const params = props.params || {};
    const r = KS.results[node.id];
    let h = `<div class="ks-group">`;
    if (tpl) h += `<label style="color:${tpl.color}">${esc(tpl.category)} · ${esc(tpl.name)}</label><div class="ks-desc">${esc(tpl.description)}${tpl.refs.length ? '<br><i>' + tpl.refs.map(esc).join('; ') + '</i>' : ''}</div>`;
    if (props.subgraph) {
      const inner = Object.values(props.subgraph.nodes || {});
      h += `<label>Group</label><div class="ks-desc">${inner.length} inner nodes · inputs: ${node.inputs.map(p => esc(p.name)).join(', ') || '—'} · outputs: ${node.outputs.map(p => esc(p.name)).join(', ') || '—'}</div>
            <div style="display:flex;gap:4px;margin-bottom:6px"><button class="refresh-btn exec-btn" id="ksEnterGrp">⤵ Enter group</button><button class="refresh-btn" id="ksUngroup">Ungroup</button></div>`;
    }
    h += `<label>Parameters</label>`;
    for (const [k, v] of Object.entries(params)) {
      const sc = (tpl && tpl.schema && tpl.schema[k]) || (props.schema && props.schema[k]) || {};
      const isExpr = typeof v === 'string' && v.startsWith('=');
      const kind = isExpr ? 'expr' : sc.kind || (ENUMS[k] ? 'select' : typeof v === 'boolean' ? 'bool' : typeof v === 'number' ? 'number'
        : (typeof v === 'string' && (LONG_TEXT.test(k) || v.includes('\n') || v.length > 30)) ? 'code' : typeof v === 'string' ? 'text' : 'json');
      const opts = sc.options || ENUMS[k];
      const unit = sc.unit ? `<em class="ks-unit">${esc(sc.unit)}</em>` : '';
      let input;
      if (kind === 'select' && opts) input = `<select data-k="${esc(k)}">${opts.map(o => `<option ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
      else if (kind === 'bool') input = `<input type="checkbox" data-k="${esc(k)}" ${v ? 'checked' : ''} style="flex:0">`;
      else if (kind === 'number' && sc.min !== undefined && sc.max !== undefined)
        input = `<input type="range" data-slider="${esc(k)}" min="${sc.min}" max="${sc.max}" step="${sc.step || 'any'}" value="${v}" style="flex:1.3"><input type="number" step="any" data-k="${esc(k)}" value="${v}" style="flex:.8">`;
      else if (kind === 'number') input = `<input type="number" step="${sc.step || 'any'}" data-k="${esc(k)}" value="${v === null ? '' : v}">`;
      else if (kind === 'code') input = `<textarea class="ks-code" data-k="${esc(k)}" spellcheck="false" rows="${Math.min(14, Math.max(2, String(v).split('\n').length + 1))}">${esc(v)}</textarea>`;
      else if (kind === 'json') input = `<textarea data-k="${esc(k)}" data-json="1" spellcheck="false">${esc(JSON.stringify(v))}</textarea>`;
      else if (kind === 'expr') input = `<input type="text" class="ks-expr" data-k="${esc(k)}" data-expr="1" value="${esc(v)}" title="expression — evaluated against Globals">`;
      else input = `<input type="text" data-k="${esc(k)}" value="${esc(v)}">`;
      const block = kind === 'code' ? ' ks-block' : '';
      h += `<div class="ks-prow${block}" title="${esc(sc.doc || '')}"><span>${esc(k)}${unit}</span>${input}${tpl && !tpl.open_params ? '' : `<button class="btn-small btn-danger" data-del="${esc(k)}">×</button>`}</div>`;
      if (kind === 'code' && sc.doc) h += `<div class="ks-hint">${esc(sc.doc)}</div>`;
    }
    if (!Object.keys(params).length) h += `<div class="ks-desc">none — code receives <code>params</code> as a dict</div>`;
    h += `<div class="ks-prow"><input type="text" id="ksNewK" placeholder="new param"><input type="text" id="ksNewV" placeholder="value (JSON or text)"><button class="btn-small" id="ksAddP">+</button></div>`;
    if (r) {
      h += `<label style="margin-top:6px">Last result <span style="color:${r.status === 'ok' ? '#2ecc71' : '#e74c3c'}">${esc(r.status)}</span>${r.ms != null ? ` · ${r.ms} ms/call` : ''}</label>`;
      if (r.status === 'error') h += `<div class="ks-out ks-err">${r.error.line ? 'line ' + r.error.line + ': ' : ''}${esc(r.error.error)}\n${esc(r.error.traceback || '')}</div>`;
      else if (r.outputs) h += `<div class="ks-out">${esc(JSON.stringify(r.outputs, null, 1).slice(0, 4000))}</div>`;
    }
    h += `<div style="display:flex;gap:4px;margin-top:6px;flex-wrap:wrap">
            <button class="refresh-btn exec-btn" id="ksRunTo">▶ Run to here</button>
            <button class="refresh-btn" id="ksPlotNode">📈 Plot outputs</button></div></div>`;
    container.insertAdjacentHTML('afterbegin', h);
    const grp = container.querySelector('.ks-group');
    const commit = (k, v) => {
      props.params = props.params || {}; props.params[k] = v;
      addDebugEntry(`Param ${node.name}.${k} = ${JSON.stringify(v).slice(0, 80)}`, 'node');
      if (tpl && tpl.ports) {
        const [ins, outs] = derivePorts(tpl, props.params);
        const same = ins.join() === node.inputs.map(p => p.name).join() && outs.join() === node.outputs.map(p => p.name).join();
        if (!same) { syncPorts(node, ins, outs); renderer.render(); status(`Ports updated: in [${ins.join(', ')}] · out [${outs.join(', ')}]`); }
      }
      saveState();
      renderer.render();
      if (KS.autoRun) scheduleAutoRun();
    };
    grp.querySelectorAll('[data-k]').forEach(el => el.addEventListener('change', () => {
      const k = el.dataset.k; let v;
      if (el.type === 'checkbox') v = el.checked;
      else if (el.type === 'number') v = el.value === '' ? null : parseFloat(el.value);
      else if (el.dataset.expr && !el.value.trim().startsWith('=')) v = isNaN(parseFloat(el.value)) ? el.value : parseFloat(el.value);
      else if (el.dataset.json) { try { v = JSON.parse(el.value); } catch (e) { v = el.value; } }
      else v = el.value;
      const sl = grp.querySelector(`[data-slider="${k}"]`); if (sl && typeof v === 'number') sl.value = v;
      commit(k, v);
    }));
    grp.querySelectorAll('[data-slider]').forEach(sl => {
      const k = sl.dataset.slider, box = grp.querySelector(`[data-k="${k}"]`);
      sl.addEventListener('input', () => { box.value = sl.value; props.params[k] = parseFloat(sl.value); if (KS.autoRun) scheduleAutoRun(); renderer.render(); });
      sl.addEventListener('change', () => commit(k, parseFloat(sl.value)));
    });
    grp.querySelectorAll('textarea.ks-code').forEach(ta => ta.addEventListener('keydown', e => {
      if (e.key === 'Tab') { e.preventDefault(); const p0 = ta.selectionStart; ta.setRangeText('    ', p0, ta.selectionEnd, 'end'); }
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ta.blur();          // commit, then the global shortcut runs
    }));
    const eg = $('#ksEnterGrp', grp); if (eg) eg.onclick = () => KnodeUI.enterGroup(node.id);
    const ug = $('#ksUngroup', grp); if (ug) ug.onclick = () => KnodeUI.ungroup(node.id);
    grp.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { delete props.params[b.dataset.del]; saveState(); updatePropertiesPanel(node); });
    $('#ksAddP', grp).onclick = () => {
      const k = $('#ksNewK', grp).value.trim(); if (!k) return;
      let v = $('#ksNewV', grp).value; try { v = JSON.parse(v); } catch (e) { /* keep text */ }
      props.params = props.params || {}; props.params[k] = v; saveState(); updatePropertiesPanel(node);
    };
    $('#ksRunTo', grp).onclick = () => executeSingleNode(node.id);
    $('#ksPlotNode', grp).onclick = () => {
      const keys = node.outputs.map(p => node.id + '.' + p.name);
      KS.plotSel = { x: 'default', y: keys };
      openPlot();
    };
  };

  // ------------------------------------------------------------------ run / simulate
  function animateWires(on) {
    for (const id in graph.wires) {
      const w = graph.wires[id];
      if (!w.enabled) continue;
      if (on === 'pulse') w.setPulsating(true);
      else if (on) w.startAnimation();
      else { w.stopAnimation(); w.setPulsating(false); }
    }
  }

  /**
   * Run once (optionally only up to a target node and its ancestors), then show results on the canvas,
   * in the Properties panel and the State panel. Uses the result cache unless disabled.
   */
  async function runGraph(target) {
    if (KS.busy) return;
    KS.busy = true;
    const payload = KS.serialize();
    if (target === null || target === undefined) KS.lastMode = 'run';
    if (target !== undefined && target !== null) payload.target = String(target);
    status(target != null ? `Running up to “${esc(nodeName(target))}”…` : 'Running graph…');
    animateWires(true);
    try {
      const rep = await api('/graph/execute', Object.assign(payload, { dt: +$('#ksDt').value || 0.01, cache: KS.useCache !== false }));
      KS.lastRun = rep;
      if (rep.outputs === undefined) throw new Error(rep.error || 'server error');
      KS.applyResults(rep);
      logReport(KS.levelView ? KS.levelView(rep) : rep, target != null ? 'Run to ' + nodeName(target) : 'Graph run');
      const nerr = Object.keys(rep.errors || {}).length;
      status(nerr ? `<span class="ks-err">${nerr} node(s) failed — see State panel</span>` :
        `<span class="ks-ok">✓ ${Object.keys(rep.status).length - (rep.cached || []).length} node(s) executed${(rep.cached || []).length ? `, ${rep.cached.length} reused from cache` : ''}</span>${rep.cycles && rep.cycles.length ? ' · loops solved by fixed-point iteration' : ''}`);
      addDebugEntry('Graph executed', nerr ? 'error' : 'success');
    } catch (e) {
      status(`<span class="ks-err">${esc(e.message)}</span>`);
      addDebugEntry(e.message, 'error');
    } finally {
      animateWires(false); KS.busy = false; renderer.render();
    }
  }

  let autoTimer = null;
  /** Debounced re-run after a parameter change when ⟳ auto is on: repeats the last mode (run or simulate). */
  function scheduleAutoRun() {
    clearTimeout(autoTimer);
    autoTimer = setTimeout(() => { if (KS.busy) return scheduleAutoRun(); (KS.lastMode === 'simulate' ? runSimulation : () => runGraph(null))(); }, 450);
  }

  /**
   * Fixed-step simulation using the toolbar's steps and dt; a second click aborts the request.
   * Opens the plot panel with the recorded traces.
   */
  async function runSimulation() {
    if (KS.busy) { if (KS.abort) KS.abort.abort(); return; }
    KS.lastMode = 'simulate';
    const steps = Math.max(1, parseInt($('#ksSteps').value) || 1000), dt = parseFloat($('#ksDt').value) || 0.01;
    KS.busy = true; KS.abort = new AbortController();
    const btn = $('#ksSimBtn'); btn.textContent = '■ Stop';
    status(`Simulating ${steps} steps × dt=${dt}…`);
    animateWires('pulse');
    try {
      const rep = await api('/graph/simulate', Object.assign(KS.serialize(), { steps, dt }), KS.abort.signal);
      KS.traceNames = KS.rootNames ? KS.rootNames() : Object.fromEntries(Object.entries(graph.nodes).map(([i, n]) => [i, n.name]));
      if (rep.traces === undefined) throw new Error(rep.error || 'server error');
      KS.lastSim = rep; KS.lastRun = rep;
      KS.applyResults(rep, true);
      logReport(KS.levelView ? Object.assign(KS.levelView(rep), { wall_ms: rep.wall_ms, stopped: rep.stopped }) : rep, `Simulation ${rep.steps_completed}/${steps} steps (t = ${fmt(rep.traces.t[rep.traces.t.length - 1])})`);
      const nerr = Object.keys(rep.errors || {}).length;
      if (rep.breakpoint) { status(`<span class="ks-warn">⏸ ${esc(rep.stopped)}</span> (step ${rep.breakpoint.step})`); graph.selectedNodes = [Number(rep.breakpoint.node)]; }
      else status(nerr ? `<span class="ks-err">Simulation stopped: ${esc(rep.stopped || '')}</span>` :
        `<span class="ks-ok">✓ simulated ${rep.steps_completed} steps in ${rep.wall_ms} ms</span> · ${Object.keys(rep.traces).length - 1} traces recorded`);
      openPlot();
    } catch (e) {
      status(e.name === 'AbortError' ? 'Simulation cancelled (server finishes its current run in the background)' : `<span class="ks-err">${esc(e.message)}</span>`);
    } finally {
      animateWires(false); KS.busy = false; KS.abort = null; btn.textContent = '▶▶ Simulate'; renderer.render();
    }
  }

  // Override the editor's run entry points
  window.executeGraphWithUI = () => runGraph(null);
  window.executeSingleNode = (id) => runGraph(id);
  // Code-editor ▶ Test: send the node itself + real upstream values from the last run
  window.executeNode = async function (nodeId, inputs) {
    const node = graph.nodes[nodeId];
    const filled = Object.assign({}, inputs || {});
    for (const id in graph.wires) {
      const w = graph.wires[id];
      if (w.to !== node.id || !w.enabled) continue;
      const src = KS.results[w.from];
      const port = w.toPortObj ? w.toPortObj.name : w.toPort, sp = w.fromPortObj ? w.fromPortObj.name : w.fromPort;
      if (src && src.outputs && sp in src.outputs) filled[port] = src.outputs[sp];
    }
    try { return await api(`/node/${nodeId}/execute`, { inputs: filled, node: serializeNode(node) }); }
    catch (e) { return { success: false, error: e.message }; }
  };

  // ------------------------------------------------------------------ plot panel
  function seriesRegistry() {
    const reg = [];
    const tr = KS.lastSim && KS.lastSim.traces;
    if (tr) for (const k in tr) {
      if (k === 't') continue;
      const [id, port] = [k.slice(0, k.indexOf('.')), k.slice(k.indexOf('.') + 1)];
      const nm = (KS.traceNames || {})[id] || (graph.nodes[id] && graph.nodes[id].name);
      if (!nm) continue;
      reg.push({ key: k, label: nm + '.' + port, y: tr[k], x: tr.t, xlabel: 't', group: 'Time series' });
    }
    const outs = (KS.lastRun && KS.lastRun.outputs) || {};
    for (const id in outs) {
      if (!graph.nodes[id]) continue;
      for (const [port, v] of Object.entries(outs[id] || {})) {
        if (Array.isArray(v) && v.length > 1 && Array.isArray(v[0]) && numericArray(v[0])) {
          reg.push({ key: 'fld:' + id + '.' + port, label: nodeName(id) + '.' + port + ' ▦', field: v, y: [], x: null, group: 'Fields (heat-map)' });
          continue;
        }
        if (numericArray(v)) reg.push({ key: 'arr:' + id + '.' + port, label: nodeName(id) + '.' + port + ' []', y: v, x: null, xlabel: 'index', group: 'Arrays' });
        else if (v && typeof v === 'object' && !Array.isArray(v))
          for (const [sub, a] of Object.entries(v)) if (numericArray(a))
            reg.push({ key: 'arr:' + id + '.' + port + '.' + sub, label: nodeName(id) + '.' + port + '.' + sub + ' []', y: a, x: null, xlabel: 'index', group: 'Arrays' });
      }
    }
    if (KS.sweep) reg.push(KS.sweep);
    return reg;
  }

  /**
   * Open the plot panel and (re)build its series list: time traces, array outputs, 2-D fields, sweep
   * results. Picks sensible default series when the current selection no longer exists.
   */
  function openPlot() {
    let p = $('#ksPlot');
    if (!p) {
      p = document.createElement('div');
      p.id = 'ksPlot';
      p.innerHTML = `<div class="ks-ph"><b style="color:#ddd">Plot</b>
          X <select id="ksPX"></select>
          <label><input type="checkbox" id="ksPLog"> log y</label>
          <label><input type="checkbox" id="ksPNorm"> normalise</label>
          <span style="flex:1"></span>
          <button id="knKeep" title="Keep this run to compare with the next ones" onclick="KnodeStudio.keepRun()">📌 keep</button>
          <button id="ksPCsv" title="download visible series as CSV">CSV</button>
          <button id="ksPPng">PNG</button><button id="ksPClose">✕</button></div>
        <div class="ks-pb"><div class="ks-ps" id="ksPS"></div><div class="ks-pc"><canvas id="ksPC"></canvas></div></div>`;
      $('#canvasContainer').appendChild(p);
      // drag by header
      const head = $('.ks-ph', p);
      head.addEventListener('mousedown', e => {
        if (e.target.closest('select,button,input,label')) return;
        const r = p.getBoundingClientRect(), pr = p.parentElement.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
        const mv = ev => { p.style.left = (ev.clientX - pr.left - dx) + 'px'; p.style.top = (ev.clientY - pr.top - dy) + 'px'; p.style.right = 'auto'; };
        const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); };
        document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up); e.preventDefault();
      });
      $('#ksPClose', p).onclick = () => p.classList.remove('active');
      $('#ksPX', p).onchange = () => { KS.plotSel.x = $('#ksPX').value; drawPlot(); };
      $('#ksPLog', p).onchange = drawPlot; $('#ksPNorm', p).onchange = drawPlot;
      $('#ksPCsv', p).onclick = plotCSV;
      $('#ksPPng', p).onclick = () => { const a = document.createElement('a'); a.href = $('#ksPC').toDataURL('image/png'); a.download = 'knode_plot.png'; a.click(); };
      new ResizeObserver(() => drawPlot()).observe($('.ks-pc', p));
      const c = $('#ksPC', p);
      c.addEventListener('mousemove', e => { KS._hover = { x: e.offsetX, y: e.offsetY }; drawPlot(); });
      c.addEventListener('mouseleave', () => { KS._hover = null; drawPlot(); });
    }
    const reg = seriesRegistry();
    if (!reg.length) { status('Nothing to plot yet — run ▶▶ Simulate or ▶ Run first'); return; }
    const keys = new Set(reg.map(s => s.key));
    if (!KS.plotSel || !KS.plotSel.y.some(k => keys.has(k))) {
      const prefer = graph.selectedNodes.map(String);
      let y = reg.filter(s => prefer.some(id => s.key.replace('arr:', '').startsWith(id + '.'))).map(s => s.key);
      if (!y.length) y = reg.filter(s => s.group === 'Time series').slice(0, 4).map(s => s.key);
      if (!y.length) y = reg.slice(0, 3).map(s => s.key);
      KS.plotSel = { x: 'default', y };
    }
    KS.plotSel.y = KS.plotSel.y.filter(k => keys.has(k));
    // series checklist
    let html = '', grp = '';
    reg.forEach((s, i) => {
      if (s.group !== grp) { grp = s.group; html += `<div style="color:#777;margin:4px 0 2px">${esc(grp)}</div>`; }
      const on = KS.plotSel.y.includes(s.key);
      html += `<label title="${esc(s.label)}"><input type="checkbox" data-k="${esc(s.key)}" ${on ? 'checked' : ''}><i style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(s.label)}</label>`;
    });
    $('#ksPS').innerHTML = html;
    $('#ksPS').querySelectorAll('input').forEach(cb => cb.onchange = () => {
      const k = cb.dataset.k;
      KS.plotSel.y = cb.checked ? [...KS.plotSel.y, k] : KS.plotSel.y.filter(x => x !== k);
      drawPlot();
    });
    $('#ksPX').innerHTML = `<option value="default">default (t / index)</option>` +
      reg.map(s => `<option value="${esc(s.key)}" ${KS.plotSel.x === s.key ? 'selected' : ''}>${esc(s.label)}</option>`).join('');
    $('#ksPX').value = KS.plotSel.x;
    p.classList.add('active');
    drawPlot();
  }

  /** Axis tick positions at 'nice' steps (1, 2, 2.5, 5 × 10ⁿ) covering [lo, hi] with about n ticks. */
  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= step0) || 10 * mag;
    const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toPrecision(12));
    return out;
  }

  /**
   * The selected series resolved to {key, label, colour, x, y}: x is time/index by default or another
   * series (phase portraits); 'normalise' rescales each series to [0, 1].
   */
  function currentSeries(reg) {
    reg = reg || seriesRegistry();
    const byKey = Object.fromEntries(reg.map((s, i) => [s.key, Object.assign({ color: PALETTE[i % PALETTE.length] }, s)]));
    const xs = KS.plotSel.x !== 'default' ? byKey[KS.plotSel.x] : null;
    const norm = $('#ksPNorm') && $('#ksPNorm').checked;
    return KS.plotSel.y.map(k => byKey[k]).filter(Boolean).map(s => {
      let x = xs ? xs.y : (s.x || s.y.map((_, i) => i));
      let y = s.y;
      const n = Math.min(x.length, y.length);
      if (norm) { const v = y.filter(a => a !== null); const lo = Math.min(...v), hi = Math.max(...v); y = y.map(a => a === null ? null : (a - lo) / ((hi - lo) || 1)); }
      return { key: s.key, label: s.label, color: s.color, x: x.slice(0, n), y: y.slice(0, n), xlabel: xs ? xs.label : s.xlabel };
    });
  }

  /**
   * Redraw the plot canvas: axes and grid, series (with per-pixel min/max decimation for long traces),
   * kept-run / data overlays, legend and the hover crosshair read-out. 2-D fields render as heat-maps.
   */
  function drawPlot() {
    const c = $('#ksPC'); if (!c || !$('#ksPlot').classList.contains('active')) return;
    const dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
    if (!W || !H) return;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = '#181818'; g.fillRect(0, 0, W, H);
    const reg = seriesRegistry();                          // built once per redraw (0.5: was built twice)
    const fld = reg.find(s => s.field && KS.plotSel.y.includes(s.key));
    if (fld) { drawField(g, W, H, fld); return; }
    const S0 = currentSeries(reg);
    const S = S0.concat(KS.overlaySeries ? KS.overlaySeries(S0, KS.plotSel.x) : []);
    const logy = $('#ksPLog').checked;
    const ty = v => (v === null || v === undefined) ? null : (logy ? (v > 0 ? Math.log10(v) : null) : v);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const s of S) for (let i = 0; i < s.x.length; i++) {
      const xv = s.x[i], yv = ty(s.y[i]);
      if (xv === null || yv === null || !isFinite(xv) || !isFinite(yv)) continue;
      x0 = Math.min(x0, xv); x1 = Math.max(x1, xv); y0 = Math.min(y0, yv); y1 = Math.max(y1, yv);
    }
    if (!isFinite(x0)) { g.fillStyle = '#666'; g.font = '11px sans-serif'; g.fillText('select series on the left', 20, 24); return; }
    if (x1 === x0) { x1 += 1; x0 -= 1; } if (y1 === y0) { y1 += 1; y0 -= 1; }
    const py = (y1 - y0) * 0.05; y0 -= py; y1 += py;
    const L = 52, R = 10, T = 10, B = 26, pw = W - L - R, ph = H - T - B;
    const X = v => L + (v - x0) / (x1 - x0) * pw, Y = v => T + ph - (v - y0) / (y1 - y0) * ph;
    g.font = '9px ui-monospace, Menlo, monospace'; g.strokeStyle = '#2a2a2a'; g.fillStyle = '#888'; g.lineWidth = 1;
    g.textAlign = 'center'; g.textBaseline = 'top';
    for (const v of niceTicks(x0, x1, Math.max(2, Math.floor(pw / 80)))) { g.beginPath(); g.moveTo(X(v), T); g.lineTo(X(v), T + ph); g.stroke(); g.fillText(fmt(v, 3), X(v), T + ph + 4); }
    g.textAlign = 'right'; g.textBaseline = 'middle';
    for (const v of niceTicks(y0, y1, Math.max(2, Math.floor(ph / 40)))) { g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(L + pw, Y(v)); g.stroke(); g.fillText(logy ? '1e' + fmt(v, 2) : fmt(v, 3), L - 4, Y(v)); }
    g.strokeStyle = '#444'; g.strokeRect(L, T, pw, ph);
    g.fillStyle = '#777'; g.textAlign = 'right'; g.textBaseline = 'bottom'; g.fillText(S[0].xlabel || '', L + pw, H - 1);
    g.save(); g.beginPath(); g.rect(L, T, pw, ph); g.clip();
    for (const s of S) {
      g.strokeStyle = s.color; g.fillStyle = s.color; g.lineWidth = s.dash ? 1.1 : 1.3; g.setLineDash(s.dash ? [5, 4] : []); g.globalAlpha = s.dash ? 0.8 : 1;
      g.beginPath(); let pen = false;
      const scatter = s.points || (s.x.length < 40 && KS.sweep && s.label === KS.sweep.label);
      // Long time series (x increasing) are drawn as a per-pixel-column min/max envelope: at most
      // ~4 vertices per pixel instead of every sample. Visually identical, much cheaper for 10⁴–10⁵ points.
      if (!scatter && s.x.length > 4 * pw && isSorted(s.x)) {
        let col = -1, mn = 0, mx = 0, first = 0, last = 0, have = false;
        const flush = () => {
          if (!have) return;
          const px = L + col + 0.5;
          if (!pen) { g.moveTo(px, Y(first)); pen = true; } else g.lineTo(px, Y(first));
          g.lineTo(px, Y(mn)); g.lineTo(px, Y(mx)); g.lineTo(px, Y(last));
        };
        for (let i = 0; i < s.x.length; i++) {
          const yv = ty(s.y[i]);
          if (yv === null || s.x[i] === null || !isFinite(yv)) { flush(); have = false; pen = false; continue; }
          const c = Math.floor(X(s.x[i]) - L);
          if (c !== col) { flush(); col = c; mn = mx = first = last = yv; have = true; }
          else { if (yv < mn) mn = yv; if (yv > mx) mx = yv; last = yv; }
        }
        flush();
        g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
        continue;
      }
      for (let i = 0; i < s.x.length; i++) {
        const yv = ty(s.y[i]);
        if (yv === null || s.x[i] === null || !isFinite(yv)) { pen = false; continue; }
        const px = X(s.x[i]), pyy = Y(yv);
        if (scatter) { g.moveTo(px + 2.5, pyy); g.arc(px, pyy, 2.5, 0, 7); if (s.points) continue; }
        pen ? g.lineTo(px, pyy) : g.moveTo(px, pyy); pen = true;
      }
      s.points ? g.fill() : g.stroke();
      g.setLineDash([]); g.globalAlpha = 1;
    }
    g.restore();
    // legend
    g.textAlign = 'left'; g.textBaseline = 'middle'; g.font = '9px "Segoe UI", sans-serif';
    S.slice(0, 10).forEach((s, i) => {
      g.fillStyle = s.color;
      if (s.points) { g.beginPath(); g.arc(L + 13, T + 9 + i * 12, 2.5, 0, 7); g.fill(); }
      else if (s.dash) { g.fillRect(L + 8, T + 8 + i * 12, 4, 2); g.fillRect(L + 14, T + 8 + i * 12, 4, 2); }
      else g.fillRect(L + 8, T + 8 + i * 12, 10, 2);
      g.fillStyle = '#bbb'; g.fillText(s.label, L + 22, T + 9 + i * 12);
    });
    // crosshair
    const hv = KS._hover;
    if (hv && hv.x > L && hv.x < L + pw) {
      const xv = x0 + (hv.x - L) / pw * (x1 - x0);
      g.strokeStyle = '#555'; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(hv.x, T); g.lineTo(hv.x, T + ph); g.stroke(); g.setLineDash([]);
      const lines = ['x = ' + fmt(xv, 5)];
      for (const s of S) {
        let bi = -1, bd = Infinity;
        for (let i = 0; i < s.x.length; i++) { const d = Math.abs(s.x[i] - xv); if (d < bd) { bd = d; bi = i; } }
        if (bi >= 0) lines.push(s.label + ' = ' + fmt(s.y[bi], 5));
      }
      const bw = Math.max(...lines.map(l => g.measureText(l).width)) + 10, bx = Math.min(hv.x + 8, W - bw - 4);
      g.fillStyle = 'rgba(20,20,20,.92)'; g.fillRect(bx, T + 4, bw, lines.length * 12 + 6);
      g.fillStyle = '#ddd'; lines.forEach((l, i) => g.fillText(l, bx + 5, T + 11 + i * 12));
    }
  }

  // true when an x-array is non-decreasing (time axes) — only then may samples be binned by pixel column
  const sortedCache = new WeakMap();
  function isSorted(a) {
    const hit = sortedCache.get(a);
    if (hit && hit.len === a.length) return hit.ok;
    let ok = true, prev = -Infinity;
    for (const v of a) { if (v === null) continue; if (v < prev) { ok = false; break; } prev = v; }
    sortedCache.set(a, { len: a.length, ok });
    return ok;
  }

  /** Render a 2-D numeric array as a heat-map with a colour bar (nearest-neighbour scaling). */
  /**
   * Rasterise a 2-D field into an offscreen canvas (one pixel per cell) with its value range.
   * Cached per array (0.7): hovering the plot redraws it on every mouse move, and re-colouring a
   * 96×96 field each time cost ~9 000 colour conversions per event.
   */
  const fieldCanvasCache = new WeakMap();
  function fieldCanvas(F) {
    const hit = fieldCanvasCache.get(F);
    if (hit) return hit;
    const ny = F.length, nx = F[0].length;
    let lo = Infinity, hi = -Infinity;
    for (const row of F) for (const v of row) if (v !== null && isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (hi === lo) hi = lo + 1;
    const img = new ImageData(nx, ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const c = heatColor((F[j][i] - lo) / (hi - lo)).match(/\d+/g), k = 4 * (j * nx + i);
      img.data[k] = +c[0]; img.data[k + 1] = +c[1]; img.data[k + 2] = +c[2]; img.data[k + 3] = 255;
    }
    const tmp = document.createElement('canvas'); tmp.width = nx; tmp.height = ny; tmp.getContext('2d').putImageData(img, 0, 0);
    const out = { canvas: tmp, lo, hi, nx, ny };
    fieldCanvasCache.set(F, out);
    return out;
  }

  /** Draw a 2-D field as a heat-map (cached raster, see fieldCanvas) with a colour bar and label. */
  function drawField(g, W, H, s) {
    const fc = fieldCanvas(s.field), nx = fc.nx, ny = fc.ny, lo = fc.lo, hi = fc.hi;
    const side = Math.min(W - 70, H - 20), ox = 10 + (W - 70 - side) / 2, oy = 10;
    g.imageSmoothingEnabled = false; g.drawImage(fc.canvas, ox, oy, side, side);   // GPU-scaled blit of the cached raster
    const bx = ox + side + 12;
    for (let k = 0; k < side; k++) { g.fillStyle = heatColor(1 - k / side); g.fillRect(bx, oy + k, 10, 1); }
    g.fillStyle = '#aaa'; g.font = '9px ui-monospace, monospace'; g.textAlign = 'left'; g.textBaseline = 'top';
    g.fillText(fmt(hi, 3), bx + 14, oy); g.textBaseline = 'bottom'; g.fillText(fmt(lo, 3), bx + 14, oy + side);
    g.textBaseline = 'top'; g.fillText(s.label + '  ' + nx + '×' + ny, ox, oy + side + 2 > H - 12 ? H - 12 : oy + side + 2);
  }

  /** Download the visible series as CSV (one x column followed by one column per series). */
  function plotCSV() {
    const S = currentSeries(); if (!S.length) return;
    const n = Math.max(...S.map(s => s.x.length));
    const head = [S[0].xlabel || 'x', ...S.map(s => s.label)];
    const rows = [head.map(h => JSON.stringify(h)).join(',')];
    for (let i = 0; i < n; i++) rows.push([S[0].x[i], ...S.map(s => s.y[i])].map(v => v === null || v === undefined ? '' : v).join(','));
    download(new Blob([rows.join('\n')], { type: 'text/csv' }), 'knode_series.csv');
  }
  /** Save a Blob as a file via a temporary object URL. */
  function download(blob, name) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }

  // ------------------------------------------------------------------ analysis
  async function openAnalysis() {
    const body = modal('ksAnalysis', 'Graph analysis', 760);
    body.innerHTML = 'Analysing…';
    const weights = {};
    const prof = (KS.lastRun && KS.lastRun.profile) || {};
    for (const id in prof) weights[id] = Math.max(1e-6, prof[id].mean_ms);
    let a;
    try { a = await api('/graph/analyze', Object.assign(serialize(), { weights: Object.keys(weights).length ? weights : null })); }
    catch (e) { body.innerHTML = `<span class="ks-err">${esc(e.message)}</span>`; return; }
    if (a.success === false) { body.innerHTML = `<span class="ks-err">${esc(a.error)}</span>`; return; }
    KS.analysis = a;
    const link = id => `<span class="ks-link" data-sel="${id}">${esc(nodeName(id))}</span>`;
    const top = Object.entries(a.nodes).sort((p, q) => q[1].pagerank - p[1].pagerank);
    body.innerHTML = `
      <div class="ks-grid">
        <div class="ks-kpi"><b>${a.n_nodes}</b><span>nodes</span></div><div class="ks-kpi"><b>${a.n_edges}</b><span>data edges (+${a.n_relations} relations)</span></div>
        <div class="ks-kpi"><b>${fmt(a.density, 3)}</b><span>density</span></div><div class="ks-kpi"><b>${a.depth}</b><span>DAG depth (levels)</span></div>
        <div class="ks-kpi"><b class="${a.is_dag ? 'ks-ok' : 'ks-warn'}">${a.is_dag ? 'acyclic' : a.cycles.length + ' loop(s)'}</b><span>feedback structure</span></div>
        <div class="ks-kpi"><b>${a.weak_components}</b><span>connected components</span></div>
        <div class="ks-kpi"><b>${a.sources.length}/${a.sinks.length}</b><span>sources / sinks</span></div>
        <div class="ks-kpi"><b>${a.lint.filter(i => i.level === 'error').length}/${a.lint.filter(i => i.level === 'warning').length}</b><span>lint errors / warnings</span></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">Canvas heat-map:
        <select id="ksHeat"><option value="">off</option><option value="pagerank">PageRank (influence)</option><option value="betweenness">betweenness (bottlenecks)</option>
        <option value="level">topological level</option><option value="in">in-degree</option><option value="out">out-degree</option>${Object.keys(weights).length ? '<option value="time">execution time</option>' : ''}</select>
        <button class="ks-btn" id="ksSelCrit">select critical path</button></div>
      ${a.cycles.length ? `<div style="margin-bottom:8px"><b>Feedback loops</b> (strongly connected components)<br>${a.cycles.map(c => c.map(link).join(' → ') + ' ↺').join('<br>')}
        <div style="color:#888;font-size:10px">Back edges (carry the previous step in simulation): ${a.feedback_edges.map(e => esc(nodeName(e.from) + '.' + e.fromPort + ' → ' + nodeName(e.to) + '.' + e.toPort)).join(', ')}</div></div>` : ''}
      <div style="margin-bottom:8px"><b>Critical path</b> ${Object.keys(weights).length ? '(weighted by measured ms/call)' : '(by node count)'}: ${a.critical_path.map(link).join(' → ') || '—'}</div>
      ${a.lint.length ? `<div style="margin-bottom:8px"><b>Lint</b><br>${a.lint.map(i => `<span class="${i.level === 'error' ? 'ks-err' : 'ks-warn'}">${i.level}</span> ${link(i.node)}: ${esc(i.msg)}`).join('<br>')}</div>` : ''}
      <table class="ks-t"><tr><th>node</th><th>in</th><th>out</th><th>level</th><th>betweenness</th><th>PageRank</th><th>loop</th></tr>
      ${top.map(([id, s]) => `<tr><td>${link(id)}</td><td>${s.in}</td><td>${s.out}</td><td>${s.level}</td><td>${fmt(s.betweenness, 3)}</td>
        <td><span class="ks-bar" style="width:${Math.round(s.pagerank * 120)}px;background:#667eea"></span> ${fmt(s.pagerank, 3)}</td><td>${s.in_cycle ? '↺' : ''}</td></tr>`).join('')}</table>`;
    body.onclick = e => { const id = e.target.dataset && e.target.dataset.sel; if (id) focusNodes([id]); };
    $('#ksHeat', body).value = KS.heat ? KS.heat.metric : '';
    $('#ksHeat', body).onchange = e => setHeat(e.target.value, weights);
    $('#ksSelCrit', body).onclick = () => focusNodes(a.critical_path);
  }
  /** Colour nodes on the canvas by an analysis metric (PageRank, betweenness, level, degree, time), normalised to [0, 1]. */
  function setHeat(metric, weights) {
    if (!metric || !KS.analysis) { KS.heat = null; renderer.render(); return; }
    const raw = {};
    for (const [id, s] of Object.entries(KS.analysis.nodes)) raw[id] = metric === 'time' ? (weights[id] || 0) : s[metric];
    const vals = Object.values(raw), lo = Math.min(...vals), hi = Math.max(...vals);
    const values = {}; for (const id in raw) values[id] = hi > lo ? (raw[id] - lo) / (hi - lo) : 0.5;
    KS.heat = { metric, raw, values };
    renderer.render();
  }
  /** Select the given nodes and frame them in the view. */
  function focusNodes(ids) {
    ids = ids.map(Number).filter(id => graph.nodes[id]);
    if (!ids.length) return;
    graph.selectedNodes = ids; graph.selectedWires = [];
    frame(ids);
    updatePropertiesPanel(ids.length === 1 ? graph.nodes[ids[0]] : null);
  }

  // ------------------------------------------------------------------ sweep / Monte Carlo
  function nodeOptions(filter) {
    return Object.values(graph.nodes).filter(filter || (() => true)).map(n => `<option value="${n.id}">${esc(n.name)} #${n.id}</option>`).join('');
  }
  /** Filter: nodes that have at least one numeric parameter (candidates for sweeps and Monte Carlo). */
  function paramNodes() { return n => n.properties && n.properties.params && Object.values(n.properties.params).some(v => typeof v === 'number'); }

  /**
   * Parameter-study dialog: 1-D sweep (linear/log) or Monte Carlo with Latin-hypercube sampling and
   * Spearman sensitivity; results go to the plot panel / a histogram and tornado chart.
   */
  function openSweep() {
    const body = modal('ksSweep', 'Parameter study', 700);
    if (KS.inGroup) { body.innerHTML = 'Parameter studies run on the top-level model — exit the group first (breadcrumb bar).'; return; }
    if (!Object.values(graph.nodes).some(paramNodes())) { body.innerHTML = 'No numeric parameters in this graph. Add library nodes (Tab) or give a node a parameter in the Properties panel.'; return; }
    body.innerHTML = `
      <div class="ks-chips"><span class="ks-chip on" data-tab="sw" style="background:#ccc">1-D sweep</span><span class="ks-chip" data-tab="mc">Monte Carlo + sensitivity</span></div>
      <div id="ksTabSw">
        <div class="ks-prow"><span>parameter</span><select id="swNode">${nodeOptions(paramNodes())}</select><select id="swParam"></select></div>
        <div class="ks-prow"><span>values</span><input id="swFrom" type="number" step="any" placeholder="from"><input id="swTo" type="number" step="any" placeholder="to"><input id="swN" type="number" value="21" title="number of points"></div>
        <div class="ks-prow"><span>scale</span><select id="swScale"><option>linear</option><option>log</option></select></div>
      </div>
      <div id="ksTabMc" style="display:none">
        <div class="ks-desc" style="color:#999;margin-bottom:6px">Latin-hypercube sampling of uncertain inputs; Spearman ρ ranks which inputs drive the output (global, monotone sensitivity).</div>
        <table class="ks-t" id="mcTable"><tr><th>node</th><th>param</th><th>distribution</th><th>a (low / μ)</th><th>b (high / σ)</th><th></th></tr></table>
        <button class="ks-btn" id="mcAdd" style="margin:4px 0">+ factor</button>
        <div class="ks-prow"><span>samples</span><input id="mcN" type="number" value="200"><span style="width:auto">seed</span><input id="mcSeed" type="number" value="0"></div>
      </div>
      <hr style="border-color:#333;margin:8px 0">
      <div class="ks-prow"><span>output</span><select id="swTN">${nodeOptions()}</select><select id="swTP"></select></div>
      <div class="ks-prow"><span>mode</span><select id="swMode"><option value="run">single run (static)</option><option value="simulate">simulate (uses toolbar steps & dt)</option></select>
        <select id="swRed" title="how to reduce a time series"><option value="last">final value</option><option value="max">max</option><option value="min">min</option><option value="mean">mean</option><option value="integral">integral ∫dt</option><option value="argmax_t">time of max</option></select></div>
      <div style="display:flex;gap:8px;margin-top:8px"><button class="ks-btn pri" id="swGo">Run study</button><span id="swMsg" style="color:#888;align-self:center"></span></div>
      <div id="swOut" style="margin-top:10px"></div>`;
    let tab = 'sw';
    body.querySelector('.ks-chips').onclick = e => {
      if (!e.target.dataset.tab) return; tab = e.target.dataset.tab;
      body.querySelectorAll('.ks-chip').forEach(c => { const on = c.dataset.tab === tab; c.classList.toggle('on', on); c.style.background = on ? '#ccc' : ''; });
      $('#ksTabSw', body).style.display = tab === 'sw' ? '' : 'none'; $('#ksTabMc', body).style.display = tab === 'mc' ? '' : 'none';
    };
    const numParams = id => Object.entries(((graph.nodes[id] || {}).properties || {}).params || {}).filter(([, v]) => typeof v === 'number');
    const fillParams = (sel, id) => { sel.innerHTML = numParams(id).map(([k]) => `<option>${esc(k)}</option>`).join(''); };
    const swNode = $('#swNode', body), swParam = $('#swParam', body);
    const setRange = () => { const v = (graph.nodes[swNode.value].properties.params || {})[swParam.value]; if (typeof v === 'number') { $('#swFrom', body).value = v === 0 ? 0 : +(v * 0.5).toPrecision(4); $('#swTo', body).value = v === 0 ? 1 : +(v * 1.5).toPrecision(4); } };
    swNode.onchange = () => { fillParams(swParam, swNode.value); setRange(); };
    swParam.onchange = setRange;
    fillParams(swParam, swNode.value); setRange();
    const tn = $('#swTN', body), tp = $('#swTP', body);
    const fillPorts = () => { tp.innerHTML = (graph.nodes[tn.value].outputs || []).map(p => `<option>${esc(p.name)}</option>`).join(''); };
    tn.onchange = fillPorts;
    const sinks = Object.values(graph.nodes).filter(n => !Object.values(graph.wires).some(w => w.from === n.id));
    const allN = Object.values(graph.nodes);
    tn.value = (sinks.length ? sinks[sinks.length - 1] : allN[allN.length - 1]).id;
    fillPorts();
    if (Object.values(graph.nodes).some(n => KS.byId[(n.properties || {}).template] && KS.byId[n.properties.template].stateful)) $('#swMode', body).value = 'simulate';
    const addFactor = () => {
      const row = document.createElement('tr');
      row.innerHTML = `<td><select class="mcN">${nodeOptions(paramNodes())}</select></td><td><select class="mcP"></select></td>
        <td><select class="mcD"><option>uniform</option><option>normal</option><option>lognormal</option><option>triangular</option></select></td>
        <td><input class="mcA ks-input" type="number" step="any" style="width:80px"></td><td><input class="mcB ks-input" type="number" step="any" style="width:80px"></td><td><button class="ks-btn mcX">×</button></td>`;
      $('#mcTable', body).appendChild(row);
      const n = $('.mcN', row), p = $('.mcP', row);
      const upd = () => { const v = graph.nodes[n.value].properties.params[p.value]; $('.mcA', row).value = +(v * 0.8).toPrecision(4); $('.mcB', row).value = +(v * 1.2).toPrecision(4); };
      n.onchange = () => { fillParams(p, n.value); upd(); }; p.onchange = upd;
      $('.mcD', row).onchange = () => { const v = graph.nodes[n.value].properties.params[p.value]; if ($('.mcD', row).value === 'normal') { $('.mcA', row).value = v; $('.mcB', row).value = +(Math.abs(v) * 0.1 || 0.1).toPrecision(3); } else upd(); };
      $('.mcX', row).onclick = () => row.remove();
      fillParams(p, n.value); upd();
    };
    $('#mcAdd', body).onclick = addFactor; addFactor();

    $('#swGo', body).onclick = async () => {
      const base = Object.assign(serialize(), {
        target_node: tn.value, target_port: tp.value, mode: $('#swMode', body).value, reduce: $('#swRed', body).value,
        steps: parseInt($('#ksSteps').value) || 500, dt: parseFloat($('#ksDt').value) || 0.01,
      });
      const msg = $('#swMsg', body), out = $('#swOut', body);
      msg.textContent = 'running…'; out.innerHTML = '';
      try {
        if (tab === 'sw') {
          const a = parseFloat($('#swFrom', body).value), b = parseFloat($('#swTo', body).value), n = Math.max(2, parseInt($('#swN', body).value) || 11);
          const log = $('#swScale', body).value === 'log';
          if (log && (a <= 0 || b <= 0)) throw new Error('log scale needs positive bounds');
          const values = Array.from({ length: n }, (_, i) => log ? Math.exp(Math.log(a) + (Math.log(b) - Math.log(a)) * i / (n - 1)) : a + (b - a) * i / (n - 1));
          const r = await api('/graph/sweep', Object.assign(base, { node: swNode.value, param: swParam.value, values }));
          if (!r.results) throw new Error(r.error || 'sweep failed');
          const pname = nodeName(swNode.value) + '.' + swParam.value, oname = nodeName(tn.value) + '.' + tp.value + (base.mode === 'simulate' ? ' (' + base.reduce + ')' : '');
          KS.sweep = { key: 'sweep', label: 'sweep: ' + oname, x: r.values, y: r.results.map(v => typeof v === 'number' ? v : null), xlabel: pname, group: 'Parameter sweep' };
          KS.plotSel = { x: 'default', y: ['sweep'] };
          const errs = r.errors.filter(Boolean);
          out.innerHTML = `<table class="ks-t"><tr><th>${esc(pname)}</th><th>${esc(oname)}</th></tr>${r.values.map((v, i) => `<tr><td>${fmt(v, 5)}</td><td>${r.errors[i] ? `<span class="ks-err">${esc(r.errors[i])}</span>` : esc(fmt(r.results[i], 6))}</td></tr>`).join('')}</table>`;
          msg.textContent = errs.length ? `${errs.length} point(s) failed` : 'done — plotted';
          openPlot();
        } else {
          const factors = [...body.querySelectorAll('#mcTable tr')].slice(1).map(row => ({
            node: $('.mcN', row).value, param: $('.mcP', row).value, dist: $('.mcD', row).value,
            a: parseFloat($('.mcA', row).value), b: parseFloat($('.mcB', row).value) }));
          if (!factors.length) throw new Error('add at least one factor');
          const r = await api('/graph/montecarlo', Object.assign(base, { factors, n: parseInt($('#mcN', body).value) || 100, seed: parseInt($('#mcSeed', body).value) || 0 }));
          if (!r.success) throw new Error(r.error || 'Monte Carlo failed');
          const s = r.stats;
          const nb = 24, lo = s.min, hi = s.max, w = (hi - lo) / nb || 1, counts = new Array(nb).fill(0);
          r.y.forEach(v => counts[Math.min(nb - 1, Math.floor((v - lo) / w))]++);
          const cmax = Math.max(...counts);
          out.innerHTML = `
            <div class="ks-grid"><div class="ks-kpi"><b>${fmt(s.mean, 5)}</b><span>mean ± ${fmt(s.std, 3)} (sd)</span></div>
              <div class="ks-kpi"><b>${fmt(s.p50, 5)}</b><span>median</span></div>
              <div class="ks-kpi"><b>${fmt(s.p05, 4)} … ${fmt(s.p95, 4)}</b><span>90% interval (p5–p95)</span></div>
              <div class="ks-kpi"><b>${s.n}</b><span>samples${s.failed ? ` (${s.failed} failed)` : ''}</span></div></div>
            <div style="display:flex;align-items:flex-end;gap:1px;height:80px;border-bottom:1px solid #444;margin-bottom:2px">${counts.map(c => `<div style="flex:1;background:#667eea;height:${(c / cmax * 100).toFixed(1)}%" title="${c}"></div>`).join('')}</div>
            <div style="display:flex;justify-content:space-between;color:#777;font-size:9px"><span>${fmt(lo, 4)}</span><span>${esc(nodeName(tn.value) + '.' + tp.value)}</span><span>${fmt(hi, 4)}</span></div>
            <div style="margin-top:10px"><b>Sensitivity</b> (rank correlation with output)</div>
            <table class="ks-t">${r.sensitivity.sort((p, q) => Math.abs(q.spearman) - Math.abs(p.spearman)).map(f => {
              const [id, pn] = [f.factor.slice(0, f.factor.indexOf('.')), f.factor.slice(f.factor.indexOf('.') + 1)];
              const v = f.spearman || 0;
              return `<tr><td>${esc(nodeName(id) + '.' + pn)}</td><td style="width:260px"><div style="position:relative;height:10px;background:#1a1a1a">
                <div style="position:absolute;left:${v < 0 ? 50 + v * 50 : 50}%;width:${Math.abs(v) * 50}%;height:10px;background:${v < 0 ? '#ff6b6b' : '#1dd1a1'}"></div>
                <div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:#555"></div></div></td><td>ρ = ${fmt(v, 3)}</td><td style="color:#777">r = ${fmt(f.pearson, 3)}</td></tr>`; }).join('')}</table>`;
          msg.textContent = r.method;
        }
      } catch (e) { msg.innerHTML = `<span class="ks-err">${esc(e.message)}</span>`; }
    };
  }

  // ------------------------------------------------------------------ examples
  function clearGraph() {
    restoreSnapshot({ nodes: {}, wires: {}, nextId: 1 });
    KS.results = {}; KS.lastRun = null; KS.lastSim = null; KS.sweep = null; KS.heat = null; KS.plotSel = null;
    const pl = $('#ksPlot'); if (pl) pl.classList.remove('active');
  }
  /** Replace the graph with an example (confirming first), set its steps/dt/plot, then run it. */
  function loadExample(eid) {
    const ex = KS.examples.find(e => e.id === eid);
    if (!ex) return;
    if (Object.keys(graph.nodes).length && !confirm(`Replace the current graph with “${ex.title}”? (Undo with Ctrl+Z)`)) return;
    saveState();
    if (window.KnodeUI) KnodeUI.resetContext();
    clearGraph();
    const ids = ex.nodes.map(n => n.group ? KnodeUI.createGroupFromExample(ex, n).id : createFromTemplate(KS.byId[n.tpl], n.x, n.y, n.params, n.name).id);
    for (const [a, ap, b, bp] of ex.wires) {
      const w = graph.connect(ids[a], ids[b], ap, bp);
      if (!w) addDebugEntry(`Example wire ${ap}→${bp} failed`, 'warning');
    }
    if (ex.steps) $('#ksSteps').value = ex.steps;
    if (ex.dt) $('#ksDt').value = ex.dt;
    const p = ex.plot;
    KS.plotSel = null;
    if (p && p.y) KS.plotSel = { x: Array.isArray(p.x) ? ids[p.x[0]] + '.' + p.x[1] : 'default', y: p.y.map(([i, port]) => ids[i] + '.' + port) };
    if (p && p.fields) KS.plotSel = { x: 'default', y: ['fld:' + ids[p.fields[0]] + '.' + p.fields[1]] };
    if (p && p.arrays) { const [first, ...rest] = p.arrays.map(([i, port]) => 'arr:' + ids[i] + '.' + port.replace('Y.', 'Y.')); KS.plotSel = { x: rest.length > 1 ? first : 'default', y: rest.length ? rest : [first] }; }
    graph.selectedNodes = []; graph.selectedWires = [];
    if (KS.afterExample) KS.afterExample(ex, ids);
    frame();
    updateLiveState(); updateStatus(); updatePropertiesPanel(null);
    saveState();
    status(`<b>${esc(ex.title)}</b> — ${esc(ex.description)} &nbsp;→ press <b>${ex.mode === 'simulate' ? '▶▶ Simulate' : '▶ Run'}</b>`);
    const plotAfter = KS.plotSel;
    (ex.mode === 'simulate' ? runSimulation() : runGraph(null)).then(() => { if (plotAfter && ex.plot) { KS.plotSel = plotAfter; openPlot(); } if ($('#ksPlot') && $('#ksPlot').classList.contains('active')) frame(); });
  }

  // ------------------------------------------------------------------ view helpers
  function frame(ids) {
    const nodes = (ids || Object.keys(graph.nodes)).map(id => graph.nodes[id]).filter(Boolean);
    if (!nodes.length) return;
    const x0 = Math.min(...nodes.map(n => n.x)) - 40, y0 = Math.min(...nodes.map(n => n.y)) - 40;
    const x1 = Math.max(...nodes.map(n => n.x + n.width)) + 40, y1 = Math.max(...nodes.map(n => n.y + n.height)) + 70;
    const r = renderer.canvas.getBoundingClientRect(), v = renderer.viewport;
    const plot = $('#ksPlot'), reserve = plot && plot.classList.contains('active') ? plot.offsetWidth + 24 : 0;
    const W = Math.max(200, r.width - reserve);
    v.zoom = Math.max(0.25, Math.min(1.6, Math.min(W / (x1 - x0), r.height / (y1 - y0))));
    v.panX = (W - (x1 - x0) * v.zoom) / 2 - x0 * v.zoom;
    v.panY = (r.height - (y1 - y0) * v.zoom) / 2 - y0 * v.zoom;
    $('#zoomLabel').textContent = Math.round(v.zoom * 100) + '%';
    renderer.render();
  }
  /** The node under a world position, or null. */
  function nodeAt(world) {
    for (const id in graph.nodes) { const n = graph.nodes[id]; if (world.x >= n.x && world.x <= n.x + n.width && world.y >= n.y && world.y <= n.y + n.height) return n; }
    return null;
  }

  // ------------------------------------------------------------------ backend, autosave, HDF5
  function setHealth(h) {
    KS.health = h;
    const d = $('#ksDot'); if (!d) return;
    d.style.background = h ? '#2ecc71' : '#e74c3c';
    d.title = h ? `backend ${h.version} · Python ${h.python} · numpy ${h.numpy ? 'yes' : 'no'} · h5py ${h.h5py ? 'yes' : 'no'}` : 'backend offline — run: python server.py';
    const opt = document.querySelector('#exportFormat option[value="hdf5"]');
    if (opt) opt.textContent = h && h.h5py ? 'HDF5 (real .h5, includes traces)' : 'HDF5 (fallback: base64 JSON — install h5py)';
  }
  /** Fetch backend health, the node library and examples; update the status dot and example menu. */
  async function loadLibrary() {
    try {
      setHealth(await api('/api/health'));
      const lib = await api('/library');
      KS.library = lib; KS.byId = Object.fromEntries(lib.templates.map(t => [t.id, t]));
      KS.examples = (await api('/examples')).examples || [];
      const sel = $('#ksEx');
      const doms = [...new Set(KS.examples.map(e => e.domain))];
      sel.innerHTML = `<option value="">Examples…</option>` + doms.map(d => `<optgroup label="${esc(d)}">${KS.examples.filter(e => e.domain === d).map(e => `<option value="${e.id}">${esc(e.title)}</option>`).join('')}</optgroup>`).join('') + autosaveOption();
      if (graph && graph.selectedNodes.length === 1) updatePropertiesPanel(graph.nodes[graph.selectedNodes[0]]);
    } catch (e) { setHealth(null); addDebugEntry(e.message, 'warning'); }
  }
  /** Menu entry for restoring the last autosaved session, if one exists. */
  function autosaveOption() {
    try { const a = JSON.parse(localStorage.getItem('knode.autosave') || 'null'); if (a && a.graph && Object.keys(a.graph.nodes || {}).length) return `<optgroup label="Session"><option value="__autosave">↺ Restore autosave (${new Date(a.at).toLocaleString()})</option></optgroup>`; }
    catch (e) { /* storage unavailable */ }
    return '';
  }
  let saveTimer = null;
  const origSave = window.saveState;
  window.saveState = function () {
    origSave.apply(this, arguments);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { try { if (graph && Object.keys(graph.nodes).length) localStorage.setItem('knode.autosave', JSON.stringify({ at: Date.now(), graph: graph.toJSON() })); } catch (e) { /* quota */ } }, 1000);
  };
  const origExport = window.exportState, origImport = window.importState;
  window.exportState = async function () {
    if ($('#exportFormat').value === 'hdf5' && KS.health && KS.health.h5py) {
      const res = await fetch(BACKEND_URL + '/export/hdf5', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ graph: graph.toJSON(), traces: KS.lastSim ? KS.lastSim.traces : null, outputs: KS.lastRun ? KS.lastRun.outputs : null }) });
      if (res.ok) { download(await res.blob(), 'knode_graph.h5'); status('Exported HDF5 (graph + traces)'); return; }
    }
    return origExport.apply(this, arguments);
  };
  window.importState = async function () {
    const f = $('#importFile').files[0];
    if ($('#importFormat').value === 'hdf5' && f && KS.health && KS.health.h5py) {
      const res = await fetch(BACKEND_URL + '/import/hdf5', { method: 'POST', body: await f.arrayBuffer() });
      const d = await res.json().catch(() => ({}));
      if (d.success) {
        graph.fromJSON(d.graph);
        if (d.traces && Object.keys(d.traces).length) { KS.lastSim = { traces: d.traces, outputs: {} }; }
        renderer.render(); updateStatus(); closeModal('importModal'); status('Imported HDF5'); return;
      }
    }
    return origImport.apply(this, arguments);
  };

  Object.assign(KS, { api, serialize, serializeNode, derivePorts, syncPorts, createFromTemplate, addTemplateAt, runGraph,
    runSimulation, openPlot, openAnalysis, openSweep, openPalette, frame, loadExample, loadLibrary, status, worldAtScreen,
    viewCenter, nodeAt, esc, fmt, modal, download, clearGraph, heatColor, scheduleAutoRun, applyResults, drawPlot, logReport,
    seriesRegistry });

  // ------------------------------------------------------------------ toolbar & input
  function buildToolbar() {
    const bar = $('.header-actions'), runBtn = $('.header-actions .run-btn');
    const frag = document.createElement('span');
    frag.style.cssText = 'display:contents';
    frag.innerHTML = `
      <span class="ks-sep"></span>
      <button class="ks-accent" id="ksLibBtn" title="Node library (Tab or double-click the canvas)">⌕ Library</button>
      <select class="ks-sel" id="ksEx" title="Load an example model"><option>Examples…</option></select>
      <span class="ks-sep"></span>
      <span class="ks-lbl">steps</span><input class="ks-num" id="ksSteps" type="number" value="1000" min="1">
      <span class="ks-lbl">dt</span><input class="ks-num" id="ksDt" type="number" value="0.01" step="any">
      <button class="ks-accent" id="ksSimBtn" title="Fixed-step simulation (Ctrl+Shift+Enter)">▶▶ Simulate</button>
      <button id="ksPlotBtn" title="Plot panel (P)">📈 Plot</button>
      <button id="ksAnaBtn" title="Graph analysis: loops, critical path, centrality, lint">⚙ Analyze</button>
      <button id="ksSwBtn" title="Parameter sweep / Monte Carlo">∿ Study</button>
      <button id="ksFitBtn" title="Frame all nodes (F)">⤢</button>
      <span class="ks-sep"></span>`;
    bar.insertBefore(frag, runBtn);
    runBtn.title = 'Single pass (Ctrl+Enter)';
    const dot = document.createElement('span'); dot.className = 'ks-dot'; dot.id = 'ksDot';
    bar.appendChild(dot);
    $('#ksLibBtn').onclick = () => openPalette(null);
    $('#ksSimBtn').onclick = runSimulation;
    $('#ksPlotBtn').onclick = () => { const p = $('#ksPlot'); if (p && p.classList.contains('active')) p.classList.remove('active'); else openPlot(); };
    $('#ksAnaBtn').onclick = openAnalysis;
    $('#ksSwBtn').onclick = openSweep;
    $('#ksFitBtn').onclick = () => frame();
    $('#ksEx').onchange = e => {
      const v = e.target.value; e.target.value = '';
      if (v === '__autosave') {
        try { const a = JSON.parse(localStorage.getItem('knode.autosave')); graph.fromJSON(a.graph); KS.results = {}; frame(); status('Restored autosaved session'); } catch (err) { status('Could not restore: ' + esc(err.message)); }
      } else if (v) loadExample(v);
    };
  }

  /** True while the user is typing in a form field (single-key shortcuts must not fire). */
  function typing() {
    const a = document.activeElement;
    return a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable);
  }
  /** True while any dialog is open. */
  function anyModalOpen() { return !!document.querySelector('.ks-modal.active, .modal-overlay.active, .code-editor-modal.active'); }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { document.querySelectorAll('.ks-modal.active').forEach(m => m.classList.remove('active')); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); if (e.shiftKey) runSimulation(); else runGraph(null); return; }
    if (typing() || anyModalOpen() || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Tab') { e.preventDefault(); openPalette(worldAtScreen(KS.mouse.x, KS.mouse.y)); }
    else if (e.key === 'f' || e.key === 'F') frame(graph.selectedNodes.length ? graph.selectedNodes : null);
    else if (e.key === 'p' || e.key === 'P') $('#ksPlotBtn').click();
  });

  document.addEventListener('DOMContentLoaded', () => {
    buildToolbar();
    const cv = renderer.canvas;
    cv.addEventListener('mousemove', e => { KS.mouse = { x: e.clientX, y: e.clientY }; });
    cv.addEventListener('dblclick', e => {
      const w = worldAtScreen(e.clientX, e.clientY), n = nodeAt(w);
      if (n) (n.properties && n.properties.subgraph ? KnodeUI.enterGroup(n.id) : openCodeEditor(n.id)); else openPalette(w);
    });
    // context menu: add library entry
    const sub = document.querySelector('#contextMenu .submenu');
    if (sub) {
      const item = document.createElement('div');
      item.className = 'menu-item'; item.textContent = 'From Library…  (Tab)';
      item.onclick = () => { $('#contextMenu').classList.remove('active'); const p = renderer.lastContextMenuPos; openPalette(worldAtScreen(p.x, p.y)); };
      sub.insertBefore(item, sub.firstChild);
    }
    const info = document.querySelector('.info-panel');
    if (info) info.textContent = 'Tab / double-click: node library · Ctrl+Enter: run · Ctrl+Shift+Enter: simulate · F: frame · P: plot · double-click node: code';
    loadLibrary().then(() => status(KS.health ? `Ready — backend ${KS.health.version}. Press <b>Tab</b> for the library of ${KS.library.templates.length} models or pick an <b>Example</b>.` : '<span class="ks-err">Backend offline — run <code>python server.py</code> and open http://127.0.0.1:5000</span>'));
  });
})();

/* knode_menu.js — context-sensitive right-click menus (knode 0.6)
 *
 * Right-click decides what is under the mouse — port › node › wire › frame › canvas — and opens a
 * menu for exactly that thing. Menus support nested submenus, check marks, shortcuts, colour
 * swatches, disabled items and keyboard navigation (↑ ↓ → ← Enter Esc).
 *
 *   canvas : add node (search, recent, every category, basic classes), note / frame / globals /
 *            send-receive, paste, select all, frame all, run / simulate / live, wire style,
 *            backend, export image, undo / redo
 *   node   : run to here, plot, pin outputs, edit code / open group, rename, colour, duplicate,
 *            flags (bypass / freeze / cache / break-if), connections, select up/downstream,
 *            group / frame selection, node type (save / edit / reset), help
 *   port   : value, disconnect, feed a Constant, add node here, plot / pin output, enable/disable
 *   wire   : value, insert node / reroute, enable/disable, per-wire style, select ends, delete
 *   frame  : rename, colour, select contents, delete (with or without contents)
 */
(function () {
  'use strict';
  const KS = window.KnodeSci, UI = window.KnodeUI;
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => escapeHtml(s === undefined || s === null ? '' : String(s));
  const MN = window.KnodeMenu = {};
  const COLORS = ['#7c8cff', '#4ecdc4', '#1dd1a1', '#feca57', '#ff9f43', '#ff6b6b', '#ff9ff3', '#a29bfe', '#54a0ff', '#c8d6e5'];

  const css = `
  .kx-menu{position:fixed;z-index:4000;min-width:210px;max-width:320px;background:#1d1e24;border:1px solid #373a44;border-radius:8px;padding:4px;
    box-shadow:0 12px 36px #000b;font:12px Inter,"Segoe UI",system-ui,sans-serif;color:#c9ccd6;max-height:80vh;overflow:auto}
  .kx-menu.sub{max-height:70vh}
  .kx-it{display:flex;align-items:center;gap:8px;padding:5px 10px;border-radius:5px;cursor:pointer;white-space:nowrap;position:relative}
  .kx-it:hover,.kx-it.hot{background:#2a2c38}
  .kx-it .ic{width:14px;text-align:center;color:#8a93a8;flex-shrink:0}
  .kx-it .lb{flex:1;overflow:hidden;text-overflow:ellipsis}
  .kx-it kbd{color:#6c7488;font:10px ui-monospace,monospace;background:none;border:none;padding:0}
  .kx-it .ar{color:#6c7488}
  .kx-it.dis{opacity:.4;pointer-events:none}
  .kx-it.danger{color:#ff8a80}
  .kx-it.chk .ic{color:#7c8cff}
  .kx-sep{height:1px;background:#2e3039;margin:4px 6px}
  .kx-hd{padding:6px 10px 4px;font-size:10px;color:#8a93a8;text-transform:uppercase;letter-spacing:.06em;display:flex;gap:6px;align-items:center}
  .kx-hd i{width:9px;height:9px;border-radius:2px;display:inline-block}
  .kx-info{padding:3px 10px 5px;font:10.5px ui-monospace,Menlo,monospace;color:#b8c0e0;white-space:pre-wrap;max-width:300px;word-break:break-all}
  .kx-sw{display:flex;gap:5px;padding:5px 10px 7px;flex-wrap:wrap}
  .kx-sw span{width:16px;height:16px;border-radius:4px;cursor:pointer;border:1px solid #0005}
  .kx-sw span:hover{outline:2px solid #fff}
  `;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // ====================================================================== generic menu component
  // An item is '-' (separator), {header, color}, {info}, {swatches, pick} or
  // {label, icon, key, act, sub, check, disabled, danger}.
  let stack = [];                     // open menu elements (root + submenus)

  /** Close every open context menu. */
  function closeAll() { stack.forEach(m => m.remove()); stack = []; }
  MN.close = closeAll;

  /** Render a menu (or submenu) at screen position x, y; `level` is its depth in the stack. */
  function openMenu(items, x, y, level) {
    while (stack.length > level) stack.pop().remove();
    const m = document.createElement('div');
    m.className = 'kx-menu' + (level ? ' sub' : '');
    items = items.filter(Boolean);
    m.innerHTML = items.map((it, i) => {
      if (it === '-') return '<div class="kx-sep"></div>';
      if (it.header) return `<div class="kx-hd">${it.color ? `<i style="background:${esc(it.color)}"></i>` : ''}${esc(it.header)}</div>`;
      if (it.info !== undefined) return `<div class="kx-info">${esc(it.info)}</div>`;
      if (it.swatches) return `<div class="kx-sw" data-i="${i}">${it.swatches.map(c => `<span data-c="${esc(c)}" style="background:${esc(c)}"></span>`).join('')}</div>`;
      const cls = ['kx-it', it.disabled ? 'dis' : '', it.danger ? 'danger' : '', it.check ? 'chk' : ''].join(' ');
      return `<div class="${cls}" data-i="${i}"><span class="ic">${it.check ? '✓' : esc(it.icon || '')}</span><span class="lb">${esc(it.label)}</span>` +
        `${it.key ? `<kbd>${esc(it.key)}</kbd>` : ''}${it.sub ? '<span class="ar">›</span>' : ''}</div>`;
    }).join('');
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 6)) + 'px';
    m.style.top = Math.max(4, Math.min(y, innerHeight - r.height - 6)) + 'px';
    stack.push(m);
    const openSub = (row) => {
      const it = items[+row.dataset.i];
      if (!it || !it.sub) return;
      const rr = row.getBoundingClientRect();
      const x2 = rr.right + 2 + 220 > innerWidth ? rr.left - 222 : rr.right + 2;
      openMenu(typeof it.sub === 'function' ? it.sub() : it.sub, x2, rr.top - 4, level + 1);
    };
    m.addEventListener('mouseover', e => {
      const row = e.target.closest('.kx-it'); if (!row || row.classList.contains('dis')) return;
      m.querySelectorAll('.kx-it.hot').forEach(x => x.classList.remove('hot')); row.classList.add('hot');
      const it = items[+row.dataset.i];
      if (it && it.sub) openSub(row); else while (stack.length > level + 1) stack.pop().remove();
    });
    m.addEventListener('click', e => {
      const sw = e.target.dataset && e.target.dataset.c;
      if (sw) { const it = items[+e.target.parentElement.dataset.i]; closeAll(); it.pick(sw); return; }
      const row = e.target.closest('.kx-it'); if (!row) return;
      const it = items[+row.dataset.i];
      if (!it || it.disabled) return;
      if (it.sub) { openSub(row); return; }
      closeAll();
      if (it.act) try { it.act(); } catch (err) { KS.status(`<span class="ks-err">${esc(err.message)}</span>`); console.error(err); }
    });
    m.addEventListener('contextmenu', e => e.preventDefault());
    return m;
  }
  /** Open a menu at screen position (x, y), closing any other open menu first. */
  MN.open = (items, x, y) => { closeAll(); return openMenu(items, x, y, 0); };

  // keyboard navigation
  document.addEventListener('keydown', e => {
    if (!stack.length) return;
    const m = stack[stack.length - 1];
    const rows = [...m.querySelectorAll('.kx-it:not(.dis)')];
    let i = rows.findIndex(r => r.classList.contains('hot'));
    const hot = (k) => { rows.forEach(r => r.classList.remove('hot')); if (rows[k]) { rows[k].classList.add('hot'); rows[k].scrollIntoView({ block: 'nearest' }); } };
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); if (stack.length > 1) stack.pop().remove(); else closeAll(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); hot((i + 1) % rows.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); hot((i - 1 + rows.length) % rows.length); }
    else if (e.key === 'ArrowRight' && rows[i]) { e.preventDefault(); rows[i].dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); const sub = stack[stack.length - 1]; if (sub !== m) { const f = sub.querySelector('.kx-it:not(.dis)'); if (f) f.classList.add('hot'); } }
    else if (e.key === 'ArrowLeft' && stack.length > 1) { e.preventDefault(); stack.pop().remove(); }
    else if (e.key === 'Enter' && rows[i]) { e.preventDefault(); rows[i].click(); }
  }, true);
  document.addEventListener('mousedown', e => { if (stack.length && !e.target.closest('.kx-menu')) closeAll(); }, true);
  window.addEventListener('blur', closeAll);

  // ====================================================================== helpers
  const WR = () => window.KnodeWires, SD = () => window.KnodeStudio;
  const pn = (p) => (p ? p.name : '');
  /** Select exactly one node and show it in the Properties panel. */
  function selectOnly(id) { graph.selectedNodes = [id]; graph.selectedWires = []; renderer.render(); updatePropertiesPanel(graph.nodes[id]); }
  /** Delete the given wires (de-duplicated) and record one undo step. */
  function removeWires(ids) { [...new Set(ids)].forEach(id => graph.wires[id] && graph.removeWire(Number(id))); renderer.render(); saveState(); }
  /** Node ids reachable from `start` following wires upstream ('up') or downstream ('down'). */
  function reach(start, dir) {                    // upstream / downstream closure through wires
    const seen = new Set([start]), q = [start];
    while (q.length) {
      const v = q.shift();
      for (const w of Object.values(graph.wires)) {
        const [a, b] = dir === 'up' ? [w.to, w.from] : [w.from, w.to];
        if (a === v && !seen.has(b)) { seen.add(b); q.push(b); }
      }
    }
    return [...seen];
  }
  /** The recently added template ids (most recent first), from localStorage. */
  function recent() { try { return JSON.parse(localStorage.getItem('knode.recent') || '[]'); } catch (e) { return []; } }
  /** Remember a template as recently used (keeps the last 8) for the Add node ▸ Recent menu. */
  KS.noteRecent = (tid) => {
    try { localStorage.setItem('knode.recent', JSON.stringify([tid, ...recent().filter(x => x !== tid)].slice(0, 8))); } catch (e) { /* ignore */ }
  };
  const addAt = (tid, w) => KS.addTemplateAt(tid, w);

  /** "Add node" submenu: search, recent, all categories, basic node classes. */
  function addNodeItems(w, clientXY) {
    const lib = KS.library;
    const items = [{ label: 'Search library…', icon: '⌕', key: 'Tab', act: () => KS.openPalette(w) }];
    const rec = recent().filter(t => KS.byId && KS.byId[t]);
    if (rec.length) items.push({ label: 'Recent', icon: '↺', sub: rec.map(t => ({ label: KS.byId[t].name, act: () => addAt(t, w) })) });
    if (lib) {
      items.push('-');
      const cats = {};
      for (const t of lib.templates) (cats[t.category] = cats[t.category] || []).push(t);
      for (const [c, ts] of Object.entries(cats))
        items.push({ label: c, icon: '●', sub: () => [{ header: c, color: lib.categories[c] }, ...ts.map(t => ({ label: t.name + (t.stateful ? '  ⟳' : ''), act: () => addAt(t.id, w) }))] });
    } else items.push({ label: 'Library unavailable — backend offline', disabled: true });
    items.push('-', { label: 'Basic node', icon: '□', sub: ['standard', 'dominant', 'empty'].map(k => ({
      label: k[0].toUpperCase() + k.slice(1) + ' node', act: () => { renderer.lastContextMenuPos = clientXY; addNodeAtCursor(k); } })) });
    return items;
  }

  const styleItems = (cur, set) => [['smart', 'Smart curve'], ['classic', 'Classic bezier'], ['linear', 'Straight'], ['orthogonal', 'Orthogonal'], ['step', 'Step'], ['cubic', 'Arched']]
    .map(([k, l]) => ({ label: l, check: cur === k, act: () => set(k) }));

  // ====================================================================== menus per target
  function canvasMenu(w, xy) {
    const L = SD() && SD().live;
    const h = KS.health;
    return [
      { header: 'Canvas' },
      { label: 'Add node', icon: '＋', sub: () => addNodeItems(w, xy) },
      { label: 'Add note', icon: '✎', act: () => addAt('note', w), disabled: !KS.byId || !KS.byId.note },
      { label: 'Add frame here', icon: '▭', act: () => { KS.frames.push({ id: Date.now(), x: w.x - 150, y: w.y - 90, w: 300, h: 180, title: 'Frame', color: COLORS[KS.frames.length % COLORS.length] }); renderer.render(); saveState(); } },
      { label: 'Add Globals', icon: 'ƒ', act: () => addAt('globals', w), disabled: !KS.byId || !KS.byId.globals },
      { label: 'Add Send / Receive pair', icon: '📡', act: () => { const ch = prompt('Channel name', 'signal'); if (!ch) return; const a = addAt('send', { x: w.x - 130, y: w.y }), b = addAt('receive', { x: w.x + 130, y: w.y }); a.properties.params.channel = ch; b.properties.params.channel = ch; renderer.render(); saveState(); } },
      '-',
      { label: 'Paste', icon: '⎘', key: 'Ctrl+V', act: () => pasteNodes() },
      { label: 'Select all', icon: '▦', key: 'Ctrl+A', act: () => { graph.selectedNodes = Object.keys(graph.nodes).map(Number); renderer.render(); } },
      { label: 'Frame all', icon: '⤢', key: 'F', act: () => KS.frame() },
      '-',
      { label: 'Run once', icon: '▶', key: 'Ctrl+Enter', act: () => KS.runGraph(null) },
      { label: 'Simulate', icon: '▶▶', key: 'Ctrl+⇧+Enter', act: () => KS.runSimulation() },
      { label: L && L.on ? 'Stop live mode' : 'Start live mode', icon: '●', key: 'Space', act: () => SD().toggleLive() },
      { label: 'Clear results', icon: '⌫', act: () => { KS.results = {}; KS.lastRun = null; KS.lastSim = null; renderer.render(); } },
      '-',
      { label: 'Wire style', icon: '∿', sub: () => styleItems(KS.wireStyle, s => WR().setWireStyle(s)) },
      { label: 'Backend', icon: h ? '🟢' : '🔴', sub: () => [
        { info: h ? `online · ${h.version} · Python ${h.python}${h.supervised ? ' · launcher' : ''}` : 'offline' },
        { label: 'Backend manager…', act: () => window.KnodeBackend.open() },
        { label: 'Reconnect', act: () => window.KnodeBackend.check(true) },
        { label: 'Restart backend', disabled: !h, act: () => window.KnodeBackend.restart() }] },
      { label: 'Export image with model', icon: '🖼', act: () => SD().exportPNG() },
      '-',
      { label: 'Undo', icon: '↶', key: 'Ctrl+Z', act: () => undo(), disabled: undoStack.length < 2 },
      { label: 'Redo', icon: '↷', key: 'Ctrl+⇧+Z', act: () => redo(), disabled: !redoStack.length },
    ];
  }

  /** Context menu for a node (or the current multi-selection that contains it). */
  function nodeMenu(n, w) {
    const p = n.properties || {}, tpl = KS.byId && KS.byId[p.template];
    const isGroup = !!p.subgraph, multi = graph.selectedNodes.length > 1 && graph.selectedNodes.includes(n.id);
    const r = KS.results[n.id];
    const allWires = [...n.inputs, ...n.outputs, ...n.dummyPorts].flatMap(q => q.connections || []);
    return [
      { header: multi ? `${graph.selectedNodes.length} nodes selected` : n.name, color: n.lineColor },
      r && r.status === 'error' ? { info: `✗ ${r.error.line ? 'line ' + r.error.line + ': ' : ''}${r.error.error}` } : null,
      { label: 'Run to here', icon: '▶', act: () => executeSingleNode(n.id) },
      { label: 'Plot outputs', icon: '📈', disabled: !n.outputs.length, act: () => { KS.plotSel = { x: 'default', y: n.outputs.map(o => n.id + '.' + o.name) }; KS.openPlot(); } },
      n.outputs.length ? { label: 'Pin output to dashboard', icon: '📌', sub: n.outputs.map(o => ({ label: o.name, act: () => SD().pinOutput(n, o.name) })) } : null,
      '-',
      isGroup ? { label: 'Open group', icon: '⤵', key: 'dbl-click', act: () => UI.enterGroup(n.id) } : { label: 'Edit code…', icon: '⚙', key: 'dbl-click', act: () => openCodeEditor(n.id) },
      isGroup ? { label: 'Ungroup', icon: '⤴', key: 'Ctrl+⇧+G', act: () => UI.ungroup(n.id) } : null,
      { label: 'Rename…', icon: '✎', act: () => { const v = prompt('Node name', n.name); if (v) { updateNodeName(n.id, v); renderer.render(); updatePropertiesPanel(n); } } },
      { label: 'Colour', icon: '◐', sub: [{ swatches: COLORS, pick: c => { n.setLineColor(c); renderer.render(); saveState(); } }] },
      { label: 'Duplicate', icon: '⧉', key: 'Ctrl+D', act: () => { if (!multi) selectOnly(n.id); copySelected(); pasteNodes(); } },
      { label: 'Copy', icon: '⎘', key: 'Ctrl+C', act: () => { if (!multi) selectOnly(n.id); copySelected(); } },
      '-',
      { label: 'Flags', icon: '⚑', sub: () => [
        { label: 'Bypass', check: !!p.bypass, key: 'Ctrl+E', act: () => SD().toggleFlag(n, 'bypass') },
        { label: 'Freeze outputs', check: !!p.frozen, key: 'Ctrl+⇧+L', act: () => SD().toggleFlag(n, 'frozen') },
        { label: 'Use result cache', check: p.cache !== false, act: () => SD().toggleFlag(n, 'cache') },
        { label: p.break_if ? `Break if: ${p.break_if}` : 'Break if…', check: !!p.break_if, act: () => { const c = prompt('Pause the simulation when this is true (outputs, t, step). Empty = off.', p.break_if || ''); if (c === null) return; if (c.trim()) p.break_if = c.trim(); else delete p.break_if; renderer.render(); saveState(); } }] },
      { label: 'Connections', icon: '⇄', sub: () => [
        { label: 'Select upstream', act: () => { graph.selectedNodes = reach(n.id, 'up'); renderer.render(); } },
        { label: 'Select downstream', act: () => { graph.selectedNodes = reach(n.id, 'down'); renderer.render(); } },
        '-',
        { label: 'Disconnect inputs', disabled: !n.inputs.some(q => q.connections.length), act: () => removeWires(n.inputs.flatMap(q => q.connections)) },
        { label: 'Disconnect outputs', disabled: !n.outputs.some(q => q.connections.length), act: () => removeWires(n.outputs.flatMap(q => q.connections)) },
        { label: 'Disconnect all', disabled: !allWires.length, danger: true, act: () => removeWires(allWires) }] },
      multi ? { label: 'Group selection', icon: '⧈', key: 'Ctrl+G', act: () => UI.groupSelection() } : { label: 'Make group', icon: '⧈', key: 'Ctrl+G', act: () => { selectOnly(n.id); UI.groupSelection(); } },
      { label: 'Frame selection', icon: '▭', key: 'Ctrl+J', act: () => { if (!multi) selectOnly(n.id); SD().frameSelection(); } },
      '-',
      { label: 'Node type', icon: '◈', sub: () => [
        { label: 'Save as node type…', act: () => UI.designer(UI.fromNode(n)) },
        { label: 'Edit this type…', disabled: !tpl, act: () => UI.designer(JSON.parse(JSON.stringify(tpl))) },
        { label: 'Reset parameters to defaults', disabled: !tpl, act: () => {
          p.params = JSON.parse(JSON.stringify(tpl.params));
          const [ins, outs] = KS.derivePorts(tpl, p.params); KS.syncPorts(n, ins, outs);
          renderer.render(); updatePropertiesPanel(n); saveState(); } },
        { label: 'Help for this node', disabled: !tpl, act: () => { window.KnodeAbout.show('library'); const s = document.querySelector('#abLS'); if (s) { s.value = tpl.name; s.dispatchEvent(new Event('input')); } } }] },
      '-',
      { label: multi ? `Delete ${graph.selectedNodes.length} nodes` : 'Delete', icon: '🗑', key: 'Del', danger: true, act: () => { if (!multi) selectOnly(n.id); deleteSelected(); } },
    ];
  }

  /** Context menu for a port: its value, disconnect, feed a Constant, add a node here, plot / pin, enable. */
  function portMenu(hit, xy) {
    const { node: n, port: q } = hit;
    const wr = WR();
    const dirIdx = q.isDummy ? ['dummy', n.dummyPorts.indexOf(q)] : q.isInput ? ['input', n.inputs.indexOf(q)] : ['output', n.outputs.indexOf(q)];
    const r = KS.results[n.id];
    const v = !q.isInput && r && r.outputs ? r.outputs[q.name] : undefined;
    const pw = KS.worldAtScreen(xy.x, xy.y);
    return [
      { header: `${n.name} · ${q.name} (${q.isDummy ? 'relation' : q.isInput ? 'input' : 'output'})`, color: n.lineColor },
      v !== undefined ? { info: '= ' + KS.fmt(v, 8) } : null,
      { label: `Disconnect (${q.connections.length})`, icon: '✂', disabled: !q.connections.length, act: () => removeWires(q.connections) },
      q.isInput && !q.isDummy ? { label: 'Feed a Constant', icon: '＃', key: 'Alt+click', disabled: q.connections.length > 0, act: () => wr.feedConstant(n, q) } : null,
      !q.isDummy ? { label: q.isInput ? 'Add node feeding this input…' : 'Add node from this output…', icon: '＋', act: () => KS.openPalette({ x: pw.x + (q.isInput ? -260 : 60), y: pw.y - 30 }, {
        filter: t => { const [i, o] = KS.derivePorts(t, t.params); return q.isInput ? o.length > 0 : i.length > 0; },
        onPick: m => { const ok = q.isInput ? graph.connect(m.id, n.id, m.outputs[0].name, q.name) : graph.connect(n.id, m.id, q.name, m.inputs[0].name); if (ok) { renderer.render(); saveState(); } } }) } : null,
      !q.isInput && !q.isDummy ? { label: 'Plot this output', icon: '📈', act: () => { KS.plotSel = { x: 'default', y: [n.id + '.' + q.name] }; KS.openPlot(); } } : null,
      !q.isInput && !q.isDummy ? { label: 'Pin to dashboard', icon: '📌', act: () => SD().pinOutput(n, q.name) } : null,
      v !== undefined ? { label: 'Copy value', icon: '⎘', act: () => navigator.clipboard && navigator.clipboard.writeText(JSON.stringify(v)) } : null,
      '-',
      { label: q.enabled ? 'Disable port' : 'Enable port', icon: '⏻', act: () => { togglePortEnabled(n.id, dirIdx[0], dirIdx[1], !q.enabled); renderer.render(); } },
    ];
  }

  /** Context menu for a wire: its value and type, insert node / reroute, enable, style, select ends, delete. */
  function wireMenu(wid, w) {
    const wire = graph.wires[wid];
    const a = graph.nodes[wire.from], b = graph.nodes[wire.to];
    const r = a && KS.results[a.id], fp = pn(wire.fromPortObj) || wire.fromPort;
    const v = r && r.outputs ? r.outputs[fp] : undefined;
    const t = WR().wireType(wire);
    return [
      { header: `${a ? a.name : '?'}.${fp} → ${b ? b.name : '?'}.${pn(wire.toPortObj) || wire.toPort}`, color: t && t !== 'none' ? WR().TYPES[t].color : '#8a93a8' },
      v !== undefined ? { info: `${t ? WR().TYPES[t].label + ' ' : ''}= ${KS.fmt(v, 8)}` } : { info: 'no value yet — run the model' },
      { label: 'Insert node…', icon: '＋', act: () => KS.openPalette(w, { filter: tt => { const [i, o] = KS.derivePorts(tt, tt.params); return i.length && o.length; },
        onPick: m => { if (graph.wires[wid] && WR().spliceNode(wid, m)) saveState(); } }) },
      { label: 'Insert reroute dot', icon: '•', key: 'dbl-click', act: () => WR().insertReroute(wid, w) },
      { label: wire.enabled ? 'Disable wire' : 'Enable wire', icon: '⏻', act: () => { toggleWireEnabled(wid); renderer.render(); saveState(); } },
      { label: 'Style', icon: '∿', sub: () => [{ label: 'Follow global style', check: !wire.curveType || wire.curveType === 'bezier', act: () => setWireCurveType(wid, 'bezier') }, '-',
        ...styleItems(wire.curveType, s => setWireCurveType(wid, s))] },
      v !== undefined ? { label: 'Copy value', icon: '⎘', act: () => navigator.clipboard && navigator.clipboard.writeText(JSON.stringify(v)) } : null,
      '-',
      { label: 'Select source node', icon: '←', act: () => a && selectOnly(a.id) },
      { label: 'Select target node', icon: '→', act: () => b && selectOnly(b.id) },
      '-',
      { label: 'Delete wire', icon: '🗑', danger: true, act: () => removeWires([Number(wid)]) },
    ];
  }

  /** Context menu for a frame: rename, colour, select / group / delete its contents. */
  function frameMenu(f) {
    const inside = () => Object.values(graph.nodes).filter(n => n.x >= f.x && n.y >= f.y && n.x + n.width <= f.x + f.w && n.y + n.height <= f.y + f.h);
    return [
      { header: 'Frame · ' + f.title, color: f.color },
      { label: 'Rename…', icon: '✎', act: () => { const t = prompt('Frame title', f.title); if (t !== null) { f.title = t || 'Frame'; renderer.render(); saveState(); } } },
      { label: 'Colour', icon: '◐', sub: [{ swatches: COLORS, pick: c => { f.color = c; renderer.render(); saveState(); } }] },
      { label: 'Select contents', icon: '▦', act: () => { graph.selectedNodes = inside().map(n => n.id); renderer.render(); } },
      { label: 'Group contents', icon: '⧈', act: () => { graph.selectedNodes = inside().map(n => n.id); UI.groupSelection(); } },
      '-',
      { label: 'Delete frame (keep nodes)', icon: '🗑', danger: true, act: () => { KS.frames = KS.frames.filter(x => x !== f); renderer.render(); saveState(); } },
      { label: 'Delete frame and nodes', icon: '🗑', danger: true, act: () => { graph.selectedNodes = inside().map(n => n.id); deleteSelected(); KS.frames = KS.frames.filter(x => x !== f); renderer.render(); saveState(); } },
    ];
  }

  /** The frame under a world position (title bar or body), topmost first. */
  function frameAt(w) {
    for (let i = KS.frames.length - 1; i >= 0; i--) { const f = KS.frames[i]; if (w.x >= f.x && w.x <= f.x + f.w && w.y >= f.y && w.y <= f.y + f.h) return f; }
    return null;
  }

  // ====================================================================== right-click dispatch
  function onContext(e) {
    e.preventDefault(); e.stopImmediatePropagation();
    const w = KS.worldAtScreen(e.clientX, e.clientY), xy = { x: e.clientX, y: e.clientY };
    renderer.lastContextMenuPos = xy;
    const oldMenu = document.getElementById('contextMenu'); if (oldMenu) oldMenu.classList.remove('active');
    let items;
    const hit = WR() && WR().portAt(w);
    const node = !hit && KS.nodeAt(w);
    if (hit) items = portMenu(hit, xy);
    else if (node) {
      if (!graph.selectedNodes.includes(node.id)) { graph.selectedNodes = [node.id]; graph.selectedWires = []; renderer.render(); updatePropertiesPanel(node); }
      items = nodeMenu(node, w);
    } else {
      const wid = renderer.getWireAt(w);
      if (wid !== null && wid !== undefined) { graph.selectedWires = [Number(wid)]; graph.selectedNodes = []; renderer.render(); items = wireMenu(wid, w); }
      else { const f = frameAt(w); items = f ? frameMenu(f) : canvasMenu(w, xy); }
    }
    MN.open(items, e.clientX, e.clientY);
  }
  MN.onContext = onContext;

  document.addEventListener('DOMContentLoaded', () => {
    renderer.canvas.addEventListener('contextmenu', onContext, true);
  });
})();

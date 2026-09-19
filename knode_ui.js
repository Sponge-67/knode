/* knode_ui.js — interface layer for knode 0.3
 *
 *  • Menubar (File / Edit / View / Model / Run / Help) replacing the crowded toolbar
 *  • Docked library sidebar: search, collapsible categories, drag-and-drop, your own node types
 *  • Groups: pack a selection into one node, enter / exit with breadcrumbs, ungroup, nested to any depth
 *  • Node Designer: create, test, save, share and update your own node types
 *  • Minimap, find node (Ctrl+F), shortcut sheet (?), node subtitles, refreshed theme
 */
(function () {
  'use strict';
  const KS = window.KnodeSci;
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => escapeHtml(s === undefined || s === null ? '' : s);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const UI = window.KnodeUI = { stack: [], sidebar: true, minimap: true };

  // =================================================================== theme
  const css = `
  :root{--bg:#131418;--panel:#1a1b20;--panel2:#202127;--line:#2b2d35;--line2:#373a44;--txt:#c9ccd6;--mute:#7d8599;--acc:#7c8cff;--acc2:#5b6bd8}
  body{background:var(--bg);color:var(--txt);font-family:Inter,"Segoe UI",system-ui,-apple-system,sans-serif}
  .header{background:var(--panel);border-bottom:1px solid var(--line);padding:0 10px;height:38px;gap:10px}
  .header h1{font-size:14px;font-weight:700;letter-spacing:.5px;color:#e6e8ef;display:flex;align-items:center;gap:6px}
  .header h1::before{content:"";width:14px;height:14px;border-radius:4px;background:linear-gradient(135deg,#7c8cff,#1dd1a1);display:inline-block}
  .header-actions{display:none!important}
  .canvas-container{background:var(--bg)}
  .properties-panel,.live-state-panel,.status-bar{background:var(--panel)!important;border-color:var(--line)!important}
  .properties-panel{box-shadow:inset 1px 0 0 #0006}
  .status-bar{color:var(--mute)!important}
  .info-panel{background:#1a1b20cc!important;border:1px solid var(--line)!important;border-radius:6px!important;backdrop-filter:blur(4px)}
  .kn-bar{display:flex;align-items:center;gap:2px;flex:1;min-width:0}
  .kn-menu{position:relative}
  .kn-menu>button{background:none;border:none;color:var(--txt);font-size:12px;padding:6px 9px;border-radius:5px;cursor:pointer}
  .kn-menu>button:hover,.kn-menu.open>button{background:var(--panel2)}
  .kn-drop{display:none;position:absolute;left:0;top:100%;min-width:250px;background:#1d1e24;border:1px solid var(--line2);border-radius:8px;padding:4px;z-index:3000;box-shadow:0 12px 32px #000a}
  .kn-menu.open>.kn-drop{display:block}
  .kn-item{display:flex;justify-content:space-between;gap:16px;padding:6px 10px;border-radius:5px;cursor:pointer;font-size:12px;white-space:nowrap;position:relative}
  .kn-item:hover{background:#2a2c38}.kn-item kbd{color:var(--mute);font:10px ui-monospace,monospace}
  .kn-item.dis{opacity:.4;pointer-events:none}.kn-item .chk{color:var(--acc);width:12px;display:inline-block}
  .kn-sep{height:1px;background:var(--line2);margin:4px 6px}
  .kn-sub>.kn-drop{left:100%;top:-5px}.kn-sub:hover>.kn-drop{display:block}
  .kn-sec{font-size:9px;color:var(--mute);padding:6px 10px 2px;text-transform:uppercase;letter-spacing:.06em}
  .kn-quick{display:flex;align-items:center;gap:6px;margin-left:auto}
  .kn-quick label{font-size:10px;color:var(--mute);display:flex;align-items:center;gap:4px}
  .kn-quick input.ks-num{width:62px;background:var(--bg);border:1px solid var(--line2);border-radius:5px;color:var(--txt);padding:3px 6px;font-size:11px}
  .kn-btn{background:var(--panel2);border:1px solid var(--line2);color:var(--txt);border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;display:flex;align-items:center;gap:5px}
  .kn-btn:hover{border-color:var(--acc)}.kn-btn.pri{background:var(--acc2);border-color:var(--acc);color:#fff}.kn-btn.go{background:#1e6f52;border-color:#27a577;color:#fff}
  .kn-btn.on{border-color:var(--acc);color:#fff;background:#2b3163}
  #knSide{width:230px;flex-shrink:0;background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
  #knSide.hidden{display:none}
  #knSide .kn-sh{padding:8px;border-bottom:1px solid var(--line);display:flex;gap:6px}
  #knSide input{flex:1;background:var(--bg);border:1px solid var(--line2);border-radius:6px;color:var(--txt);padding:5px 8px;font-size:11px;min-width:0}
  #knSideList{flex:1;overflow:auto;padding:4px 0 12px}
  .kn-cat{padding:6px 10px 4px;font-size:10px;font-weight:600;color:#aab0c0;cursor:pointer;display:flex;align-items:center;gap:6px;user-select:none;letter-spacing:.02em}
  .kn-cat i{width:8px;height:8px;border-radius:2px;display:inline-block}
  .kn-cat .n{margin-left:auto;color:var(--mute);font-weight:400}
  .kn-it{padding:4px 10px 4px 24px;font-size:11px;color:var(--txt);cursor:grab;display:flex;align-items:center;gap:6px;border-left:2px solid transparent}
  .kn-it:hover{background:var(--panel2);border-left-color:var(--acc)}
  .kn-it .tag{font-size:8px;color:var(--mute);border:1px solid var(--line2);border-radius:3px;padding:0 3px}
  .kn-it .act{margin-left:auto;display:none;gap:4px}.kn-it:hover .act{display:flex}
  .kn-it .act b{font-weight:400;color:var(--mute);cursor:pointer}.kn-it .act b:hover{color:#fff}
  #knCrumb{position:absolute;top:10px;left:50%;transform:translateX(-50%);background:#1d1e24ee;border:1px solid var(--acc);border-radius:18px;padding:4px 6px 4px 12px;
           display:none;align-items:center;gap:6px;font-size:11px;z-index:40;box-shadow:0 6px 20px #0008}
  #knCrumb.on{display:flex}#knCrumb a{color:#9fb0ff;cursor:pointer}#knCrumb span.cur{color:#fff;font-weight:600}
  #knMini{position:absolute;right:12px;bottom:12px;width:190px;height:120px;background:#0e0f12e6;border:1px solid var(--line2);border-radius:6px;z-index:30;cursor:pointer}
  #knMini.hidden{display:none}
  #knFind{position:absolute;top:10px;left:12px;z-index:45;background:#1d1e24;border:1px solid var(--line2);border-radius:8px;padding:6px;display:none;width:260px;box-shadow:0 8px 24px #000a}
  #knFind.on{display:block}#knFind input{width:100%;background:var(--bg);border:1px solid var(--line2);border-radius:5px;color:var(--txt);padding:5px 8px;font-size:12px}
  #knFind .r{padding:4px 8px;font-size:11px;cursor:pointer;border-radius:4px}#knFind .r.sel,#knFind .r:hover{background:#2a2c38}
  .kn-drop-hint{outline:2px dashed var(--acc);outline-offset:-6px}
  .kd-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .kd-f label{display:block;font-size:10px;color:var(--mute);margin-bottom:3px}
  .kd-f input,.kd-f select,.kd-f textarea{width:100%}
  .kd-f input[type=checkbox]{width:auto}
  .kd-code{font-family:ui-monospace,Menlo,Consolas,monospace!important;font-size:11.5px!important;line-height:1.5;min-height:230px;tab-size:4;white-space:pre}
  table.kd-p input,table.kd-p select{width:100%;padding:3px 4px!important;font-size:10.5px!important}
  table.kd-p td{padding:2px!important}
  .kd-msg{font-size:11px;margin-top:6px;white-space:pre-wrap}
  .ks-modal .ks-box{background:#1b1c21;border-color:var(--line2)}
  .kn-keys td{padding:3px 10px 3px 0;font-size:11px}.kn-keys kbd{background:#2a2c38;border:1px solid var(--line2);border-radius:4px;padding:1px 6px;font:10px ui-monospace,monospace}
  `;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // =================================================================== node JSON builders (no live graph needed)
  let jid = 1;
  const portJSON = (name, isInput) => ({ id: jid++, name, isInput, capacity: isInput ? 4 : 16, connections: [], enabled: true, portClass: 'standard',
    isDummy: false, properties: {}, dummySide: 'left', color: null, number_of_inputs: 0, isAlien: false, alienClass: null, parentClass: null });
  /**
   * Build a node's snapshot JSON from a template without touching the live graph
   * (used to assemble group contents and Group Input/Output markers).
   */
  function templateNodeJSON(tid, x, y, params, name) {
    const tpl = KS.byId[tid];
    const p = tpl.open_params && params && Object.keys(params).length ? clone(params) : Object.assign(clone(tpl.params), params || {});
    const [ins, outs] = KS.derivePorts(tpl, p);
    return { id: jid++, name: name || tpl.name, x, y, nodeClass: 'standard', properties: { template: tid, params: p }, code: tpl.code,
      note: '', noteExpanded: false, lineColor: tpl.color, snapEnabled: true, snapThreshold: 15, description: tpl.description,
      inputs: ins.map(n => portJSON(n, true)), outputs: outs.map(n => portJSON(n, false)), dummyPorts: [] };
  }
  const wireJSON = (from, fromPort, to, toPort) => ({ id: jid++, from, to, fromPort, toPort, fromPortId: null, toPortId: null, wireClass: 'standard',
    enabled: true, properties: {}, color: '#505050', selectedColor: '#888888', curveType: 'bezier' });

  /** Create a group node on the canvas that embeds `snapshot` and exposes the given input/output port names. */
  function makeGroupNode(name, x, y, snapshot, ins, outs) {
    const node = graph.addNode(name, Math.round(x), Math.round(y), 'standard');
    node.properties = { group: true, subgraph: snapshot, params: {} };
    node.inputs = []; node.outputs = [];
    ins.forEach(n => node.addInput(n, 4)); outs.forEach(n => node.addOutput(n, 16));
    node.code = 'def process():\n    # group node — the model lives inside (double-click to enter)\n    return {}\n';
    node._lastGenCode = null;
    node.description = 'Group: a graph packed into one node.';
    node.setLineColor('#9aa4b8');
    node._updateHeight();
    return node;
  }

  /** Build a group node for an example from its declarative group definition. */
  UI.createGroupFromExample = function (ex, spec) {
    const g = ex.groups[spec.group];
    jid = 1;
    const ids = [], snap = { nodes: {}, wires: {}, nextId: 1 };
    g.nodes.forEach((n, j) => {
      const params = Object.assign({}, n.params || {}, (spec.inner_params || {})[String(j)] || {});
      const nj = templateNodeJSON(n.tpl, n.x, n.y, params, n.name);
      snap.nodes[nj.id] = nj; ids.push(nj.id);
    });
    for (const [a, ap, b, bp] of g.wires) { const w = wireJSON(ids[a], ap, ids[b], bp); snap.wires[w.id] = w; }
    snap.nextId = jid;
    return makeGroupNode(spec.name || 'Group', spec.x, spec.y, snap, g.inputs, g.outputs);
  };

  // =================================================================== groups: create / enter / exit / ungroup
  const ident = (s) => (String(s).replace(/[^A-Za-z0-9_]/g, '_').replace(/^(\d)/, '_$1') || 'port');
  const uniq = (base, used) => { let n = ident(base), k = 2; while (used.has(n)) n = ident(base) + '_' + k++; used.add(n); return n; };
  const pname = (w, side) => side === 'from' ? (w.fromPortObj ? w.fromPortObj.name : w.fromPort) : (w.toPortObj ? w.toPortObj.name : w.toPort);

  /**
   * Ctrl+G: pack the selected nodes into a group node. Wires crossing the selection boundary become
   * Group Input / Group Output marker nodes inside and ports outside; outer wires are reconnected.
   */
  UI.groupSelection = function () {
    const sel = graph.selectedNodes.map(Number).filter(id => graph.nodes[id]);
    if (!sel.length) return KS.status('Select one or more nodes, then Edit ▸ Group (Ctrl+G)');
    const inSel = new Set(sel);
    saveState();
    jid = 1;
    const snap = { nodes: {}, wires: {}, nextId: 1 }, map = {};
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const id of sel) {
      const n = graph.nodes[id], j = clone(n.toJSON());
      j.id = jid++; map[id] = j.id;
      for (const k of ['inputs', 'outputs', 'dummyPorts']) for (const p of j[k] || []) { p.id = jid++; p.connections = []; }
      snap.nodes[j.id] = j;
      x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x + n.width); y1 = Math.max(y1, n.y + n.height);
    }
    const incoming = new Map(), outgoing = new Map(), used = new Set(), usedOut = new Set();
    for (const wid in graph.wires) {
      const w = graph.wires[wid], a = inSel.has(w.from), b = inSel.has(w.to);
      if (a && b) { const wj = wireJSON(map[w.from], pname(w, 'from'), map[w.to], pname(w, 'to')); wj.enabled = w.enabled; snap.wires[wj.id] = wj; }
      else if (!a && b) {                                   // outside → inside : Group Input per distinct source
        const key = w.from + '|' + pname(w, 'from');
        if (!incoming.has(key)) incoming.set(key, { from: w.from, port: pname(w, 'from'), name: uniq(pname(w, 'to'), used), targets: [] });
        incoming.get(key).targets.push([map[w.to], pname(w, 'to'), graph.nodes[w.to].y]);
      } else if (a && !b) {                                 // inside → outside : Group Output per distinct inner source
        const key = w.from + '|' + pname(w, 'from');
        if (!outgoing.has(key)) outgoing.set(key, { from: map[w.from], port: pname(w, 'from'), name: uniq(pname(w, 'from'), usedOut), targets: [], y: graph.nodes[w.from].y });
        outgoing.get(key).targets.push([w.to, pname(w, 'to')]);
      }
    }
    for (const inc of incoming.values()) {
      const m = templateNodeJSON('graph_in', x0 - 260, inc.targets[0][2], { name: inc.name, default: 0.0 }, 'in: ' + inc.name);
      snap.nodes[m.id] = m;
      for (const [tid, tp] of inc.targets) { const wj = wireJSON(m.id, 'value', tid, tp); snap.wires[wj.id] = wj; }
    }
    for (const o of outgoing.values()) {
      const m = templateNodeJSON('graph_out', x1 + 80, o.y, { name: o.name }, 'out: ' + o.name);
      snap.nodes[m.id] = m;
      const wj = wireJSON(o.from, o.port, m.id, 'value'); snap.wires[wj.id] = wj;
    }
    snap.nextId = jid;
    for (const id of sel) graph.removeNode(id);
    const node = makeGroupNode('Group', (x0 + x1) / 2 - 85, (y0 + y1) / 2 - 40, snap, [...incoming.values()].map(i => i.name), [...outgoing.values()].map(o => o.name));
    for (const inc of incoming.values()) graph.connect(Number(inc.from), node.id, inc.port, inc.name);
    for (const o of outgoing.values()) for (const [to, tp] of o.targets) graph.connect(node.id, Number(to), o.name, tp);
    graph.selectedNodes = [node.id];
    renderer.render(); updateStatus(); updatePropertiesPanel(node); saveState();
    KS.status(`Grouped ${sel.length} node(s) · ${incoming.size} input(s), ${outgoing.size} output(s) — double-click the group to open it`);
  };

  /** Names of Group Input (tid 'graph_in') or Group Output markers in a snapshot, ordered top to bottom. */
  function markers(snapOrGraph, tid) {
    const nodes = snapOrGraph.nodes;
    return Object.values(nodes).filter(n => (n.properties || {}).template === tid)
      .sort((a, b) => a.y - b.y).map(n => (n.properties.params || {}).name).filter(Boolean);
  }

  /** Execution reports for the groups at the current nesting level (from the last run of the whole model). */
  function currentReports() {
    let rep = KS.lastRun ? KS.lastRun.groups : null;
    for (const lvl of UI.stack) rep = rep && rep[lvl.groupId] ? rep[lvl.groupId].groups : null;
    return rep;
  }

  /**
   * Open a group for editing: push the current level (graph, undo history, view) and show the inner graph.
   * Inner results from the last run of the whole model are shown on the inner nodes.
   */
  UI.enterGroup = function (id) {
    const node = graph.nodes[id];
    if (!node || !node.properties.subgraph) return;
    const rep = currentReports();
    const inner = rep && rep[id];
    UI.stack.push({ parent: createSnapshot(), groupId: id, name: node.name, undo: undoStack, redo: redoStack, results: KS.results,
      view: { z: renderer.viewport.zoom, x: renderer.viewport.panX, y: renderer.viewport.panY } });
    undoStack = []; redoStack = [];
    restoreSnapshot(clone(node.properties.subgraph));
    KS.results = {};
    if (inner) for (const nid in inner.status) KS.results[nid] = { status: inner.status[nid], outputs: (inner.outputs || {})[nid], error: (inner.errors || {})[nid] };
    KS.inGroup = true;
    KS.frame(); updateCrumb(); updateUndoButtons();
    KS.status(`Inside “${esc(node.name)}” — Group Input / Group Output nodes are its ports. Esc or the breadcrumb returns.`);
  };

  /**
   * Close the current group: write the edited inner graph back into its group node, re-derive the group's
   * ports from its markers and restore the outer level with its undo history and view.
   */
  UI.exitGroup = function () {
    const top = UI.stack.pop();
    if (!top) return;
    const inner = createSnapshot();
    delete inner.selectedNodes; delete inner.selectedWires;
    restoreSnapshot(top.parent);
    undoStack = top.undo; redoStack = top.redo;
    const node = graph.nodes[top.groupId];
    if (node) {
      node.properties.subgraph = inner;
      KS.syncPorts(node, markers(inner, 'graph_in'), markers(inner, 'graph_out'));
    }
    KS.results = top.results;
    KS.inGroup = UI.stack.length > 0;
    Object.assign(renderer.viewport, { zoom: top.view.z, panX: top.view.x, panY: top.view.y });
    $('#zoomLabel').textContent = Math.round(top.view.z * 100) + '%';
    graph.selectedNodes = node ? [node.id] : [];
    renderer.render(); updateCrumb(); updateUndoButtons(); updateStatus();
    if (node) { updatePropertiesPanel(node); saveState(); }
  };
  /** Leave groups until the nesting depth equals `depth` (0 = the top-level model). */
  UI.exitTo = (depth) => { while (UI.stack.length > depth) UI.exitGroup(); };
  /** Leave all groups and return to the top-level model (used before loading or exporting). */
  UI.resetContext = () => UI.exitTo(0);

  /** Ctrl+Shift+G: replace a group node with its contents, reconnecting outer wires through the markers. */
  UI.ungroup = function (id) {
    const g = graph.nodes[id];
    if (!g || !g.properties.subgraph) return;
    saveState();
    const snap = clone(g.properties.subgraph), newId = {}, ins = {}, outs = {};
    const nodes = Object.values(snap.nodes);
    const ix0 = Math.min(...nodes.map(n => n.x)), iy0 = Math.min(...nodes.map(n => n.y));
    for (const nj of nodes) {
      const t = (nj.properties || {}).template;
      if (t === 'graph_in') { ins[nj.id] = nj.properties.params.name; continue; }
      if (t === 'graph_out') { outs[nj.id] = nj.properties.params.name; continue; }
      delete nj.id;
      for (const k of ['inputs', 'outputs', 'dummyPorts']) for (const p of nj[k] || []) { delete p.id; p.connections = []; }
      const C = nj.nodeClass === 'dominant' ? DominantNode : nj.nodeClass === 'empty' ? EmptyNode : StandardNode;
      const node = C.fromJSON(nj, C);
      node.x = g.x + (nj.x - ix0); node.y = g.y + (nj.y - iy0);
      graph.nodes[node.id] = node;
      newId[Object.keys(snap.nodes).find(k => snap.nodes[k] === nj)] = node.id;
    }
    // map old ids (keys) → new ids for real nodes
    const idOf = {}; Object.entries(snap.nodes).forEach(([k, nj]) => { if (newId[k] !== undefined) idOf[k] = newId[k]; });
    const outer = Object.values(graph.wires).filter(w => w.from === g.id || w.to === g.id)
      .map(w => ({ from: w.from, to: w.to, fp: pname(w, 'from'), tp: pname(w, 'to') }));
    graph.removeNode(g.id);
    for (const w of Object.values(snap.wires)) {
      const f = String(w.from), t = String(w.to);
      if (idOf[f] !== undefined && idOf[t] !== undefined) graph.connect(idOf[f], idOf[t], w.fromPort, w.toPort);
      else if (ins[f] !== undefined && idOf[t] !== undefined)        // Group Input → inner node: reconnect outer sources
        for (const o of outer) if (o.to === g.id && o.tp === ins[f]) graph.connect(o.from, idOf[t], o.fp, w.toPort);
      else if (idOf[f] !== undefined && outs[t] !== undefined)       // inner node → Group Output: reconnect outer targets
        for (const o of outer) if (o.from === g.id && o.fp === outs[t]) graph.connect(idOf[f], o.to, w.fromPort, o.tp);
    }
    graph.selectedNodes = Object.values(idOf);
    renderer.render(); updateStatus(); updatePropertiesPanel(null); saveState();
    KS.status('Ungrouped');
  };

  /** Show / refresh the breadcrumb bar (Model › Group › …) while inside groups. */
  function updateCrumb() {
    const c = $('#knCrumb');
    if (!UI.stack.length) { c.classList.remove('on'); return; }
    c.innerHTML = `<a data-d="0">⌂ Model</a>` + UI.stack.map((l, i) => i === UI.stack.length - 1
      ? ` › <span class="cur">⧉ ${esc(l.name)}</span>` : ` › <a data-d="${i + 1}">${esc(l.name)}</a>`).join('') +
      ` <button class="kn-btn" data-d="${UI.stack.length - 1}" style="padding:2px 8px">⤴ Exit</button>`;
    c.classList.add('on');
    c.onclick = e => { const d = e.target.dataset.d; if (d !== undefined) UI.exitTo(+d); };
  }

  // whole-model serialisation while inside groups: fold the edited level back into its ancestors
  const localSerialize = KS.serialize;
  /** Snapshot of the whole model with the currently edited group level folded back into its ancestors. */
  function rootSnapshot() {
    let child = createSnapshot();
    for (let i = UI.stack.length - 1; i >= 0; i--) {
      const lvl = UI.stack[i], parent = clone(lvl.parent);
      const gn = parent.nodes[lvl.groupId];
      gn.properties.subgraph = child;
      const ins = markers(child, 'graph_in'), outs = markers(child, 'graph_out');
      gn.inputs = ins.map(n => portJSON(n, true)); gn.outputs = outs.map(n => portJSON(n, false));
      child = parent;
    }
    return child;
  }
  /** Engine payload for runs: the whole model even while a group is being edited. */
  KS.serialize = function () {
    if (!UI.stack.length) return localSerialize();
    const root = rootSnapshot();
    const conns = Object.values(root.wires).filter(w => w.enabled !== false)
      .map(w => ({ id: w.id, from: String(w.from), to: String(w.to), fromPort: w.fromPort, toPort: w.toPort, kind: w.wireClass === 'dummy' ? 'relation' : 'data' }));
    return { nodes: root.nodes, connections: conns };
  };
  /** Names of the top-level nodes by id — trace labels stay correct while a group is open. */
  KS.rootNames = () => {
    const root = UI.stack.length ? UI.stack[0].parent : null;
    const nodes = root ? root.nodes : graph.nodes;
    return Object.fromEntries(Object.entries(nodes).map(([i, n]) => [i, n.name]));
  };
  /** Narrow a whole-model report to the group level currently shown, so inner nodes display their values. */
  KS.levelView = function (rep) {
    if (!UI.stack.length) return rep;
    let g = { outputs: rep.outputs, status: rep.status, errors: rep.errors, groups: rep.groups };
    for (const lvl of UI.stack) {
      const nxt = g.groups && g.groups[lvl.groupId];
      if (!nxt) {
        const err = g.errors && g.errors[lvl.groupId];
        return { outputs: {}, status: {}, errors: {}, groups: {}, warnings: [err ? 'group failed: ' + err.error : 'this group did not run'], cycles: [], loops: [], stdout: {} };
      }
      g = nxt;
    }
    return { outputs: g.outputs || {}, status: g.status || {}, errors: g.errors || {}, groups: g.groups || {}, profile: {}, stdout: {},
      warnings: rep.warnings, cycles: [], loops: [] };
  };

  // =================================================================== node subtitles
  const firstLine = (t) => String(t || '').split('\n').map(l => l.split('#')[0].trim()).filter(Boolean);
  /**
   * One to three short lines drawn inside a node: its key equation, reaction, topology, grid size,
   * group size or note text — whatever best identifies what the node models.
   */
  KS.subtitle = function (node) {
    const props = node.properties || {};
    if (props.subgraph) {
      const n = Object.values(props.subgraph.nodes || {}).filter(x => !['graph_in', 'graph_out'].includes((x.properties || {}).template)).length;
      return ['⧉ group · ' + n + ' node' + (n === 1 ? '' : 's'), 'double-click to open'];
    }
    const t = props.template, p = props.params || {};
    if (!t) return Object.keys(p).length ? Object.entries(p).slice(0, 3).map(([k, v]) => k + ' = ' + (typeof v === 'number' ? KS.fmt(v) : String(v).split('\n')[0])) : null;
    switch (t) {
      case 'formula': return firstLine(p.equations);
      case 'dynamic_system': return firstLine(p.equations);
      case 'discrete_map': return firstLine(p.update);
      case 'reaction_network': return firstLine(p.reactions).map(l => l.split(',')[0]).concat(p.method === 'ssa' ? ['stochastic (SSA)'] : []);
      case 'state_machine': return ['states: ' + p.states, ...firstLine(p.transitions).slice(0, 2)];
      case 'agent_based': return ['N = ' + p.N + ' agents', ...firstLine(p.rules).slice(0, 1)];
      case 'network_dynamics': return [p.topology + ' · N=' + p.N, ...firstLine(p.rules).slice(0, 1)];
      case 'field2d': return [p.size + '×' + p.size + ' grid', ...firstLine(p.equations).slice(0, 1)];
      case 'transfer_function': return ['G(s) = [' + p.num + '] / [' + p.den + ']'];
      case 'expr': case 'condition': return [p.expr || p.condition];
      case 'graph_in': return ['→ port “' + p.name + '”'];
      case 'graph_out': return ['port “' + p.name + '” →'];
      case 'note': return String(p.text || '').split('\n').slice(0, 3);
      case 'ode': return firstLine(p.equations);
      case 'minimize': return [p.objective];
      default: return Object.entries(p).filter(([, v]) => typeof v !== 'object').slice(0, 3)
        .map(([k, v]) => k + ' = ' + (typeof v === 'number' ? KS.fmt(v) : String(v).split('\n')[0]));
    }
  };

  // =================================================================== menubar
  const on = (k) => UI[k];
  /** Menubar definition: [menu, [[label, action, shortcut, submenu, checked?] | '-', …]]. */
  function menus() {
    const ex = KS.examples || [];
    const doms = [...new Set(ex.map(e => e.domain))];
    const m = [
      ['File', [
        ['New model', 'newModel', 'Ctrl+Alt+N'], ['Import…', () => showImportModal()], ['Export…', () => showExportModal(), 'Ctrl+S'], '-',
        ['Examples', null, null, doms.map(d => [d, null, null, ex.filter(e => e.domain === d).map(e => [e.title, () => KS.loadExample(e.id)])])],
        ['Restore autosave', 'restoreAutosave'],
      ]],
      ['Edit', [
        ['Undo', () => undo(), 'Ctrl+Z'], ['Redo', () => redo(), 'Ctrl+Shift+Z'], '-',
        ['Copy', () => copySelected(), 'Ctrl+C'], ['Paste', () => pasteNodes(), 'Ctrl+V'], ['Duplicate', 'duplicate', 'Ctrl+D'], ['Delete', () => deleteSelected(), 'Del'],
        ['Select all', 'selectAll', 'Ctrl+A'], '-',
        ['Group selection', () => UI.groupSelection(), 'Ctrl+G'], ['Ungroup', 'ungroupSel', 'Ctrl+Shift+G'], ['Exit group', () => UI.exitGroup(), 'Esc'], '-',
        ['Find node…', 'find', 'Ctrl+F'],
      ]],
      ['View', [
        ['Frame all', () => KS.frame(), 'F'], ['Zoom in', () => zoomIn()], ['Zoom out', () => zoomOut()], ['Reset zoom', () => zoomReset()], '-',
        ['Library sidebar', 'toggleSidebar', 'Ctrl+B', null, () => UI.sidebar], ['Minimap', 'toggleMinimap', 'M', null, () => UI.minimap],
        ['Properties panel', () => togglePanel('propertiesPanel')], ['State & log panel', () => togglePanel('liveStatePanel')],
        ['Plot panel', () => $('#ksPlotBtn').click(), 'P'], ['Snap to grid', () => toggleSnap(), null, null, () => snapEnabled],
      ]],
      ['Model', [
        ['Add node from library…', () => KS.openPalette(null), 'Tab'], '-',
        ['New node type…', () => UI.designer(), 'Ctrl+Shift+N'], ['Save selected node as type…', 'saveAsType'], ['Edit selected node\'s type…', 'editType'],
        ['Import node type (.json)…', 'importType'], '-',
        ['Group selection', () => UI.groupSelection(), 'Ctrl+G'],
      ]],
      ['Run', [
        ['Run once', () => KS.runGraph(null), 'Ctrl+Enter'], ['Simulate', () => KS.runSimulation(), 'Ctrl+Shift+Enter'],
        ['Re-run automatically on parameter change', 'toggleAuto', null, null, () => KS.autoRun], '-',
        ['Parameter study (sweep / Monte Carlo)…', () => KS.openSweep()], ['Graph analysis…', () => KS.openAnalysis()],
      ]],
      ['Help', [['Keyboard shortcuts', 'keys', '?'], ['Universal nodes guide', 'guide'], ['About knode', 'about']]],
    ];
    return UI.extendMenus ? UI.extendMenus(m) : m;
  }
  const ACTIONS = {
    newModel() { if (Object.keys(graph.nodes).length && !confirm('Start a new, empty model? (Undo with Ctrl+Z)')) return; UI.resetContext(); saveState(); KS.clearGraph(); renderer.render(); updateStatus(); updatePropertiesPanel(null); saveState(); },
    restoreAutosave() { try { const a = JSON.parse(localStorage.getItem('knode.autosave')); UI.resetContext(); graph.fromJSON(a.graph); KS.results = {}; KS.frame(); KS.status('Restored autosave from ' + new Date(a.at).toLocaleString()); } catch (e) { KS.status('No autosave available'); } },
    duplicate() { copySelected(); pasteNodes(); },
    selectAll() { graph.selectedNodes = Object.keys(graph.nodes).map(Number); graph.selectedWires = []; renderer.render(); updatePropertiesPanel(null); },
    ungroupSel() { const id = graph.selectedNodes[0]; if (id !== undefined) UI.ungroup(id); },
    find() { openFind(); },
    toggleSidebar() { UI.sidebar = !UI.sidebar; $('#knSide').classList.toggle('hidden', !UI.sidebar); setTimeout(() => renderer.resize(), 0); },
    toggleMinimap() { UI.minimap = !UI.minimap; $('#knMini').classList.toggle('hidden', !UI.minimap); },
    toggleAuto() { KS.autoRun = !KS.autoRun; $('#knAuto').classList.toggle('on', !!KS.autoRun); KS.status(KS.autoRun ? 'Auto re-run ON: parameter edits re-run the last Run/Simulate' : 'Auto re-run off'); },
    saveAsType() { const n = graph.nodes[graph.selectedNodes[0]]; if (!n) return KS.status('Select a node first'); UI.designer(fromNode(n)); },
    editType() { const n = graph.nodes[graph.selectedNodes[0]]; const t = n && KS.byId[(n.properties || {}).template]; if (!t) return KS.status('Select a node made from a type'); UI.designer(clone(t)); },
    importType() { const f = document.createElement('input'); f.type = 'file'; f.accept = '.json'; f.onchange = async () => { try { UI.designer(JSON.parse(await f.files[0].text())); } catch (e) { KS.status('Not a node-type file: ' + esc(e.message)); } }; f.click(); },
    keys() { showKeys(); }, guide() { showGuide(); },
    about() { KS.modal('ksAbout', 'About knode', 460).innerHTML = `<p><b>knode ${esc((KS.health || {}).version || '')}</b> — node-based modelling, simulation and data-flow programming with embedded Python.</p><p style="margin-top:8px;color:#999">${(KS.library || { templates: [] }).templates.length} node types · backend ${KS.health ? 'online' : 'offline'} · numpy ${KS.health && KS.health.numpy ? 'yes' : 'no'}</p>`; },
  };

  /** Render menu items (including submenus and check marks) to HTML; actions are registered by index. */
  function buildMenuHTML(items) {
    return items.map(it => {
      if (it === '-') return '<div class="kn-sep"></div>';
      const [label, act, key, sub, check] = it;
      if (sub) return `<div class="kn-item kn-sub">${esc(label)}<span>›</span><div class="kn-drop">${buildMenuHTML(sub)}</div></div>`;
      const c = check ? `<span class="chk">${check() ? '✓' : ''}</span> ` : '';
      return `<div class="kn-item" data-act="${typeof act === 'string' ? act : ''}" data-fn="${typeof act === 'function' ? UI._fns.push(act) - 1 : ''}">${c}${esc(label)}${key ? `<kbd>${esc(key)}</kbd>` : ''}</div>`;
    }).join('');
  }
  UI.renderMenubar = () => renderMenubar();
  /** (Re)build the menubar — called after the library/examples load and whenever check marks change. */
  function renderMenubar() {
    UI._fns = [];
    const bar = $('#knMenus');
    bar.innerHTML = menus().map(([name, items]) => `<div class="kn-menu"><button>${name}</button><div class="kn-drop">${buildMenuHTML(items)}</div></div>`).join('');
    bar.querySelectorAll('.kn-menu>button').forEach(b => {
      b.onclick = e => { const m = b.parentElement, open = m.classList.contains('open'); closeMenus(); if (!open) { renderMenubarKeep(m); } e.stopPropagation(); };
      b.onmouseenter = () => { if (bar.querySelector('.kn-menu.open') && !b.parentElement.classList.contains('open')) { closeMenus(); renderMenubarKeep(b.parentElement); } };
    });
    bar.onclick = e => {
      const it = e.target.closest('.kn-item'); if (!it || it.classList.contains('kn-sub')) return;
      closeMenus();
      if (it.dataset.act) ACTIONS[it.dataset.act](); else if (it.dataset.fn !== '') UI._fns[+it.dataset.fn]();
    };
  }
  /** Rebuild the menubar and keep the given menu open (so check marks update in place). */
  function renderMenubarKeep(m) {        // re-render to refresh check marks, then open the same menu
    const idx = [...m.parentElement.children].indexOf(m);
    renderMenubar();
    $('#knMenus').children[idx].classList.add('open');
  }
  const closeMenus = () => document.querySelectorAll('.kn-menu.open').forEach(m => m.classList.remove('open'));
  document.addEventListener('click', closeMenus);

  /** Replace the old toolbar with the menubar and the quick controls (steps, dt, auto, Run, Simulate, Plot). */
  function buildHeader() {
    const header = $('.header');
    const bar = document.createElement('div');
    bar.className = 'kn-bar';
    bar.innerHTML = `<div id="knMenus" style="display:flex;gap:1px"></div>
      <div class="kn-quick" id="knQuick">
        <label>steps</label><label>dt</label>
        <button class="kn-btn" id="knAuto" title="Re-run automatically when a parameter changes">⟳ auto</button>
        <button class="kn-btn go" id="knRun" title="Run once (Ctrl+Enter)">▶ Run</button>
      </div>`;
    header.insertBefore(bar, header.children[1]);
    const q = $('#knQuick'), labels = q.querySelectorAll('label');
    labels[0].appendChild($('#ksSteps')); labels[1].appendChild($('#ksDt'));
    const sim = $('#ksSimBtn'); sim.className = 'kn-btn pri'; q.appendChild(sim);
    const plot = $('#ksPlotBtn'); plot.className = 'kn-btn'; q.appendChild(plot);
    const dot = $('#ksDot'); q.appendChild(dot);
    $('#knRun').onclick = () => KS.runGraph(null);
    $('#knAuto').onclick = () => ACTIONS.toggleAuto();
    renderMenubar();
  }

  // =================================================================== sidebar library
  const collapsed = new Set(JSON.parse(localStorage.getItem('knode.collapsed') || '[]'));
  /** Create the docked library sidebar and make the canvas accept templates dropped from it. */
  function buildSidebar() {
    const side = document.createElement('div');
    side.id = 'knSide';
    side.innerHTML = `<div class="kn-sh"><input id="knQ" placeholder="Search ${''}nodes…"><button class="kn-btn" id="knNewType" title="New node type (Node Designer)">＋</button></div><div id="knSideList"></div>`;
    const mid = $('.middle-section');
    mid.insertBefore(side, mid.firstChild);
    $('#knQ').oninput = renderSide;
    $('#knNewType').onclick = () => UI.designer();
    const cc = $('#canvasContainer');
    cc.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('knode/template')) { e.preventDefault(); cc.classList.add('kn-drop-hint'); } });
    cc.addEventListener('dragleave', () => cc.classList.remove('kn-drop-hint'));
    cc.addEventListener('drop', e => {
      cc.classList.remove('kn-drop-hint');
      const tid = e.dataTransfer.getData('knode/template'); if (!tid) return;
      e.preventDefault(); KS.addTemplateAt(tid, KS.worldAtScreen(e.clientX, e.clientY));
    });
  }
  /**
   * Render the sidebar: search-filtered, collapsible categories (collapsed state is remembered),
   * draggable items, edit/delete for user types.
   */
  function renderSide() {
    const list = $('#knSideList');
    if (!KS.library) { list.innerHTML = '<div style="padding:10px;color:#777;font-size:11px">Start the backend:<br><code>python server.py</code></div>'; return; }
    const q = ($('#knQ').value || '').toLowerCase().split(/\s+/).filter(Boolean);
    const cats = {};
    for (const t of KS.library.templates) {
      const hay = (t.name + ' ' + t.category + ' ' + t.description + ' ' + t.id).toLowerCase();
      if (q.length && !q.every(w => hay.includes(w))) continue;
      (cats[t.category] = cats[t.category] || []).push(t);
    }
    const order = Object.keys(cats).sort((a, b) => (a === 'Universal' ? -2 : a === 'My Nodes' ? -1 : 0) - (b === 'Universal' ? -2 : b === 'My Nodes' ? -1 : 0));
    list.innerHTML = order.map(c => {
      const open = q.length || !collapsed.has(c), col = KS.library.categories[c] || '#888';
      return `<div class="kn-cat" data-c="${esc(c)}"><span>${open ? '▾' : '▸'}</span><i style="background:${col}"></i>${esc(c)}<span class="n">${cats[c].length}</span></div>` +
        (open ? cats[c].map(t => `<div class="kn-it" draggable="true" data-t="${esc(t.id)}" title="${esc(t.description)}">${esc(t.name)}
          ${t.stateful ? '<span class="tag">⟳</span>' : ''}${t.user ? '<span class="act"><b data-edit="1" title="edit type">✎</b><b data-del="1" title="delete type">🗑</b></span>' : ''}</div>`).join('') : '');
    }).join('') || '<div style="padding:10px;color:#777;font-size:11px">No matches</div>';
    list.onclick = async e => {
      const cat = e.target.closest('.kn-cat');
      if (cat) { const c = cat.dataset.c; collapsed.has(c) ? collapsed.delete(c) : collapsed.add(c); localStorage.setItem('knode.collapsed', JSON.stringify([...collapsed])); return renderSide(); }
      const it = e.target.closest('.kn-it'); if (!it) return;
      const t = KS.byId[it.dataset.t];
      if (e.target.dataset.edit) return UI.designer(clone(t));
      if (e.target.dataset.del) {
        if (!confirm(`Delete your node type “${t.name}”? Existing nodes keep working.`)) return;
        await fetch(BACKEND_URL + '/library/user/' + encodeURIComponent(t.id), { method: 'DELETE' });
        await KS.loadLibrary(); return renderSide();
      }
      KS.addTemplateAt(t.id, null);
    };
    list.querySelectorAll('.kn-it').forEach(el => el.addEventListener('dragstart', e => { e.dataTransfer.setData('knode/template', el.dataset.t); e.dataTransfer.effectAllowed = 'copy'; }));
  }

  // =================================================================== minimap
  function buildMinimap() {
    const c = document.createElement('canvas');
    c.id = 'knMini'; $('#canvasContainer').appendChild(c);
    let drag = false;
    const go = e => {
      const m = UI._mm; if (!m) return;
      const r = c.getBoundingClientRect(), wx = m.x0 + (e.clientX - r.left - m.ox) / m.s, wy = m.y0 + (e.clientY - r.top - m.oy) / m.s;
      const cr = renderer.canvas.getBoundingClientRect(), v = renderer.viewport;
      v.panX = cr.width / 2 - wx * v.zoom; v.panY = cr.height / 2 - wy * v.zoom; renderer.render();
    };
    c.addEventListener('mousedown', e => { drag = true; go(e); e.stopPropagation(); });
    document.addEventListener('mousemove', e => { if (drag) go(e); });
    document.addEventListener('mouseup', () => { drag = false; });
    // 0.7: redraw after the canvas renders (throttled to ≤ 8 per second, with a trailing update so the
    // final state is always shown) instead of polling on a 150 ms timer forever.
    let last = 0, trailing = null;
    const schedule = () => {
      const now = performance.now();
      if (now - last > 120) { last = now; drawMinimap(); }
      else if (!trailing) trailing = setTimeout(() => { trailing = null; last = performance.now(); drawMinimap(); }, 130);
    };
    const renderNow = renderer.renderNow;
    renderer.renderNow = function () { renderNow.apply(this, arguments); schedule(); };
  }
  /** Draw the minimap (nodes, wires, visible rectangle) — skipped when nothing visible changed. */
  function drawMinimap() {
    const c = $('#knMini'); if (!c || !UI.minimap || !graph) return;
    const nodes = Object.values(graph.nodes);
    // 0.5: skip the redraw unless nodes, wires, selection or the view changed (was: every 150 ms)
    const v0 = renderer.viewport;
    let sig = nodes.length * 7 + Object.keys(graph.wires).length * 13 + graph.selectedNodes.length * 17 + v0.zoom * 1e3 + v0.panX * 3 + v0.panY * 5;
    for (const n of nodes) sig += n.x * 0.37 + n.y * 0.61 + n.id;
    if (sig === UI._mmSig && c.width) return;
    UI._mmSig = sig;
    const dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    if (!nodes.length) { UI._mm = null; return; }
    const cr = renderer.canvas.getBoundingClientRect(), v = renderer.viewport;
    const vx0 = -v.panX / v.zoom, vy0 = -v.panY / v.zoom, vx1 = vx0 + cr.width / v.zoom, vy1 = vy0 + cr.height / v.zoom;
    let x0 = Math.min(vx0, ...nodes.map(n => n.x)), y0 = Math.min(vy0, ...nodes.map(n => n.y));
    let x1 = Math.max(vx1, ...nodes.map(n => n.x + n.width)), y1 = Math.max(vy1, ...nodes.map(n => n.y + n.height));
    const s = Math.min((W - 10) / (x1 - x0), (H - 10) / (y1 - y0)), ox = (W - (x1 - x0) * s) / 2, oy = (H - (y1 - y0) * s) / 2;
    UI._mm = { x0, y0, s, ox, oy };
    g.strokeStyle = '#3a3d4a'; g.lineWidth = 1;
    for (const w of Object.values(graph.wires)) {
      const a = graph.nodes[w.from], b = graph.nodes[w.to]; if (!a || !b) continue;
      g.beginPath(); g.moveTo(ox + (a.x + a.width - x0) * s, oy + (a.y + a.height / 2 - y0) * s); g.lineTo(ox + (b.x - x0) * s, oy + (b.y + b.height / 2 - y0) * s); g.stroke();
    }
    for (const n of nodes) {
      g.fillStyle = graph.selectedNodes.includes(n.id) ? '#fff' : n.lineColor;
      g.globalAlpha = .85; g.fillRect(ox + (n.x - x0) * s, oy + (n.y - y0) * s, Math.max(2, n.width * s), Math.max(2, n.height * s)); g.globalAlpha = 1;
    }
    g.strokeStyle = '#7c8cff'; g.strokeRect(ox + (vx0 - x0) * s, oy + (vy0 - y0) * s, (vx1 - vx0) * s, (vy1 - vy0) * s);
  }

  // =================================================================== find
  function openFind() {
    const f = $('#knFind'); f.classList.add('on');
    const inp = $('input', f); inp.value = ''; inp.focus(); renderFind();
  }
  /** Update the Find (Ctrl+F) result list for the current query. */
  function renderFind() {
    const f = $('#knFind'), q = $('input', f).value.toLowerCase();
    const hits = Object.values(graph.nodes).filter(n => (n.name + ' ' + ((n.properties || {}).template || '')).toLowerCase().includes(q)).slice(0, 12);
    UI._hits = hits; UI._hs = Math.min(UI._hs || 0, Math.max(0, hits.length - 1));
    $('.res', f).innerHTML = hits.map((n, i) => `<div class="r ${i === UI._hs ? 'sel' : ''}" data-i="${i}">${esc(n.name)} <span style="color:#777">#${n.id}</span></div>`).join('') || '<div class="r" style="color:#777">no match</div>';
  }
  /** Select and frame the chosen search hit. */
  function pickFind(i) {
    const n = UI._hits[i]; $('#knFind').classList.remove('on'); if (!n) return;
    graph.selectedNodes = [n.id]; graph.selectedWires = []; KS.frame([n.id]); updatePropertiesPanel(n);
  }
  /** Create the Find overlay and its keyboard handling (↑ ↓ Enter Esc). */
  function buildFind() {
    const f = document.createElement('div'); f.id = 'knFind';
    f.innerHTML = '<input placeholder="Find node by name or type…"><div class="res"></div>';
    $('#canvasContainer').appendChild(f);
    const inp = $('input', f);
    inp.oninput = () => { UI._hs = 0; renderFind(); };
    inp.onkeydown = e => {
      if (e.key === 'ArrowDown') { UI._hs = Math.min(UI._hits.length - 1, UI._hs + 1); renderFind(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { UI._hs = Math.max(0, UI._hs - 1); renderFind(); e.preventDefault(); }
      else if (e.key === 'Enter') pickFind(UI._hs);
      else if (e.key === 'Escape') f.classList.remove('on');
    };
    $('.res', f).onclick = e => { const r = e.target.closest('.r'); if (r && r.dataset.i) pickFind(+r.dataset.i); };
  }

  // =================================================================== Node Designer
  UI.fromNode = (n) => fromNode(n);          // used by the context menu (Save as node type)
  /** Node Designer seed from an existing node: its ports, parameters, schema and code. */
  function fromNode(n) {
    const props = n.properties || {}, tpl = KS.byId[props.template];
    return { id: ident(n.name).toLowerCase(), name: n.name, category: tpl ? 'My Nodes' : 'My Nodes', color: n.lineColor,
      description: n.description || (tpl ? tpl.description : ''), inputs: n.inputs.map(p => p.name), outputs: n.outputs.map(p => p.name),
      params: clone(props.params || {}), schema: clone((tpl && tpl.schema) || props.schema || {}), code: n.code,
      stateful: tpl ? tpl.stateful : /\bstate\b/.test(n.code), ports: tpl ? tpl.ports : null };
  }
  /** Generate starter code for a node type from its ports, parameters and stateful flag. */
  function skeleton(t) {
    const ins = t.inputs, ps = Object.keys(t.params || {});
    const args = ins.map(i => `${i}=None`).concat(['params=None', ...(t.stateful ? ['state=None', 't=0.0', 'dt=0.01'] : [])]).join(', ');
    let c = `def process(${args}):\n`;
    for (const i of ins) c += `    ${i} = ks.pick(${i}, ${ps.includes(i) ? `params["${i}"]` : '0.0'})   # unconnected → default\n`;
    for (const p of ps.filter(p => !ins.includes(p))) c += `    ${ident(p)} = params["${p}"]\n`;
    if (t.stateful) c += `    s = state.get("s", 0.0)                 # persists across simulation steps\n    state["s"] = s + dt\n`;
    c += `    return {${t.outputs.map(o => `"${o}": None`).join(', ')}}\n`;
    return c;
  }
  /**
   * Node Designer: define a reusable node type (ports, parameter widgets, code), test it with sample
   * inputs, place an instance, export/import it, save it to the user library and update existing instances.
   */
  UI.designer = function (t) {
    t = Object.assign({ id: 'my_node', name: 'My Node', category: 'My Nodes', color: '#e1b12c', description: '', inputs: ['x'], outputs: ['y'],
      params: { k: 1.0 }, schema: {}, code: '', stateful: false, ports: null }, t || {});
    if (!t.code) t.code = skeleton(t);
    const body = KS.modal('knDesigner', 'Node Designer — define your own node type', 900);
    const kinds = ['number', 'text', 'code', 'select', 'bool', 'json'];
    const prow = (k, v, sc) => `<tr><td><input class="ks-input pk" value="${esc(k)}"></td>
      <td><input class="ks-input pv" value="${esc(typeof v === 'string' ? v : JSON.stringify(v))}"></td>
      <td><select class="pkind">${kinds.map(x => `<option ${x === (sc.kind || (typeof v === 'number' ? 'number' : typeof v === 'boolean' ? 'bool' : typeof v === 'string' ? 'text' : 'json')) ? 'selected' : ''}>${x}</option>`).join('')}</select></td>
      <td><input class="ks-input pmin" value="${sc.min ?? ''}" placeholder="min"></td><td><input class="ks-input pmax" value="${sc.max ?? ''}" placeholder="max"></td>
      <td><input class="ks-input punit" value="${esc(sc.unit || '')}" placeholder="unit"></td>
      <td><input class="ks-input popt" value="${esc((sc.options || []).join(','))}" placeholder="options a,b"></td>
      <td><input class="ks-input pdoc" value="${esc(sc.doc || '')}" placeholder="help text"></td><td><button class="ks-btn px">×</button></td></tr>`;
    body.innerHTML = `
      <div class="kd-grid">
        <div class="kd-f"><label>Name</label><input class="ks-input" id="kdName" value="${esc(t.name)}"></div>
        <div class="kd-f"><label>Type id (file name, a-z 0-9 _ -)</label><input class="ks-input" id="kdId" value="${esc(t.id)}"></div>
        <div class="kd-f"><label>Category</label><input class="ks-input" id="kdCat" value="${esc(t.category)}" list="kdCats"><datalist id="kdCats">${Object.keys((KS.library || {}).categories || {}).map(c => `<option>${esc(c)}</option>`).join('')}</datalist></div>
        <div class="kd-f" style="display:flex;gap:10px;align-items:end"><div style="flex:1"><label>Colour</label><input type="color" id="kdCol" value="${esc(t.color)}" style="height:28px;padding:1px"></div>
          <label style="display:flex;gap:5px;align-items:center;font-size:11px;color:#ccc"><input type="checkbox" id="kdState" ${t.stateful ? 'checked' : ''}> dynamic (has state / evolves in time)</label></div>
        <div class="kd-f" style="grid-column:1/-1"><label>Description (shown in the library and Properties)</label><input class="ks-input" id="kdDesc" value="${esc(t.description)}"></div>
        <div class="kd-f"><label>Input ports (comma-separated)</label><input class="ks-input" id="kdIn" value="${esc(t.inputs.join(', '))}"></div>
        <div class="kd-f"><label>Output ports (comma-separated)</label><input class="ks-input" id="kdOut" value="${esc(t.outputs.join(', '))}"></div>
      </div>
      <div class="kd-f" style="margin-top:10px"><label>Parameters (edited per node in the Properties panel; min+max gives a slider)</label>
        <table class="ks-t kd-p" id="kdParams"><tr><th>name</th><th>default</th><th>widget</th><th></th><th></th><th></th><th></th><th></th><th></th></tr>
        ${Object.entries(t.params).map(([k, v]) => prow(k, v, (t.schema || {})[k] || {})).join('')}</table>
        <button class="ks-btn" id="kdAddP" style="margin-top:4px">+ parameter</button></div>
      <div class="kd-f" style="margin-top:10px"><label style="display:flex;justify-content:space-between">Python code — <span>args: inputs by name · params · state · t · dt · step · ctx &nbsp;·&nbsp; return a dict of outputs &nbsp;·&nbsp; ks, math, np available</span></label>
        <textarea class="ks-input kd-code" id="kdCode" spellcheck="false">${esc(t.code)}</textarea></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center">
        <button class="ks-btn" id="kdSkel" title="Replace the code with a skeleton matching the ports and parameters">Generate skeleton</button>
        <span style="flex:1"></span>
        <label style="font-size:10px;color:#888">test inputs (JSON) <input class="ks-input" id="kdTestIn" value='${esc(JSON.stringify(Object.fromEntries(t.inputs.map(i => [i, 1]))))}' style="width:180px"></label>
        <button class="ks-btn" id="kdTest">▶ Test</button>
        <button class="ks-btn" id="kdExport">Export .json</button>
        <button class="ks-btn" id="kdPlace">Place node</button>
        <button class="ks-btn pri" id="kdSave">Save to library</button>
      </div>
      <div class="kd-msg" id="kdMsg"></div>
      ${t.ports ? '<div class="kd-msg" style="color:#888">This type derives its ports from parameters (universal node). Port lists above are defaults.</div>' : ''}`;
    const ta = $('#kdCode', body);
    ta.addEventListener('keydown', e => { if (e.key === 'Tab') { e.preventDefault(); ta.setRangeText('    ', ta.selectionStart, ta.selectionEnd, 'end'); } });
    $('#kdAddP', body).onclick = () => $('#kdParams', body).insertAdjacentHTML('beforeend', prow('p' + ($('#kdParams', body).rows.length), 0, {}));
    $('#kdParams', body).onclick = e => { if (e.target.classList.contains('px')) e.target.closest('tr').remove(); };
    const names = s => s.split(',').map(x => x.trim()).filter(Boolean);
    const read = () => {
      const params = {}, schema = {};
      for (const tr of [...$('#kdParams', body).rows].slice(1)) {
        const k = $('.pk', tr).value.trim(); if (!k) continue;
        const kind = $('.pkind', tr).value, raw = $('.pv', tr).value;
        let v = raw;
        if (kind === 'number') v = parseFloat(raw) || 0; else if (kind === 'bool') v = /^(1|true|yes)$/i.test(raw); else if (kind === 'json') { try { v = JSON.parse(raw); } catch (e) { v = raw; } }
        params[k] = v;
        const sc = { kind };
        const mn = $('.pmin', tr).value, mx = $('.pmax', tr).value;
        if (mn !== '') sc.min = parseFloat(mn); if (mx !== '') sc.max = parseFloat(mx);
        if ($('.punit', tr).value) sc.unit = $('.punit', tr).value;
        if ($('.popt', tr).value) sc.options = names($('.popt', tr).value);
        if ($('.pdoc', tr).value) sc.doc = $('.pdoc', tr).value;
        schema[k] = sc;
      }
      return { id: $('#kdId', body).value.trim().toLowerCase(), name: $('#kdName', body).value.trim(), category: $('#kdCat', body).value.trim() || 'My Nodes',
        color: $('#kdCol', body).value, description: $('#kdDesc', body).value, inputs: names($('#kdIn', body).value), outputs: names($('#kdOut', body).value),
        params, schema, code: ta.value, stateful: $('#kdState', body).checked, ports: t.ports || null, refs: t.refs || [] };
    };
    const msg = (html, ok) => { const m = $('#kdMsg', body); m.innerHTML = html; m.style.color = ok ? '#2ecc71' : '#e74c3c'; };
    $('#kdSkel', body).onclick = () => { if (!ta.value.trim() || confirm('Replace the current code with a generated skeleton?')) ta.value = skeleton(read()); };
    $('#kdTest', body).onclick = async () => {
      const d = read();
      let inputs; try { inputs = JSON.parse($('#kdTestIn', body).value || '{}'); } catch (e) { return msg('test inputs must be JSON, e.g. {"x": 2}'); }
      const r = await KS.api('/node/designer/execute', { inputs, node: { name: d.name, code: d.code, inputs: d.inputs, outputs: d.outputs, params: d.params } }).catch(e => ({ error: e.message }));
      if (r.success) msg('✓ outputs: ' + esc(JSON.stringify(r.output)) + (r.stdout ? '\nstdout: ' + esc(r.stdout) : ''), true);
      else msg('✗ ' + esc(r.error || 'failed') + (r.line ? ` (line ${r.line})` : '') + (r.traceback ? '\n' + esc(r.traceback) : ''));
    };
    $('#kdExport', body).onclick = () => KS.download(new Blob([JSON.stringify(read(), null, 2)], { type: 'application/json' }), read().id + '.knode-type.json');
    $('#kdPlace', body).onclick = () => {
      const d = read(), n = graph.addNode(d.name, 0, 0, 'standard'), c = KS.viewCenter();
      n.x = Math.round(c.x - 85); n.y = Math.round(c.y - 40);
      n.properties = { params: d.params, schema: d.schema };
      n.inputs = []; n.outputs = []; d.inputs.forEach(p => n.addInput(p, 4)); d.outputs.forEach(p => n.addOutput(p, 16));
      n.code = d.code; n._lastGenCode = null; n.description = d.description; n.setLineColor(d.color); n._updateHeight();
      graph.selectedNodes = [n.id]; renderer.render(); updatePropertiesPanel(n); saveState();
      msg('✓ placed an (unsaved) instance on the canvas', true);
    };
    $('#kdSave', body).onclick = async () => {
      const d = read();
      const res = await fetch(BACKEND_URL + '/library/user', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) })
        .then(r => r.json()).catch(e => ({ error: e.message }));
      if (!res.success) return msg('✗ ' + esc(res.error) + (res.line ? ` (line ${res.line})` : ''));
      await KS.loadLibrary(); renderSide();
      const insts = Object.values(graph.nodes).filter(n => (n.properties || {}).template === d.id);
      let upd = '';
      if (insts.length && confirm(`Update ${insts.length} existing node(s) of type “${d.name}” to the new definition? (parameter values are kept)`)) {
        const tpl = KS.byId[d.id];
        for (const n of insts) {
          n.code = tpl.code; n.description = tpl.description; n.setLineColor(tpl.color);
          n.properties.params = Object.assign(clone(tpl.params), Object.fromEntries(Object.entries(n.properties.params || {}).filter(([k]) => k in tpl.params)));
          const [ins, outs] = KS.derivePorts(tpl, n.properties.params); KS.syncPorts(n, ins, outs);
        }
        renderer.render(); saveState(); upd = ` · updated ${insts.length} node(s)`;
      }
      msg(`✓ saved “${esc(d.name)}” to ${esc(d.category)} (user_library/${esc(d.id)}.json)${upd}`, true);
    };
  };

  // =================================================================== help
  function showKeys() {
    const rows = [['Tab / double-click canvas', 'node library'], ['drag from sidebar', 'place a node'], ['double-click node', 'edit code · open group'],
      ['Ctrl+Enter', 'run once'], ['Ctrl+Shift+Enter', 'simulate'], ['Ctrl+G / Ctrl+Shift+G', 'group / ungroup selection'], ['Esc', 'exit group · close dialogs'],
      ['Ctrl+F', 'find node'], ['Ctrl+D', 'duplicate'], ['Ctrl+A', 'select all'], ['Ctrl+B', 'toggle library sidebar'], ['F', 'frame all / selection'],
      ['P', 'plot panel'], ['M', 'minimap'], ['Ctrl+Z / Ctrl+Shift+Z', 'undo / redo'], ['Ctrl+Shift+N', 'new node type'], ['?', 'this sheet']];
    KS.modal('knKeys', 'Keyboard shortcuts', 460).innerHTML = `<table class="kn-keys">${rows.map(([k, v]) => `<tr><td>${k.split(' / ').map(x => `<kbd>${esc(x)}</kbd>`).join(' / ')}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
  }
  /** Help ▸ Universal nodes guide: which formalism to use for which kind of system. */
  function showGuide() {
    KS.modal('knGuide', 'Modelling with universal nodes', 720).innerHTML = `<div style="line-height:1.55;font-size:12px">
      <p>Every universal node is a <b>formalism</b>: describe the system in its parameters and its ports appear automatically.</p>
      <table class="ks-t" style="margin:8px 0"><tr><th>node</th><th>describe…</th><th>good for</th></tr>
      <tr><td>Formula Block</td><td><code>y = a*x + b</code> lines</td><td>any static relation, unit conversions, cost models</td></tr>
      <tr><td>Dynamic System</td><td><code>dx = …</code> ODEs + inputs + observables</td><td>mechanics, circuits, pharmacokinetics, ecology, neurons</td></tr>
      <tr><td>Difference Equations</td><td><code>x = f(x)</code> updates</td><td>generations, finance, iterated maps, digital filters</td></tr>
      <tr><td>Reaction Network</td><td><code>A + B -> C, k</code></td><td>biochemistry, gene expression, epidemics — ODE or exact stochastic</td></tr>
      <tr><td>State Machine</td><td>states, <code>a -> b : cond</code>, per-state outputs</td><td>controllers, protocols, behaviour modes, cell cycle</td></tr>
      <tr><td>Agent-Based Model</td><td>init / rules / observables per individual</td><td>heterogeneous populations, markets, crowds</td></tr>
      <tr><td>Network Dynamics</td><td>topology + neighbour rules</td><td>contagion, opinions, power grids, neural nets</td></tr>
      <tr><td>2-D Field</td><td><code>du = D*lap(u) + …</code></td><td>diffusion, patterns, waves, heat</td></tr>
      <tr><td>Transfer Function</td><td>num / den in s</td><td>control plants, filters</td></tr>
      <tr><td>Lookup Table</td><td>x, y rows</td><td>empirical curves, calibration data</td></tr>
      <tr><td>State Machine + Dynamic System</td><td>wired in a loop</td><td>hybrid systems (discrete logic + physics)</td></tr>
      <tr><td>Python Script / Node Designer</td><td>code</td><td>anything else — save it as your own reusable type</td></tr></table>
      <p><b>Hierarchy.</b> Select nodes → <kbd>Ctrl+G</kbd> packs them into a <b>group</b> node; wires crossing the boundary become Group Input / Group Output ports. Groups nest, can be duplicated (each copy has its own state) and are entered with a double-click. Build large systems from reusable sub-models.</p>
      <p style="margin-top:6px"><b>Loops.</b> Feedback between nodes is allowed: single runs iterate to a fixed point; simulations break the loop with a one-step delay.</p></div>`;
  }

  // =================================================================== keyboard
  const typing = () => { const a = document.activeElement; return a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable); };
  const modalOpen = () => !!document.querySelector('.ks-modal.active, .modal-overlay.active, .code-editor-modal.active');
  // capture phase: decide about Esc before other handlers close dialogs
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modalOpen() && !typing() && UI.stack.length && !$('#knFind.on') && !document.querySelector('.kn-menu.open')) UI.exitGroup();
    if (e.key === 'Escape') closeMenus();
  }, true);
  document.addEventListener('keydown', e => {
    const ctrl = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
    if (ctrl && e.shiftKey && k === 'n') { e.preventDefault(); UI.designer(); return; }
    if (typing() || modalOpen()) return;
    if (ctrl && !e.shiftKey && k === 'g') { e.preventDefault(); UI.groupSelection(); }
    else if (ctrl && e.shiftKey && k === 'g') { e.preventDefault(); ACTIONS.ungroupSel(); }
    else if (ctrl && k === 'f') { e.preventDefault(); openFind(); }
    else if (ctrl && k === 'd') { e.preventDefault(); ACTIONS.duplicate(); }
    else if (ctrl && k === 'a') { e.preventDefault(); ACTIONS.selectAll(); }
    else if (ctrl && k === 'b') { e.preventDefault(); ACTIONS.toggleSidebar(); }
    else if (ctrl && k === 's') { e.preventDefault(); showExportModal(); }
    else if (ctrl && e.altKey && k === 'n') { e.preventDefault(); ACTIONS.newModel(); }
    else if (!ctrl && k === 'm') ACTIONS.toggleMinimap();
    else if (!ctrl && e.key === '?') showKeys();
  });

  // =================================================================== start
  document.addEventListener('DOMContentLoaded', () => {
    buildHeader(); buildSidebar(); buildMinimap(); buildFind();
    const crumb = document.createElement('div'); crumb.id = 'knCrumb'; $('#canvasContainer').appendChild(crumb);
    const origLoad = KS.loadLibrary;
    /** Reload the library, then refresh the sidebar and menus (wraps the science layer's loader). */
    KS.loadLibrary = async function () { const r = await origLoad.apply(this, arguments); renderSide(); renderMenubar(); return r; };
    KS.loadLibrary().then(() => setTimeout(() => renderer.resize(), 0));
    renderSide();
    setTimeout(() => renderer.resize(), 50);
  });
})();

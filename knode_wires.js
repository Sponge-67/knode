/* knode_wires.js — wires & ports (knode 0.6)
 *
 *  Typed data ........... wires and ports are coloured / shaped by the kind of value they carry
 *                         (number, bool, text, list, 2-D field, table) — Blender-style sockets
 *  Wire styles .......... View ▸ Wire style: smart curves (loop around for feedback), classic bezier,
 *                         straight, orthogonal (circuit-style), step
 *  Flow animation ....... dots travel along wires while the model runs live
 *  Port tooltips ........ hover a port: name, direction, type, current value, wires / capacity,
 *                         what an unconnected input falls back to
 *  Connection helpers ... compatible ports glow while you drag a wire and snap magnetically
 *  Insert on wire ....... drop a node onto a wire to splice it in (Blender / Nuke)
 *  Reroute dots ......... double-click a wire to add a dot you can drag (Blender / Unreal / Nuke)
 *  Knife ................ hold Y and drag across wires to cut them (Houdini / Blender)
 *  Quick constant ....... Alt+click an unconnected input to feed it a Constant (ComfyUI widgets)
 *
 * Performance notes (0.7): all canvas work happens inside the renderer's frame (drawOverlays); the
 * flow-dot animation requests the next frame only while live mode is playing, so an idle editor runs
 * no animation frames at all. Port lookup (portAt) first rejects nodes by bounding box.
 */
(function () {
  'use strict';
  const KS = window.KnodeSci;
  const WR = window.KnodeWires = {};

  // ====================================================================== data types
  /** Visual identity of each value kind: colour, port shape and a short label. */
  const TYPES = {
    number: { color: '#a0aec8', shape: 'circle', label: 'number' },
    bool: { color: '#e056fd', shape: 'circle', label: 'boolean' },
    text: { color: '#48dbfb', shape: 'pill', label: 'text' },
    list: { color: '#feca57', shape: 'diamond', label: 'list' },
    field: { color: '#ff9f43', shape: 'grid', label: '2-D field' },
    dict: { color: '#a29bfe', shape: 'square', label: 'table / dict' },
    none: { color: '#5d6373', shape: 'ring', label: 'no value' },
  };
  WR.TYPES = TYPES;

  /** Kind of a runtime value (see TYPES). */
  function typeOf(v) {
    if (v === null || v === undefined) return 'none';
    if (typeof v === 'boolean') return 'bool';
    if (typeof v === 'number') return 'number';
    if (typeof v === 'string') return (v === 'Infinity' || v === '-Infinity') ? 'number' : 'text';
    if (Array.isArray(v)) return v.length && Array.isArray(v[0]) ? 'field' : 'list';
    return 'dict';
  }
  WR.typeOf = typeOf;

  const pname = (p) => (p ? p.name : undefined);

  /** Value currently on an output port (from the last run), or undefined if unknown. */
  function outputValue(node, port) {
    const r = KS.results[node.id];
    return r && r.outputs && port.name in r.outputs ? r.outputs[port.name] : undefined;
  }

  /** Wires attached to a port (as wire objects). */
  function portWires(port) {
    return (port.connections || []).map(id => graph.wires[id]).filter(Boolean);
  }

  /**
   * What an input port receives: the value of the connected output(s), or — when unconnected — the
   * parameter of the same name (the value the node falls back to). Returns {value, source}.
   */
  function inputValue(node, port) {
    const ws = portWires(port).filter(w => w.enabled);
    if (ws.length) {
      const vals = ws.map(w => { const src = graph.nodes[w.from]; return src && w.fromPortObj ? outputValue(src, w.fromPortObj) : undefined; });
      return { value: vals.length === 1 ? vals[0] : vals, source: 'wire' };
    }
    const params = (node.properties || {}).params || {};
    if (port.name in params) return { value: params[port.name], source: 'param' };
    return { value: undefined, source: 'none' };
  }

  /** Kind of value flowing through a wire, or null before the model has run. */
  function wireType(w) {
    const src = graph.nodes[w.from];
    if (!src || !w.fromPortObj || w.fromPortObj.isDummy) return null;
    const v = outputValue(src, w.fromPortObj);
    return v === undefined ? null : typeOf(v);
  }
  WR.wireType = wireType;

  // Colour and width of every wire come from Wire.getColor / getWidth — wrap them so an unselected,
  // enabled wire shows its data type (selection, disabled and match highlights keep their colours).
  KS.typedWires = localStorage.getItem('knode.typedWires') !== '0';
  const origColor = Wire.prototype.getColor, origWidth = Wire.prototype.getWidth;
  Wire.prototype.getColor = function (sel) {
    const c = origColor.call(this, sel);
    if (sel || !this.enabled || !KS.typedWires) return c;
    const t = wireType(this);
    return t && t !== 'none' ? TYPES[t].color : c;
  };
  Wire.prototype.getWidth = function (sel) {
    const w = origWidth.call(this, sel);
    if (!KS.typedWires || !this.enabled) return w;
    const t = wireType(this);
    return t === 'list' || t === 'field' || t === 'dict' ? w + 1.2 : w;      // collections read as "thicker" data
  };

  // ====================================================================== wire style (global)
  KS.wireStyle = localStorage.getItem('knode.wireStyle') || 'smart';
  /** Change the global wire routing (smart / classic / linear / orthogonal / step) and remember it. */
  WR.setWireStyle = function (style) {
    KS.wireStyle = style;
    try { localStorage.setItem('knode.wireStyle', style); } catch (e) { /* ignore */ }
    renderer.render();
    KS.status('Wire style: ' + style);
  };
  /** Turn colouring wires by their data type on or off (remembered). */
  WR.setTypedWires = function (on) {
    KS.typedWires = on;
    try { localStorage.setItem('knode.typedWires', on ? '1' : '0'); } catch (e) { /* ignore */ }
    renderer.render();
  };

  // ====================================================================== geometry helpers
  /** Screen-independent hit radius (world units) for ports. */
  const hitR = () => 9 / Math.max(0.3, renderer.viewport.zoom);

  /** The port under a world position (inputs, outputs and dummies of every node), or null. */
  function portAt(w) {
    const r = hitR();
    for (const n of Object.values(graph.nodes)) {
      if (w.x < n.x - r || w.x > n.x + n.width + r || w.y < n.y - r || w.y > n.y + n.height + r) continue;
      for (const p of [...n.inputs, ...n.outputs, ...n.dummyPorts]) {
        if (!p.enabled) continue;
        const pos = n.getPortPosition(p);
        if (pos && Math.hypot(pos.x - w.x, pos.y - w.y) <= r) return { node: n, port: p, pos };
      }
    }
    return null;
  }
  WR.portAt = portAt;

  /** Sampled polyline of a wire (world coordinates), following its curve style. */
  function wirePoints(w, n = 24) {
    const a = graph.nodes[w.from], b = graph.nodes[w.to];
    if (!a || !b || !w.fromPortObj || !w.toPortObj) return null;
    const p = a.getPortPosition(w.fromPortObj), q = b.getPortPosition(w.toPortObj);
    if (!p || !q) return null;
    const pts = [];
    for (let i = 0; i <= n; i++) pts.push(renderer.getCurvePoint(p.x, p.y, q.x, q.y, i / n, w.curveType));
    return pts;
  }
  WR.wirePoints = wirePoints;

  /** True if segments ab and cd intersect (knife test). */
  function segCross(a, b, c, d) {
    const o = (p, q, r) => Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
    return o(a, b, c) !== o(a, b, d) && o(c, d, a) !== o(c, d, b);
  }

  /** Can a wire be started at `from` and end at `to`? (direction, dummies, capacity, not the same node) */
  function compatible(from, to) {
    if (!from || !to || from.node === to.node || !to.enabled) return false;
    if (!!from.isDummy !== !!to.isDummy) return false;
    if (!from.isDummy && from.isInput === to.isInput) return false;
    const target = from.isInput ? from : to;
    return (target.connections || []).length < (target.capacity || 1);
  }

  // ====================================================================== splice helpers
  /**
   * Replace wire `wid` (A → B) by A → node → B, using the node's first input and first output.
   * Used by "drop node on wire", reroute insertion and the wire context menu.
   */
  WR.spliceNode = function (wid, node) {
    const w = graph.wires[wid];
    if (!w || !node.inputs.length || !node.outputs.length) return false;
    const info = { from: w.from, to: w.to, fp: pname(w.fromPortObj) || w.fromPort, tp: pname(w.toPortObj) || w.toPort, enabled: w.enabled };
    graph.removeWire(Number(wid));
    const a = graph.connect(info.from, node.id, info.fp, node.inputs[0].name);
    const b = graph.connect(node.id, info.to, node.outputs[0].name, info.tp);
    renderer.render();
    return !!(a && b);
  };

  /** Insert a reroute dot on a wire at a world position. */
  WR.insertReroute = function (wid, w) {
    const tpl = KS.byId && KS.byId.reroute;
    if (!tpl) return KS.status('Reroute needs the backend library (start the server)');
    const node = KS.createFromTemplate(tpl, w.x - 11, w.y - 11, {}, 'Reroute');
    node.width = node.height = 22;
    WR.spliceNode(wid, node);
    graph.selectedNodes = [node.id]; graph.selectedWires = [];
    renderer.render(); saveState();
    KS.status('Reroute added — drag it to route the wire');
    return node;
  };

  /** Alt+click on an input: create a Constant connected to it (value = the parameter it would fall back to). */
  WR.feedConstant = function (node, port) {
    const tpl = KS.byId && KS.byId.const;
    if (!tpl) return;
    const params = (node.properties || {}).params || {};
    const v = port.name in params && typeof params[port.name] !== 'string' ? params[port.name] : 0;
    const pos = node.getPortPosition(port);
    const c = KS.createFromTemplate(tpl, pos.x - 230, pos.y - 30, { value: v }, port.name);
    graph.connect(c.id, node.id, 'value', port.name);
    graph.selectedNodes = [c.id];
    renderer.render(); updatePropertiesPanel(c); saveState();
    KS.status(`Constant “${port.name}” = ${KS.fmt(v)} feeds ${node.name}.${port.name}`);
  };

  // ====================================================================== reroute drawing
  KS.drawReroute = function (ctx, node, r) {
    node.width = node.height = 22;                       // fixed geometry (ports sit on its edges)
    const cx = node.x + 11, cy = node.y + 11;
    const sel = graph.selectedNodes.includes(node.id);
    const inW = node.inputs[0] && portWires(node.inputs[0])[0];
    const t = inW ? wireType(inW) : null;
    const col = t && t !== 'none' ? TYPES[t].color : '#8a93a8';
    ctx.save();
    ctx.fillStyle = '#1b1c21'; ctx.beginPath(); ctx.arc(cx, cy, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fill();
    ctx.lineWidth = sel ? 2 : 1; ctx.strokeStyle = sel ? '#fff' : 'rgba(255,255,255,.25)';
    ctx.beginPath(); ctx.arc(cx, cy, 8, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
  };

  // ====================================================================== overlays
  const origOverlays = KS.drawOverlays;
  /**
   * Wires & ports overlay: live flow dots, typed port glyphs, compatible-port rings while wiring,
   * the wire a dragged node would be inserted into, the knife line and the hovered port's tooltip.
   */
  KS.drawOverlays = function (ctx, r) {
    origOverlays(ctx, r);
    const z = r.viewport.zoom;
    // --- flow dots while the model runs live (TouchDesigner-style activity)
    const live = window.KnodeStudio && KnodeStudio.live && KnodeStudio.live.on && KnodeStudio.live.playing;
    if (live) {
      const phase = (performance.now() / 900) % 1;
      for (const w of Object.values(graph.wires)) {
        if (!w.enabled || !w.fromPortObj || w.fromPortObj.isDummy) continue;
        const a = graph.nodes[w.from], b = graph.nodes[w.to];
        if (!a || !b) continue;
        const p = a.getPortPosition(w.fromPortObj), q = b.getPortPosition(w.toPortObj);
        if (!p || !q) continue;
        const t = wireType(w);
        ctx.fillStyle = t && t !== 'none' ? TYPES[t].color : '#8fd3ff';
        for (let k = 0; k < 3; k++) {
          const pt = r.getCurvePoint(p.x, p.y, q.x, q.y, (phase + k / 3) % 1, w.curveType);
          ctx.beginPath(); ctx.arc(pt.x, pt.y, 2.2, 0, Math.PI * 2); ctx.fill();
        }
      }
      r.render();          // 0.7: ask for the next frame only while live — no frames at all when idle
    }
    // --- typed port shapes (after a run) — Blender-style sockets
    if (z >= 0.35) {
      for (const n of Object.values(graph.nodes)) {
        if (n.properties && n.properties.template === 'reroute') continue;
        for (const p of n.outputs) {
          if (!p.enabled) continue;
          const v = outputValue(n, p);
          if (v !== undefined) drawShape(ctx, n.getPortPosition(p), typeOf(v));
        }
        for (const p of n.inputs) {
          if (!p.enabled) continue;
          const iv = inputValue(n, p);
          if (iv.source === 'wire' && iv.value !== undefined) drawShape(ctx, n.getPortPosition(p), typeOf(iv.value));
        }
      }
    }
    // --- compatible targets while dragging a wire
    if (r.connectingFrom !== null && r.connectingFrom !== undefined && r.connectingFromPort) {
      const from = r.connectingFromPort;
      for (const n of Object.values(graph.nodes)) {
        for (const p of [...n.inputs, ...n.outputs, ...n.dummyPorts]) {
          if (!compatible(from, p)) continue;
          const pos = n.getPortPosition(p); if (!pos) continue;
          const hot = r.connectingToPort === p;
          ctx.save(); ctx.strokeStyle = hot ? '#2ecc71' : 'rgba(46,204,113,.55)'; ctx.lineWidth = hot ? 2.5 : 1.5;
          ctx.beginPath(); ctx.arc(pos.x, pos.y, hot ? 8 : 6.5, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
        }
      }
    }
    // --- wire that a dragged node would be inserted into
    if (WR.insertTarget) {
      const pts = wirePoints(graph.wires[WR.insertTarget] || {}, 30);
      if (pts) {
        ctx.save(); ctx.strokeStyle = 'rgba(124,140,255,.55)'; ctx.lineWidth = 7; ctx.lineCap = 'round';
        ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.stroke(); ctx.restore();
      }
    }
    // --- knife
    if (WR.knife) {
      const k = WR.knife;
      ctx.save(); ctx.strokeStyle = '#ff6b6b'; ctx.setLineDash([6 / z, 4 / z]); ctx.lineWidth = 1.5 / z;
      ctx.beginPath(); ctx.moveTo(k.a.x, k.a.y); ctx.lineTo(k.b.x, k.b.y); ctx.stroke(); ctx.restore();
    }
    // --- port tooltip (drawn at constant screen size)
    const hp = WR.hoverPort;
    if (hp && graph.nodes[hp.node.id] && r.connectingFrom === null && !r.isDraggingNode) drawTooltip(ctx, hp, z);
  };

  /** Small type glyph drawn on a port: circle, diamond, square, pill, grid or ring. */
  function drawShape(ctx, pos, t) {
    if (!pos) return;
    const T = TYPES[t]; if (!T) return;
    const s = 3.6;
    ctx.save(); ctx.fillStyle = T.color; ctx.strokeStyle = '#111'; ctx.lineWidth = 0.8;
    ctx.beginPath();
    switch (T.shape) {
      case 'diamond': ctx.moveTo(pos.x, pos.y - s - 0.8); ctx.lineTo(pos.x + s + 0.8, pos.y); ctx.lineTo(pos.x, pos.y + s + 0.8); ctx.lineTo(pos.x - s - 0.8, pos.y); ctx.closePath(); break;
      case 'square': ctx.rect(pos.x - s, pos.y - s, 2 * s, 2 * s); break;
      case 'grid': ctx.rect(pos.x - s, pos.y - s, 2 * s, 2 * s); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(pos.x, pos.y - s); ctx.lineTo(pos.x, pos.y + s); ctx.moveTo(pos.x - s, pos.y); ctx.lineTo(pos.x + s, pos.y); ctx.stroke(); ctx.restore(); return;
      case 'pill': r2(ctx, pos.x - s - 1.5, pos.y - s + 0.8, 2 * s + 3, 2 * s - 1.6, s - 0.8); break;
      case 'ring': ctx.arc(pos.x, pos.y, s, 0, Math.PI * 2); ctx.stroke(); ctx.restore(); return;
      default: ctx.arc(pos.x, pos.y, s, 0, Math.PI * 2);
    }
    ctx.fill(); ctx.stroke(); ctx.restore();
  }
  /** Rounded-rectangle path helper for the pill-shaped text port glyph. */
  function r2(ctx, x, y, w, h, rad) { ctx.moveTo(x + rad, y); ctx.arcTo(x + w, y, x + w, y + h, rad); ctx.arcTo(x + w, y + h, x, y + h, rad); ctx.arcTo(x, y + h, x, y, rad); ctx.arcTo(x, y, x + w, y, rad); ctx.closePath(); }

  /** Tooltip for the hovered port: identity, type, value, wiring and fallback. */
  function drawTooltip(ctx, hp, z) {
    const { node, port } = hp, pos = node.getPortPosition(port); if (!pos) return;
    const lines = [];
    const dir = port.isDummy ? 'relation port' : port.isInput ? 'input' : 'output';
    lines.push([`${port.name}`, '#fff', true]);
    let v, src = null;
    if (port.isDummy) v = undefined;
    else if (port.isInput) { const iv = inputValue(node, port); v = iv.value; src = iv.source; }
    else v = outputValue(node, port);
    const t = v === undefined ? null : typeOf(v);
    lines.push([`${dir}${t ? ' · ' + TYPES[t].label : ''}`, t ? TYPES[t].color : '#8a93a8']);
    if (v !== undefined) lines.push([`${src === 'param' ? 'unconnected → uses parameter = ' : '= '}${KS.fmt(v, 6)}`, '#dfe3ff']);
    else if (!port.isDummy) lines.push([port.isInput ? 'unconnected (None / default)' : 'run the model to see the value', '#8a93a8']);
    const ws = portWires(port);
    lines.push([`wires ${ws.length}/${port.capacity}${port.isAlien ? ' · alien' : ''}`, '#8a93a8']);
    for (const w of ws.slice(0, 4)) {
      const other = port.isInput ? graph.nodes[w.from] : graph.nodes[w.to];
      const op = port.isInput ? pname(w.fromPortObj) : pname(w.toPortObj);
      if (other) lines.push([`${port.isInput ? '← ' : '→ '}${other.name}.${op}${w.enabled ? '' : ' (disabled)'}`, '#aab0c0']);
    }
    if (!port.isDummy && port.isInput && !ws.length) lines.push(['Alt+click: feed a Constant', '#6c7488']);
    const fs = 10 / z, pad = 6 / z, lh = 13 / z;
    ctx.save(); ctx.font = `${fs}px ui-monospace, Menlo, monospace`;
    const w = Math.max(...lines.map(l => ctx.measureText(l[0]).width)) + 2 * pad, h = lines.length * lh + 2 * pad;
    let x = port.isInput ? pos.x - w - 12 / z : pos.x + 12 / z, y = pos.y - h / 2;
    ctx.fillStyle = 'rgba(16,17,21,.96)'; ctx.strokeStyle = t ? TYPES[t].color : '#3a3f55'; ctx.lineWidth = 1 / z;
    renderer.roundRect(ctx, x, y, w, h, 5 / z); ctx.fill(); ctx.stroke();
    ctx.textBaseline = 'top'; ctx.textAlign = 'left';
    lines.forEach(([txt, col, bold], i) => { ctx.fillStyle = col; ctx.font = `${bold ? '600 ' : ''}${fs}px ui-monospace, Menlo, monospace`; ctx.fillText(txt, x + pad, y + pad + i * lh); });
    ctx.restore();
  }

  // ====================================================================== interaction
  let knifeKey = false;
  /**
   * Install the canvas interaction handlers: knife, Alt+click constants, magnetic snapping,
   * insert-on-wire, port hover, reroute on double-click, and the Y key for the knife.
   */
  function bind() {
    const cv = renderer.canvas;
    const world = (e) => KS.worldAtScreen(e.clientX, e.clientY);

    cv.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      const w = world(e);
      if (knifeKey) {                                   // Y + drag: knife
        e.stopImmediatePropagation(); e.preventDefault();
        WR.knife = { a: w, b: w }; renderer.render(); return;
      }
      if (e.altKey) {                                   // Alt+click an unconnected input → Constant
        const hit = portAt(w);
        if (hit && hit.port.isInput && !hit.port.isDummy && !hit.port.connections.length) {
          e.stopImmediatePropagation(); e.preventDefault();
          WR.feedConstant(hit.node, hit.port);
        }
      }
    }, true);

    cv.addEventListener('mousemove', e => {
      const w = world(e), r = renderer;
      if (WR.knife) { WR.knife.b = w; r.render(); return; }
      // magnetic snapping: while dragging a wire, snap to the nearest compatible port within reach
      if (r.connectingFrom !== null && r.connectingFrom !== undefined && r.connectingFromPort && !r.connectingToPort) {
        let best = null, bd = 26 / Math.max(0.3, r.viewport.zoom);
        for (const n of Object.values(graph.nodes)) for (const p of [...n.inputs, ...n.outputs, ...n.dummyPorts]) {
          if (!compatible(r.connectingFromPort, p)) continue;
          const pos = n.getPortPosition(p); if (!pos) continue;
          const d = Math.hypot(pos.x - w.x, pos.y - w.y);
          if (d < bd) { bd = d; best = { p, pos }; }
        }
        if (best) { r.connectingToPort = best.p; r.tempEndX = best.pos.x; r.tempEndY = best.pos.y; r.render(); }
      }
      // node dragged over a wire → candidate for insertion
      const prev = WR.insertTarget;
      WR.insertTarget = null;
      if (r.isDraggingNode && r.dragging && graph.selectedNodes.length <= 1) {
        const n = r.dragging;
        const free = n.inputs.length && n.outputs.length && ![...n.inputs, ...n.outputs].some(p => p.connections.length);
        if (free) {
          const wid = r.getWireAt({ x: n.x + n.width / 2, y: n.y + n.height / 2 });
          if (wid !== null && wid !== undefined) WR.insertTarget = wid;
        }
      }
      // port hover (tooltips)
      const hp = !r.isDraggingNode && !r.isPanning ? portAt(w) : null;
      const changed = (hp && hp.port) !== (WR.hoverPort && WR.hoverPort.port);
      WR.hoverPort = hp;
      if (changed || prev !== WR.insertTarget) r.render();
    });

    cv.addEventListener('mouseup', e => {
      const r = renderer;
      if (WR.knife) {                                   // cut every wire the knife line crosses
        const k = WR.knife; WR.knife = null;
        const cut = [];
        for (const [id, w] of Object.entries(graph.wires)) {
          const pts = wirePoints(w, 30); if (!pts) continue;
          for (let i = 1; i < pts.length; i++) if (segCross(k.a, k.b, pts[i - 1], pts[i])) { cut.push(Number(id)); break; }
        }
        cut.forEach(id => graph.removeWire(id));
        r.render();
        if (cut.length) { saveState(); KS.status(`✂ cut ${cut.length} wire${cut.length > 1 ? 's' : ''}`); }
        e.stopImmediatePropagation(); return;
      }
      if (WR.insertTarget && r.isDraggingNode && r.dragging) {       // drop onto a wire → splice
        const node = r.dragging, wid = WR.insertTarget;
        WR.insertTarget = null;
        if (WR.spliceNode(wid, node)) { saveState(); KS.status(`Inserted ${node.name} into the wire`); }
      }
    }, true);

    cv.addEventListener('mouseleave', () => { if (WR.hoverPort) { WR.hoverPort = null; renderer.render(); } });

    cv.addEventListener('dblclick', e => {                          // double-click a wire → reroute dot
      const w = world(e);
      if (KS.nodeAt(w)) return;
      const wid = renderer.getWireAt(w);
      if (wid !== null && wid !== undefined) { e.stopImmediatePropagation(); WR.insertReroute(wid, w); }
    }, true);

    const typing = () => { const a = document.activeElement; return a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable); };
    document.addEventListener('keydown', e => {
      if ((e.key === 'y' || e.key === 'Y') && !e.ctrlKey && !e.metaKey && !typing()) { knifeKey = true; renderer.canvas.style.cursor = 'crosshair'; }
    });
    document.addEventListener('keyup', e => {
      if (e.key === 'y' || e.key === 'Y') { knifeKey = false; renderer.canvas.style.cursor = 'default'; if (WR.knife) { WR.knife = null; renderer.render(); } }
    });
  }

  // ====================================================================== menu entries
  const UI = window.KnodeUI;
  const prevExtend = UI.extendMenus;
  /** Add this layer's entries to the menubar definition (each layer wraps the previous one's extension). */
  UI.extendMenus = function (m) {
    m = prevExtend ? prevExtend(m) : m;
    const view = m.find(x => x[0] === 'View');
    if (view) view[1].push('-', ['Wire style', null, null, [
      ['Smart curves (default)', () => WR.setWireStyle('smart'), null, null, () => KS.wireStyle === 'smart'],
      ['Classic bezier', () => WR.setWireStyle('classic'), null, null, () => KS.wireStyle === 'classic'],
      ['Straight', () => WR.setWireStyle('linear'), null, null, () => KS.wireStyle === 'linear'],
      ['Orthogonal (circuit)', () => WR.setWireStyle('orthogonal'), null, null, () => KS.wireStyle === 'orthogonal'],
      ['Step', () => WR.setWireStyle('step'), null, null, () => KS.wireStyle === 'step']]],
      ['Colour wires by data type', () => WR.setTypedWires(!KS.typedWires), null, null, () => KS.typedWires]);
    return m;
  };

  document.addEventListener('DOMContentLoaded', () => { bind(); if (UI.renderMenubar) UI.renderMenubar(); });
})();

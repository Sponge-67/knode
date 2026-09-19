/* knode_studio.js — features adopted from other node systems (knode 0.4)
 *
 *  Live mode ............ TouchDesigner / Max-MSP / Pure Data: the model runs while you patch it
 *                         (0.7: pipelined requests + adaptive chunk size — see tick / requestChunk)
 *  Dashboard ............ LabVIEW front panel / Max presentation mode: sliders, toggles, readouts, gauges
 *  Node flags ........... Houdini bypass & lock, n8n pinned data, Blueprint breakpoints, ComfyUI cache
 *  Frames ............... Blender frames / Nuke backdrops / Unreal comment boxes
 *  Link-drag search ..... Blender / Unreal / ComfyUI: drop a wire on empty canvas → add & connect
 *  Wire probes .......... LabVIEW probes: hover a wire to read the value it carries
 *  Wireless links ....... Node-RED link nodes (Send / Receive), drawn as ghost links
 *  Scenarios & kept runs  Houdini takes / Nuke A-B: parameter variants overlaid in the plot
 *  Calibrate / optimise . Grasshopper Galapagos / Simulink Design Optimization / COPASI
 *  PNG with model ....... ComfyUI: images carry their graph; drop a PNG/JSON to open it
 *  Node previews ........ Substance / TouchDesigner: field thumbnails inside nodes
 */
(function () {
  'use strict';
  const KS = window.KnodeSci, UI = window.KnodeUI;
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => escapeHtml(s === undefined || s === null ? '' : s);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const SD = window.KnodeStudio = {};

  KS.frames = [];
  KS.model = { dashboard: [], scenarios: [] };
  KS.kept = [];
  /** Per-level metadata stored in every undo snapshot (currently the frames of this level). */
  KS.getLevelMeta = () => ({ frames: clone(KS.frames) });
  /** Restore per-level metadata from a snapshot (called by restoreSnapshot on undo / group change). */
  KS.setLevelMeta = (m) => { KS.frames = (m && m.frames) ? clone(m.frames) : []; KS.selFrame = null; };
  /** Model-wide metadata written into exports: dashboard widgets and scenarios. */
  KS.getModelMeta = () => clone(KS.model);
  /** Load model-wide metadata from an imported file and refresh the dashboard. */
  KS.setModelMeta = (m) => { KS.model = Object.assign({ dashboard: [], scenarios: [] }, m || {}); if (SD.renderDash) SD.renderDash(); };

  const css = `
  #knLive{display:flex;align-items:center;gap:3px;border:1px solid var(--line2);border-radius:7px;padding:1px 3px}
  #knLive.on{border-color:#e74c3c;box-shadow:0 0 0 1px #e74c3c55}
  #knLive button{background:none;border:none;color:var(--txt);cursor:pointer;font-size:12px;padding:2px 5px;border-radius:4px}
  #knLive button:hover{background:var(--panel2)}
  #knLive .rec{color:#e74c3c;font-weight:700;font-size:10px;letter-spacing:.05em}
  #knLive select{background:var(--bg);border:1px solid var(--line2);color:var(--txt);font-size:10px;border-radius:4px}
  #knLive .clock{font:10px ui-monospace,monospace;color:var(--mute);min-width:74px}
  #knDash{position:absolute;left:14px;top:14px;width:430px;height:300px;min-width:260px;min-height:160px;resize:both;overflow:hidden;background:rgba(22,23,28,.97);
    border:1px solid var(--line2);border-radius:8px;display:none;flex-direction:column;z-index:55;box-shadow:0 8px 28px #000a}
  #knDash.active{display:flex}
  #knDash.present{position:fixed;left:40px!important;top:60px!important;right:40px;bottom:40px;width:auto!important;height:auto!important;resize:none;z-index:2500}
  #knDash .dh{display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--line);cursor:move;font-size:11px;color:#ddd}
  #knDash .dh button{background:var(--panel2);border:1px solid var(--line2);color:var(--txt);font-size:10px;border-radius:4px;padding:1px 6px;cursor:pointer}
  #knDash .db{flex:1;overflow:auto;padding:8px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;align-content:start}
  #knDash.present .db{grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;padding:16px}
  .dw{background:var(--panel2);border:1px solid var(--line);border-radius:7px;padding:7px 9px;position:relative;min-height:62px}
  .dw .dt{font-size:10px;color:var(--mute);display:flex;justify-content:space-between;gap:6px}
  .dw .dt span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .dw .dx{opacity:0;cursor:pointer;color:var(--mute)}.dw:hover .dx{opacity:1}
  .dw .dv{font:600 20px ui-monospace,Menlo,monospace;color:#eef;margin-top:4px}
  #knDash.present .dw .dv{font-size:30px}
  .dw input[type=range]{width:100%;accent-color:#7c8cff;margin-top:8px}
  .dw canvas{width:100%;height:46px;display:block;margin-top:4px}
  .dw .tg{margin-top:8px;display:flex;gap:8px;align-items:center;font-size:12px}
  .ks-pin{background:none;border:none;color:#6c7488;cursor:pointer;font-size:10px;padding:0 2px}.ks-pin:hover{color:#ffd479}
  .ks-fx{background:none;border:none;color:#6c7488;cursor:pointer;font:italic 11px Georgia,serif;padding:0 2px}.ks-fx:hover{color:#ffd479}
  .ks-flags{display:flex;gap:4px;flex-wrap:wrap;margin:4px 0 6px}
  .ks-flag{font-size:10px;padding:2px 7px;border-radius:10px;border:1px solid var(--line2);background:none;color:var(--txt);cursor:pointer}
  .ks-flag.on{background:#2b3163;border-color:var(--acc);color:#fff}
  .ks-flag.byp.on{background:#5a4a1a;border-color:#d4a72c}.ks-flag.frz.on{background:#1a4a5a;border-color:#48c9e0}
  .ks-outpins{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
  .ks-outpins button{font-size:9px;background:var(--bg);border:1px solid var(--line2);color:var(--mute);border-radius:4px;padding:1px 5px;cursor:pointer}
  .ks-outpins button:hover{color:#ffd479;border-color:#6b5a2a}
  .sc-row{display:flex;gap:6px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}
  .sc-row b{flex:1;font-weight:500}
  `;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  const rootLevel = () => !UI.stack.length;

  // ====================================================================== overlays: probes, wireless, flags, thumbnails
  const origOverlays = KS.drawOverlays;
  const thumbCache = new WeakMap();
  /** Heat-map thumbnail canvas for a 2-D field, cached per array (WeakMap) so it is built once per result. */
  function fieldThumb(F) {
    let c = thumbCache.get(F);
    if (c) return c;
    const ny = F.length, nx = F[0].length;
    let lo = Infinity, hi = -Infinity;
    for (const r of F) for (const v of r) if (v !== null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    if (hi === lo) hi = lo + 1;
    c = document.createElement('canvas'); c.width = nx; c.height = ny;
    const g = c.getContext('2d'), img = g.createImageData(nx, ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const m = KS.heatColor((F[j][i] - lo) / (hi - lo)).match(/\d+/g), k = 4 * (j * nx + i);
      img.data[k] = +m[0]; img.data[k + 1] = +m[1]; img.data[k + 2] = +m[2]; img.data[k + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    thumbCache.set(F, c);
    return c;
  }
  /**
   * Studio overlays on top of the science overlays: wireless Send→Receive ghost links, bypass / freeze /
   * breakpoint badges, field thumbnails, cache markers and the wire probe for the hovered wire.
   */
  KS.drawOverlays = function (ctx, r) {
    // wireless (Send → Receive) ghost links
    const sends = {}, recvs = [];
    for (const n of Object.values(graph.nodes)) {
      const t = (n.properties || {}).template, ch = ((n.properties || {}).params || {}).channel;
      if (t === 'send') (sends[ch] = sends[ch] || []).push(n); else if (t === 'receive') recvs.push([n, ch]);
    }
    ctx.save(); ctx.setLineDash([2, 5]); ctx.lineWidth = 1.2;
    for (const [rn, ch] of recvs) for (const sn of sends[ch] || []) {
      const sel = graph.selectedNodes.includes(sn.id) || graph.selectedNodes.includes(rn.id);
      ctx.strokeStyle = sel ? '#48c9e0' : 'rgba(72,201,224,.28)';
      const a = { x: sn.x + sn.width, y: sn.y + sn.height / 2 }, b = { x: rn.x, y: rn.y + rn.height / 2 };
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.bezierCurveTo(a.x + 80, a.y, b.x - 80, b.y, b.x, b.y); ctx.stroke();
      if (sel) { ctx.fillStyle = '#48c9e0'; ctx.font = '8px sans-serif'; ctx.fillText('📡 ' + ch, (a.x + b.x) / 2, (a.y + b.y) / 2 - 4); }
    }
    ctx.restore();
    origOverlays(ctx, r);
    for (const n of Object.values(graph.nodes)) {
      const p = n.properties || {};
      const { x, y, width: w, height: h } = n;
      if (p.template === 'reroute') continue;
      if (p.bypass) {
        ctx.save(); ctx.fillStyle = 'rgba(19,20,24,.55)'; r.roundRect(ctx, x, y, w, h, 6); ctx.fill();
        ctx.strokeStyle = '#d4a72c'; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; r.roundRect(ctx, x - 2, y - 2, w + 4, h + 4, 7); ctx.stroke();
        ctx.fillStyle = '#d4a72c'; ctx.font = 'bold 9px sans-serif'; ctx.textAlign = 'center'; ctx.fillText('BYPASSED', x + w / 2, y + h / 2 + 3); ctx.restore();
      }
      if (p.frozen) {
        ctx.save(); ctx.strokeStyle = '#48c9e0'; ctx.lineWidth = 1.5; r.roundRect(ctx, x - 2, y - 2, w + 4, h + 4, 7); ctx.stroke();
        ctx.fillStyle = '#48c9e0'; ctx.font = '10px sans-serif'; ctx.textAlign = 'right'; ctx.fillText('❄ frozen', x + w - 4, y - 4); ctx.restore();
      }
      if (p.break_if) {
        ctx.save(); ctx.fillStyle = '#e74c3c'; ctx.beginPath(); ctx.arc(x + 2, y + 2, 4.5, 0, 7); ctx.fill();
        ctx.font = '7px sans-serif'; ctx.textAlign = 'left'; ctx.fillText(p.break_if, x + 9, y - 3); ctx.restore();
      }
      const res = KS.results[n.id];
      if (res && res.outputs) {
        const F = Object.values(res.outputs).find(v => Array.isArray(v) && v.length > 1 && Array.isArray(v[0]));
        if (F) { ctx.imageSmoothingEnabled = false; ctx.drawImage(fieldThumb(F), x + w + 8, y, 56, 56); ctx.strokeStyle = '#444'; ctx.strokeRect(x + w + 8, y, 56, 56); }
      }
      if (res && res.cached) { ctx.fillStyle = '#6c7488'; ctx.font = '7px sans-serif'; ctx.textAlign = 'right'; ctx.fillText('⟲ cached', x + w, y + h + 3 + 8 * 3); ctx.textAlign = 'left'; }
    }
    // wire probe (LabVIEW): value on the hovered wire
    const wid = r._hoveredWire, wire = wid !== null && wid !== undefined ? graph.wires[wid] : null;
    if (wire) {
      const src = KS.results[wire.from];
      const port = wire.fromPortObj ? wire.fromPortObj.name : wire.fromPort;
      const a = graph.nodes[wire.from], b = graph.nodes[wire.to];
      if (a && b && wire.fromPortObj && wire.toPortObj) {
        const pa = a.getPortPosition(wire.fromPortObj), pb = b.getPortPosition(wire.toPortObj);
        const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;
        const val = src && src.outputs && port in src.outputs ? KS.fmt(src.outputs[port], 5) : 'no value yet — run the model';
        const txt = `${port} = ${val}`;
        ctx.save(); ctx.font = '9px ui-monospace, Menlo, monospace';
        const tw = ctx.measureText(txt).width + 12;
        ctx.fillStyle = 'rgba(15,16,20,.95)'; ctx.strokeStyle = '#7c8cff'; ctx.lineWidth = 1;
        r.roundRect(ctx, mx - tw / 2, my - 22, tw, 16, 4); ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#e6e8ff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(txt, mx, my - 14);
        ctx.restore();
      }
    }
  };
  const origApply = KS.applyResults;
  /** After the science layer applies results, mark cached nodes and refresh dashboard readouts. */
  KS.applyResults = function (rep, sim) {
    origApply(rep, sim);
    for (const id of rep.cached || []) if (KS.results[id]) KS.results[id].cached = true;
    if (SD.updateDash) SD.updateDash();
  };

  // ====================================================================== frames (backdrops)
  const FRAME_COLORS = ['#7c8cff', '#1dd1a1', '#feca57', '#ff6b6b', '#48c9e0', '#ff9ff3', '#9aa4b8'];
  const TITLE = 22;
  /** Draw frames (backdrops) under wires and nodes: tinted body, title bar, colour dot, resize corner. */
  KS.drawUnderlays = function (ctx, r) {
    for (const f of KS.frames) {
      const sel = KS.selFrame === f.id;
      ctx.save();
      ctx.globalAlpha = 0.08; ctx.fillStyle = f.color; r.roundRect(ctx, f.x, f.y, f.w, f.h, 10); ctx.fill();
      ctx.globalAlpha = 0.22; r.roundRect(ctx, f.x, f.y, f.w, TITLE, 10); ctx.fill();
      ctx.globalAlpha = sel ? 0.95 : 0.45; ctx.strokeStyle = f.color; ctx.lineWidth = sel ? 2 : 1; r.roundRect(ctx, f.x, f.y, f.w, f.h, 10); ctx.stroke();
      ctx.globalAlpha = 1; ctx.fillStyle = '#e8eaf2'; ctx.font = '600 11px Inter, "Segoe UI", sans-serif'; ctx.textBaseline = 'middle';
      ctx.fillText(f.title, f.x + 10, f.y + TITLE / 2 + 1);
      ctx.fillStyle = f.color; ctx.beginPath(); ctx.arc(f.x + f.w - 12, f.y + TITLE / 2, 5, 0, 7); ctx.fill();
      ctx.globalAlpha = 0.6; ctx.beginPath(); ctx.moveTo(f.x + f.w - 3, f.y + f.h - 12); ctx.lineTo(f.x + f.w - 3, f.y + f.h - 3); ctx.lineTo(f.x + f.w - 12, f.y + f.h - 3); ctx.stroke();
      ctx.restore();
    }
  };
  /** Which part of which frame is under a world position: 'title' (drag), 'color' (cycle) or 'resize'. */
  function frameHit(w) {
    for (let i = KS.frames.length - 1; i >= 0; i--) {
      const f = KS.frames[i];
      if (w.x >= f.x + f.w - 18 && w.x <= f.x + f.w && w.y >= f.y && w.y <= f.y + TITLE) return { f, part: 'color' };
      if (w.x >= f.x && w.x <= f.x + f.w && w.y >= f.y && w.y <= f.y + TITLE) return { f, part: 'title' };
      if (w.x >= f.x + f.w - 14 && w.x <= f.x + f.w + 2 && w.y >= f.y + f.h - 14 && w.y <= f.y + f.h + 2) return { f, part: 'resize' };
    }
    return null;
  }
  /** Ctrl+J: create a titled frame around the selected nodes (or an empty one at the view centre). */
  SD.frameSelection = function () {
    const ids = graph.selectedNodes.filter(id => graph.nodes[id]);
    let x0, y0, x1, y1;
    if (ids.length) {
      const ns = ids.map(id => graph.nodes[id]);
      x0 = Math.min(...ns.map(n => n.x)) - 24; y0 = Math.min(...ns.map(n => n.y)) - TITLE - 18;
      x1 = Math.max(...ns.map(n => n.x + n.width)) + 24; y1 = Math.max(...ns.map(n => n.y + n.height)) + 64;
    } else { const c = KS.viewCenter(); x0 = c.x - 220; y0 = c.y - 140; x1 = c.x + 220; y1 = c.y + 140; }
    const title = prompt('Frame title', ids.length ? 'Subsystem' : 'Notes');
    if (title === null) return;
    KS.frames.push({ id: Date.now(), x: x0, y: y0, w: x1 - x0, h: y1 - y0, title: title || 'Frame', color: FRAME_COLORS[KS.frames.length % FRAME_COLORS.length] });
    renderer.render(); saveState();
  };
  /**
   * Mouse handling for frames (capture phase, so the canvas does not start a node selection):
   * drag title to move the frame and the nodes inside it, drag the corner to resize, double-click to rename.
   */
  function bindFrames() {
    const cv = renderer.canvas;
    cv.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      const w = KS.worldAtScreen(e.clientX, e.clientY);
      if (KS.nodeAt(w)) return;
      const hit = frameHit(w);
      if (!hit) { if (KS.selFrame) { KS.selFrame = null; renderer.render(); } return; }
      e.stopImmediatePropagation(); e.preventDefault();
      const f = hit.f;
      KS.selFrame = f.id;
      if (hit.part === 'color') { f.color = FRAME_COLORS[(FRAME_COLORS.indexOf(f.color) + 1) % FRAME_COLORS.length]; renderer.render(); saveState(); return; }
      const inside = Object.values(graph.nodes).filter(n => n.x >= f.x && n.y >= f.y && n.x + n.width <= f.x + f.w && n.y + n.height <= f.y + f.h)
        .map(n => ({ n, x: n.x, y: n.y }));
      const start = { x: w.x, y: w.y, fx: f.x, fy: f.y, fw: f.w, fh: f.h };
      const mv = ev => {
        const p = KS.worldAtScreen(ev.clientX, ev.clientY), dx = p.x - start.x, dy = p.y - start.y;
        if (hit.part === 'resize') { f.w = Math.max(120, start.fw + dx); f.h = Math.max(60, start.fh + dy); }
        else { f.x = start.fx + dx; f.y = start.fy + dy; for (const o of inside) { o.n.x = o.x + dx; o.n.y = o.y + dy; } }
        renderer.render();
      };
      const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); saveState(); };
      document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
      renderer.render();
    }, true);
    cv.addEventListener('dblclick', e => {
      const w = KS.worldAtScreen(e.clientX, e.clientY);
      if (KS.nodeAt(w)) return;
      const hit = frameHit(w);
      if (hit && hit.part === 'title') {
        e.stopImmediatePropagation();
        const t = prompt('Frame title', hit.f.title);
        if (t !== null) { hit.f.title = t || 'Frame'; renderer.render(); saveState(); }
      }
    }, true);
  }

  // ====================================================================== link-drag search
  function bindLinkDrag() {
    renderer.canvas.addEventListener('mouseup', e => {
      const r = renderer;
      if (r.connectingFrom === null || r.connectingFrom === undefined || r.connectingToPort || !r.connectingFromPort || r.connectingFromPort.isDummy) return;
      const w = KS.worldAtScreen(e.clientX, e.clientY);
      if (KS.nodeAt(w)) return;
      const fromId = r.connectingFrom, port = r.connectingFromPort, fromOutput = !port.isInput;
      setTimeout(() => KS.openPalette(w, {
        filter: t => { const [ins, outs] = KS.derivePorts(t, t.params); return fromOutput ? ins.length > 0 : outs.length > 0; },
        onPick: node => {
          const ok = fromOutput ? graph.connect(fromId, node.id, port.name, node.inputs[0].name) : graph.connect(node.id, fromId, node.outputs[0].name, port.name);
          if (ok) { renderer.render(); saveState(); KS.status(`Added <b>${esc(node.name)}</b> and connected it to ${esc(port.name)}`); }
        },
      }), 0);
    }, true);
  }

  // ====================================================================== properties: flags, expressions, pins
  const origDecorate = KS.decorateProperties;
  /**
   * Extend the Properties panel: flag buttons (bypass, freeze, cache), break-if condition, ƒ expression
   * and 📌 dashboard buttons on every parameter, and 📌 buttons for every output.
   */
  KS.decorateProperties = function (node, container) {
    origDecorate(node, container);
    const grp = container.querySelector('.ks-group');
    if (!grp) return;
    const p = node.properties || (node.properties = {});
    const flags = document.createElement('div');
    flags.innerHTML = `<label>Flags</label><div class="ks-flags">
        <button class="ks-flag byp ${p.bypass ? 'on' : ''}" data-f="bypass" title="Pass inputs straight to outputs (Houdini bypass / Blender mute) · Ctrl+E">⤳ bypass</button>
        <button class="ks-flag frz ${p.frozen ? 'on' : ''}" data-f="frozen" title="Pin the last outputs and stop re-computing (n8n pin data / Houdini lock) · Ctrl+Shift+L">❄ freeze</button>
        <button class="ks-flag ${p.cache === false ? '' : 'on'}" data-f="cache" title="Reuse results when nothing upstream changed (Run once)">⟲ cache</button>
      </div>
      <div class="ks-prow"><span title="Pause the simulation when this becomes true (outputs, t, step)">break if</span><input type="text" class="ks-expr" id="ksBreak" placeholder="e.g. V > 0 and t > 5" value="${esc(p.break_if || '')}"></div>`;
    const plab = [...grp.querySelectorAll(':scope > label')].find(l => l.textContent.trim().startsWith('Parameters'));
    grp.insertBefore(flags, plab || grp.firstChild);
    flags.querySelectorAll('[data-f]').forEach(b => b.onclick = () => SD.toggleFlag(node, b.dataset.f));
    $('#ksBreak', flags).onchange = e => { const v = e.target.value.trim(); if (v) p.break_if = v; else delete p.break_if; renderer.render(); saveState(); };
    // expression toggles and dashboard pins on each parameter row
    grp.querySelectorAll('.ks-prow').forEach(row => {
      const el = row.querySelector('[data-k]'); if (!el) return;
      const k = el.dataset.k;
      const fx = document.createElement('button'); fx.className = 'ks-fx'; fx.textContent = 'ƒ'; fx.title = 'Use an expression (=… evaluated against Globals)';
      fx.onclick = () => {
        const cur = p.params[k];
        const e = prompt(`Expression for ${k} (starts with =, e.g. =g*2 or =P("Node", "param")). Empty = back to a value.`, typeof cur === 'string' && cur.startsWith('=') ? cur : '=' + JSON.stringify(cur));
        if (e === null) return;
        p.params[k] = e.trim() ? (e.trim().startsWith('=') ? e.trim() : (isNaN(+e) ? e : +e)) : 0;
        saveState(); updatePropertiesPanel(node);
      };
      const pin = document.createElement('button'); pin.className = 'ks-pin'; pin.textContent = '📌'; pin.title = 'Pin to dashboard';
      pin.onclick = () => SD.pinParam(node, k);
      (row.querySelector('span') || row).appendChild(fx);
      (row.querySelector('span') || row).appendChild(pin);
    });
    // output pins
    if (node.outputs.length) {
      const d = document.createElement('div');
      d.className = 'ks-outpins';
      d.innerHTML = '<span style="font-size:9px;color:#6c7488">pin output:</span>' + node.outputs.map(o => `<button data-o="${esc(o.name)}">📌 ${esc(o.name)}</button>`).join('');
      d.onclick = e => { const o = e.target.dataset.o; if (o) SD.pinOutput(node, o); };
      const btns = grp.querySelector('#ksRunTo');
      grp.insertBefore(d, btns ? btns.parentElement : null);
    }
  };
  /** Toggle a node flag. Freezing stores the node's last outputs; bypass and freeze take effect on the next run. */
  SD.toggleFlag = function (node, f) {
    const p = node.properties || (node.properties = {});
    if (f === 'bypass') { p.bypass = !p.bypass; if (!p.bypass) delete p.bypass; }
    else if (f === 'cache') { if (p.cache === false) delete p.cache; else p.cache = false; }
    else if (f === 'frozen') {
      if (p.frozen) delete p.frozen;
      else {
        const r = KS.results[node.id];
        if (!r || !r.outputs) return KS.status('Run the model once — freezing pins the node’s last outputs');
        p.frozen = clone(r.outputs);
      }
    }
    renderer.render(); saveState(); updatePropertiesPanel(node);
    KS.status(`${esc(node.name)}: ${f} ${p[f] === undefined || p[f] === false ? 'off' : 'on'}`);
  };

  // ====================================================================== dashboard (front panel)
  const nodeLabel = (id) => (graph.nodes[id] ? graph.nodes[id].name : '#' + id);
  /** Add a parameter to the dashboard with a fitting widget (slider range from the schema or around the value). */
  SD.pinParam = function (node, k) {
    const v = node.properties.params[k];
    const tpl = KS.byId[(node.properties || {}).template];
    const sc = (tpl && tpl.schema && tpl.schema[k]) || (node.properties.schema || {})[k] || {};
    let kind = typeof v === 'boolean' ? 'toggle' : typeof v === 'number' ? 'slider' : (sc.options ? 'select' : 'text');
    const w = { id: Date.now(), kind, node: node.id, key: k, label: `${node.name} · ${k}` };
    if (kind === 'slider') {
      w.min = sc.min !== undefined ? sc.min : (v > 0 ? 0 : v < 0 ? 2 * v : -1);
      w.max = sc.max !== undefined ? sc.max : (v > 0 ? 2 * v : v < 0 ? 0 : 1);
      w.step = sc.step || Math.abs(w.max - w.min) / 200 || 0.01;
    }
    if (kind === 'select') w.options = sc.options;
    KS.model.dashboard.push(w); SD.openDash(); saveState();
  };
  /** Add an output to the dashboard as a readout (⇄ switches to gauge or sparkline). */
  SD.pinOutput = function (node, port) {
    KS.model.dashboard.push({ id: Date.now(), kind: 'readout', node: node.id, key: port, label: `${node.name} · ${port}` });
    SD.openDash(); saveState();
  };
  /** Show the dashboard panel (draggable, resizable; ⛶ switches to full-screen presentation mode). */
  SD.openDash = function () {
    let d = $('#knDash');
    if (!d) {
      d = document.createElement('div'); d.id = 'knDash';
      d.innerHTML = `<div class="dh"><b>🎛 Dashboard</b><span style="flex:1"></span><button id="knPresent" title="Presentation mode (front panel)">⛶ present</button><button id="knDashX">✕</button></div><div class="db" id="knDashBody"></div>`;
      $('#canvasContainer').appendChild(d);
      const head = $('.dh', d);
      head.addEventListener('mousedown', e => {
        if (e.target.closest('button') || d.classList.contains('present')) return;
        const r = d.getBoundingClientRect(), pr = d.parentElement.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
        const mv = ev => { d.style.left = (ev.clientX - pr.left - dx) + 'px'; d.style.top = (ev.clientY - pr.top - dy) + 'px'; };
        const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); };
        document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
      });
      $('#knDashX', d).onclick = () => { d.classList.remove('active', 'present'); };
      $('#knPresent', d).onclick = () => { d.classList.toggle('present'); SD.updateDash(); };
    }
    d.classList.add('active');
    SD.renderDash();
  };
  let dashSaveTimer = null;
  /** Build the dashboard widgets and wire their inputs to node parameters (debounced undo + auto re-run). */
  SD.renderDash = function () {
    const body = $('#knDashBody'); if (!body) return;
    const W = KS.model.dashboard;
    if (!W.length) { body.innerHTML = '<div style="color:#777;font-size:11px;grid-column:1/-1;line-height:1.6">Pin parameters (📌 next to a parameter) and outputs (📌 under Last result) from the Properties panel. Sliders drive the model — combine with ● Live or ⟳ auto for instant feedback.</div>'; return; }
    body.innerHTML = W.map(w => {
      const head = `<div class="dt"><span title="${esc(w.label)}">${esc(w.label)}</span><span><b class="dx" data-kind="${w.id}" title="change display">⇄</b> <b class="dx" data-del="${w.id}">✕</b></span></div>`;
      const n = graph.nodes[w.node], v = n && n.properties.params ? n.properties.params[w.key] : undefined;
      if (w.kind === 'slider') return `<div class="dw">${head}<div class="dv" data-val="${w.id}">${KS.fmt(v, 5)}</div><input type="range" data-w="${w.id}" min="${w.min}" max="${w.max}" step="${w.step}" value="${v}"></div>`;
      if (w.kind === 'toggle') return `<div class="dw">${head}<label class="tg"><input type="checkbox" data-w="${w.id}" ${v ? 'checked' : ''}> ${v ? 'on' : 'off'}</label></div>`;
      if (w.kind === 'select') return `<div class="dw">${head}<select data-w="${w.id}" style="margin-top:8px;width:100%">${(w.options || []).map(o => `<option ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select></div>`;
      if (w.kind === 'text') return `<div class="dw">${head}<input type="text" data-w="${w.id}" value="${esc(v)}" style="margin-top:8px;width:100%"></div>`;
      if (w.kind === 'gauge' || w.kind === 'spark') return `<div class="dw">${head}<div class="dv" data-out="${w.id}">—</div><canvas data-c="${w.id}"></canvas></div>`;
      return `<div class="dw">${head}<div class="dv" data-out="${w.id}">—</div></div>`;
    }).join('');
    body.oninput = body.onchange = e => {
      const id = +e.target.dataset.w; if (!id) return;
      const w = W.find(x => x.id === id), n = graph.nodes[w.node]; if (!n) return;
      const el = e.target;
      const v = w.kind === 'slider' ? parseFloat(el.value) : w.kind === 'toggle' ? el.checked : el.value;
      n.properties.params[w.key] = v;
      const lab = body.querySelector(`[data-val="${id}"]`); if (lab) lab.textContent = KS.fmt(v, 5);
      if (w.kind === 'toggle') el.parentElement.lastChild.textContent = ' ' + (v ? 'on' : 'off');
      renderer.render();
      if (KS.autoRun && !(SD.live && SD.live.on)) KS.scheduleAutoRun();
      clearTimeout(dashSaveTimer);
      dashSaveTimer = setTimeout(() => { saveState(); if (graph.selectedNodes[0] === n.id) updatePropertiesPanel(n); }, 600);
    };
    body.onclick = e => {
      const del = +e.target.dataset.del, kind = +e.target.dataset.kind;
      if (del) { KS.model.dashboard = W.filter(w => w.id !== del); SD.renderDash(); saveState(); }
      if (kind) {
        const w = W.find(x => x.id === kind);
        const cycle = ['slider', 'toggle', 'select', 'text'].includes(w.kind) ? null : ['readout', 'gauge', 'spark'];
        if (cycle) { w.kind = cycle[(cycle.indexOf(w.kind) + 1) % 3]; if (w.kind === 'gauge' && w.max === undefined) { w.min = 0; w.max = null; } SD.renderDash(); SD.updateDash(); saveState(); }
      }
    };
    SD.updateDash();
  };
  /** Refresh dashboard outputs: readouts, gauges and sparklines from the latest results and traces. */
  SD.updateDash = function () {
    const body = $('#knDashBody'); if (!body || !$('#knDash').classList.contains('active')) return;
    for (const w of KS.model.dashboard) {
      const el = body.querySelector(`[data-out="${w.id}"]`);
      if (!el) continue;
      const r = rootLevel() ? KS.results[w.node] : null;
      const v = r && r.outputs ? r.outputs[w.key] : undefined;
      el.textContent = rootLevel() ? KS.fmt(v, 5) : '(exit group)';
      const c = body.querySelector(`[data-c="${w.id}"]`);
      if (!c) continue;
      const dpr = window.devicePixelRatio || 1, Wd = c.clientWidth, H = c.clientHeight;
      c.width = Wd * dpr; c.height = H * dpr;
      const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const tr = KS.lastSim && KS.lastSim.traces && KS.lastSim.traces[w.node + '.' + w.key];
      if (w.kind === 'spark' && tr) {
        const s = tr.filter(x => x !== null); if (s.length < 2) continue;
        let lo = Math.min(...s), hi = Math.max(...s); if (hi === lo) { hi++; lo--; }
        g.strokeStyle = '#7c8cff'; g.lineWidth = 1.4; g.beginPath();
        const stp = Math.max(1, Math.floor(s.length / 300));
        for (let i = 0; i < s.length; i += stp) { const px = i / (s.length - 1) * Wd, py = H - 3 - (s[i] - lo) / (hi - lo) * (H - 6); i ? g.lineTo(px, py) : g.moveTo(px, py); }
        g.stroke();
      } else if (w.kind === 'gauge' && typeof v === 'number') {
        if (w.max === null || w.max === undefined) w.max = tr ? Math.max(...tr.filter(x => x !== null), v) : Math.abs(v) * 2 || 1;
        const lo = w.min || 0, hi = w.max, f = Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1)));
        const cx = Wd / 2, cy = H - 4, R = Math.min(Wd / 2 - 6, H - 8);
        g.lineWidth = 7; g.lineCap = 'round';
        g.strokeStyle = '#2a2c38'; g.beginPath(); g.arc(cx, cy, R, Math.PI, 2 * Math.PI); g.stroke();
        g.strokeStyle = KS.heatColor(f); g.beginPath(); g.arc(cx, cy, R, Math.PI, Math.PI + f * Math.PI); g.stroke();
      }
    }
  };
  // dashboard readouts refresh twice a second, but never in a hidden tab or while live mode drives them
  setInterval(() => { if (document.hidden || (SD.live && SD.live.on)) return; SD.updateDash(); }, 500);

  // ====================================================================== live mode (streaming session)
  // spf = fixed steps per frame; auto = adapt the chunk size (autoN) to the round-trip time; inflight = the
  // pipelined request for the next chunk (see tick).
  const L = SD.live = { on: false, playing: false, sid: null, spf: 5, auto: true, autoN: 5, inflight: null, busy: false, sig: null, fps: 0, lastT: 0, steps: 0 };
  /**
   * Signature of everything that requires restarting a live session: code, ports, wires, groups, flags,
   * wireless channels. Parameter values are excluded — those are sent live without a restart.
   */
  function structureSig(payload) {
    const nodes = {};
    for (const [id, n] of Object.entries(payload.nodes)) {
      const p = n.properties || {};
      nodes[id] = [n.code, n.inputs && n.inputs.map ? n.inputs.map(x => typeof x === 'string' ? x : x.name + (x.enabled === false ? '-' : '')) : 0,
        n.outputs && n.outputs.map ? n.outputs.map(x => typeof x === 'string' ? x : x.name) : 0,
        n.subgraph || p.subgraph || null, !!(n.bypass || p.bypass), !!(n.frozen || p.frozen), n.break_if || p.break_if || null, n.template || p.template || null,
        (n.template || p.template) === 'send' || (n.template || p.template) === 'receive' ? JSON.stringify(n.params || p.params) : null];
    }
    return JSON.stringify([nodes, payload.connections.map(c => [c.from, c.fromPort, c.to, c.toPort]).sort()]);
  }
  /** Current parameters of every top-level node, sent with each live step (the server applies only changes). */
  function liveParams() {
    if (!rootLevel()) return null;
    const out = {};
    for (const [id, n] of Object.entries(graph.nodes)) if (n.properties && n.properties.params && !n.properties.subgraph) out[id] = n.properties.params;
    return out;
  }
  /** Start (or restart) a live session on the server and begin the animation loop. */
  async function liveStart(keepPlaying) {
    const payload = KS.serialize();
    const dt = parseFloat($('#ksDt').value) || 0.01;
    if (L.sid) KS.api('/session/stop', { id: L.sid }).catch(() => {});
    let res;
    try { res = await KS.api('/session/start', Object.assign(payload, { dt })); }
    catch (e) { KS.status(`<span class="ks-err">${esc(e.message)}</span>`); return liveOff(); }
    L.inflight = null; L.autoN = L.spf;
    L.sid = res.id; L.sig = structureSig(payload); L.on = true; L.playing = keepPlaying !== false; L.steps = 0; L.plotShown = !!($('#ksPlot') && $('#ksPlot').classList.contains('active'));
    KS.lastSim = { traces: { t: [] }, outputs: {} }; KS.lastRun = KS.lastSim;
    KS.traceNames = KS.rootNames ? KS.rootNames() : null;
    KS.results = {};
    if (!res.success) { const e = Object.values(res.errors)[0]; KS.status(`<span class="ks-err">Live: ${esc(e ? e.error : 'start failed')}</span>`); }
    $('#knLive').classList.add('on'); updateLiveUI();
    requestAnimationFrame(tick);
  }
  /** Stop live mode and discard the server session. */
  function liveOff() {
    if (L.sid) KS.api('/session/stop', { id: L.sid }).catch(() => {});
    Object.assign(L, { on: false, playing: false, sid: null, inflight: null });
    $('#knLive').classList.remove('on'); updateLiveUI();
  }
  /**
   * Append a chunk of live samples to the trace buffers (new series are back-filled with gaps; the buffer
   * is halved once it exceeds 20 000 samples so memory stays bounded).
   */
  function appendChunk(chunk) {
    const tr = KS.lastSim.traces;
    const n0 = tr.t.length;
    for (const k in chunk) {
      if (k === 't') continue;
      if (!tr[k]) tr[k] = new Array(n0).fill(null);
    }
    tr.t.push(...chunk.t);
    for (const k in tr) if (k !== 't') tr[k].push(...(chunk[k] || new Array(chunk.t.length).fill(null)));
    if (tr.t.length > 20000) for (const k in tr) tr[k] = tr[k].filter((_, i) => i % 2 === 0);     // keep memory bounded
  }
  let plotClock = 0;
  /**
   * One live frame: restart if the structure changed, otherwise advance the session by 'steps/frame' with
   * the current parameters, append traces, refresh results, plot (≤ 16 Hz) and dashboard; pause on stop.
   */
  async function tick(ts) {
    if (!L.on) return;
    if (!L.playing || L.busy) { if (L.on) requestAnimationFrame(tick); return; }
    L.busy = true;
    try {
      const payload = KS.serialize();
      if (structureSig(payload) !== L.sig) { L.busy = false; L.inflight = null; await liveStart(true); KS.status('Live: model structure changed — restarted'); return; }
      if (!L.inflight) L.inflight = requestChunk();
      const sid = L.sid;
      const { res, n, ms } = await L.inflight;
      L.inflight = null;
      if (sid !== L.sid) return;                               // session was restarted meanwhile: drop the stale chunk
      if (res.expired) { L.busy = false; await liveStart(true); return; }
      // 0.7 — pipelining: ask for the next chunk *before* processing this one, so the server computes
      // it while the browser parses, renders and plots (both processes stay busy instead of alternating).
      if (!res.stopped && L.playing) L.inflight = requestChunk();
      if (L.auto && ms > 0) {
        // adaptive chunk size: aim for ~25 ms per round trip (smooth frame rate, little request overhead)
        const ideal = n * 25 / ms;
        L.autoN = Math.max(1, Math.min(5000, Math.round(0.7 * L.autoN + 0.3 * ideal)));
      }
      if (res.chunk) appendChunk(res.chunk);
      KS.lastSim.outputs = res.outputs;
      KS.lastRun = Object.assign(KS.lastSim, { groups: res.groups, status: res.status, errors: res.errors });
      KS.applyResults(res, true);
      L.steps += res.steps_done || 0; L.t = res.t;
      const now = performance.now();
      if (now - L.lastT > 500) { L.fps = Math.round(L.steps / ((now - (L.t0 || now)) / 1000 || 1)); }
      if (!L.t0) L.t0 = now;
      if (now - plotClock > 60) {
        plotClock = now;
        const pl = $('#ksPlot');
        if (!L.plotShown && KS.lastSim.traces.t.length > 1) { KS.openPlot(); L.plotShown = true; }
        else if (pl && pl.classList.contains('active')) KS.drawPlot();
        SD.updateDash();
      }
      updateLiveUI();
      if (res.stopped) {
        L.playing = false; updateLiveUI();
        if (res.breakpoint) { graph.selectedNodes = [Number(res.breakpoint.node)]; updatePropertiesPanel(graph.nodes[res.breakpoint.node]); }
        KS.status(`<span class="ks-warn">⏸ Live paused — ${esc(res.stopped)}</span> at t = ${KS.fmt(res.t)}`);
        KS.logReport(KS.levelView ? KS.levelView(res) : res, 'Live paused: ' + res.stopped);
        if (res.stopped === 'error') { KS.api('/session/stop', { id: L.sid }); L.sid = null; }
        KS.openPlot();
      }
    } catch (e) {
      L.playing = false; KS.status(`<span class="ks-err">Live: ${esc(e.message)}</span>`); updateLiveUI();
    } finally { L.busy = false; }
    if (L.on) requestAnimationFrame(tick);
  }
  /**
   * Send one /session/step request (steps = fixed setting, or the adaptive size in auto mode).
   * Resolves to { res, n, ms } — the report, the steps asked for and the round-trip time.
   * max_points caps the samples returned per chunk (large auto chunks are downsampled).
   */
  function requestChunk() {
    const n = L.auto ? L.autoN : L.spf, t0 = performance.now();
    return KS.api('/session/step', { id: L.sid, n, params: liveParams(), max_points: Math.min(n, 400) })
      .then(res => ({ res, n, ms: performance.now() - t0 }));
  }

  /** Refresh the live transport (● / ⏹, play/pause, LIVE badge, clock). */
  function updateLiveUI() {
    const box = $('#knLive'); if (!box) return;
    $('#knLivePlay').textContent = L.playing ? '⏸' : '▶';
    $('#knLiveRec').style.display = L.on ? '' : 'none';
    $('#knLiveClock').textContent = L.on ? `t=${KS.fmt(L.t || 0, 4)}` : 'live';
    $('#knLiveBtn').textContent = L.on ? '⏹' : '●';
    $('#knLiveBtn').title = L.on ? 'Stop live session' : 'Start live session (model runs while you edit)';
  }
  /** Start or stop live mode (Space / the ● button). */
  SD.toggleLive = () => (L.on ? liveOff() : liveStart(true));
  /** Pause or resume a live session (starts one if needed); resets the steps/s counter. */
  SD.playPause = () => { if (!L.on) return SD.toggleLive(); if (!L.sid) return liveStart(true); L.playing = !L.playing; L.t0 = null; L.steps = 0; updateLiveUI(); if (L.playing) requestAnimationFrame(tick); };
  /** Restart the live session from t = 0 keeping the play state. */
  SD.rewind = () => { if (L.on) liveStart(L.playing); };

  // ====================================================================== kept runs & scenarios (plot overlays)
  KS.overlaySeries = function (S, xKey) {
    const out = [];
    for (const run of KS.kept) {
      if (run.hidden) continue;
      const tr = run.traces || {};
      for (const s of S) {
        if (!s.key || s.key.startsWith('arr:') || s.key.startsWith('fld:') || s.key === 'sweep') continue;
        const y = tr[s.key]; if (!y) continue;
        const x = xKey && xKey !== 'default' ? tr[xKey] : tr.t;
        if (!x) continue;
        out.push({ label: `${run.name} · ${s.label}`, color: run.color || s.color, x, y, dash: true });
      }
    }
    if (KS.dataOverlay) out.push(Object.assign({ points: true }, KS.dataOverlay));
    return out;
  };
  /** Keep the current simulation as a named run; kept runs are drawn dashed behind later runs. */
  SD.keepRun = function () {
    if (!KS.lastSim || !KS.lastSim.traces) return KS.status('Simulate first, then keep the run for comparison');
    const name = prompt('Name this run', 'run ' + (KS.kept.length + 1));
    if (name === null) return;
    KS.kept.push({ name, traces: clone(KS.lastSim.traces), color: ['#feca57', '#ff9ff3', '#48c9e0', '#1dd1a1', '#ff6b6b'][KS.kept.length % 5] });
    KS.drawPlot(); KS.status(`Kept “${esc(name)}” — it is drawn dashed behind new runs`);
  };
  /** Snapshot of every top-level node's parameters (a scenario). */
  function scenarioParams() {
    const out = {};
    for (const [id, n] of Object.entries(graph.nodes)) if (n.properties && n.properties.params && !n.properties.subgraph && Object.keys(n.properties.params).length) out[id] = clone(n.properties.params);
    return out;
  }
  /**
   * Scenarios dialog: capture / apply / update / delete parameter variants, run them all on the server and
   * overlay the results; manage kept runs.
   */
  SD.openScenarios = function () {
    const body = KS.modal('knScen', 'Scenarios (parameter variants) & compared runs', 620);
    if (!rootLevel()) { body.innerHTML = 'Scenarios apply to the top-level model — exit the group first.'; return; }
    const S = KS.model.scenarios;
    body.innerHTML = `<div class="ks-desc" style="color:#999;margin-bottom:8px">A scenario stores every parameter of the model (like Houdini takes). Capture a baseline, change parameters, capture again, then run all to compare them in the plot.</div>
      <div id="scList">${S.map((s, i) => `<div class="sc-row"><b>${esc(s.name)}</b><span style="color:#777;font-size:10px">${Object.keys(s.params).length} nodes</span>
        <button class="ks-btn" data-apply="${i}">apply</button><button class="ks-btn" data-upd="${i}" title="overwrite with current parameters">update</button><button class="ks-btn" data-del="${i}">✕</button></div>`).join('') || '<div style="color:#777;padding:6px 0">No scenarios yet.</div>'}</div>
      <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap"><button class="ks-btn" id="scCap">＋ capture current parameters</button><span style="flex:1"></span>
        <select id="scMode"><option value="simulate">simulate (toolbar steps & dt)</option><option value="run">single run</option></select>
        <button class="ks-btn pri" id="scRun" ${S.length ? '' : 'disabled'}>▶ run all & compare</button></div>
      <div id="scMsg" class="kd-msg"></div>
      <div style="margin-top:10px"><b style="font-size:11px">Kept runs in the plot</b> <button class="ks-btn" id="scClear" style="margin-left:6px">clear all</button>
        <div id="scKept">${KS.kept.map((k, i) => `<div class="sc-row"><i style="width:14px;height:2px;background:${k.color};display:inline-block"></i><b>${esc(k.name)}</b><label style="font-size:10px"><input type="checkbox" data-vis="${i}" ${k.hidden ? '' : 'checked'}> show</label><button class="ks-btn" data-kd="${i}">✕</button></div>`).join('') || '<div style="color:#777;padding:4px 0;font-size:11px">Use 📌 keep in the plot, or run scenarios.</div>'}</div></div>`;
    body.onclick = async e => {
      const d = e.target.dataset;
      if (d.apply !== undefined) {
        const sc = S[+d.apply];
        for (const [id, p] of Object.entries(sc.params)) if (graph.nodes[id]) graph.nodes[id].properties.params = clone(p);
        saveState(); renderer.render(); KS.status(`Applied scenario “${esc(sc.name)}”`); if (KS.autoRun) KS.scheduleAutoRun();
      } else if (d.upd !== undefined) { S[+d.upd].params = scenarioParams(); saveState(); SD.openScenarios(); }
      else if (d.del !== undefined) { S.splice(+d.del, 1); saveState(); SD.openScenarios(); }
      else if (d.kd !== undefined) { KS.kept.splice(+d.kd, 1); KS.drawPlot(); SD.openScenarios(); }
      else if (e.target.id === 'scCap') {
        const name = prompt('Scenario name', S.length ? 'variant ' + S.length : 'baseline'); if (name === null) return;
        S.push({ name, params: scenarioParams() }); saveState(); SD.openScenarios();
      } else if (e.target.id === 'scClear') { KS.kept = []; KS.drawPlot(); SD.openScenarios(); }
      else if (e.target.id === 'scRun') {
        const msg = $('#scMsg', body); msg.style.color = '#aaa'; msg.textContent = 'running…';
        const mode = $('#scMode', body).value;
        const res = await KS.api('/graph/scenarios', Object.assign(KS.serialize(), {
          scenarios: S.map(s => ({ name: s.name, overrides: s.params })), mode,
          steps: parseInt($('#ksSteps').value) || 1000, dt: parseFloat($('#ksDt').value) || 0.01 })).catch(err => ({ error: err.message }));
        if (!res.scenarios) { msg.style.color = '#e74c3c'; msg.textContent = res.error || 'failed'; return; }
        const cols = ['#feca57', '#ff9ff3', '#48c9e0', '#1dd1a1', '#ff6b6b', '#a29bfe', '#54a0ff'];
        KS.kept = KS.kept.filter(k => !k.scenario);
        res.scenarios.forEach((sc, i) => { if (sc.traces) KS.kept.push({ name: sc.name, traces: sc.traces, color: cols[i % cols.length], scenario: true }); });
        const errs = res.scenarios.filter(s => s.error);
        msg.style.color = errs.length ? '#e74c3c' : '#2ecc71';
        msg.textContent = errs.length ? errs.map(s => `${s.name}: ${s.error}`).join('\n') : `✓ ${res.scenarios.length} scenarios — overlaid (dashed) on the plot`;
        if (mode === 'simulate' && res.scenarios[0] && res.scenarios[0].traces) {
          KS.lastSim = { traces: res.scenarios[0].traces, outputs: res.scenarios[0].outputs }; KS.lastRun = KS.lastSim;
          KS.traceNames = KS.rootNames ? KS.rootNames() : null;
          KS.openPlot();
        }
        SD.openScenarios(); $('#scMsg').textContent = msg.textContent; $('#scMsg').style.color = msg.style.color;
      }
    };
    body.onchange = e => { const v = e.target.dataset.vis; if (v !== undefined) { KS.kept[+v].hidden = !e.target.checked; KS.drawPlot(); } };
  };

  // ====================================================================== calibration / optimisation
  SD.openCalibrate = function () {
    const body = KS.modal('knCal', 'Calibrate & optimise', 760);
    if (!rootLevel()) { body.innerHTML = 'Optimisation works on the top-level model — exit the group first.'; return; }
    const nodes = Object.values(graph.nodes);
    const numNodes = nodes.filter(n => n.properties && n.properties.params && Object.values(n.properties.params).some(v => typeof v === 'number'));
    if (!numNodes.length) { body.innerHTML = 'No numeric parameters to vary.'; return; }
    const nodeOpts = (list) => list.map(n => `<option value="${n.id}">${esc(n.name)} #${n.id}</option>`).join('');
    const stateful = nodes.some(n => { const t = KS.byId[(n.properties || {}).template]; return t && t.stateful; });
    body.innerHTML = `
      <div class="ks-desc" style="color:#999;margin-bottom:8px">Search parameter values within bounds that minimise or maximise an output, or <b>fit the model to measured data</b> (least squares). Differential evolution explores globally; Nelder–Mead refines locally from the current values.</div>
      <table class="ks-t" id="calF"><tr><th>node</th><th>parameter</th><th>lower</th><th>upper</th><th></th></tr></table>
      <button class="ks-btn" id="calAdd" style="margin:4px 0 10px">＋ parameter</button>
      <div class="ks-prow"><span>goal</span><select id="calType"><option value="fit">fit to data</option><option value="minimize">minimise</option><option value="maximize">maximise</option></select>
        <select id="calN">${nodeOpts(nodes)}</select><select id="calP"></select>
        <select id="calRed" title="reduce a time series"><option value="last">final</option><option value="max">max</option><option value="min">min</option><option value="mean">mean</option><option value="integral">∫dt</option><option value="argmax_t">time of max</option></select></div>
      <div class="ks-prow ks-block" id="calDataRow"><span>data — one “t, y” pair per line (paste from a spreadsheet)</span><textarea class="ks-code" id="calData" rows="5" placeholder="0, 5\n2, 11.8\n4, 27.3"></textarea></div>
      <div class="ks-prow"><span>method</span><select id="calM"><option value="de">differential evolution (global)</option><option value="nm">Nelder–Mead (local)</option></select>
        <span style="width:auto">budget</span><input type="number" id="calB" value="300" style="width:70px">
        <select id="calMode"><option value="simulate" ${stateful ? 'selected' : ''}>simulate (toolbar steps & dt)</option><option value="run" ${stateful ? '' : 'selected'}>single run</option></select></div>
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center"><button class="ks-btn pri" id="calGo">▶ Optimise</button><span id="calMsg" style="color:#888;font-size:11px"></span></div>
      <div id="calOut" style="margin-top:10px"></div>`;
    const fillParams = (sel, id) => { const p = (graph.nodes[id].properties || {}).params || {}; sel.innerHTML = Object.entries(p).filter(([, v]) => typeof v === 'number').map(([k]) => `<option>${esc(k)}</option>`).join(''); };
    const addRow = () => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><select class="cn">${nodeOpts(numNodes)}</select></td><td><select class="cp"></select></td><td><input class="ks-input clo" type="number" step="any" style="width:90px"></td><td><input class="ks-input chi" type="number" step="any" style="width:90px"></td><td><button class="ks-btn cx">×</button></td>`;
      $('#calF', body).appendChild(tr);
      const n = $('.cn', tr), p = $('.cp', tr);
      const bounds = () => { const v = graph.nodes[n.value].properties.params[p.value]; $('.clo', tr).value = v > 0 ? +(v / 4).toPrecision(3) : v < 0 ? +(v * 4).toPrecision(3) : -1; $('.chi', tr).value = v > 0 ? +(v * 4).toPrecision(3) : v < 0 ? +(v / 4).toPrecision(3) : 1; };
      n.onchange = () => { fillParams(p, n.value); bounds(); }; p.onchange = bounds;
      $('.cx', tr).onclick = () => tr.remove();
      fillParams(p, n.value); bounds();
    };
    const preset = KS.model.calibration && graph.nodes[KS.model.calibration.node] ? KS.model.calibration : null;
    if (preset) for (const [param, lo, hi] of preset.params) {
      addRow(); const tr = body.querySelector('#calF').lastElementChild;
      $('.cn', tr).value = preset.node; $('.cn', tr).onchange(); $('.cp', tr).value = param; $('.clo', tr).value = lo; $('.chi', tr).value = hi;
    } else addRow();
    $('#calAdd', body).onclick = addRow;
    const cn = $('#calN', body), cp = $('#calP', body);
    const ports = () => { cp.innerHTML = graph.nodes[cn.value].outputs.map(o => `<option>${esc(o.name)}</option>`).join(''); };
    const sinks = nodes.filter(n => !Object.values(graph.wires).some(w => w.from === n.id));
    cn.value = (sinks[sinks.length - 1] || nodes[nodes.length - 1]).id; cn.onchange = ports; ports();
    if (preset) { cn.value = preset.node; ports(); cp.value = preset.port; $('#calData', body).value = preset.data; }
    const syncType = () => { $('#calDataRow', body).style.display = $('#calType', body).value === 'fit' ? '' : 'none'; $('#calRed', body).style.display = $('#calType', body).value === 'fit' ? 'none' : ''; };
    $('#calType', body).onchange = syncType; syncType();
    $('#calGo', body).onclick = async () => {
      const msg = $('#calMsg', body), out = $('#calOut', body);
      const factors = [...body.querySelectorAll('#calF tr')].slice(1).map(tr => ({ node: $('.cn', tr).value, param: $('.cp', tr).value, lo: parseFloat($('.clo', tr).value), hi: parseFloat($('.chi', tr).value) }));
      if (factors.some(f => !(f.hi > f.lo))) { msg.innerHTML = '<span class="ks-err">each upper bound must exceed its lower bound</span>'; return; }
      const type = $('#calType', body).value;
      const objective = { type, node: cn.value, port: cp.value, reduce: $('#calRed', body).value };
      if (type === 'fit') {
        const rows = $('#calData', body).value.split('\n').map(l => l.replace(/[;\t]/g, ',').split(/[,\s]+/).filter(Boolean).map(Number)).filter(r => r.length >= 2 && r.every(isFinite));
        if (rows.length < 2) { msg.innerHTML = '<span class="ks-err">paste at least two “t, y” rows</span>'; return; }
        objective.data = { t: rows.map(r => r[0]), y: rows.map(r => r[1]) };
      }
      msg.textContent = 'optimising… (each evaluation is a full model run)'; out.innerHTML = '';
      const t0 = performance.now();
      const res = await KS.api('/graph/optimize', Object.assign(KS.serialize(), { factors, objective, method: $('#calM', body).value,
        budget: parseInt($('#calB', body).value) || 300, mode: $('#calMode', body).value,
        steps: parseInt($('#ksSteps').value) || 500, dt: parseFloat($('#ksDt').value) || 0.01 })).catch(e => ({ error: e.message }));
      if (!res.success) { msg.innerHTML = `<span class="ks-err">${esc(res.error || 'failed')}</span>`; return; }
      msg.textContent = `${res.evaluations} evaluations in ${((performance.now() - t0) / 1000).toFixed(1)} s`;
      out.innerHTML = `<div class="ks-grid"><div class="ks-kpi"><b>${KS.fmt(res.objective, 6)}</b><span>${type === 'fit' ? 'sum of squared errors' : 'objective'}</span></div>
          ${type === 'fit' ? `<div class="ks-kpi"><b>${KS.fmt(res.r2, 5)}</b><span>R²</span></div><div class="ks-kpi"><b>${KS.fmt(res.rmse, 4)}</b><span>RMSE</span></div>` : ''}
          <div class="ks-kpi"><b>${res.method === 'de' ? 'DE' : 'NM'}</b><span>${res.evaluations} evaluations</span></div></div>
        <table class="ks-t">${factors.map((f, i) => `<tr><td>${esc(nodeLabel(f.node))} · ${esc(f.param)}</td><td><b>${KS.fmt(res.values[i], 6)}</b></td><td style="color:#777">[${KS.fmt(f.lo)}, ${KS.fmt(f.hi)}]${Math.abs(res.values[i] - f.lo) < 1e-3 * (f.hi - f.lo) || Math.abs(res.values[i] - f.hi) < 1e-3 * (f.hi - f.lo) ? ' <span class="ks-warn">at bound — widen?</span>' : ''}</td></tr>`).join('')}</table>
        <canvas id="calConv" style="width:100%;height:90px;margin-top:8px"></canvas>
        <div style="display:flex;gap:6px;margin-top:6px"><button class="ks-btn pri" id="calApply">Apply best values</button>${res.traces ? '<button class="ks-btn" id="calShow">Show best fit in plot</button>' : ''}</div>`;
      const c = $('#calConv', out), dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
      c.width = W * dpr; c.height = H * dpr;
      const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const hs = res.history.filter(v => v !== null && isFinite(v));
      if (hs.length > 1) {
        const lg = hs.every(v => v > 0) && Math.max(...hs) / Math.min(...hs) > 100;
        const tv = v => lg ? Math.log10(v) : v;
        const lo = Math.min(...hs.map(tv)), hi = Math.max(...hs.map(tv)) || lo + 1;
        g.strokeStyle = '#7c8cff'; g.lineWidth = 1.5; g.beginPath();
        hs.forEach((v, i) => { const x = 30 + i / (hs.length - 1) * (W - 40), y = H - 14 - (tv(v) - lo) / ((hi - lo) || 1) * (H - 24); i ? g.lineTo(x, y) : g.moveTo(x, y); });
        g.stroke(); g.fillStyle = '#888'; g.font = '9px sans-serif';
        g.fillText('best objective per ' + (res.method === 'de' ? 'generation' : 'iteration') + (lg ? ' (log)' : ''), 32, 10);
      }
      $('#calApply', out).onclick = () => {
        factors.forEach((f, i) => { graph.nodes[f.node].properties.params[f.param] = +res.values[i].toPrecision(8); });
        saveState(); renderer.render(); KS.status('Applied optimised values');
        if (graph.selectedNodes.length === 1) updatePropertiesPanel(graph.nodes[graph.selectedNodes[0]]);
      };
      const sh = $('#calShow', out);
      if (sh) sh.onclick = () => {
        $('#calApply', out).onclick();                                   // apply, then re-run so every view agrees
        KS.dataOverlay = type === 'fit' ? { label: 'data', color: '#fff', x: objective.data.t, y: objective.data.y } : null;
        KS.plotSel = { x: 'default', y: [objective.node + '.' + objective.port] };
        document.querySelector('#knCal').classList.remove('active');
        ($('#calMode', body).value === 'simulate' ? KS.runSimulation() : KS.runGraph(null)).then(() => KS.openPlot());
      };
    };
  };

  // ====================================================================== PNG with embedded model (ComfyUI-style)
  const crcTable = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = (bytes) => { let c = 0xffffffff; for (const b of bytes) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  /** Base64 of a UTF-8 string (PNG tEXt chunks are Latin-1, so the JSON is base64-encoded). */
  function b64utf8(s) { return btoa(unescape(encodeURIComponent(s))); }
  /** Inverse of b64utf8. */
  function unb64utf8(s) { return decodeURIComponent(escape(atob(s))); }
  /** Whole-model JSON for embedding (leaves any open group first so the root model is saved). */
  function modelJSON() { if (UI.stack.length) UI.resetContext(); return JSON.stringify(graph.toJSON()); }
  /**
   * Export the canvas as PNG with the whole model embedded in a 'knode' tEXt chunk (ComfyUI-style):
   * the image both shows and *is* the model.
   */
  SD.exportPNG = async function () {
    const json = modelJSON();
    renderer.renderNow();                                    // pixels are needed now (render() is deferred to the next frame)
    const url = renderer.canvas.toDataURL('image/png');
    const bin = Uint8Array.from(atob(url.split(',')[1]), c => c.charCodeAt(0));
    const key = new TextEncoder().encode('knode'), text = new TextEncoder().encode(b64utf8(json));
    const data = new Uint8Array(key.length + 1 + text.length); data.set(key, 0); data[key.length] = 0; data.set(text, key.length + 1);
    const type = new TextEncoder().encode('tEXt');
    const chunk = new Uint8Array(12 + data.length), dv = new DataView(chunk.buffer);
    dv.setUint32(0, data.length); chunk.set(type, 4); chunk.set(data, 8);
    const crcIn = new Uint8Array(4 + data.length); crcIn.set(type, 0); crcIn.set(data, 4);
    dv.setUint32(8 + data.length, crc32(crcIn));
    const iend = bin.length - 12;                                   // insert before IEND
    const out = new Uint8Array(bin.length + chunk.length); out.set(bin.subarray(0, iend), 0); out.set(chunk, iend); out.set(bin.subarray(iend), iend + chunk.length);
    KS.download(new Blob([out], { type: 'image/png' }), 'knode_model.png');
    KS.status('Saved PNG with the full model embedded — drop it back onto the canvas to open it');
  };
  /** Extract the embedded model from a knode PNG by walking its chunks. */
  function modelFromPNG(buf) {
    const b = new Uint8Array(buf), dv = new DataView(b.buffer);
    if (b[0] !== 0x89 || b[1] !== 0x50) throw new Error('not a PNG');
    let p = 8;
    while (p < b.length) {
      const len = dv.getUint32(p), type = String.fromCharCode(...b.subarray(p + 4, p + 8));
      if (type === 'tEXt') {
        const data = b.subarray(p + 8, p + 8 + len), z = data.indexOf(0);
        if (new TextDecoder().decode(data.subarray(0, z)) === 'knode') return JSON.parse(unb64utf8(new TextDecoder().decode(data.subarray(z + 1))));
      }
      p += 12 + len;
    }
    throw new Error('this PNG does not contain a knode model');
  }
  /** Open a dropped or chosen file: knode PNG, model JSON, or a node-type JSON (opens the Node Designer). */
  async function openFile(file) {
    try {
      const data = /\.png$/i.test(file.name) || file.type === 'image/png' ? modelFromPNG(await file.arrayBuffer()) : JSON.parse(await file.text());
      if (data.id && data.code && data.params && !data.nodes) return UI.designer(data);        // a node-type file
      if (Object.keys(graph.nodes).length && !confirm(`Replace the current model with “${file.name}”? (Undo with Ctrl+Z)`)) return;
      UI.resetContext(); saveState(); graph.fromJSON(data); KS.results = {}; KS.frame();
      KS.status(`Opened ${esc(file.name)}`);
    } catch (e) { KS.status(`<span class="ks-err">Could not open ${esc(file.name)}: ${esc(e.message)}</span>`); }
  }
  /** Pick a .json or knode .png file to open (Ctrl+O). */
  SD.openDialog = () => { const f = document.createElement('input'); f.type = 'file'; f.accept = '.json,.png'; f.onchange = () => f.files[0] && openFile(f.files[0]); f.click(); };
  /** Accept PNG / JSON files dropped onto the canvas. */
  function bindFileDrop() {
    const cc = $('#canvasContainer');
    cc.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); cc.classList.add('kn-drop-hint'); } });
    cc.addEventListener('drop', e => {
      if (!e.dataTransfer.files.length) return;
      e.preventDefault(); cc.classList.remove('kn-drop-hint'); openFile(e.dataTransfer.files[0]);
    });
  }

  // ====================================================================== examples: frames, dashboard, calibration presets
  KS.afterExample = function (ex, ids) {
    KS.frames = []; KS.model = { dashboard: [], scenarios: [] }; KS.kept = []; KS.dataOverlay = null;
    if (L.on) liveOff();
    for (const f of ex.frames || []) {
      const ns = f.nodes.map(i => graph.nodes[ids[i]]);
      const x0 = Math.min(...ns.map(n => n.x)) - 24, y0 = Math.min(...ns.map(n => n.y)) - TITLE - 18;
      const x1 = Math.max(...ns.map(n => n.x + n.width)) + 24, y1 = Math.max(...ns.map(n => n.y + n.height)) + 70;
      KS.frames.push({ id: Date.now() + Math.random(), x: x0, y: y0, w: x1 - x0, h: y1 - y0, title: f.title, color: f.color || FRAME_COLORS[0] });
    }
    for (const w of ex.dashboard || []) {
      const n = graph.nodes[ids[w.node]];
      KS.model.dashboard.push(Object.assign({ id: Date.now() + Math.random(), label: `${n.name} · ${w.key}` }, w, { node: n.id, step: w.step || ((w.max - w.min) / 200 || 0.01) }));
    }
    if (ex.calibration) KS.model.calibration = Object.assign({}, ex.calibration, { node: ids[ex.calibration.node] });
    const d = $('#knDash');
    if (KS.model.dashboard.length) SD.openDash(); else if (d) d.classList.remove('active', 'present');
  };

  // ====================================================================== menus, header, keys
  UI.extendMenus = function (m) {
    const add = (name, items, at) => { const menu = m.find(x => x[0] === name); if (!menu) return; at === undefined ? menu[1].push(...items) : menu[1].splice(at, 0, ...items); };
    add('File', [['Open file (JSON / PNG)…', () => SD.openDialog(), 'Ctrl+O']], 1);
    add('File', ['-', ['Export image with model (.png)', () => SD.exportPNG()]]);
    add('Edit', ['-', ['Frame selection (backdrop)', () => SD.frameSelection(), 'Ctrl+J'], ['Toggle bypass', () => flagSel('bypass'), 'Ctrl+E'],
      ['Toggle freeze (pin outputs)', () => flagSel('frozen'), 'Ctrl+Shift+L']]);
    add('View', ['-', ['Dashboard', () => SD.openDash(), 'Ctrl+Shift+D']]);
    add('Run', ['-', ['Live mode (run while editing)', () => SD.toggleLive(), 'Space', null, () => L.on], ['Scenarios & compared runs…', () => SD.openScenarios()],
      ['Calibrate / optimise…', () => SD.openCalibrate()], ['Clear result cache', () => KS.api('/cache/clear', {}).then(() => KS.status('Cache cleared'))],
      ['Use result cache for Run once', () => { KS.useCache = KS.useCache === false; KS.status('Result cache ' + (KS.useCache === false ? 'off' : 'on')); }, null, null, () => KS.useCache !== false]]);
    add('Model', ['-', ['Add Globals node (model variables)', () => KS.addTemplateAt('globals', null)], ['Add Send / Receive pair', () => {
      const c = KS.viewCenter(); const ch = prompt('Channel name', 'signal'); if (!ch) return;
      const a = KS.addTemplateAt('send', { x: c.x - 150, y: c.y }), b = KS.addTemplateAt('receive', { x: c.x + 150, y: c.y });
      a.properties.params.channel = ch; b.properties.params.channel = ch; renderer.render(); saveState(); }]]);
    return m;
  };
  /** Toggle a flag on every selected node. */
  function flagSel(f) { for (const id of graph.selectedNodes) if (graph.nodes[id]) SD.toggleFlag(graph.nodes[id], f); }
  /** Add the live transport and dashboard button to the header quick controls. */
  function buildHeader() {
    const q = $('#knQuick'); if (!q) return;
    const live = document.createElement('div'); live.id = 'knLive';
    live.innerHTML = `<button id="knLiveBtn">●</button><span class="rec" id="knLiveRec" style="display:none">LIVE</span>
      <button id="knLivePlay" title="Play / pause (Space)">▶</button><button id="knLiveRew" title="Restart from t = 0">⏮</button>
      <select id="knLiveSpeed" title="steps per frame — auto adapts to the model's speed"><option value="auto" selected>auto</option>${[1, 2, 5, 10, 20, 50, 100, 500].map(n => `<option>${n}</option>`).join('')}</select>
      <span class="clock" id="knLiveClock">live</span>`;
    q.insertBefore(live, $('#knRun'));
    $('#knLiveBtn').onclick = SD.toggleLive; $('#knLivePlay').onclick = SD.playPause; $('#knLiveRew').onclick = SD.rewind;
    $('#knLiveSpeed').onchange = e => { L.auto = e.target.value === 'auto'; if (!L.auto) L.spf = +e.target.value; };
    const dash = document.createElement('button'); dash.className = 'kn-btn'; dash.textContent = '🎛'; dash.title = 'Dashboard (Ctrl+Shift+D)';
    dash.onclick = () => { const d = $('#knDash'); if (d && d.classList.contains('active')) d.classList.remove('active'); else SD.openDash(); };
    q.insertBefore(dash, $('#ksDot'));
    updateLiveUI();
  }
  const typing = () => { const a = document.activeElement; return a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable); };
  const modalOpen = () => !!document.querySelector('.ks-modal.active, .modal-overlay.active, .code-editor-modal.active');
  document.addEventListener('keydown', e => {
    const ctrl = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
    if (typing() || modalOpen()) return;
    if (ctrl && k === 'j') { e.preventDefault(); SD.frameSelection(); }
    else if (ctrl && k === 'e') { e.preventDefault(); flagSel('bypass'); }
    else if (ctrl && e.shiftKey && k === 'l') { e.preventDefault(); flagSel('frozen'); }
    else if (ctrl && e.shiftKey && k === 'd') { e.preventDefault(); SD.openDash(); }
    else if (ctrl && k === 'o') { e.preventDefault(); SD.openDialog(); }
    else if (!ctrl && e.key === ' ') { e.preventDefault(); L.on ? SD.playPause() : SD.toggleLive(); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && KS.selFrame && !graph.selectedNodes.length) {
      KS.frames = KS.frames.filter(f => f.id !== KS.selFrame); KS.selFrame = null; renderer.render(); saveState();
    }
  }, true);

  document.addEventListener('DOMContentLoaded', () => {
    buildHeader(); bindFrames(); bindLinkDrag(); bindFileDrop();
    if (UI.renderMenubar) UI.renderMenubar();
  });
})();

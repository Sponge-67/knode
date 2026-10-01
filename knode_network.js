/* knode_network.js — network-device modelling UI for knode 0.8.2.
 *
 * The actual forwarding models are ordinary library templates (knode_network.py).
 * This layer only adds device-preset ergonomics and network-specific subtitles /
 * status, so exported graphs stay plain knode graphs and remain headless/CLI-safe.
 */
(function () {
  'use strict';
  const KS = window.KnodeSci;
  if (!KS) return;
  const esc = KS.esc || (s => String(s));

  const css = `
    .kn-netbox{border:1px solid #23585b;background:#172628;border-radius:5px;padding:7px;margin:0 0 8px}
    .kn-netbox label{display:block;font-size:9px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#6fcdd0;margin:2px 0 5px}
    .kn-netrow{display:flex;gap:4px;align-items:center;margin:4px 0;flex-wrap:wrap}
    .kn-netrow select{flex:1;min-width:130px;background:#141414;border:1px solid #31585a;color:#ddd;border-radius:3px;padding:3px 4px;font-size:10px}
    .kn-netmeta{font-size:9px;color:#7f9b9c;line-height:1.4;margin:4px 0;white-space:normal}
    .kn-netstat{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:9px;background:#10191a;border-radius:3px;padding:5px;white-space:pre-wrap;overflow:auto;max-height:120px}
    .kn-netpill{display:inline-block;border:1px solid #31585a;border-radius:9px;padding:1px 6px;margin:1px 3px 1px 0;color:#87cacc;font-size:8px}
  `;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  function template(node) { return KS.byId && KS.byId[(node.properties || {}).template]; }
  function isNetwork(node) { const t = template(node); return !!(t && t.network); }
  function customPresets() {
    try { const x = JSON.parse(localStorage.getItem('knode.networkPresets') || '[]'); return Array.isArray(x) ? x : []; } catch (e) { return []; }
  }
  function presets() { return ((KS.library && KS.library.network_presets) || []).concat(customPresets()); }
  function pById(id) { return presets().find(p => p.id === id); }
  const hostToolResults = new Map();

  function setInterfaces(node, list) {
    const t = template(node); if (!t) return;
    node.properties.params.interfaces = list.join(',');
    const d = KS.derivePorts(t, node.properties.params);
    KS.syncPorts(node, d[0], d[1]);
  }

  function applyPreset(node, preset, all) {
    if (!preset) return;
    const pp = node.properties.params || (node.properties.params = {});
    if (preset.params) Object.assign(pp, JSON.parse(JSON.stringify(preset.params)));
    pp.vendor = preset.vendor;
    pp.model = preset.model;
    pp.role = preset.role;
    pp.os = preset.os || '';
    pp.hostname = pp.hostname && !/^(network-device|router|ethernet-switch|wireless-access-point)$/i.test(pp.hostname)
      ? pp.hostname : String(preset.model).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    node.properties.networkPreset = preset.id;
    node.properties.networkHardware = preset.physical_ports || '';
    setInterfaces(node, (all ? preset.all_interfaces : preset.interfaces) || preset.interfaces || []);
    renderer.render(); saveState(); updatePropertiesPanel(node);
    KS.status(`Applied <b>${esc(preset.vendor)} ${esc(preset.model)}</b> network preset${all ? ' with all physical interfaces' : ''}`);
  }

  const origSubtitle = KS.subtitle;
  KS.subtitle = function (node) {
    const t = template(node), p = (node.properties || {}).params || {};
    if (t && t.network) {
      if (t.network.kind === 'device') {
        const n = String(p.interfaces || '').split(',').filter(x => x.trim()).length;
        return [`${p.vendor || 'Generic'} ${p.model || node.name}`, `${p.role || 'device'} · ${n} interface${n === 1 ? '' : 's'}`, p.os || ''];
      }
      if (t.network.kind === 'host') return [`${p.hostname || node.name} · ${p.ip || 'no IP'}`, p.ping_destination ? `ping → ${p.ping_destination}` : 'endpoint'];
      if (t.network.kind === 'link') return [`delay ${p.delay_steps || 0} step(s) · loss ${Math.round((+p.loss || 0) * 100)}%`];
      if (t.network.kind === 'internet') return [p.enabled ? 'REAL host network enabled' : 'host network disabled', 'ICMP · DNS · TCP probes'];
      if (t.network.kind === 'console') return [p.enabled ? (p.command || 'network console') : 'network console disabled', 'host diagnostics'];
      if (t.network.kind === 'monitor') return ['packet tap / counters'];
    }
    return origSubtitle ? origSubtitle(node) : null;
  };

  const origDecorate = KS.decorateProperties;
  KS.decorateProperties = function (node, container) {
    origDecorate(node, container);
    if (!node || graph.selectedNodes.length !== 1 || !isNetwork(node)) return;
    const t = template(node), p = (node.properties || {}).params || {}, net = t.network || {};
    const box = document.createElement('div'); box.className = 'kn-netbox';

    if (net.kind === 'device') {
      const ps = presets();
      const selected = node.properties.networkPreset || '';
      const options = [];
      let lastVendor = null;
      for (const x of ps) {
        if (x.vendor !== lastVendor) {
          if (lastVendor !== null) options.push('</optgroup>');
          options.push(`<optgroup label="${esc(x.vendor)}">`); lastVendor = x.vendor;
        }
        options.push(`<option value="${esc(x.id)}" ${x.id === selected ? 'selected' : ''}>${esc(x.model)}</option>`);
      }
      if (lastVendor !== null) options.push('</optgroup>');
      const cur = pById(selected);
      box.innerHTML = `<label>Network device</label>
        <div class="kn-netrow"><select id="knNetPreset"><option value="">Choose a hardware preset…</option>${options.join('')}</select><button class="btn-small" id="knNetApply">Apply</button></div>
        <div class="kn-netrow"><button class="btn-small" id="knNetCompact" ${cur ? '' : 'disabled'}>Compact ports</button><button class="btn-small" id="knNetAll" ${cur ? '' : 'disabled'}>All physical ports</button><button class="btn-small" id="knNetSave">Save custom preset</button></div>
        <div class="kn-netmeta" id="knNetMeta">${cur ? `${esc(cur.vendor)} · ${esc(cur.model)} · ${esc(cur.os || '')}<br>${esc(cur.physical_ports || '')}` : 'Generic/custom mode: edit role, vendor, model and interfaces below, or choose a preset.'}</div>`;
      const sel = box.querySelector('#knNetPreset');
      sel.onchange = () => {
        const x = pById(sel.value), m = box.querySelector('#knNetMeta');
        m.innerHTML = x ? `${esc(x.vendor)} · ${esc(x.model)} · ${esc(x.os || '')}<br>${esc(x.physical_ports || '')}` : 'Generic/custom mode';
      };
      box.querySelector('#knNetApply').onclick = () => applyPreset(node, pById(sel.value), false);
      box.querySelector('#knNetCompact').onclick = () => applyPreset(node, pById(node.properties.networkPreset), false);
      box.querySelector('#knNetAll').onclick = () => applyPreset(node, pById(node.properties.networkPreset), true);
      box.querySelector('#knNetSave').onclick = () => {
        const name = prompt('Custom preset name', p.model || node.name); if (!name) return;
        const xs = customPresets(), id = 'custom_' + Date.now();
        xs.push({id, vendor: p.vendor || 'Custom', model: name, role: p.role || 'switch', os: p.os || 'custom',
          interfaces: String(p.interfaces || '').split(',').map(x => x.trim()).filter(Boolean),
          all_interfaces: String(p.interfaces || '').split(',').map(x => x.trim()).filter(Boolean),
          physical_ports: 'Saved custom knode preset', params: JSON.parse(JSON.stringify(p))});
        localStorage.setItem('knode.networkPresets', JSON.stringify(xs)); node.properties.networkPreset = id; saveState(); updatePropertiesPanel(node);
        KS.status(`Saved custom network preset <b>${esc(name)}</b>`);
      };
    } else if (net.kind === 'host') {
      box.innerHTML = `<label>Network endpoint</label><div class="kn-netmeta">Set <b>ping_destination</b> to generate ICMP test traffic. A reply counter and traversed device trace appear after simulation.</div>`;
    } else if (net.kind === 'link') {
      box.innerHTML = `<label>Network link</label><div class="kn-netmeta"><b>a → to_b</b> and <b>b → to_a</b>. Put this between two devices to model full-duplex delay/loss; direct device-to-device wires remain valid too.</div>`;
    } else if (net.kind === 'internet') {
      const lr = hostToolResults.get(String(node.id));
      box.innerHTML = `<label>Real Internet gateway</label>
        <div class="kn-netmeta">Uses the <b>backend machine's real network stack</b>. Simulated ICMP echo, DNS and TCP-probe frames arriving on <b>lan</b> are translated into real diagnostics and replies are injected back into the topology. This is not a raw Ethernet/TUN bridge.</div>
        <div class="kn-netrow"><button class="btn-small" id="knNetTestInternet">Test ${esc(p.test_target || '1.1.1.1')}</button><span class="kn-netpill">${p.enabled ? 'graph access enabled' : 'graph access disabled'}</span></div>
        ${lr ? `<div class="kn-netstat">${esc((lr.stdout || '') + (lr.stderr ? '\n' + lr.stderr : ''))}</div>` : ''}`;
      box.querySelector('#knNetTestInternet').onclick = async () => {
        const b = box.querySelector('#knNetTestInternet'); b.disabled = true; b.textContent = 'Testing…';
        const target = String(p.test_target || '1.1.1.1').trim();
        const r = await KS.api('/network/console', {command: `ping ${target} 1`, timeout: p.timeout || 4, allow_private: !!p.allow_private_targets}).catch(e => ({success:false,stderr:e.message}));
        hostToolResults.set(String(node.id), r); updatePropertiesPanel(node);
      };
    } else if (net.kind === 'console') {
      const lr = hostToolResults.get(String(node.id));
      box.innerHTML = `<label>Host network console</label>
        <div class="kn-netmeta">Runs bounded diagnostics on the backend host, without a shell. Supported: <b>ping</b>, <b>traceroute/tracepath</b>, <b>dns</b>, <b>tcp HOST PORT</b>, <b>ip addr/route/neigh/link</b>, <b>hostname</b>.</div>
        <div class="kn-netrow"><button class="btn-small" id="knNetConsoleRun">▶ Run command now</button><button class="btn-small" id="knNetConsoleHelp">help</button><button class="btn-small" id="knNetConsoleRoute">ip route</button></div>
        ${lr ? `<div class="kn-netstat">$ ${esc(p.command || '')}\n${esc((lr.stdout || '') + (lr.stderr ? '\n' + lr.stderr : ''))}</div>` : ''}`;
      const run = async (override) => {
        if (override) { p.command = override; saveState(); }
        const b = box.querySelector('#knNetConsoleRun'); if (b) { b.disabled = true; b.textContent = 'Running…'; }
        const r = await KS.api('/network/console', {command: p.command || 'help', timeout: p.timeout || 8, allow_private: p.allow_private_targets !== false}).catch(e => ({success:false,stderr:e.message}));
        hostToolResults.set(String(node.id), r); updatePropertiesPanel(node);
      };
      box.querySelector('#knNetConsoleRun').onclick = () => run();
      box.querySelector('#knNetConsoleHelp').onclick = () => run('help');
      box.querySelector('#knNetConsoleRoute').onclick = () => run('ip route');
    } else {
      box.innerHTML = `<label>Network monitor</label><div class="kn-netmeta">Inline transparent packet tap with cumulative frame/byte counters.</div>`;
    }

    const r = KS.results && KS.results[node.id];
    if (r && r.outputs) {
      const status = r.outputs.status || (net.kind === 'host' ? r.outputs.status : null);
      if (status) box.insertAdjacentHTML('beforeend', `<div class="kn-netstat">${esc(JSON.stringify(status, null, 1))}</div>`);
      else if (net.kind === 'monitor') box.insertAdjacentHTML('beforeend', `<div class="kn-netstat">packets=${esc(r.outputs.packets)}  bytes=${esc(r.outputs.bytes)}\nlast=${esc(JSON.stringify(r.outputs.last || null))}</div>`);
    }
    container.insertBefore(box, container.firstChild);
  };

  // Palette search should find vendor/model names even though presets are not
  // separate templates.  We append them to the generic device description once
  // the library arrives; no backend/model data is changed by this convenience.
  const origLoad = KS.loadLibrary;
  KS.loadLibrary = async function () {
    const r = await origLoad.apply(this, arguments);
    const t = KS.byId && KS.byId.network_device;
    if (t && !t._networkKeywords) {
      t._networkKeywords = true;
      t.description += ' Presets: ' + presets().map(p => p.vendor + ' ' + p.model).join(', ') + '.';
    }
    return r;
  };
})();

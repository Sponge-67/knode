/* knode_backend.js — run and manage the backend from the UI (knode 0.6)
 *
 * A web page cannot start a process by itself, so knode ships a launcher (python knode.py or the
 * start-* scripts) that starts the server and opens this page. From then on everything is managed
 * here:
 *
 *   status dot / banner ... live connection state; offline banner with the start command, copy
 *                           button and automatic reconnection (back-off 2 → 10 s)
 *   Backend Manager ....... status (version, pid, uptime, Python, memory, packages, launcher),
 *                           restart / stop, clear cache, reload library; live sessions (end them);
 *                           settings (cache size, session idle timeout, time limit); install the
 *                           optional packages numpy / h5py; live log viewer with filter; connect to
 *                           another backend URL (remembered)
 *
 * Management endpoints are refused by the server for anything but localhost, so a backend reached
 * over the network can be used but not restarted or reconfigured from another machine.
 */
(function () {
  'use strict';
  const KS = window.KnodeSci, UI = window.KnodeUI;
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => escapeHtml(s === undefined || s === null ? '' : String(s));
  const BK = window.KnodeBackend = { online: null, retryIn: 0 };
  const DEFAULT_URL = (location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : 'http://127.0.0.1:5000';

  const css = `
  #knOffline{position:absolute;left:50%;top:12px;transform:translateX(-50%);z-index:60;background:#2a1d1f;border:1px solid #e74c3c;border-radius:10px;
    padding:10px 14px;display:none;gap:10px;align-items:center;font-size:12px;color:#f5d5d2;box-shadow:0 8px 24px #000a;max-width:92%}
  #knOffline.on{display:flex;flex-wrap:wrap}
  #knOffline code{background:#15161a;border:1px solid #3a3f55;border-radius:5px;padding:3px 8px;color:#ffd479;font:12px ui-monospace,Menlo,monospace}
  #knOffline button{background:#33262a;border:1px solid #6b3a3a;color:#f5d5d2;border-radius:6px;padding:3px 9px;cursor:pointer;font-size:11px}
  #knOffline button:hover{border-color:#e74c3c}
  #knRestarting{position:fixed;inset:0;background:rgba(10,11,14,.6);z-index:5000;display:none;align-items:center;justify-content:center;color:#dfe3ff;font-size:14px;flex-direction:column;gap:10px}
  #knRestarting.on{display:flex}
  #knRestarting .sp{width:34px;height:34px;border:3px solid #3a3f55;border-top-color:#7c8cff;border-radius:50%;animation:knspin 1s linear infinite}
  @keyframes knspin{to{transform:rotate(360deg)}}
  #knBackend .ks-box{width:min(860px,94vw);height:min(640px,88vh)}
  #knBackend .ks-body{display:flex;flex-direction:column;padding:0;min-height:0;flex:1}
  .bk-tabs{display:flex;gap:2px;padding:8px 12px 0;border-bottom:1px solid var(--line)}
  .bk-tabs div{padding:6px 12px;border-radius:6px 6px 0 0;cursor:pointer;font-size:12px;color:#aab0c0}
  .bk-tabs div.on{background:#23252d;color:#fff}
  .bk-main{flex:1;overflow:auto;padding:14px 16px;font-size:12px}
  .bk-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}
  .bk-row label{width:190px;color:#8a93a8}
  .bk-log{font:11px/1.45 ui-monospace,Menlo,monospace;background:#101115;border:1px solid var(--line);border-radius:6px;padding:8px;height:390px;overflow:auto;white-space:pre-wrap}
  .bk-log .warn{color:#f39c12}.bk-log .error{color:#e74c3c}.bk-log .t{color:#5d6373}
  .bk-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
  #ksDot{cursor:pointer}
  `;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // ====================================================================== low-level calls
  /** fetch with a timeout; resolves to parsed JSON (or throws). */
  async function call(path, opts = {}, timeout = 4000) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), timeout);
    try {
      const r = await fetch(BACKEND_URL + path, Object.assign({ signal: ctl.signal }, opts));
      const data = await r.json().catch(() => ({}));
      if (!r.ok && data.success === undefined) data.success = false;
      data._status = r.status;
      return data;
    } finally { clearTimeout(timer); }
  }
  const post = (path, body, timeout) => call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }, timeout);

  // ====================================================================== connection state
  let retryTimer = null, backoff = 2;

  /** Check the backend; on a state change update the UI (and reload the library when it comes back). */
  BK.check = async function (manual) {
    clearTimeout(retryTimer);
    let h = null;
    try { h = await call('/api/health', {}, 2500); if (!h.ok) h = null; } catch (e) { h = null; }
    const was = BK.online;
    BK.online = !!h; BK.health = h;
    if (h) {
      backoff = 2;
      if (was !== true) {                                   // (re)connected
        await KS.loadLibrary();
        if (was === false) KS.status(`<span class="ks-ok">Backend connected</span> — ${esc(h.version)} at ${esc(BACKEND_URL)}`);
      }
      retryTimer = setTimeout(BK.check, 15000);             // keep watching for drops
    } else {
      if (was !== false && window.KnodeStudio && KnodeStudio.live && KnodeStudio.live.on) KnodeStudio.toggleLive();
      retryTimer = setTimeout(BK.check, backoff * 1000);
      BK.retryIn = backoff; backoff = Math.min(10, backoff * 1.6);
      if (manual) KS.status('<span class="ks-err">Backend still offline</span>');
    }
    renderBanner();
    const dot = $('#ksDot');
    if (dot) { dot.style.background = h ? '#2ecc71' : '#e74c3c'; dot.title = h ? `backend ${h.version} — click for the Backend Manager` : 'backend offline — click for help'; }
    return !!h;
  };

  /** Show or hide the offline banner (start command, copy, retry, connect-to, retry countdown). */
  function renderBanner() {
    const b = $('#knOffline'); if (!b) return;
    if (BK.online !== false) { b.classList.remove('on'); return; }
    const custom = BACKEND_URL !== DEFAULT_URL;
    b.innerHTML = `<b>⚠ Backend offline</b><span>You can edit models; running needs the backend. Start it with</span>
      <code>python knode.py</code><button id="knCopyCmd" title="copy the command">copy</button>
      <span style="color:#b99">or double-click <b>start-windows.bat</b> / <b>start-mac.command</b> / <b>start.sh</b>.</span>
      <button id="knRetry">↻ Retry</button><button id="knConnect">Connect to…</button>
      <span style="color:#a88;font-size:11px">${custom ? `trying ${esc(BACKEND_URL)} · ` : ''}auto-retry every ${Math.round(BK.retryIn || 2)} s</span>`;
    b.classList.add('on');
    $('#knCopyCmd', b).onclick = () => { navigator.clipboard && navigator.clipboard.writeText('python knode.py'); KS.status('Copied: python knode.py'); };
    $('#knRetry', b).onclick = () => BK.check(true);
    $('#knConnect', b).onclick = () => BK.open('connection');
  }

  /** Point the UI at another backend (or back to the default) and reconnect. */
  BK.setUrl = async function (url) {
    url = (url || '').trim().replace(/\/+$/, '') || DEFAULT_URL;
    BACKEND_URL = url;
    try { if (url === DEFAULT_URL) localStorage.removeItem('knode.backendUrl'); else localStorage.setItem('knode.backendUrl', url); } catch (e) { /* ignore */ }
    BK.online = null;
    return BK.check(true);
  };

  // ====================================================================== restart / stop
  function overlay(on, text) {
    let o = $('#knRestarting');
    if (!o) { o = document.createElement('div'); o.id = 'knRestarting'; o.innerHTML = '<div class="sp"></div><div class="tx"></div>'; document.body.appendChild(o); }
    $('.tx', o).textContent = text || '';
    o.classList.toggle('on', on);
  }

  /** Restart the server and wait until it is back (a new process or a fresh start time). */
  BK.restart = async function () {
    const before = BK.health;
    let r;
    try { r = await post('/admin/restart'); } catch (e) { return KS.status(`<span class="ks-err">Restart failed: ${esc(e.message)}</span>`); }
    if (!r.success) return KS.status(`<span class="ks-err">${esc(r.error || 'restart refused')}</span>`);
    overlay(true, 'Restarting backend…');
    clearTimeout(retryTimer);
    const t0 = Date.now();
    while (Date.now() - t0 < 30000) {
      await new Promise(res => setTimeout(res, 400));
      try {
        const h = await call('/api/health', {}, 1500);
        if (h.ok && (!before || h.pid !== before.pid || h.started !== before.started)) {
          overlay(false); BK.online = null; await BK.check();
          KS.status(`<span class="ks-ok">Backend restarted</span> (pid ${h.pid})`);
          if ($('#knBackend.active')) BK.open(BK.tab);
          return true;
        }
      } catch (e) { /* still down */ }
    }
    overlay(false); BK.check();
    KS.status('<span class="ks-err">Backend did not come back within 30 s — start it again with python knode.py</span>');
    return false;
  };

  /** Stop the server (the launcher exits too). */
  BK.stop = async function () {
    if (!confirm('Stop the knode backend? Running models needs it; you can start it again with python knode.py.')) return;
    try { await post('/admin/shutdown'); } catch (e) { /* connection may drop */ }
    setTimeout(() => { BK.online = null; BK.check(); }, 900);
    document.querySelector('#knBackend') && document.querySelector('#knBackend').classList.remove('active');
  };

  // ====================================================================== Backend Manager
  let logTimer = null, logSince = 0;
  const TABS = [['status', 'Status'], ['sessions', 'Live sessions'], ['settings', 'Settings'], ['packages', 'Packages'], ['logs', 'Logs'], ['connection', 'Connection']];

  /** Open a menu at screen position (x, y), closing any other open menu first. */
  BK.open = async function (tab) {
    BK.tab = tab || BK.tab || 'status';
    const body = KS.modal('knBackend', 'Backend Manager', 860);
    body.innerHTML = `<div class="bk-tabs">${TABS.map(([k, l]) => `<div data-t="${k}" class="${k === BK.tab ? 'on' : ''}">${l}</div>`).join('')}</div><div class="bk-main" id="bkMain">Loading…</div>`;
    $('.bk-tabs', body).onclick = e => { const t = e.target.dataset.t; if (t) BK.open(t); };
    clearInterval(logTimer);
    const main = $('#bkMain', body);
    if (BK.tab === 'connection') return renderConnection(main);
    await BK.check();
    if (!BK.online) { main.innerHTML = offlineHelp(); return; }
    let info;
    try { info = await call('/admin/info'); } catch (e) { info = { success: false, error: e.message }; }
    if (info._status === 403 || info.success === false) {
      main.innerHTML = `<p>Connected to <code>${esc(BACKEND_URL)}</code> (${esc(BK.health.version)}).</p><p class="ks-warn">${esc(info.error || 'Management is only available on the backend\'s own machine.')}</p>`;
      return;
    }
    ({ status: renderStatus, sessions: renderSessions, settings: renderSettings, packages: renderPackages, logs: renderLogs })[BK.tab](main, info);
  };

  /** Backend Manager content while offline: why a page cannot start the server and how to start it. */
  function offlineHelp() {
    return `<h3 style="margin:0 0 6px;color:#eef">Backend offline</h3>
      <p>The backend is a small Python server that runs your models. A web page cannot start programs, so start it once with the launcher —
      it opens this page, restarts the server when you press <b>Restart</b> here, and restarts it automatically after a crash:</p>
      <pre style="background:#15161a;border:1px solid #2e3039;border-radius:6px;padding:10px;color:#ffd479">python knode.py            # or double-click start-windows.bat / start-mac.command / start.sh
python knode.py --port 8080 --no-browser</pre>
      <p>Requirements: Python 3.8+ and <code>pip install flask</code> (numpy and h5py optional — installable from the Packages tab once running).</p>
      <p>Trying <code>${esc(BACKEND_URL)}</code>; retrying automatically. <button class="ks-btn" onclick="KnodeBackend.check(true).then(ok=>ok&&KnodeBackend.open())">↻ Retry now</button>
      <button class="ks-btn" onclick="KnodeBackend.open('connection')">Use another address…</button></p>`;
  }

  const fmtDur = (s) => s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.floor(s / 3600)} h ${Math.floor(s % 3600 / 60)} min`;

  /** Backend Manager ▸ Status: health tiles, environment table, restart / reload / clear cache / stop. */
  function renderStatus(main, info) {
    const pk = info.packages;
    main.innerHTML = `
      <div class="ks-grid">
        <div class="ks-kpi"><b><span class="bk-dot" style="background:#2ecc71"></span> online</b><span>${esc(BACKEND_URL)}</span></div>
        <div class="ks-kpi"><b>${esc(info.version)}</b><span>knode backend</span></div>
        <div class="ks-kpi"><b>${fmtDur(info.uptime_s)}</b><span>uptime · pid ${info.pid}</span></div>
        <div class="ks-kpi"><b>${info.peak_memory_mb ? Math.round(info.peak_memory_mb) + ' MB' : '—'}</b><span>peak memory</span></div>
        <div class="ks-kpi"><b>${info.sessions.length}</b><span>live sessions</span></div>
        <div class="ks-kpi"><b>${info.cache.entries}/${info.cache.capacity}</b><span>cached results</span></div>
        <div class="ks-kpi"><b>${info.compiled_nodes}</b><span>compiled node codes</span></div>
        <div class="ks-kpi"><b>${info.supervised ? 'launcher' : 'direct'}</b><span>${info.supervised ? 'restarts via knode.py' : 'restart re-executes server.py'}</span></div>
        <div class="ks-kpi"><b>${info.workers_in_use || 'serial'}</b><span>parallel workers · ${info.cpu_count} CPU core${info.cpu_count === 1 ? '' : 's'}</span></div>
      </div>
      <table class="ks-t">
        <tr><td>Python</td><td>${esc(info.python)} — <code>${esc(info.executable)}</code></td></tr>
        <tr><td>Platform</td><td>${esc(info.platform)}</td></tr>
        <tr><td>Folder</td><td><code>${esc(info.cwd)}</code></td></tr>
        <tr><td>User node types</td><td><code>${esc(info.user_library)}</code></td></tr>
        <tr><td>Packages</td><td>flask ${esc(pk.flask || '—')} · numpy ${pk.numpy ? esc(pk.numpy) : '<span class="ks-warn">not installed</span>'} · h5py ${pk.h5py ? esc(pk.h5py) : '<span class="ks-warn">not installed</span>'}</td></tr>
      </table>
      <div class="bk-row" style="margin-top:14px">
        <button class="ks-btn pri" id="bkRestart">↻ Restart backend</button>
        <button class="ks-btn" id="bkReload">Reload node library</button>
        <button class="ks-btn" id="bkCache">Clear result cache</button>
        <span style="flex:1"></span>
        <button class="ks-btn" id="bkStop" style="border-color:#6b3a3a;color:#ff8a80">⏻ Stop backend</button>
      </div>
      <p style="color:#8a93a8">Restart reloads Python code, newly installed packages and the user library. Models on the canvas are kept.</p>`;
    $('#bkRestart', main).onclick = () => BK.restart();
    $('#bkReload', main).onclick = async () => { await KS.loadLibrary(); KS.status('Library reloaded'); };
    $('#bkCache', main).onclick = async () => { await post('/cache/clear'); BK.open('status'); };
    $('#bkStop', main).onclick = () => BK.stop();
  }

  /** Backend Manager ▸ Live sessions: table of server-side sessions with an 'end' button each. */
  function renderSessions(main, info) {
    main.innerHTML = `<p>Live-mode sessions keep a running model in the backend. Sessions idle for more than ${Math.round(info.settings.session_idle_minutes)} min are ended automatically.</p>
      <table class="ks-t"><tr><th>id</th><th>nodes</th><th>steps</th><th>t</th><th>idle</th><th>state</th><th></th></tr>
      ${info.sessions.map(s => `<tr><td><code>${esc(s.id)}</code>${window.KnodeStudio && KnodeStudio.live && KnodeStudio.live.sid === s.id ? ' <span class="ks-ok">(this tab)</span>' : ''}</td><td>${s.nodes}</td><td>${s.steps}</td><td>${KS.fmt(s.t)}</td><td>${fmtDur(s.idle_s)}</td><td>${esc(s.stopped || 'running')}</td>
        <td><button class="ks-btn" data-kill="${esc(s.id)}">end</button></td></tr>`).join('') || '<tr><td colspan="7" style="color:#777">no live sessions</td></tr>'}</table>`;
    main.onclick = async e => {
      const id = e.target.dataset.kill; if (!id) return;
      await call('/admin/sessions/' + encodeURIComponent(id), { method: 'DELETE' });
      if (window.KnodeStudio && KnodeStudio.live && KnodeStudio.live.sid === id) KnodeStudio.toggleLive();
      BK.open('sessions');
    };
  }

  /** Backend Manager ▸ Settings: cache capacity, session idle timeout, default time limit. */
  function renderSettings(main, info) {
    const s = info.settings;
    main.innerHTML = `
      <div class="bk-row"><label>Result cache capacity (entries)</label><input class="ks-input" id="bkCacheN" type="number" value="${s.cache_size}" min="0" style="width:110px"><span style="color:#777">LRU cache for Run once; 0 disables it</span></div>
      <div class="bk-row"><label>Live-session idle timeout (min)</label><input class="ks-input" id="bkIdle" type="number" value="${Math.round(s.session_idle_minutes)}" min="1" style="width:110px"></div>
      <div class="bk-row"><label>Parallel workers for studies</label><input class="ks-input" id="bkWorkers" type="number" value="${s.workers}" min="-1" max="64" style="width:110px">
        <span style="color:#777">0 = automatic (cores − 1; serial on 1 core) · −1 = serial · n = n processes. Used by sweeps, Monte Carlo, scenarios, calibration.</span></div>
      <div class="bk-row"><label>Default time limit per run (s)</label><input class="ks-input" id="bkLimit" type="number" value="${s.time_limit}" min="1" style="width:110px"><span style="color:#777">protects against endless loops in node code</span></div>
      <div class="bk-row"><label></label><button class="ks-btn pri" id="bkSave">Apply</button><span id="bkMsg" style="color:#2ecc71"></span></div>
      <p style="color:#8a93a8">Settings apply immediately and last until the backend restarts.</p>`;
    $('#bkSave', main).onclick = async () => {
      const r = await post('/admin/settings', { cache_size: +$('#bkCacheN', main).value, session_idle_minutes: +$('#bkIdle', main).value,
        time_limit: +$('#bkLimit', main).value, workers: +$('#bkWorkers', main).value });
      $('#bkMsg', main).textContent = r.settings ? '✓ applied' : (r.error || 'failed');
    };
  }

  /** Backend Manager ▸ Packages: install numpy / h5py into the backend's Python (then offer a restart). */
  function renderPackages(main, info) {
    const rows = [['numpy', 'faster FFT and binomial sampling; required by the 2-D Field (PDE) node'], ['h5py', 'real HDF5 export / import with simulation traces']];
    main.innerHTML = `<p>knode needs only Flask. These optional packages unlock extra features and can be installed into the backend's Python
      (<code>${esc(info.executable)}</code>) from here:</p>
      <table class="ks-t">${rows.map(([p, d]) => `<tr><td><b>${p}</b></td><td>${d}</td><td>${info.packages[p] ? `<span class="ks-ok">✓ ${esc(info.packages[p])}</span>` : `<button class="ks-btn pri" data-pkg="${p}">Install</button>`}</td></tr>`).join('')}</table>
      <pre id="bkOut" class="bk-log" style="height:220px;display:none"></pre>`;
    main.onclick = async e => {
      const p = e.target.dataset.pkg; if (!p) return;
      e.target.disabled = true; e.target.textContent = 'installing…';
      const out = $('#bkOut', main); out.style.display = 'block'; out.textContent = `pip install ${p} …`;
      let r;
      try { r = await post('/admin/install', { package: p }, 620000); } catch (err) { r = { success: false, output: String(err) }; }
      out.textContent = r.output || r.error || '';
      if (r.success && confirm(`${p} installed. Restart the backend now to load it?`)) BK.restart();
      else if (!r.success) { e.target.disabled = false; e.target.textContent = 'Retry install'; }
    };
  }

  /** Backend Manager ▸ Logs: incremental polling of the server log with filter and follow. */
  function renderLogs(main) {
    main.innerHTML = `<div class="bk-row"><input class="ks-input" id="bkFilter" placeholder="filter…" style="flex:1"><label style="width:auto"><input type="checkbox" id="bkFollow" checked> follow</label>
      <button class="ks-btn" id="bkClear">clear view</button></div><div class="bk-log" id="bkLog"></div>`;
    const box = $('#bkLog', main), filter = $('#bkFilter', main);
    logSince = 0;
    const lines = [];
    const draw = () => {
      const q = filter.value.toLowerCase();
      box.innerHTML = lines.filter(l => !q || l[3].toLowerCase().includes(q)).map(l =>
        `<div class="${esc(l[2])}"><span class="t">${new Date(l[1] * 1000).toLocaleTimeString()}</span> ${esc(l[3])}</div>`).join('');
      if ($('#bkFollow', main).checked) box.scrollTop = box.scrollHeight;
    };
    const poll = async () => {
      if (!$('#knBackend.active') || BK.tab !== 'logs') return clearInterval(logTimer);
      try { const r = await call('/admin/logs?since=' + logSince); if (r.lines) { lines.push(...r.lines); logSince = r.last; if (lines.length > 3000) lines.splice(0, lines.length - 3000); draw(); } } catch (e) { /* offline */ }
    };
    filter.oninput = draw;
    $('#bkClear', main).onclick = () => { lines.length = 0; draw(); };
    poll(); logTimer = setInterval(poll, 1500);
  }

  /** Backend Manager ▸ Connection: test / switch the backend address or return to the default. */
  function renderConnection(main) {
    main.innerHTML = `<p>The editor talks to one backend. By default that is the server that delivered this page (<code>${esc(DEFAULT_URL)}</code>).
      You can point it at another knode backend — for example one on a workstation you reach through an SSH tunnel.</p>
      <div class="bk-row"><label>Backend address</label><input class="ks-input" id="bkUrl" value="${esc(BACKEND_URL)}" style="flex:1"></div>
      <div class="bk-row"><label></label><button class="ks-btn" id="bkTest">Test</button><button class="ks-btn pri" id="bkUse">Connect</button><button class="ks-btn" id="bkDefault">Use default</button><span id="bkCMsg"></span></div>
      <p style="color:#8a93a8">Remote backends can run models but can only be restarted or configured from their own machine. Executing a model runs its Python code on the backend — connect only to backends you trust.</p>`;
    const msg = (t, ok) => { const m = $('#bkCMsg', main); m.textContent = t; m.style.color = ok ? '#2ecc71' : '#e74c3c'; };
    $('#bkTest', main).onclick = async () => {
      const url = $('#bkUrl', main).value.trim().replace(/\/+$/, '');
      try { const r = await fetch(url + '/api/health'); const h = await r.json(); msg(h.ok ? `✓ knode ${h.version}, Python ${h.python}` : 'not a knode backend', h.ok); }
      catch (e) { msg('✗ cannot reach ' + url, false); }
    };
    $('#bkUse', main).onclick = async () => { const ok = await BK.setUrl($('#bkUrl', main).value); msg(ok ? '✓ connected' : '✗ offline — will keep retrying', ok); };
    $('#bkDefault', main).onclick = async () => { $('#bkUrl', main).value = DEFAULT_URL; const ok = await BK.setUrl(DEFAULT_URL); msg(ok ? '✓ connected' : '✗ offline', ok); };
  }

  // ====================================================================== menus & wiring
  const prevExtend = UI.extendMenus;
  /** Add this layer's entries to the menubar definition (each layer wraps the previous one's extension). */
  UI.extendMenus = function (m) {
    m = prevExtend ? prevExtend(m) : m;
    const i = m.findIndex(x => x[0] === 'Help');
    m.splice(i, 0, ['Backend', [
      ['Backend Manager…', () => BK.open('status')],
      ['Restart backend', () => BK.restart()],
      ['Reconnect', () => BK.check(true)],
      '-',
      ['Live sessions', () => BK.open('sessions')], ['Settings', () => BK.open('settings')], ['Install packages', () => BK.open('packages')],
      ['Logs', () => BK.open('logs')], ['Connect to another backend…', () => BK.open('connection')],
      '-',
      ['Stop backend', () => BK.stop()],
    ]]);
    return m;
  };

  document.addEventListener('DOMContentLoaded', () => {
    const b = document.createElement('div'); b.id = 'knOffline'; $('#canvasContainer').appendChild(b);
    const dot = $('#ksDot'); if (dot) dot.onclick = () => BK.open(BK.online ? 'status' : 'connection');
    if (UI.renderMenubar) UI.renderMenubar();
    setTimeout(() => BK.check(), 600);
  });
})();

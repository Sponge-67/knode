/* knode_about.js — the About & Guide centre (Help ▸ About knode, F1)
 *
 * A tabbed, searchable in-app reference. Everything that can be generated from the running
 * application is generated (node catalogue, category counts, backend status, examples), the rest
 * is structured data below so it stays easy to maintain:
 *
 *   Overview · Features · Node library · How it runs · Science & methods · Shortcuts ·
 *   Files & API · Performance · History & credits
 */
(function () {
  'use strict';
  const KS = window.KnodeSci, UI = window.KnodeUI;
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => escapeHtml(s === undefined || s === null ? '' : String(s));
  const VERSION = '0.7.0';

  // ------------------------------------------------------------------ styles
  const css = `
  #knAbout .ks-box{width:min(1080px,94vw);height:min(760px,90vh)}
  #knAbout .ks-body{padding:0;display:flex;min-height:0;flex:1}
  .ab-nav{width:190px;flex-shrink:0;border-right:1px solid var(--line);padding:10px 6px;overflow:auto;background:#17181d}
  .ab-nav div{padding:7px 10px;border-radius:6px;cursor:pointer;font-size:12px;color:#aab0c0;display:flex;gap:8px;align-items:center}
  .ab-nav div:hover{background:#23252d}.ab-nav div.on{background:#2b3163;color:#fff}
  .ab-main{flex:1;overflow:auto;padding:18px 24px 30px;font-size:12.5px;line-height:1.6;color:#c9ccd6}
  .ab-main h3{font-size:17px;color:#eef;margin:0 0 4px}.ab-main h4{font-size:13px;color:#dfe3ff;margin:18px 0 6px}
  .ab-main p{margin:6px 0}.ab-main code{font:11px ui-monospace,Menlo,Consolas,monospace;background:#23252d;padding:1px 5px;border-radius:4px;color:#ffd479}
  .ab-main pre{font:11px/1.5 ui-monospace,Menlo,Consolas,monospace;background:#15161a;border:1px solid var(--line);border-radius:6px;padding:10px 12px;overflow:auto;color:#d8dcf0}
  .ab-lead{font-size:13.5px;color:#dfe3ef}
  .ab-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px;margin:10px 0}
  .ab-card{background:#1d1e24;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
  .ab-card b{color:#eef;display:block;margin-bottom:3px}.ab-card small{color:#8a93a8;display:block;margin-top:6px;font-size:10.5px}
  .ab-kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin:12px 0}
  .ab-kpi{background:#1d1e24;border:1px solid var(--line);border-radius:8px;padding:8px 10px}
  .ab-kpi b{display:block;font-size:20px;color:#fff}.ab-kpi span{font-size:10.5px;color:#8a93a8}
  .ab-feat{border-bottom:1px solid #24262e;padding:8px 0;display:grid;grid-template-columns:220px 1fr;gap:12px}
  .ab-feat b{color:#e8ebff}.ab-feat .how{color:#8a93a8;font-size:11px;margin-top:2px}
  .ab-tag{display:inline-block;font-size:9.5px;padding:0 6px;border-radius:9px;border:1px solid #3a3f55;color:#9fb0ff;margin-left:4px}
  .ab-search{width:100%;margin:6px 0 12px;background:#15161a;border:1px solid var(--line2);border-radius:6px;color:#ddd;padding:6px 10px;font-size:12px}
  table.ab-t{border-collapse:collapse;width:100%;font-size:11.5px;margin:6px 0}
  table.ab-t td,table.ab-t th{padding:5px 8px;border-bottom:1px solid #24262e;text-align:left;vertical-align:top}
  table.ab-t th{color:#8a93a8;font-weight:500}
  .ab-cat{margin:16px 0 6px;display:flex;align-items:center;gap:8px;font-weight:600;color:#e8ebff}
  .ab-cat i{width:10px;height:10px;border-radius:3px;display:inline-block}
  .ab-node{padding:6px 0 6px 18px;border-bottom:1px solid #212329}
  .ab-node b{color:#e6e9ff}.ab-node .pt{font:10.5px ui-monospace,monospace;color:#8a93a8}
  .ab-good{color:#2ecc71}.ab-warn{color:#f39c12}
  kbd{background:#2a2c38;border:1px solid var(--line2);border-radius:4px;padding:1px 6px;font:10.5px ui-monospace,monospace}
  `;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // ------------------------------------------------------------------ feature catalogue (data)
  // [area, [[feature, description, how to use, tag?], …]]
  const FEATURES = [
    ['Building models', [
      ['Node library', 'Over 80 ready-made node types in 13 categories, from constants and math to epidemics, neurons, PID controllers, PDEs and design tools. Every node carries its equations, defaults, description and literature references.', 'Sidebar (drag onto the canvas) · Tab · double-click the canvas'],
      ['Universal nodes', 'Nodes that are modelling formalisms rather than single models: Formula Block, Dynamic System (ODEs), Difference Equations, Reaction Network, State Machine, Agent-Based Model, Network Dynamics, 2-D Field (PDE), Transfer Function, Lookup Table, Python Script. Their ports are generated from what you write.', 'Sidebar ▸ Universal'],
      ['Dynamic ports', 'Add an equation and an output port appears; list an input name and an input port appears. Wires on ports that still exist are kept.', 'Edit the node\'s parameters'],
      ['Any Python', 'Every node is editable Python with math, numpy (np) and knode\'s numerical library (ks) available. Inputs bind to arguments by name.', 'Double-click a node · ⚙ in Properties'],
      ['Link-drag search', 'Drag a wire from a port into empty space, pick a node — it is created and connected.', 'Drag from any port', 'Blender · Unreal · ComfyUI'],
      ['Send / Receive', 'Wireless named channels: a Send node transmits to every Receive node with the same channel. Drawn as faint ghost links.', 'Model ▸ Add Send / Receive pair', 'Node-RED'],
      ['Globals & expressions', 'Model-wide variables in a Globals node; any parameter can be an expression like =R0*gamma or =P("Room", "C"). Sweeping a global updates every parameter that uses it.', 'ƒ next to a parameter', 'Houdini · Blender drivers'],
    ]],
    ['Wires & ports', [
      ['Typed wires & ports', 'After a run, wires and ports are coloured and shaped by the value they carry: number, boolean, text, list (thicker, diamond), 2-D field, table.', 'View ▸ Colour wires by data type', 'Blender sockets'],
      ['Wire styles', 'Smart curves that swing around for feedback loops, classic bezier, straight, orthogonal (circuit-style) or step — globally or per wire.', 'View ▸ Wire style · wire right-click ▸ Style', 'Simulink · Unreal'],
      ['Port tooltips', 'Hover a port: name, direction, data type, current value, wires/capacity, where it connects, and what an unconnected input falls back to.', 'Hover a port', 'Unreal · Houdini'],
      ['Connection helpers', 'While dragging a wire, every compatible port glows and the wire snaps to the nearest one within reach.', 'Drag from a port'],
      ['Insert on wire', 'Drag a free node onto a wire — the wire highlights and the node is spliced in when you drop it.', 'Drag a node onto a wire', 'Blender · Nuke'],
      ['Reroute dots', 'Double-click a wire to add a dot you can drag to route wires around other nodes (a real pass-through node).', 'Double-click a wire', 'Blender · Unreal · Nuke'],
      ['Knife', 'Hold Y and drag across wires to cut them; undoable.', 'Y + drag', 'Houdini · Blender'],
      ['Quick constant', 'Alt+click an unconnected input to feed it a Constant carrying the value the input was falling back to.', 'Alt+click an input', 'ComfyUI widgets'],
      ['Flow animation', 'Dots travel along the wires while the model runs live.', 'Live mode', 'TouchDesigner'],
    ]],
    ['Right-click menus', [
      ['Context menus', 'Right-click decides what is under the mouse — port, node, wire, frame or canvas — and shows the actions for exactly that: add nodes from any category or recent list, flags, rename, colour, connections, group, node type, insert on wire, per-wire style, disconnect, plot, pin, backend and more. Keyboard navigable.', 'Right-click · ↑ ↓ → ← Enter Esc'],
    ]],
    ['Backend', [
      ['One-command start', 'python knode.py (or double-click start-windows.bat / start-mac.command / start.sh) starts the backend, opens the editor and supervises the server.', 'python knode.py'],
      ['Backend Manager', 'Status, restart, stop, live sessions, settings (cache size, session timeout, time limit), package installation (numpy, h5py) and a live log — all from the UI.', 'Backend menu · click the status dot'],
      ['Offline banner & reconnection', 'When the backend is unreachable the editor keeps working, shows how to start it and reconnects automatically.', 'Automatic'],
      ['Remote backends', 'Point the editor at another knode backend (e.g. through an SSH tunnel). Management actions stay local-only for safety.', 'Backend ▸ Connect to another backend'],
    ]],
    ['Organising large models', [
      ['Groups (hierarchy)', 'Pack a selection into one group node; boundary wires become Group Input / Group Output ports. Groups nest to any depth and each copy keeps its own state.', 'Ctrl+G · double-click to enter · Esc to leave · Ctrl+Shift+G to ungroup'],
      ['Frames', 'Titled, coloured backdrops that move the nodes inside them.', 'Ctrl+J · drag the title · double-click to rename · click the dot for colour', 'Blender · Nuke'],
      ['Node Designer', 'Create your own node types with ports, parameter widgets (sliders, selects, units, help) and code; test, save to your library, share as JSON, update all instances.', 'Model ▸ New node type · ＋ in the sidebar'],
      ['Find, minimap, subtitles', 'Search nodes by name or type; navigate with the minimap; every node shows its key equation or configuration.', 'Ctrl+F · M'],
    ]],
    ['Running models', [
      ['Run once', 'A single pass in dependency order. Algebraic loops are solved by fixed-point iteration. Only nodes whose code, parameters or inputs changed are recomputed (incremental cache).', 'Ctrl+Enter · ▶ Run'],
      ['Simulate', 'Fixed-step time integration with persistent node state; feedback loops are allowed (one-step delay at the loop break). Every numeric output is recorded.', 'Ctrl+Shift+Enter · ▶▶ Simulate'],
      ['Live mode', 'The model streams from a server session while you edit: parameter changes apply instantly without restarting; structural edits restart automatically.', 'Space · ● in the header', 'TouchDesigner · Max/MSP'],
      ['Node flags', 'Bypass (pass inputs through), Freeze (pin last outputs), Cache on/off, Break-if condition that pauses a simulation and selects the node.', 'Properties ▸ Flags · Ctrl+E · Ctrl+Shift+L', 'Houdini · n8n · Unreal'],
      ['Auto re-run', 'Re-runs the last Run/Simulate after every parameter edit.', '⟳ auto'],
    ]],
    ['Seeing results', [
      ['Values on the canvas', 'Outputs are printed under each node with a sparkline of their history; errors are outlined with their line number; 2-D fields get heat-map thumbnails.', 'Automatic'],
      ['Wire probes', 'Hover any wire to read the value it carries.', 'Hover', 'LabVIEW'],
      ['Plot panel', 'Time series, phase portraits (any series as x), arrays, heat-maps, log scale, normalisation, crosshair read-out, CSV and PNG export.', 'P'],
      ['Kept runs & scenarios', 'Keep a run to compare against later runs (dashed overlay); define parameter scenarios and run them side by side.', '📌 keep · Run ▸ Scenarios', 'Houdini takes · Nuke A/B'],
      ['Dashboard', 'Sliders, toggles, selects, readouts, gauges and sparklines pinned from any node; full-screen presentation mode.', '📌 in Properties · Ctrl+Shift+D', 'LabVIEW front panel'],
    ]],
    ['Science & analysis', [
      ['Parameter sweeps', 'Vary one parameter (linear or logarithmic spacing) and reduce a simulated output to final / max / min / mean / integral / time-of-max.', 'Run ▸ Parameter study'],
      ['Monte Carlo & sensitivity', 'Latin-hypercube sampling of uncertain parameters (uniform, normal, lognormal, triangular); output distribution, 90 % interval and Spearman rank sensitivity.', 'Run ▸ Parameter study ▸ Monte Carlo'],
      ['Calibration & optimisation', 'Fit parameters to measured data (least squares, R², RMSE) or minimise / maximise any output with differential evolution or Nelder–Mead.', 'Run ▸ Calibrate / optimise', 'Grasshopper Galapagos'],
      ['Graph analysis', 'Feedback loops and their back edges, DAG depth, critical path (weighted by measured run time), betweenness and PageRank heat-maps, lint.', 'Run ▸ Graph analysis'],
      ['Verified numerics', 'Every built-in model is tested against an analytic solution, a conservation law or an independent implementation (96 automated tests in total).', 'python tests/test_*.py'],
    ]],
    ['Files & sharing', [
      ['JSON / YAML / XML export', 'The whole model; JSON also carries frames, dashboard and scenarios.', 'Ctrl+S · File ▸ Export'],
      ['PNG with embedded model', 'Export an image of the canvas that also contains the model; drop it back onto the canvas to open it.', 'File ▸ Export image with model', 'ComfyUI'],
      ['Drag & drop files', 'Drop .json or knode .png files onto the canvas to open them; drop node-type files to open them in the Node Designer.', 'Drag a file onto the canvas'],
      ['HDF5', 'Real HDF5 files with simulation traces as datasets when h5py is installed.', 'File ▸ Export ▸ HDF5'],
      ['Headless CLI', 'Run, simulate, sweep and analyse saved models from the command line or CI.', 'python knode_cli.py …'],
      ['Autosave', 'The model is saved in the browser a second after each change.', 'File ▸ Restore autosave'],
    ]],
  ];

  const SHORTCUTS = [
    ['Building', [['Tab', 'node library at the mouse'], ['double-click canvas', 'node library'], ['drag from sidebar', 'place a node'], ['drag wire to empty space', 'add & connect a node'],
      ['double-click node', 'edit code / open group'], ['Ctrl+C / Ctrl+V / Ctrl+D', 'copy / paste / duplicate'], ['Delete', 'delete selection (or selected frame)'], ['Ctrl+A', 'select all']]],
    ['Wires & ports', [['double-click wire', 'insert reroute dot'], ['Y + drag', 'knife: cut wires'], ['Alt+click input', 'feed a Constant'], ['drag node onto wire', 'insert it'], ['right-click', 'context menu for port / node / wire / frame / canvas']]],
    ['Organising', [['Ctrl+G', 'group selection'], ['Ctrl+Shift+G', 'ungroup'], ['Esc', 'leave group · close dialog'], ['Ctrl+J', 'frame selection'], ['Ctrl+F', 'find node'],
      ['Ctrl+E', 'toggle bypass'], ['Ctrl+Shift+L', 'toggle freeze']]],
    ['Running', [['Ctrl+Enter', 'run once'], ['Ctrl+Shift+Enter', 'simulate'], ['Space', 'live mode play / pause']]],
    ['View', [['F', 'frame all / selection'], ['P', 'plot panel'], ['M', 'minimap'], ['Ctrl+B', 'library sidebar'], ['Ctrl+Shift+D', 'dashboard'], ['wheel', 'zoom'], ['drag empty canvas', 'pan'], ['Ctrl+drag', 'box-select']]],
    ['Files & history', [['Ctrl+S', 'export'], ['Ctrl+O', 'open JSON / PNG'], ['Ctrl+Z', 'undo'], ['Ctrl+Shift+Z / Ctrl+Y', 'redo'], ['Ctrl+Shift+N', 'new node type'], ['F1', 'this guide'], ['?', 'shortcut sheet']]],
  ];

  const METHODS = [
    ['Classical Runge–Kutta (RK4)', '4th-order fixed-step ODE integration with automatic sub-stepping per node', 'Kutta 1901', 'global error ∝ h⁴ (tested: observed order 3.8–4.2)'],
    ['Dormand–Prince RK5(4)', 'adaptive embedded Runge–Kutta for the ODE Solver node', 'Dormand & Prince 1980', 'harmonic oscillator closes its orbit to 10⁻⁷'],
    ['Gillespie direct method (SSA)', 'exact stochastic simulation of reaction networks', 'Gillespie 1977', 'mean of decay runs matches A₀e^{-kt}'],
    ['FTCS with stability control', 'explicit heat equation, sub-stepped so r = αΔt/Δx² ≤ 0.4', 'forward-time centred-space; von Neumann stability requires r ≤ ½', 'converges to the linear steady state'],
    ['Exact exponential updates', 'RC circuits, first-order filters and logistic growth use closed-form steps', '—', 'match analytic solutions to 10⁻⁹'],
    ['Tarjan SCC', 'finds feedback loops; the scheduler orders their condensation topologically', 'Tarjan 1972', 'linear in nodes + edges'],
    ['Gauss–Seidel coupling', 'loops in simulations read the previous step at back edges; algebraic loops iterate to a fixed point', '—', 'x = 0.5x + 1 converges to 2'],
    ['Latin hypercube sampling', 'stratified Monte Carlo design (one sample per stratum per parameter)', 'McKay, Beckman & Conover 1979', ''],
    ['Spearman rank correlation', 'global, monotone sensitivity of an output to each uncertain input', 'Spearman 1904', ''],
    ['Differential evolution', 'rand/1/bin global optimiser for calibration', 'Storn & Price 1997', 'recovers r, K of logistic growth from data'],
    ['Nelder–Mead simplex', 'derivative-free local optimiser', 'Nelder & Mead 1965', 'Rosenbrock minimum (1, 1) to 10⁻⁴'],
    ['Brandes betweenness', 'bottleneck nodes in the model graph', 'Brandes 2001', ''],
    ['PageRank', 'influence ranking of nodes', 'Page et al. 1999', 'sums to 1'],
    ['Watts–Strogatz / Barabási–Albert', 'small-world and scale-free networks for Network Dynamics', 'Watts & Strogatz 1998 · Barabási & Albert 1999', ''],
  ];

  const HISTORY = [
    ['0.7', 'CPU/GPU utilisation: parallel studies on worker processes (bit-identical to serial), generation-parallel differential evolution, 2.3–2.7× live-mode throughput (pipelining + adaptive chunks), zero idle CPU in the editor, coalesced rendering, native wire paths with culling, opaque canvas, memoised text layout, vectorised Kuramoto, 3× faster JSON path; Nelder–Mead convergence fix; every function documented.'],
    ['0.6', 'Run and manage the backend from the UI (launcher with supervisor, Backend Manager, offline banner, reconnection, remote backends); typed wires and ports, smart / orthogonal routing, port tooltips, compatible-port highlighting and snapping, insert-on-wire, reroute dots, knife, quick constants, flow animation; context-sensitive right-click menus.'],
    ['0.5', 'Performance: 1.5–2.7× faster simulations, 3–10× faster scheduling of large models, 4× faster canvas rendering of large graphs (culling, level of detail, cached sparklines). Extensive documentation in code, this About centre, architecture guide, benchmark suite, 8 equivalence tests.'],
    ['0.4', 'Features adopted from other node systems: live mode, dashboard, node flags, incremental cache, frames, link-drag search, wire probes, wireless links, globals & expressions, scenarios, calibration, PNG models. Fixed undo aliasing and the redo shortcut (present since 0.1.1).'],
    ['0.3', 'Universal nodes with parameter-derived ports, hierarchical groups, Node Designer and user library, menubar, sidebar, minimap, 2-D heat-maps.'],
    ['0.2', 'Execution engine (loops, simulation, sweeps, Monte Carlo, analysis), 64-model scientific library with verification tests, plot panel, CLI; fixed the unreachable run endpoint and code-overwrite bugs of 0.1.1.'],
    ['0.1.1', 'Original canvas editor: node classes, typed ports, animated wires, undo/redo, import/export, per-node Python via Flask.'],
  ];

  const PERF7 = [
    ['Idle editor: animation frames / timers per second', '68 / 8', '0 / 0', 'idle'],
    ['Live mode throughput (Lotka–Volterra), best manual setting vs auto', '22 625 steps/s', '53 162 steps/s', '2.3×'],
    ['Live mode throughput (PID loop)', '14 875 steps/s', '40 826 steps/s', '2.7×'],
    ['Wire drawing, 218 wires (JavaScript time)', '0.96 ms', '0.24 ms', '4.0×'],
    ['Canvas frame, 120 nodes / 218 wires @ 100 % zoom', '5.7 ms', '4.8 ms', '1.2×'],
    ['Canvas frame @ 20 % zoom', '6.3 ms', '4.9 ms', '1.3×'],
    ['Renders for a burst of 50 mouse moves', '3', '1', '3×'],
    ['Simulation 50-node chain incl. HTTP/JSON', '375 ms', '261 ms', '1.4×'],
    ['JSON overhead of that response', '56 ms', '18 ms', '3.1×'],
    ['Kuramoto N = 200, 400 steps (numpy)', '83 ms', '27 ms', '3.1×'],
  ];

  const INSPIRED = ['TouchDesigner', 'Max/MSP', 'Pure Data', 'LabVIEW', 'Houdini', 'Blender', 'Unreal Blueprints', 'ComfyUI', 'n8n', 'Node-RED', 'Nuke', 'Grasshopper', 'Simulink', 'Substance Designer'];

  const PERF = [
    ['Gain chain ×50, 2 000 steps', '692.6 ms', '271.9 ms', '2.5×'],
    ['Formula Block ×20, 2 000 steps', '603.7 ms', '222.7 ms', '2.7×'],
    ['Dynamic System (Duffing), 10 000 steps', '542.7 ms', '210.9 ms', '2.6×'],
    ['PID ↔ plant loop, 20 000 steps', '471.8 ms', '241.5 ms', '2.0×'],
    ['Reaction network ODE, 5 000 steps', '317.4 ms', '178.4 ms', '1.8×'],
    ['Agent-based SIR N = 1 000, 200 steps', '177.5 ms', '102.1 ms', '1.7×'],
    ['Network dynamics N = 1 000, 60 steps', '184.9 ms', '113.9 ms', '1.6×'],
    ['Lotka–Volterra RK4, 20 000 steps', '196.1 ms', '127.4 ms', '1.5×'],
    ['Gray–Scott 96×96, 500 steps (numpy)', '126.7 ms', '105.1 ms', '1.2×'],
    ['Hodgkin–Huxley, 4 000 steps (exp-bound)', '192.5 ms', '179.4 ms', '1.1×'],
    ['Single run, 400-node DAG', '29.5 ms', '8.8 ms', '3.4×'],
    ['Single run, 4 000-node DAG', '2 226 ms', '225 ms', '9.9×'],
    ['Canvas frame, 200 nodes with 5 000-step sparklines', '28.5 ms', '7.1 ms', '4.0×'],
  ];

  // ------------------------------------------------------------------ pages
  const PAGES = {
    overview: ['◎ Overview', () => {
      const lib = KS.library || { templates: [], categories: {} };
      const user = lib.templates.filter(t => t.user).length;
      const h = KS.health;
      return `<h3>knode ${VERSION}</h3>
        <p class="ab-lead">A node-based environment for <b>modelling, simulation and data-flow programming</b>. You build a system from
        nodes — equations, reactions, controllers, agents, networks, fields or your own Python — wire them together, and knode runs it
        once, through time, live while you edit, or thousands of times for sweeps, uncertainty analysis and calibration.</p>
        <div class="ab-kpis">
          <div class="ab-kpi"><b>${lib.templates.length - user}</b><span>built-in node types</span></div>
          <div class="ab-kpi"><b>${Object.keys(lib.categories).length}</b><span>categories</span></div>
          <div class="ab-kpi"><b>${user}</b><span>your node types</span></div>
          <div class="ab-kpi"><b>${(KS.examples || []).length}</b><span>examples</span></div>
          <div class="ab-kpi"><b>96</b><span>automated tests</span></div>
          <div class="ab-kpi"><b class="${h ? 'ab-good' : 'ab-warn'}">${h ? 'online' : 'offline'}</b><span>backend ${h ? esc(h.version) + ' · Python ' + esc(h.python) : '— run python server.py'}</span></div>
        </div>
        <h4>Who it is for</h4>
        <div class="ab-cards">
          <div class="ab-card"><b>Biology & chemistry</b>epidemics (SIR/SEIR, agent-based, network), gene circuits, enzyme kinetics, neurons, population genetics, reaction networks with exact stochastic simulation.</div>
          <div class="ab-card"><b>Engineering & physics</b>control loops (PID, transfer functions), mechanics, circuits, heat conduction, beam checks, hybrid systems with state machines.</div>
          <div class="ab-card"><b>Complex systems</b>chaos, synchronisation, cellular automata, cascades on networks, Turing patterns, any ODE or difference equation you type.</div>
          <div class="ab-card"><b>Data & statistics</b>CSV pipelines, regression, spectra, histograms, Monte-Carlo uncertainty, calibration to measurements.</div>
          <div class="ab-card"><b>Design</b>colour harmonies with WCAG contrast, modular type scales, Bézier curves, layout grids — as live parametric graphs.</div>
          <div class="ab-card"><b>Coding</b>visual data-flow over Python: text, JSON, regex, hashing, and any node you write or design.</div>
        </div>
        <h4>Quick start</h4>
        <ol style="margin:4px 0 0 18px;padding:0">
          <li>Start with <code>python knode.py</code> (or a start-* script) — it launches the backend and opens this editor.</li>
          <li>Open <b>File ▸ Examples</b> — every example runs as soon as it loads.</li>
          <li>Drag nodes from the <b>sidebar</b> (or press <kbd>Tab</kbd>), connect ports by dragging.</li>
          <li>Select a node to edit its parameters in <b>Properties</b>; the formula appears on the node.</li>
          <li><kbd>Ctrl</kbd>+<kbd>Enter</kbd> runs once, <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Enter</kbd> simulates, <kbd>Space</kbd> goes live.</li>
          <li>Press <kbd>P</kbd> for the plot, pin sliders to the <b>dashboard</b> with 📌, pack sub-systems with <kbd>Ctrl</kbd>+<kbd>G</kbd>.</li>
        </ol>`;
    }],
    features: ['✦ Features', () => `<h3>Feature catalogue</h3><p>Everything knode can do, where to find it, and which system inspired it.</p>
        <input class="ab-search" id="abFS" placeholder="Filter features…">
        <div id="abFL">${FEATURES.map(([area, items]) => `<h4 data-area>${esc(area)}</h4>` + items.map(([n, d, how, tag]) =>
          `<div class="ab-feat" data-t="${esc((n + ' ' + d + ' ' + how + ' ' + (tag || '')).toLowerCase())}"><div><b>${esc(n)}</b>${tag ? `<div><span class="ab-tag">${esc(tag)}</span></div>` : ''}</div>
           <div>${esc(d)}<div class="how">→ ${esc(how)}</div></div></div>`).join('')).join('')}</div>`,
      (root) => { $('#abFS', root).oninput = e => { const q = e.target.value.toLowerCase(); root.querySelectorAll('.ab-feat').forEach(f => { f.style.display = f.dataset.t.includes(q) ? '' : 'none'; }); }; }],
    library: ['▦ Node library', () => {
      const lib = KS.library;
      if (!lib) return '<h3>Node library</h3><p class="ab-warn">The backend is offline — start <code>python server.py</code> to load the library.</p>';
      const cats = {};
      for (const t of lib.templates) (cats[t.category] = cats[t.category] || []).push(t);
      return `<h3>Node library</h3><p>${lib.templates.length} node types. <span class="ab-tag">⟳ dynamic</span> nodes evolve over simulation steps; <span class="ab-tag">universal</span> nodes derive their ports from their parameters.</p>
        <input class="ab-search" id="abLS" placeholder="Search nodes, equations, domains…">
        <div id="abLL">${Object.entries(cats).map(([c, ts]) => `<div class="ab-cat"><i style="background:${esc(lib.categories[c] || '#888')}"></i>${esc(c)} <span style="color:#777;font-weight:400">(${ts.length})</span></div>` +
          ts.map(t => `<div class="ab-node" data-t="${esc((t.name + ' ' + t.description + ' ' + t.category + ' ' + t.id).toLowerCase())}"><b>${esc(t.name)}</b>
            ${t.stateful ? '<span class="ab-tag">⟳ dynamic</span>' : ''}${t.universal ? '<span class="ab-tag">universal</span>' : ''}${t.user ? '<span class="ab-tag">yours</span>' : ''}
            <div>${esc(t.description)}</div>
            <div class="pt">in: ${esc(t.inputs.join(', ') || '—')} · out: ${esc(t.outputs.join(', ') || '—')}${t.refs && t.refs.length ? ' · ' + esc(t.refs.join('; ')) : ''}</div></div>`).join('')).join('')}</div>`;
    }, (root) => { const s = $('#abLS', root); if (s) s.oninput = e => { const q = e.target.value.toLowerCase(); root.querySelectorAll('.ab-node').forEach(n => { n.style.display = n.dataset.t.includes(q) ? '' : 'none'; }); }; }],
    runs: ['⚙ How it runs', () => `<h3>How a model runs</h3>
        <h4>Architecture</h4>
        <p>The editor (this page) is a canvas application; the <b>engine</b> is Python (<code>knode_engine.py</code>), reached through a small Flask server
        bound to your machine only. The same engine powers the command-line tool and the tests, so a model behaves identically everywhere.</p>
        <pre>editor ──payload──▶ server ──▶ engine: parse → resolve '=expressions' → schedule (Tarjan SCC) → compile → execute → report
          ◀────────────── JSON report: outputs, statuses, errors (with line numbers), stdout, traces, profile</pre>
        <h4>Writing a node</h4>
        <pre>def process(u=None, params=None, state=None, t=0.0, dt=0.01, step=0, ctx=None):
    k = params["k"]                 # edited in Properties (sliders, units, expressions)
    y = state.get("y", 0.0)         # persists across simulation steps
    state["y"] = y + k * (u or 0.0) * dt
    ctx.log("step", step)           # per-node log; ctx.stop() ends a simulation
    return {"y": y}                 # one entry per output port</pre>
        <p>Input ports bind to arguments by name (unconnected inputs use the argument's default); <code>params state t dt step ctx</code> are injected when requested;
        <code>**inputs</code> receives every wired value; several wires into one port arrive as a list in wire order.</p>
        <h4>Run once</h4><p>Nodes execute in dependency order. A strongly connected component (algebraic loop) is iterated until its outputs stop changing;
        the report says whether it converged. With the cache on, a node is recomputed only when its code, resolved parameters or inputs changed.</p>
        <h4>Simulate & live mode</h4><p>Each step evaluates every node once. Dynamic nodes follow <i>output, then advance</i>: the value emitted at step k is the state at tₖ,
        so they can close feedback loops. The loop is broken at a <i>back edge</i> that carries the previous step's value — an explicit one-step delay, so keep
        <code>dt</code> small in tight loops. Live mode runs the same stepping in chunks on the server and applies parameter changes between chunks.</p>
        <h4>Groups</h4><p>A group node embeds a whole graph. Each copy has its own inner run and state; Group Input/Output nodes are its ports. Running from inside a group
        runs the whole model and shows the inner values.</p>
        <h4>Flags & expressions</h4><p>Bypass passes inputs to outputs, Freeze replays pinned outputs, Break-if pauses when its condition holds. Parameters starting with
        <code>=</code> are evaluated against Globals nodes before anything runs; <code>P("Node", "param")</code> reads another node's parameter.</p>
        <h4>Errors</h4><p>A failing node is outlined in red with its line number; nodes downstream are marked <i>blocked</i> rather than fed <code>None</code>.
        Tracebacks show only your node's code.</p>`],
    science: ['∑ Science & methods', () => `<h3>Science & methods</h3>
        <p>knode is meant for results you can trust. The numerical methods are standard, documented in the code, and each built-in model is checked by automated tests
        against analytic solutions, conservation laws or an independent implementation of the same model.</p>
        <table class="ab-t"><tr><th>method</th><th>used for</th><th>reference</th><th>verified by</th></tr>
        ${METHODS.map(m => `<tr><td><b>${esc(m[0])}</b></td><td>${esc(m[1])}</td><td>${esc(m[2])}</td><td>${esc(m[3])}</td></tr>`).join('')}</table>
        <h4>Examples of verification</h4>
        <ul style="margin:4px 0 0 18px;padding:0">
          <li>SIR: S + I + R = N at every step; final size satisfies ln(S∞/S₀) = −R₀(1 − S∞/N).</li>
          <li>Lotka–Volterra: the conserved quantity drifts by less than 10⁻⁶ over 5 000 steps.</li>
          <li>Hodgkin–Huxley: rests at −65 mV and spikes 3–6 times in 50 ms at 10 µA/cm².</li>
          <li>Logistic map: Lyapunov exponent ln 2 at r = 4; Kuramoto: synchronisation above the critical coupling.</li>
          <li>Cross-validation: the generic ODE node reproduces the mass–spring model to 10⁻⁶; reaction notation reproduces SIR exactly.</li>
          <li>Calibration recovers known parameters from generated data; a breakpoint fires at the analytic crossing time.</li>
        </ul>
        <p style="margin-top:10px"><b>Limits to keep in mind:</b> loops in simulations use explicit coupling (not an implicit DAE solver); fixed-step integration
        needs a sensible dt; agent-based and network nodes are pure Python (comfortable up to a few thousand individuals); node code is not sandboxed.</p>`],
    keys: ['⌨ Shortcuts', () => `<h3>Keyboard & mouse</h3>` + SHORTCUTS.map(([g, rows]) => `<h4>${esc(g)}</h4><table class="ab-t">${rows.map(([k, v]) =>
        `<tr><td style="width:260px">${k.split(' / ').map(x => `<kbd>${esc(x)}</kbd>`).join(' / ')}</td><td>${esc(v)}</td></tr>`).join('')}</table>`).join('')],
    files: ['⇅ Files & API', () => `<h3>Files, command line & API</h3>
        <h4>File formats</h4><table class="ab-t">
          <tr><td><b>.json</b></td><td>the model (nodes, wires, frames, dashboard, scenarios); also runs headlessly with the CLI</td></tr>
          <tr><td><b>.png</b></td><td>canvas image with the model embedded in a <code>knode</code> text chunk — drop it back to open</td></tr>
          <tr><td><b>.h5</b></td><td>HDF5 with graph JSON and simulation traces as compressed datasets (requires h5py)</td></tr>
          <tr><td><b>.knode-type.json</b></td><td>a node type from the Node Designer; saved types live in <code>user_library/</code> (or <code>$KNODE_USER_LIBRARY</code>)</td></tr>
          <tr><td><b>autosave</b></td><td>browser storage, one second after each change — File ▸ Restore autosave</td></tr></table>
        <h4>Starting knode</h4><pre>python knode.py                  # start the backend, open the editor, supervise the server
python knode.py --port 8080 --no-browser
start-windows.bat · start-mac.command · start.sh   # double-click equivalents</pre>
        <h4>Command line</h4><pre>python knode_cli.py examples                      # list examples
python knode_cli.py example pid_control --csv pid.csv --save pid.json
python knode_cli.py simulate model.json --steps 4000 --dt 0.0025 --csv out.csv
python knode_cli.py sweep model.json --node 1 --param kp --values 1:50:20 --target 2.x --simulate --reduce max
python knode_cli.py analyze model.json
python bench/bench_engine.py                      # performance benchmark</pre>
        <h4>HTTP API</h4><p>All endpoints take and return JSON; the full list with options is at the top of <code>server.py</code>.</p>
        <table class="ab-t">${[['POST /graph/execute', 'run once'], ['POST /graph/simulate', 'fixed-step simulation'], ['POST /session/start · step · stop', 'live mode'],
          ['POST /graph/sweep · /graph/montecarlo', 'parameter studies'], ['POST /graph/scenarios', 'parameter variants'], ['POST /graph/optimize', 'calibration / optimisation'],
          ['POST /graph/analyze', 'structure analysis'], ['GET /library · POST/DELETE /library/user', 'node types'], ['GET /examples', 'example models'], ['GET /api/health', 'status']]
          .map(([a, b]) => `<tr><td><code>${esc(a)}</code></td><td>${esc(b)}</td></tr>`).join('')}</table>
        <p><b>Security:</b> executing a model executes its Python code. The server listens on 127.0.0.1 and accepts browser requests only from local pages;
        use <code>--host 0.0.0.0</code> only on a network you trust.</p>`],
    perf: ['⚡ Performance', () => `<h3>Performance</h3>
        <h4>0.7 — CPU & GPU utilisation</h4>
        <table class="ab-t"><tr><th>case</th><th>0.6</th><th>0.7</th><th></th></tr>
        ${PERF7.map(r => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td><b>${esc(r[3])}</b></td></tr>`).join('')}</table>
        <ul style="margin:4px 0 0 18px;padding:0">
          <li><b>All cores</b> — sweeps, Monte-Carlo samples, scenarios and optimiser generations run on a pool of worker processes
            (automatic: cores − 1; set in Backend ▸ Settings or <code>KNODE_WORKERS</code>). Results are bit-identical to serial runs.</li>
          <li><b>Live mode</b> — the next chunk is requested before the current one is drawn (server and browser work at the same time),
            and the chunk size adapts to ~25 ms per round trip (<i>auto</i>).</li>
          <li><b>Idle = idle</b> — no animation frames or timers run while nothing changes; hidden tabs draw nothing.</li>
          <li><b>Rendering</b> — one draw per display frame however many events arrive; opaque canvas; native curve paths
            (the rasteriser flattens them) instead of 50 sampled points per wire; off-screen wires culled; memoised text layout.</li>
          <li><b>Measured and rejected</b> — a pattern-filled grid (GPU texture) was slower at fractional zoom than one stroked path, so it was not kept.</li>
        </ul>
        <p style="color:#8a93a8">Multi-core speed-ups scale with the number of cores; they were verified for correctness (parallel ≡ serial) but the
        timings above were taken on a single-core machine, where knode automatically runs studies serially.</p>
        <h4>0.5</h4>
        <p>Measured with <code>bench/bench_engine.py</code> (best of three) and a browser harness on the same machine; 0.4 vs 0.5.</p>
        <table class="ab-t"><tr><th>case</th><th>0.4</th><th>0.5</th><th>speed-up</th></tr>
        ${PERF.map(r => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td><b>${esc(r[3])}</b></td></tr>`).join('')}</table>
        <h4>What changed</h4><ul style="margin:4px 0 0 18px;padding:0">
          <li><b>Call plans</b> — how each node function's arguments are filled is decided once, not on every call.</li>
          <li><b>One stdout router</b> per run instead of a redirect per node call; one <code>ctx</code> object per node.</li>
          <li><b>Linear-time scheduler</b> — back edges are searched within each loop only (was quadratic in model size).</li>
          <li><b>Cached parsing</b> — expressions, constants, ODE and reaction systems are parsed once per distinct text.</li>
          <li><b>Population loop</b> — one reusable environment per step instead of new closures per individual.</li>
          <li><b>Canvas</b> — off-screen nodes are culled; shadows and text are skipped when zoomed out; sparklines are cached min/max envelopes;
            long plot series are drawn as per-pixel min/max envelopes.</li>
        </ul>
        <p>Results are unchanged: <code>tests/test_perf.py</code> checks that the optimised engine reproduces values recorded from 0.4 exactly,
        including the random stream of the agent-based model.</p>
        <h4>Tips for large models</h4><ul style="margin:4px 0 0 18px;padding:0">
          <li>Leave the cache on for Run once; freeze expensive nodes whose inputs no longer change.</li>
          <li>Use larger <code>dt</code> with the exact/RK4 nodes; lower <code>max_substep</code> only when accuracy requires it.</li>
          <li>Group sub-systems — it keeps the canvas light and inner nodes out of the trace recorder.</li>
          <li>Use the 2-D Field node (numpy) for spatial models instead of many small nodes.</li></ul>`],
    about: ['ℹ History & credits', () => `<h3>History & credits</h3>
        <table class="ab-t">${HISTORY.map(([v, d]) => `<tr><td style="width:60px"><b>${esc(v)}</b></td><td>${esc(d)}</td></tr>`).join('')}</table>
        <h4>Ideas adopted from</h4><p>${INSPIRED.map(x => `<span class="ab-tag" style="margin:2px">${esc(x)}</span>`).join(' ')}</p>
        <h4>License</h4><p>GNU General Public License v2.0 — see <code>LICENSE</code>.</p>
        <h4>Documentation</h4><p><code>README.md</code> (features and usage) · <code>docs/ARCHITECTURE.md</code> (code guide) · docstrings and comments throughout the source.</p>`],
  };

  let current = 'overview';
  /** Open the About & Guide centre on a page (overview, features, library, runs, science, keys, files, perf, about). */
  function show(page) {
    current = page;
    const box = KS.modal('knAbout', `About knode ${VERSION}`, 1080);
    box.innerHTML = `<div class="ab-nav">${Object.entries(PAGES).map(([k, [label]]) => `<div data-p="${k}" class="${k === page ? 'on' : ''}">${label}</div>`).join('')}</div>
      <div class="ab-main" id="abMain"></div>`;
    const main = $('#abMain', box), [, render, after] = PAGES[page];
    main.innerHTML = render();
    if (after) after(main);
    box.querySelector('.ab-nav').onclick = e => { const p = e.target.closest('[data-p]'); if (p) show(p.dataset.p); };
  }
  window.KnodeAbout = { show };

  // menus: Help ▸ About knode / Feature catalogue / Node reference
  const prevExtend = UI.extendMenus;
  /** Add this layer's entries to the menubar definition (each layer wraps the previous one's extension). */
  UI.extendMenus = function (m) {
    m = prevExtend ? prevExtend(m) : m;
    const help = m.find(x => x[0] === 'Help');
    if (help) help[1] = [['About knode', () => show('overview'), 'F1'], ['Feature catalogue', () => show('features')], ['Node reference', () => show('library')],
      ['How models run', () => show('runs')], ['Science & methods', () => show('science')], ['Performance', () => show('perf')], '-',
      ...help[1].filter(it => it === '-' || (Array.isArray(it) && it[0] !== 'About knode'))];
    return m;
  };
  document.addEventListener('keydown', e => { if (e.key === 'F1') { e.preventDefault(); show(current); } });
  document.addEventListener('DOMContentLoaded', () => {
    if (UI.renderMenubar) UI.renderMenubar();
    // one-time welcome for this version
    try {
      if (localStorage.getItem('knode.seenVersion') !== VERSION) {
        localStorage.setItem('knode.seenVersion', VERSION);
        setTimeout(() => KS.status(`Welcome to knode ${VERSION} — press <b>F1</b> for the About & Guide centre (features, node reference, methods, shortcuts).`), 2500);
      }
    } catch (e) { /* storage unavailable */ }
  });
})();

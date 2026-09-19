# knode 0.7

Node-based modelling, simulation and data-flow programming with embedded Python.
Build a graph visually, run it once, **simulate it through time**, sweep and
randomise its parameters, and analyse its structure — for biology, engineering,
complex systems, data analysis, design and general coding.

<img width="2136" height="2014" alt="knode" src="https://github.com/user-attachments/assets/8cfde738-b7da-4a91-b006-c77884900cce" />

## Run

```bash
pip install flask            # required  (numpy and h5py are optional — installable from the UI)
python knode.py              # starts the backend, opens the editor, supervises the server
```

Or double-click **start-windows.bat**, **start-mac.command** or **start.sh**. `python server.py` still works
for a plain, unsupervised server. The backend binds to **localhost only** by default; nodes execute
arbitrary Python, so only use `--host 0.0.0.0` on a network you trust.

## New in 0.7 — CPU & GPU utilisation

| case | 0.6 | 0.7 | |
|---|---|---|---|
| idle editor: animation frames / timers per second | 68 / 8 | **0 / 0** | idle |
| live mode (Lotka–Volterra), 0.6 best manual setting vs 0.7 auto | 22 625 steps/s | **53 162 steps/s** | 2.3× |
| live mode (PID loop) | 14 875 steps/s | **40 826 steps/s** | 2.7× |
| wire drawing, 218 wires (JavaScript time per frame) | 0.96 ms | **0.24 ms** | 4.0× |
| canvas frame, 120 nodes / 218 wires @ 100 % / 20 % zoom | 5.7 / 6.3 ms | **4.8 / 4.9 ms** | 1.2–1.3× |
| renders for a burst of 50 mouse moves | 3 | **1** | |
| 50-node simulation incl. HTTP/JSON (JSON overhead) | 375 ms (56 ms) | **261 ms (18 ms)** | 1.4× (3.1×) |
| Kuramoto N = 200 (numpy-vectorised) | 83 ms | **27 ms** | 3.1× |

- **All CPU cores for studies**: parameter sweeps, Monte-Carlo samples, scenarios and every generation of the
  differential-evolution optimiser run on a pool of worker processes (automatic: cores − 1, serial on one core;
  Backend ▸ Settings or `KNODE_WORKERS`). Results are bit-identical to serial execution (`tests/test_parallel.py`).
- **Live mode** requests the next chunk before drawing the current one, and **auto** sizes chunks to ~25 ms.
- **Editor**: zero work while idle, one draw per display frame, opaque canvas, native curve paths instead of
  sampled wires, off-screen wire culling, memoised text layout.
- **Measured and rejected**: a GPU pattern-filled grid (slower at fractional zoom than one stroked path).
- **Fixed**: Nelder–Mead could stop early on symmetric objectives (it only checked function values); a node name
  that wrapped to exactly two lines only showed its first line.
- **Documentation**: every Python function/class and every JavaScript function now has a docstring / doc comment;
  editor and engine headers explain the performance design.

Note: the multi-core timings scale with your core count; the numbers above were taken on a single-core machine,
where knode automatically keeps studies serial.

## New in 0.6 — backend from the UI, better wires & ports, context menus

**Run the backend from the UI.** A web page cannot start programs, so `knode.py` starts the server once,
opens the editor and supervises the process. From then on everything happens in the UI:

- **Backend Manager** (Backend menu, or click the status dot): status (version, pid, uptime, memory, Python,
  packages), **Restart** / **Stop**, reload library, clear cache, **live sessions** (end them), **settings**
  (cache size, session idle timeout, time limit), **install numpy / h5py** with one click, a **live log**,
  and **connect to another backend** (e.g. through an SSH tunnel).
- **Offline banner**: when the backend is unreachable the editor keeps working, shows the start command
  (with a copy button) and reconnects automatically; the launcher also restarts a crashed server.
- Management endpoints only answer requests from the same machine, even with `--host 0.0.0.0`.

**Wires & ports.** Typed wires and port shapes (number, boolean, text, list, 2-D field, table — Blender-style),
smart curves that loop around feedback wires, orthogonal (circuit) routing, port tooltips with live values and
fallbacks, compatible-port highlighting with magnetic snapping, drop a node onto a wire to insert it,
reroute dots (double-click a wire), a knife (hold **Y** and drag), **Alt+click** an input to feed it a Constant,
and flow dots in live mode.

**Right-click menus** for canvas, node, port, wire and frame — add nodes from any category or the recent list,
flags, rename, colour, connections, group / frame, node type, insert on wire, per-wire style, disconnect,
plot / pin, backend actions and more; keyboard navigable.

## New in 0.5 — faster, documented, self-explaining

**Performance** (measured with `bench/bench_engine.py` and a browser harness, 0.4 → 0.5):

| case | 0.4 | 0.5 | |
|---|---|---|---|
| gain chain ×50, 2 000 steps (dispatch overhead) | 693 ms | 272 ms | **2.5×** |
| Formula Block ×20, 2 000 steps | 604 ms | 223 ms | **2.7×** |
| Dynamic System (Duffing), 10 000 steps | 543 ms | 211 ms | **2.6×** |
| PID ↔ plant loop, 20 000 steps | 472 ms | 242 ms | **2.0×** |
| agent-based SIR, N = 1 000, 200 steps | 178 ms | 102 ms | **1.7×** |
| Hodgkin–Huxley (bound by `exp`) | 193 ms | 179 ms | 1.1× |
| single run, 4 000-node model | 2 226 ms | 225 ms | **9.9×** |
| canvas frame, 200 nodes with 5 000-step sparklines | 28.5 ms | 7.1 ms | **4.0×** |

How: precomputed argument-binding plans, one stdout router per run, a linear-time scheduler (was
quadratic), cached parsing of expressions/constants/ODE and reaction systems, a closure-free population
loop; on the canvas, viewport culling, level of detail (no shadows/text when zoomed out), cached
min/max sparklines and per-pixel plot decimation. `tests/test_perf.py` proves results are unchanged —
it reproduces values recorded from 0.4 exactly, including the agent-based model's random stream.

**Documentation**: every public Python function/class has a docstring and every JavaScript function a
doc comment; module headers describe architecture (engine data flow, server endpoint map, editor object
model and hooks); `docs/ARCHITECTURE.md` is a code guide for extending knode.

**About & Guide centre** (**F1** or Help ▸ About knode): overview with live status and counts, a searchable
feature catalogue (what each feature does, how to reach it, which system inspired it), a searchable
reference of every node type, how models run, numerical methods with references and how each is
verified, all shortcuts, file formats / CLI / API, performance figures, and version history.

## New in 0.4 — the best ideas from other node systems

| inspired by | feature in knode | how to use |
|---|---|---|
| TouchDesigner, Max/MSP, Pure Data (live patching) | **Live mode**: the model streams from a server session; parameter edits apply *without restarting*, structural edits restart automatically | `●` in the header or **Space**; ⏸ ⏮ and steps/frame |
| LabVIEW front panel, Max presentation mode | **Dashboard**: sliders, toggles, selects, readouts, gauges, sparklines; full-screen *present* mode | 📌 next to any parameter or output · Ctrl+Shift+D |
| LabVIEW probes | **Wire probes**: hover a wire to read the value it carries | hover |
| Houdini bypass, Blender mute | **Bypass** a node (inputs pass through) | Ctrl+E |
| n8n pinned data, Houdini lock | **Freeze**: pin a node's last outputs, stop recomputing it | Ctrl+Shift+L |
| Unreal Blueprints breakpoints | **Break if** `V > 0`: simulation pauses there and selects the node | Properties ▸ Flags |
| ComfyUI, Houdini cooking | **Incremental cache**: Run once only recomputes nodes whose code, parameters or inputs changed (impure code is detected and never cached) | on by default · Run menu |
| Node-RED link nodes, Houdini Object Merge | **Send / Receive** wireless channels, drawn as ghost links | Model ▸ Add Send / Receive pair |
| Houdini `ch()`, Blender drivers, Simulink model workspace | **Globals** node + `=expressions` in any parameter (`=R0*gamma`, `=P("Room", "C")`); sweeping a global updates everything that uses it | ƒ next to a parameter |
| Houdini takes, Nuke A/B | **Scenarios** (parameter variants) run side by side; **keep** runs and overlay them dashed | Run ▸ Scenarios · 📌 keep in the plot |
| Grasshopper Galapagos, Simulink Design Optimization, COPASI | **Calibrate / optimise**: differential evolution or Nelder–Mead over any parameters; minimise, maximise, or **fit to data** (R², RMSE, convergence plot) | Run ▸ Calibrate / optimise |
| Blender frames, Nuke backdrops, Unreal comments | **Frames**: titled, coloured backdrops that move their nodes | Ctrl+J · drag title · double-click to rename · dot = colour |
| Blender, Unreal, ComfyUI | **Link-drag search**: drop a wire on empty canvas → pick a node → it is connected | drag from a port |
| ComfyUI | **PNG with the model embedded**; **drop PNG/JSON files** on the canvas to open them | File ▸ Export image with model |
| Substance Designer, TouchDesigner | **Field thumbnails** drawn next to nodes | automatic for 2-D outputs |

Try **File ▸ Examples ▸ Live & interactive**.

## New in 0.3 — model (almost) anything with nodes only

### Universal nodes
Each is a *modelling formalism*: you describe the system in its parameters and
**its ports are generated from that description** (add an equation → a new
output port appears; name an input → a new input port appears).

| node | you write | typical systems |
|---|---|---|
| **Formula Block** | `y = a*x + b` lines | any static relation, cost/unit models (lists processed element-wise) |
| **Dynamic System** | states, `dx = …`, inputs, observables | mechanics, circuits, pharmacokinetics, ecology, neurons |
| **Difference Equations** | `x = f(x)` updates (simultaneous) | generations, finance, maps, digital filters |
| **Reaction Network** | `A + B -> C, k` · `S -> P, = Vmax*S/(Km+S)` | biochemistry, gene expression, epidemics; ODE **or exact Gillespie SSA** |
| **State Machine** | states, `a -> b : condition`, `state: out = expr` | controllers, protocols, behaviour modes, cell cycle |
| **Agent-Based Model** | per-agent init / rules / population observables | heterogeneous populations, crowds, markets |
| **Network Dynamics** | topology + rules with `nbr_mean('x')`, `deg` … | contagion, opinions, cascades, synchronisation |
| **2-D Field (PDE)** | `du = D*lap(u) + …` on a periodic grid | diffusion, Turing patterns, waves (heat-map plot) |
| **Transfer Function** | `num` / `den` in s | control plants, filters |
| **Lookup Table** | `x, y` rows | empirical/calibration curves |
| **Python Script** | code + port lists | anything else |
| Logic & Signals | If/Else, Event Detector (period, rate), Sample & Hold, Selector, Accumulator | hybrid & event-driven models |

Combine them freely — e.g. a State Machine wired to a Dynamic System in a loop
is a hybrid (discrete + continuous) system.

### Groups — hierarchical models
Select nodes → **Ctrl+G**. They collapse into one *group node*; wires crossing
the boundary become **Group Input / Group Output** ports. Double-click to
enter (breadcrumb bar shows where you are, **Esc** goes up), **Ctrl+Shift+G**
ungroups. Groups nest to any depth, each copy keeps its own simulation state,
and running from inside a group runs the whole model and shows the inner
values. Large systems become trees of reusable sub-models.

### Node Designer — your own node types
**Model ▸ New node type** (or ＋ in the sidebar, or *Save selected node as
type*): name, category, colour, ports, parameters with widgets (slider when
min/max are set, select, checkbox, code, units, help text) and Python code.
**▶ Test** runs it with sample inputs; **Save to library** writes
`user_library/<id>.json`, which appears in the sidebar and palette, can be
exported/imported to share, and can update every existing instance.
Set `KNODE_USER_LIBRARY` to keep your types elsewhere.

### Interface
Menubar (File / Edit / View / Model / Run / Help) · docked, searchable library
sidebar with drag-and-drop · minimap · find node (Ctrl+F) · auto re-run on
parameter change (⟳ auto) · schema-aware parameter widgets · node subtitles
showing the model's key equation · heat-map plots for 2-D fields · shortcut
sheet (?) · universal-nodes guide (Help).

## What you can do

| | |
|---|---|
| **Library** (sidebar, `Tab`, double-click canvas) | 83 node types in 13 categories + your own |
| **▶ Run** (`Ctrl+Enter`) | single pass; results are drawn under each node |
| **▶▶ Simulate** (`Ctrl+Shift+Enter`) | fixed-step time integration with persistent node state |
| **📈 Plot** (`P`) | time series, phase portraits (any series as X), arrays, log/normalise, CSV/PNG export |
| **⚙ Analyze** | feedback loops, critical path, centrality heat-maps, lint |
| **∿ Study** | 1-D parameter sweeps (lin/log) and Monte-Carlo uncertainty + sensitivity |
| **Examples** | 25 ready-made models (File ▸ Examples), each runs on load |
| **Properties panel** | edit model parameters, see last outputs/errors, *Run to here* |

Your original editor features (dominant/standard/empty classes, alien & dummy
ports, type matching, wire animation, undo/redo, copy/paste, JSON/YAML/XML
export) are all preserved.

## Library (by domain)

- **Sources** – constant, clock, sine, step, pulse train, seeded noise, linspace, text, CSV parse, column
- **Math** – expression (any `math.*` formula, broadcasts over lists), add, multiply, gain, clamp, reduce
- **Dynamics & Control** – integrator (trapezoidal), derivative, unit delay, low-pass (exact ZOH), PID (anti-windup, derivative-on-measurement), mass–spring–damper (RK4), RC circuit (exact)
- **Engineering & Physics** – rectangular section, cantilever beam (Euler–Bernoulli + safety factor), Ohm's law, projectile, 1-D heat equation (FTCS with automatic stability sub-stepping)
- **Biology & Chemistry** – logistic growth (closed form), Lotka–Volterra (with conserved invariant), SIR/SEIR, Michaelis–Menten, Hill functions, Gardner genetic toggle switch, Hodgkin–Huxley neuron, Wright–Fisher drift, DNA tools (GC, reverse complement, translation, ORFs), Arrhenius
- **Complex Systems** – logistic map (running Lyapunov exponent), Lorenz, Kuramoto synchronisation, elementary cellular automata, Brownian motion, **generic ODE solver** (type any system; adaptive Dormand–Prince RK45)
- **Statistics & Data** – descriptive stats + 95 % CI, OLS regression (R², SE), Pearson/Spearman, histogram, moving average, FFT spectrum, recorder
- **Optimisation** – Nelder–Mead on any expression, bisection root finder
- **Design** – modular type scale, colour harmonies with WCAG contrast ratios, Bézier curves (de Casteljau), proportional grid
- **Text & Code** – regex, JSON parse / path, format string, text statistics (Shannon entropy), hashes

## Execution model

- **Topological scheduling** over strongly connected components (Tarjan).
- **Run**: cyclic components (algebraic loops) are solved by **fixed-point iteration** until outputs converge; convergence is reported.
- **Simulate**: loops are broken at a *back edge* that carries the previous step's value (explicit Gauss–Seidel coupling, a one-step delay). Stateful nodes follow *output, then advance*, so they have no feed-through and can close loops safely, like integrator blocks. Use a small `dt` in loops.
- **Fan-in**: several wires into one input arrive as a list.
- **Errors** are local: the failing node is outlined with its line number; downstream nodes are marked *blocked* instead of receiving `None`.
- All outputs are made JSON-safe (NaN, ∞, complex, numpy, sets, bytes).

## Writing nodes

Any node's code can be edited (`⚙` or double-click). Input ports map to
arguments by name; outputs are a returned dict (a bare value goes to the first
output, a tuple is zipped over the outputs). Reserved arguments are injected
only if you ask for them:

```python
def process(u=None, params=None, state=None, t=0.0, dt=0.01, step=0, ctx=None):
    k = params["k"]                       # editable in the Properties panel
    y = state.get("y", 0.0)               # persists across simulation steps
    state["y"] = y + k * (u or 0.0) * dt
    ctx.log("step", step)                 # per-node log; ctx.stop() ends a simulation
    return {"y": y}
```

`math`, `random`, `statistics`, `json`, `re`, `np` (if installed) and `ks`
(knode's numerical library: RK4/RK45, statistics, regression, FFT,
Nelder–Mead, bisection, colour utilities…) are available in every node.
Custom nodes can get parameters too: use *+ new param* in the Properties panel.

User-written code is **never overwritten** when ports are added, renamed or a
file is imported (0.1.x regenerated the stub and discarded it).

## Scientific studies

- **Sweep**: vary one parameter (linear or log spacing), reduce a simulated output with *final / max / min / mean / ∫dt / time of max*, and plot the response curve.
- **Monte Carlo**: uniform / normal / lognormal / triangular inputs sampled by **Latin hypercube**; reports mean, SD, median and the 5–95 % interval, a histogram, and global sensitivity via **Spearman rank correlation** (plus Pearson).
- **Analysis**: density, DAG depth, sources/sinks, weak components, feedback loops and their back edges, the critical path (weighted by measured ms/call after a run), betweenness (Brandes) and PageRank, shown as a canvas heat-map, plus lint (unconnected required inputs, unused ports, syntax errors).

## Verification

Every model is checked against theory — run `python tests/test_engine.py`
`python tests/test_universal.py`, `python tests/test_adopted.py`, `python tests/test_perf.py`, `python tests/test_server.py` and `python tests/test_parallel.py` (or `pytest tests`). 96 tests.
The 0.4 features are verified too: a breakpoint fires at the analytic crossing time of logistic growth, live-session
chunks are bit-identical to a batch simulation, a hot parameter change keeps integrator state, calibration recovers
known parameters from generated data, the cache reuses exactly the unchanged nodes, and globals propagate through sweeps. The
universal nodes are **cross-validated** against independent implementations:
the generic ODE node reproduces the dedicated mass–spring model (< 10⁻⁶), the
reaction-network notation reproduces the SIR model exactly, SSA matches
exponential decay in the mean, integrated Michaelis–Menten holds, a
transfer function matches `1−e⁻ᵗ` and its DC gain, agent-based SIR conserves
N, network averaging reaches consensus, diffusion conserves mass, Gray–Scott
forms patterns, the thermostat hybrid system regulates, and nested groups equal
flat graphs. The original tests include: RK4 4th-order convergence; RK45 on the
harmonic oscillator; SIR mass conservation and the final-size relation;
Lotka–Volterra invariant drift < 10⁻⁶; logistic growth vs. closed form;
RC charging vs. `1−e⁻¹`; undamped oscillator period; heat equation → linear
steady state; Hodgkin–Huxley spiking and −65 mV rest; toggle-switch
bistability; logistic-map Lyapunov exponent = ln 2 at r = 4; Kuramoto
transition; rule-90 Sierpiński pattern; Brownian MSD = 2Dt; closed-loop PID
tracking; algebraic-loop convergence; sensitivity ranking.

## Headless / batch use

```bash
python knode_cli.py examples
python knode_cli.py example pid_control --csv pid.csv --save pid.json
python knode_cli.py simulate pid.json --steps 4000 --dt 0.0025 --csv out.csv
python knode_cli.py sweep pid.json --node 1 --param kp --values 1:50:20 --target 2.x --simulate --reduce max
python knode_cli.py analyze pid.json
```

Graphs exported from the editor (Export → JSON) run unchanged in the CLI.

## Files

| file | purpose |
|---|---|
| `index.html` | the editor (your 0.1.1 UI with fixes and hooks) |
| `knode_science.js` | library, simulation, plotting, analysis, studies, examples |
| `server.py` | Flask API |
| `knode_engine.py` | scheduler, runner, simulator, sweep, Monte Carlo, analysis |
| `knode_library.py` | model templates + user library |
| `knode_universal.py` | universal nodes and port rules |
| `knode_ui.js` | menubar, sidebar, groups, Node Designer, minimap |
| `knode_studio.js` | live mode, dashboard, flags, frames, probes, scenarios, calibration, PNG models |
| `knode_about.js` | About & Guide centre (F1) |
| `knode_wires.js` | typed wires & ports, routing, tooltips, snapping, reroute, knife, insert-on-wire |
| `knode_menu.js` | context-sensitive right-click menus |
| `knode_backend.js` | Backend Manager, offline banner, reconnection, remote backends |
| `knode.py` | launcher + supervisor (start / restart / crash recovery) |
| `start-windows.bat`, `start-mac.command`, `start.sh` | double-click starters |
| `docs/ARCHITECTURE.md` | code guide: layers, data flow, hooks, how to extend |
| `bench/bench_engine.py` | performance benchmark |
| `user_library/` | your saved node types (created on first save) |
| `knode_std.py` | numerical library available to nodes as `ks` |
| `knode_examples.py` | example graphs |
| `knode_cli.py` | command-line runner |
| `tests/` | verification suites |

## Changes in 0.7

Parallel studies on worker processes · generation-parallel differential evolution · pipelined adaptive live mode · zero-idle, coalesced, culled rendering with native wire paths · faster JSON path · vectorised Kuramoto · Nelder–Mead convergence fix · full documentation · 7 new tests.

## Changes in 0.6

Launcher/supervisor and Backend Manager (restart, stop, sessions, settings, packages, logs, remote backends, offline banner) · typed wires & ports, smart/orthogonal routing, port tooltips, snapping, insert-on-wire, reroute, knife, quick constants, flow dots · context menus for every element · 7 server tests.

## Changes in 0.5

Engine and canvas optimisations (table above) · docstrings / doc comments throughout · architecture guide · About & Guide centre · benchmark suite · 8 equivalence tests.

## Changes in 0.4

Features adopted from TouchDesigner, Max/MSP, LabVIEW, Houdini, Blender, Unreal, ComfyUI, n8n, Node-RED, Nuke, Grasshopper and Simulink (table above) · engine: live sessions, node flags, incremental cache, wireless links, parameter expressions, scenarios, optimiser · 3 new examples · 13 new tests.
**Fixed (present since 0.1.1)**: snapshots stored node `properties` by reference, so editing a parameter silently rewrote undo history; Ctrl+Shift+Z redo never fired (Shift makes the key `'Z'`), Ctrl+Y added; undo now skips snapshots identical to the current state. The palette now selects the previous query so typing replaces it.

## Changes in 0.3

Universal nodes with parameter-derived ports · hierarchical groups (engine + editor) · Node Designer and persistent user library · menubar, sidebar, minimap, find, auto re-run, parameter widgets, 2-D heat-maps · 10 new examples · 25 new tests.

## Changes from 0.1.1

**Fixed**: `/graph/execute` was nested inside another function and never registered (Run could not work) · `/` served a missing `index.html` · the function finder could pick `print`/`len` instead of your function · editing ports or importing a file overwrote user code · JSON import put node ids where wire ids belong in `port.connections` · server listened on all interfaces in debug mode · `flask_cors` was required but undocumented · NaN/∞ outputs broke the browser's JSON parser · the canvas was blurry on HiDPI screens · the grid did not cover the view when panned · node notes showed "undefined".

**Honest limits**: live mode steps on the server, so its speed depends on model cost (≈10³–10⁵ steps/s for small models); scenarios and calibration run the whole model per evaluation; loops in simulation use explicit one-step-delay coupling (not an implicit/DAE solver); agent-based and network nodes are pure Python (comfortable up to a few thousand individuals); the 2-D field node needs numpy and uses explicit Euler (set `max_substep` for stability); the default "HDF5" export is still base64 JSON unless `h5py` is installed; node code is not sandboxed.

# knode — architecture & code guide

This document explains how the code is organised, how data flows through it, and how to
extend it. For features and usage see `README.md`; inside the app press **F1**.

## Repository layout

| file | layer | responsibility |
|---|---|---|
| `index.html` | editor core | canvas editor from 0.1 (with fixes): object model, rendering, interaction, undo/redo, import/export |
| `knode_science.js` | frontend | server integration: library palette, run / simulate, plot, analysis, sweeps & Monte Carlo, examples, value overlays, parameter panel |
| `knode_ui.js` | frontend | menubar, library sidebar, groups (enter/exit/ungroup), Node Designer, minimap, find |
| `knode_studio.js` | frontend | live mode, dashboard, node flags, frames, link-drag search, wire probes, scenarios, calibration, PNG models |
| `knode_about.js` | frontend | About & Guide centre |
| `knode_wires.js` | frontend | typed wires & ports, routing styles, tooltips, snapping, insert-on-wire, reroute, knife |
| `knode_menu.js` | frontend | context-sensitive right-click menus (generic menu component + per-target menus) |
| `knode_backend.js` | frontend | Backend Manager, offline banner, reconnection, backend URL switching |
| `knode.py` | tool | launcher + supervisor: exit code 3 = restart, 0 = stop, other = crash (restart with back-off) |
| `server.py` | backend | Flask HTTP API (endpoint map at the top of the file) |
| `knode_engine.py` | backend | parsing, scheduling, execution, simulation, sessions, studies, optimisation, analysis |
| `knode_std.py` | backend | numerical library available to node code as `ks` |
| `knode_library.py` | backend | built-in templates, user library, graph builders |
| `knode_universal.py` | backend | universal nodes and the port-rule language |
| `knode_examples.py` | backend | example models (shared by UI, CLI and tests) |
| `knode_cli.py` | tool | headless command-line runner |
| `tests/` | QA | verification (`test_engine`, `test_universal`, `test_adopted`) and optimisation-equivalence (`test_perf`) |
| `bench/bench_engine.py` | QA | reproducible performance benchmark |

The frontend scripts load in the order above; each extends the previous one through a small set of
hooks, so every layer can be read on its own.

## Data flow

```
 editor graph (BaseNode / Wire objects)
      │  KnodeSci.serialize()  — or the whole model folded from nested groups (knode_ui)
      ▼
 payload {nodes: {id: {name, code, inputs, outputs, params, template, flags, subgraph}}, connections: [...]}
      │  HTTP POST (server.py)
      ▼
 parse_graph → Graph(NodeSpec, Edge)      wireless Send→Receive links become real edges here
 resolve_params                           '=expressions' against Globals nodes (P("Node","param"))
 schedule                                 Tarjan SCC → blocks in topological order + back edges
 Run.compile_all                          code → CompiledNode (cache keyed by id + code hash + name)
 Run.execute_pass (per step)              _exec_one → gather → call → normalize
 Run.report                               JSON-safe dict (to_jsonable)
      │
      ▼
 KnodeSci.applyResults → canvas overlays, Properties panel, State panel, plot, dashboard
```

## Execution model (engine)

* **Node contract.** A node's code defines a function; the entry point is a function named after the
  node, else `process`, else the last function defined. Input ports bind to arguments by name;
  `params state t dt step ctx` are injected when requested; `**inputs` receives every wired value.
  The return value is normalised to `{port: value}`.
* **Call plans.** `Run._make_plan` decides once per node how each argument is filled
  (`_ARG_INPUT / _ARG_SPECIAL / _ARG_PARAM / _ARG_NONE`). Precedence: a wired value, then the function
  default for unconnected inputs, then specials, then a parameter of the same name.
* **Loops.** `schedule()` groups strongly connected components into blocks. In `run()` a cyclic
  block is iterated to a fixed point (`_close` decides convergence). In `simulate()` a block is
  evaluated once per step; edges pointing backwards within it read `prev_outputs` — a one-step
  delay. Stateful nodes are ordered first inside a block because they have no feed-through.
* **Groups.** A node with `subgraph` compiles to `_Group`; `Run._call_group` keeps an inner `Run`
  in the node's state, so every copy of a group has independent state. `ctx.inp` / `ctx.out` connect
  Group Input/Output nodes to the outer ports.
* **Flags.** `bypass` / `frozen` compile to `_Flagged` (code never runs); `break_if` is evaluated
  after the node in `_exec_one`; `cache: false` opts out of the result cache.
* **Result cache.** `run(cache=True)` keys each call by `(code, resolved params, inputs)`; code that
  looks impure (`random`, `time.`, I/O …) is never cached. LRU of 512 entries.
* **stdout.** `_capture()` installs one `_StdoutRouter` for the whole run; each call sets
  `router.run/node`, so `print()` output lands in `run.stdout[node]`.
* **Sessions.** `Session` keeps a `Run` alive between HTTP requests; `step(n, params)` applies
  parameter changes (raw values, re-resolved) and advances `n` steps, returning a trace chunk.

## Frontend hooks

The editor core calls these on `window.KnodeSci` when present:

| hook | called from | used for |
|---|---|---|
| `drawUnderlays(ctx, renderer)` | `Renderer.render`, after the grid | frames |
| `drawOverlays(ctx, renderer)` | `Renderer.render`, after nodes | values, sparklines, probes, flags, heat-maps, port shapes, tooltips |
| `drawReroute(ctx, node, renderer)` | `Renderer.drawNode` | reroute dots instead of full nodes |
| `wireStyle` (value) | `Renderer.getCurvePoint` | global routing for wires whose curve type is 'bezier' |
| `subtitle(node)` | `Renderer._drawNodeImpl` | the lines shown inside a node |
| `decorateProperties(node, el)` | `updatePropertiesPanel` | parameters, flags, results, pins |
| `getLevelMeta / setLevelMeta` | `createSnapshot / restoreSnapshot` | per-level data (frames), undoable |
| `getModelMeta / setModelMeta` | `Graph.toJSON / fromJSON` | model data (dashboard, scenarios) |

Layers extend each other by wrapping: e.g. `knode_studio.js` replaces `KS.drawOverlays` with a
function that calls the previous one and then draws its own badges. Internal calls go through `KS.*`
(`KS.applyResults`, `KS.serialize`, `KS.openPalette`) so later layers can intercept them.

## Performance design (0.7)

* **Parallel studies** — `knode_engine.pmap` sends independent model runs to a persistent
  `ProcessPoolExecutor` (start method *forkserver*/*spawn*, never *fork*, because the threaded server could
  hand a locked `_EXEC_LOCK` to a forked child). Random draws happen in the parent before dispatch, and
  `map` preserves order, so results do not depend on the worker count. Differential evolution is
  generation-synchronous for the same reason. Any pool failure falls back to serial.
* **Live mode** — `requestChunk()` is issued before the previous chunk is processed (pipelining) and the chunk
  size adapts to ~25 ms per round trip.
* **Rendering** — `render()` coalesces into one `requestAnimationFrame` draw (`renderNow()` draws at once);
  opaque canvas; `traceWire()` emits native curve commands; wires and nodes are culled against the view;
  LOD for shadows/text; memoised text layout; the wire-animation loop stops when no wire animates.
* **Measure first** — `bench/bench_engine.py` for the engine; browser measurements in the About centre. A
  pattern-filled grid was tried and removed because it measured slower.

## Backend lifecycle

```
python knode.py ──starts──▶ server.py (KNODE_SUPERVISED=1)
      ▲                          │ POST /admin/restart → exit 3 → launcher starts it again
      └──────────── exit code ───┤ POST /admin/shutdown → exit 0 → launcher exits
                                 └ crash (other code) → restart with back-off (max 5 in a row)
```

Without the launcher, `/admin/restart` re-executes `server.py` in place (`os.execv`). All `/admin/*`
routes check `request.remote_addr` and refuse anything but localhost. The UI's `BACKEND_URL` is a
`let` in index.html so knode_backend.js can switch backends at runtime (persisted in localStorage).

## Undo / redo

`saveState()` pushes a deep-copied snapshot; `undo()` skips snapshots identical to the current state
(so code may save before *or* after a change) and restores the previous one. Snapshots include
`meta` (frames). Group editing swaps the undo stacks: each level has its own history.

## Extending knode

### Add a built-in node type
Add a `T(...)` call in `knode_library.py` (or `knode_universal.py`):

```python
T("my_decay", "Biology & Chemistry", "First-order Decay", ["x"], ["y"], {"k": 0.1}, """
    def process(x=None, params=None, state=None, dt=0.01):
        y = state.get("y", ks.pick(x, 1.0))
        state["y"] = y * math.exp(-params["k"] * dt)      # exact step
        return {"y": y}
""", "dy/dt = −k·y, advanced exactly.", sim=True, refs=["…"])
```

Then add a test in `tests/` that checks it against an analytic result. Users can do the same without
touching code via the Node Designer (saved to `user_library/`).

### Parameter-derived ports
Give the template `ports={"inputs": [...], "outputs": [...]}` using the rule language evaluated in
both `knode_universal.derive_ports` (Python) and `derivePorts` (knode_science.js):
`list:<param>` · `lhs:<param>` · `species:<param>` · `smout:<param>` · `const:a,b` · `suffix:<param>:<text>`.
Add a `schema` entry per parameter for its widget (`kind`, `min`, `max`, `step`, `unit`, `options`, `doc`).

### Add an endpoint
Add a function to `knode_engine.py` that returns a report dict (use `to_jsonable`), a route in
`server.py` (use `jresp`/`body`), a line in the endpoint map at the top of `server.py`, and a test.

## Testing & benchmarking

```bash
python tests/test_engine.py        # 36 — numerics and engine basics
python tests/test_universal.py     # 25 — universal nodes, groups, user library
python tests/test_adopted.py       # 13 — flags, cache, wireless, globals, sessions, scenarios, calibration
python tests/test_perf.py          #  8 — optimised engine ≡ 0.4 results, stdout routing, scaling
python tests/test_server.py        #  8 — HTTP API, admin endpoints, localhost-only guard, sessions, workers
python tests/test_parallel.py      #  6 — parallel studies ≡ serial, work really runs in worker processes
python bench/bench_engine.py       # timings; --json for machine-readable output
```

Optimisations must keep `tests/test_perf.py` green: it compares against values recorded from the
unoptimised engine, including the exact random stream of the agent-based model.

## Conventions

* Python: docstrings on every public function and class; comments explain *why*, not *what*.
* JavaScript: `/** … */` on every function; section banners `// ===== name` inside each file.
* Numerical code states its method, order/stability conditions and a reference.
* No new runtime dependencies beyond Flask; numpy and h5py stay optional.

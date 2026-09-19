"""
knode server — serves the editor and executes graphs.

    python server.py                 # http://127.0.0.1:5000
    python server.py --port 8080
    python server.py --host 0.0.0.0  # ONLY on a trusted network: nodes run arbitrary Python

Requires: flask  (numpy optional; h5py optional for real HDF5 export)

HTTP API (JSON in, JSON out; every POST body is an engine payload plus the listed options)
----------------------------------------------------------------------------------------
GET  /                          the editor (index.html) and its .js assets
GET  /api/health                version, numpy / h5py availability
GET  /library                   node templates + category colours      POST /library/user   save a node type
GET  /examples                  example models                          DELETE /library/user/<id>
POST /graph/execute             run once        {target?, cache?, dt?}
POST /graph/simulate            simulate        {steps, dt, t0?, record?, max_points?}
POST /session/start|step|stop   live mode       start {dt} → id;  step {id, n, params?, max_points?}
POST /graph/analyze             structure       {weights?}
POST /graph/sweep               1-D sweep       {node, param, values, target_node, target_port, mode, reduce}
POST /graph/montecarlo          uncertainty     {factors, n, seed, target_node, target_port, mode, reduce}
POST /graph/scenarios           variants        {scenarios: [{name, overrides}], mode, steps, dt}
POST /graph/optimize            calibration     {factors, objective, method, budget, mode, steps, dt}
POST /cache/clear               empty the result cache
POST /node/<id>/execute         run one node with explicit inputs (code editor ▶ Test, Node Designer)
POST /export/hdf5, /import/hdf5 real HDF5 files (needs h5py)
Legacy 0.1 endpoints: /graph/state, /graph/compile, /node/<id>/update_code.

Backend manager (localhost only — refused for remote clients even with --host 0.0.0.0):
GET  /admin/info                 pid, uptime, Python, packages, sessions, cache, settings, supervisor
GET  /admin/logs?since=N         request / event log (ring buffer of the last 2 000 lines)
POST /admin/settings             {cache_size, session_idle_minutes, time_limit}
POST /admin/restart              restart the server process (supervised: via knode.py; else re-exec)
POST /admin/shutdown             stop the server (and the launcher)
POST /admin/install              {package: numpy|h5py} pip-install an optional dependency
DELETE /admin/sessions/<id>      end a live session

Security: the server binds to 127.0.0.1 and only answers CORS requests from local pages, because
executing a graph means executing its Python code.
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import platform
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

from flask import Flask, Response, request, send_file, send_from_directory

import knode_engine as E
import knode_examples as X
import knode_library as L

try:
    import h5py
except Exception:
    h5py = None

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)

# ---------------------------------------------------------------- backend-manager state
STARTED = time.time()
SUPERVISED = os.environ.get("KNODE_SUPERVISED") == "1"   # started by knode.py (restart = exit code 3)
EXIT_RESTART = 3
LOG = collections.deque(maxlen=2000)                      # (seq, time, level, text) — shown in the Backend Manager
_log_seq = [0]
SETTINGS = {"time_limit": 120.0}
OPTIONAL_PACKAGES = ("numpy", "h5py")                     # the only packages the UI may install


def log(text, level="info"):
    """Append a line to the in-memory log shown in the Backend Manager (and echo to the console)."""
    _log_seq[0] += 1
    LOG.append((_log_seq[0], time.time(), level, str(text)))
    print(f"[{level}] {text}", file=sys.stderr)

# last graph pushed by the editor (kept for the legacy per-node endpoints)
graph_state = {"nodes": {}, "connections": []}


# ---------------------------------------------------------------- helpers

def jresp(obj, status=200):
    """JSON response that is always valid JSON (no NaN/Infinity literals).

    0.7: engine reports are already JSON-safe, so they are encoded directly (compact separators);
    only if that fails is the object passed through to_jsonable() — the generic conversion used to
    walk every value of every trace a second time.
    """
    try:
        body = json.dumps(obj, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        body = json.dumps(E.to_jsonable(obj), allow_nan=False, separators=(",", ":"))
    return Response(body, status=status, mimetype="application/json")


def body():
    """The request's JSON body, or {} when absent or malformed."""
    return request.get_json(force=True, silent=True) or {}


def _local_origin(origin: str) -> bool:
    """CORS policy: only localhost pages, file:// pages ('null' origin) and this server's own host may call the API."""
    if not origin or origin == "null":            # file:// pages send "null"
        return True
    host = urlparse(origin).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host == request.host.split(":")[0]


@app.before_request
def _t0():
    """Remember when the request started (for the duration shown in the log)."""
    request._t0 = time.perf_counter()


@app.after_request
def _access_log(resp):
    """Record every API call (method, path, status, duration) except log polling itself."""
    if not request.path.startswith("/admin/logs") and request.path != "/api/health":
        ms = (time.perf_counter() - getattr(request, "_t0", time.perf_counter())) * 1000
        log(f"{request.method} {request.path} → {resp.status_code} ({ms:.0f} ms)", "warn" if resp.status_code >= 400 else "info")
    return resp


@app.after_request
def cors(resp):
    """Add CORS headers for local origins (lets the editor be opened from file:// during development)."""
    origin = request.headers.get("Origin")
    if origin and _local_origin(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.errorhandler(Exception)
def on_error(e):
    """Turn any unhandled exception into a JSON error (with traceback for 500s) instead of an HTML page."""
    import traceback
    code = getattr(e, "code", 500)
    return jresp({"success": False, "error": f"{type(e).__name__}: {e}",
                  "traceback": traceback.format_exc() if code == 500 else ""}, code if isinstance(code, int) else 500)


# ---------------------------------------------------------------- static

@app.route("/")
def index():
    """Serve the editor."""
    return send_from_directory(HERE, "index.html")


@app.route("/<path:name>")
def static_files(name):
    """Serve the editor's own top-level assets (.js, .css, images); nothing outside the app folder."""
    if name.endswith((".js", ".css", ".png", ".svg", ".html")) and "/" not in name.strip("/"):
        return send_from_directory(HERE, name)
    return jresp({"error": "not found"}, 404)


# ---------------------------------------------------------------- meta

@app.route("/api/health")
def health():
    """Version and optional-dependency report; the editor uses it for the status dot and feature switches."""
    return jresp({"ok": True, "version": E.__version__, "python": platform.python_version(),
                  "numpy": E.np is not None, "h5py": h5py is not None, "supervised": SUPERVISED,
                  "pid": os.getpid(), "started": STARTED})


@app.route("/library")
def library():
    """All node templates (built-in + user) with category colours."""
    return jresp(L.get_library())


@app.route("/library/user", methods=["POST"])
def save_user_type():
    """Save a node type designed in the editor (validated: code must compile and define a function)."""
    t = body()
    spec = E.NodeSpec("probe", t.get("name", "probe"), t.get("code", ""), t.get("inputs", []), t.get("outputs", []),
                      dict(t.get("params", {})))
    try:
        E.compile_node(spec)
    except E.CompileError as e:
        return jresp({"success": False, "error": str(e), "line": e.line}, 400)
    try:
        saved = L.save_user_template(t)
    except ValueError as e:
        return jresp({"success": False, "error": str(e)}, 400)
    return jresp({"success": True, "template": saved})


@app.route("/library/user/<tid>", methods=["DELETE"])
def delete_user_type(tid):
    """Delete a saved user node type."""
    try:
        L.delete_user_template(tid)
    except KeyError:
        return jresp({"success": False, "error": f"no user type '{tid}'"}, 404)
    return jresp({"success": True})


@app.route("/examples")
def examples():
    """Example models (layout + template references) for File ▸ Examples."""
    return jresp({"examples": X.EXAMPLES})


# ---------------------------------------------------------------- execution

@app.route("/graph/execute", methods=["POST"])
def execute_graph():
    """Run once. Optional 'target' restricts to that node and its ancestors; 'cache' enables result reuse."""
    d = body()
    graph_state.update(nodes=d.get("nodes", {}), connections=d.get("connections", []))
    rep = E.run(d, target=d.get("target"), time_limit=float(d.get("time_limit", SETTINGS["time_limit"])), dt=float(d.get("dt", 0.01)),
                cache=bool(d.get("cache", False)))
    return jresp(rep)


@app.route("/graph/simulate", methods=["POST"])
def simulate_graph():
    """Fixed-step simulation; returns traces (downsampled to ≤ max_points) and final outputs."""
    d = body()
    rep = E.simulate(d, steps=int(d.get("steps", 1000)), dt=float(d.get("dt", 0.01)), t0=float(d.get("t0", 0)),
                     record=d.get("record"), time_limit=float(d.get("time_limit", SETTINGS["time_limit"])),
                     max_points=int(d.get("max_points", 5000)))
    return jresp(rep)


@app.route("/session/start", methods=["POST"])
def session_start():
    """Start a live session (Live mode) for the posted model; returns its id and compile errors."""
    d = body()
    sid, s = E.session_start(d, dt=float(d.get("dt", 0.01)), t0=float(d.get("t0", 0)))
    errs = {k: v for k, v in s.run.errors.items()}
    return jresp({"success": not errs, "id": sid, "errors": errs, "cycles": s.cycles})


@app.route("/session/step", methods=["POST"])
def session_step():
    """Advance a live session by n steps with optional parameter changes; returns the new trace chunk."""
    d = body()
    try:
        s = E.session_get(d.get("id"))
    except KeyError as e:
        return jresp({"success": False, "error": str(e), "expired": True}, 404)
    n = max(1, min(int(d.get("n", 10)), 100000))
    return jresp(s.step(n, params=d.get("params"), max_points=int(d.get("max_points", 200))))


@app.route("/session/stop", methods=["POST"])
def session_stop():
    """End a live session."""
    E.session_stop(body().get("id"))
    return jresp({"success": True})


@app.route("/graph/scenarios", methods=["POST"])
def scenarios_route():
    """Run each named parameter variant and return all results (Run ▸ Scenarios)."""
    d = body()
    return jresp(E.scenarios(d, d.get("scenarios", []), mode=d.get("mode", "simulate"),
                             steps=int(d.get("steps", 1000)), dt=float(d.get("dt", 0.01))))


@app.route("/graph/optimize", methods=["POST"])
def optimize_route():
    """Calibrate / optimise parameters (differential evolution or Nelder–Mead), budget capped at 5 000 runs."""
    d = body()
    return jresp(E.optimize(d, d["factors"], d["objective"], mode=d.get("mode", "simulate"), steps=int(d.get("steps", 500)),
                            dt=float(d.get("dt", 0.01)), method=d.get("method", "de"), budget=min(int(d.get("budget", 300)), 5000),
                            seed=int(d.get("seed", 0))))


@app.route("/cache/clear", methods=["POST"])
def cache_clear():
    """Empty the incremental result cache."""
    E.clear_cache()
    return jresp({"success": True})


@app.route("/graph/analyze", methods=["POST"])
def analyze_graph():
    """Structural analysis: loops, depth, critical path, centralities, lint."""
    d = body()
    return jresp(E.analyze(d, weights=d.get("weights")))


@app.route("/graph/sweep", methods=["POST"])
def sweep_graph():
    """One-dimensional parameter sweep."""
    d = body()
    return jresp(E.sweep(d, d["node"], d["param"], d["values"], (d["target_node"], d["target_port"]),
                         mode=d.get("mode", "run"), reduce=d.get("reduce", "last"),
                         sim={"steps": int(d.get("steps", 500)), "dt": float(d.get("dt", 0.01))}))


@app.route("/graph/montecarlo", methods=["POST"])
def montecarlo_graph():
    """Latin-hypercube uncertainty propagation with rank-correlation sensitivity (≤ 5 000 samples)."""
    d = body()
    n = min(int(d.get("n", 100)), 5000)
    return jresp(E.montecarlo(d, d["factors"], (d["target_node"], d["target_port"]), n=n,
                              mode=d.get("mode", "run"), reduce=d.get("reduce", "last"), seed=int(d.get("seed", 0)),
                              sim={"steps": int(d.get("steps", 500)), "dt": float(d.get("dt", 0.01))}))


# ---------------------------------------------------------------- legacy (0.1.x) endpoints

@app.route("/graph/state", methods=["GET", "POST"])
def state():
    """Legacy 0.1 endpoint: store / return the last graph pushed by the editor."""
    if request.method == "POST":
        d = body()
        graph_state.update(nodes=d.get("nodes", {}), connections=d.get("connections", []))
        return jresp({"success": True})
    return jresp(graph_state)


@app.route("/graph/compile", methods=["POST"])
def compile_graph():
    """Compile every node and report syntax errors without executing anything."""
    g = E.parse_graph(body())
    errors = {}
    for nid, spec in g.nodes.items():
        try:
            E.compile_node(spec)
        except E.CompileError as e:
            errors[nid] = {"error": str(e), "line": e.line}
    return jresp({"success": not errors, "errors": errors})


@app.route("/node/<node_id>/update_code", methods=["POST"])
def update_code(node_id):
    """Legacy 0.1 endpoint: update a node's code in the stored graph."""
    n = graph_state["nodes"].get(str(node_id))
    if n is not None:
        n["code"] = body().get("code", n.get("code", ""))
    return jresp({"success": True, "node_id": node_id})


@app.route("/node/<node_id>/execute", methods=["POST"])
def execute_node(node_id):
    """Run one node in isolation with explicitly supplied inputs (code-editor ▶ Test)."""
    d = body()
    info = d.get("node") or graph_state["nodes"].get(str(node_id))
    if not info:
        return jresp({"success": False, "error": f"Node {node_id} not found — run the graph once first"}, 404)
    single = {"nodes": {str(node_id): info}, "connections": []}
    g = E.parse_graph(single)
    spec = g.nodes[str(node_id)]
    with E._capture():                      # serialise + route print() output into r.stdout
        r = E.Run(g)
        if not r.compile_all([str(node_id)]):
            err = r.errors[str(node_id)]
            return jresp({"success": False, "error": err["error"], "line": err.get("line"), "logs": []})
        try:
            out = r.call(str(node_id), d.get("inputs", {}) or {})
        except Exception as exc:
            r.fail(str(node_id), exc)
            err = r.errors[str(node_id)]
            return jresp({"success": False, "error": err["error"], "traceback": err["traceback"], "line": err["line"], "logs": []})
    return jresp({"success": True, "output": out, "stdout": r.stdout.get(str(node_id), ""),
                  "logs": [f"{spec.name}: {list(out)}"]})


# ---------------------------------------------------------------- HDF5

@app.route("/export/hdf5", methods=["POST"])
def export_hdf5():
    """Real HDF5 export (needs h5py): graph JSON as an attribute, simulation traces as compressed datasets."""
    if h5py is None:
        return jresp({"success": False, "error": "h5py not installed (pip install h5py)"}, 501)
    d = body()
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["knode_version"] = E.__version__
        f.attrs["graph_json"] = json.dumps(d.get("graph", {}))
        tr = d.get("traces") or {}
        if tr:
            grp = f.create_group("traces")
            for k, v in tr.items():
                grp.create_dataset(k, data=[float("nan") if x is None else x for x in v], compression="gzip")
        outs = d.get("outputs") or {}
        if outs:
            f.attrs["outputs_json"] = json.dumps(outs)
    buf.seek(0)
    return send_file(buf, mimetype="application/x-hdf5", as_attachment=True, download_name="knode_graph.h5")


@app.route("/import/hdf5", methods=["POST"])
def import_hdf5():
    """Read a file written by export_hdf5 back into graph JSON + traces."""
    if h5py is None:
        return jresp({"success": False, "error": "h5py not installed (pip install h5py)"}, 501)
    with h5py.File(io.BytesIO(request.get_data()), "r") as f:
        graph = json.loads(f.attrs["graph_json"])
        traces = {k: f["traces"][k][()].tolist() for k in f["traces"]} if "traces" in f else {}
    return jresp({"success": True, "graph": graph, "traces": traces})


# ---------------------------------------------------------------- backend manager (localhost only)

def _local_request():
    """Admin actions are allowed only from this machine, whatever --host says."""
    return request.remote_addr in ("127.0.0.1", "::1", "localhost")


def _admin_guard():
    """None if the request may use management endpoints, else a 403 response to return."""
    if not _local_request():
        return jresp({"success": False, "error": "backend management is only available from this machine"}, 403)
    return None


def _pkg_version(name):
    """Installed version of a package, or None if it is not installed."""
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


@app.route("/admin/info")
def admin_info():
    """Everything the Backend Manager shows: process, environment, sessions, cache, settings."""
    g = _admin_guard()
    if g:
        return g
    try:
        import resource
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform != "darwin" else 1024 * 1024)
    except Exception:
        rss_mb = None
    now = time.monotonic()
    sessions = [{"id": sid, "steps": s.k, "t": s.run.t, "idle_s": round(now - s.last_used, 1), "nodes": len(s.graph.nodes),
                 "stopped": s.stopped} for sid, s in E._SESSIONS.items()]
    return jresp({
        "version": E.__version__, "pid": os.getpid(), "uptime_s": round(time.time() - STARTED, 1),
        "python": platform.python_version(), "executable": sys.executable, "platform": platform.platform(),
        "cwd": HERE, "supervised": SUPERVISED, "peak_memory_mb": rss_mb,
        "packages": {p: _pkg_version(p) for p in ("flask", "numpy", "h5py")},
        "user_library": L.USER_DIR, "sessions": sessions,
        "cache": {"entries": len(E._CACHE), "capacity": E._CACHE_MAX},
        "settings": dict(SETTINGS, cache_size=E._CACHE_MAX, session_idle_minutes=E.SESSION_IDLE_S / 60, workers=E.WORKERS),
        "cpu_count": os.cpu_count(), "workers_in_use": E.worker_count(),     # parallel studies (0 = serial)
        "compiled_nodes": len(E._COMPILE_CACHE),
    })


@app.route("/admin/logs")
def admin_logs():
    """Log lines with sequence number > since (the UI polls incrementally)."""
    g = _admin_guard()
    if g:
        return g
    since = int(request.args.get("since", 0))
    return jresp({"lines": [list(x) for x in LOG if x[0] > since], "last": _log_seq[0]})


@app.route("/admin/settings", methods=["POST"])
def admin_settings():
    """Change runtime limits: result-cache capacity, live-session idle timeout, default time limit."""
    g = _admin_guard()
    if g:
        return g
    d = body()
    if "cache_size" in d:
        E._CACHE_MAX = max(0, min(100000, int(d["cache_size"])))
        while len(E._CACHE) > E._CACHE_MAX:
            E._CACHE.popitem(last=False)
    if "session_idle_minutes" in d:
        E.SESSION_IDLE_S = max(60, float(d["session_idle_minutes"]) * 60)
    if "time_limit" in d:
        SETTINGS["time_limit"] = max(1.0, float(d["time_limit"]))
    if "workers" in d:                                        # 0 = automatic, -1 = serial, n = fixed count
        E.WORKERS = max(-1, min(64, int(d["workers"])))
        E.shutdown_pool()                                     # the pool is recreated at the new size on next use
    log(f"settings changed: {d}")
    return admin_info()


def _exit_later(code):
    """Exit shortly after the HTTP response has been sent (so the UI receives it)."""
    def go():
        """Background thread body: wait for the response to be sent, then re-exec or exit with `code`."""
        time.sleep(0.4)
        if code == EXIT_RESTART and not SUPERVISED:
            log("restarting (re-exec)")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        os._exit(code)
    threading.Thread(target=go, daemon=True).start()


@app.route("/admin/restart", methods=["POST"])
def admin_restart():
    """Restart the server process: reloads code, optional packages and the user library."""
    g = _admin_guard()
    if g:
        return g
    log("restart requested from the UI")
    _exit_later(EXIT_RESTART)
    return jresp({"success": True, "supervised": SUPERVISED})


@app.route("/admin/shutdown", methods=["POST"])
def admin_shutdown():
    """Stop the server (the knode.py launcher exits too)."""
    g = _admin_guard()
    if g:
        return g
    log("shutdown requested from the UI")
    _exit_later(0)
    return jresp({"success": True})


@app.route("/admin/install", methods=["POST"])
def admin_install():
    """pip-install one of the optional packages into this Python (takes effect after a restart)."""
    g = _admin_guard()
    if g:
        return g
    pkg = body().get("package")
    if pkg not in OPTIONAL_PACKAGES:
        return jresp({"success": False, "error": f"only {', '.join(OPTIONAL_PACKAGES)} can be installed from the UI"}, 400)
    log(f"installing {pkg} …")
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", pkg]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as e:
        return jresp({"success": False, "error": str(e)}, 500)
    if p.returncode != 0 and "externally-managed" in (p.stderr or ""):
        cmd.append("--break-system-packages")               # Debian/Ubuntu system Python (PEP 668)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    ok = p.returncode == 0
    log(f"install {pkg}: {'ok' if ok else 'failed'}", "info" if ok else "error")
    return jresp({"success": ok, "output": (p.stdout + p.stderr)[-6000:], "restart_needed": ok})


@app.route("/admin/sessions/<sid>", methods=["DELETE"])
def admin_kill_session(sid):
    """End a live session (e.g. one left running by another browser tab)."""
    g = _admin_guard()
    if g:
        return g
    E.session_stop(sid)
    log(f"session {sid} ended from the Backend Manager")
    return jresp({"success": True})


# ---------------------------------------------------------------- main

def main():
    """Command-line entry point: parse --host/--port/--debug and start the server (localhost by default)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: nodes execute arbitrary Python. Anyone who can reach "
              f"{a.host}:{a.port} can run code on this machine.", file=sys.stderr)
    print(f"knode {E.__version__}  →  http://{'127.0.0.1' if a.host == '0.0.0.0' else a.host}:{a.port}")
    print(f"user node types: {L.USER_DIR}")
    log(f"knode {E.__version__} started on {a.host}:{a.port} (pid {os.getpid()}{', supervised' if SUPERVISED else ''})")
    app.run(host=a.host, port=a.port, debug=a.debug, threaded=True)


if __name__ == "__main__":
    main()

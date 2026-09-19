"""
knode_engine — headless execution engine for knode graphs.

Architecture
============
::

    editor / CLI payload ──parse_graph──▶ Graph(NodeSpec…, Edge…)
                                            │  resolve_params()   '=expressions' against Globals nodes
                                            │  schedule()         Tarjan SCCs → ordered blocks + back edges
                                            ▼
                                          Run  (one execution session: state, outputs, errors, stdout)
                                            │  compile_all()      code → CompiledNode (cached by code hash)
                                            │  execute_pass()     one sweep over the blocks
                                            │    └ _exec_one → gather (wired inputs) → call (flags, cache,
                                            │                  argument binding, the node function) → normalize
                                            ▼
                                          report()  JSON-safe dict returned to the caller

Entry points (all return a report dict):

* ``run``         single pass; cyclic components (algebraic loops) are iterated to a fixed point.
* ``simulate``    fixed-step time stepping; per-node ``state`` persists; loops are broken at back
                  edges carrying the previous step's value (explicit Gauss–Seidel coupling).
* ``Session``     the same stepping, advanced in chunks with parameter changes in between (Live mode).
* ``sweep``       1-D parameter sweep.            ``montecarlo``  Latin hypercube + rank sensitivity.
* ``scenarios``   named parameter variants.       ``optimize``    differential evolution / Nelder–Mead / data fits.
* ``analyze``     structure only: loops, depth, critical path, betweenness, PageRank, lint.

Node contract
-------------
A node is Python code defining a function. Input ports bind to arguments by name; the reserved
names ``params state t dt step ctx`` are injected on request; ``**inputs`` receives every wired
value. The function returns a dict of outputs (a bare value goes to the first output, a tuple is
zipped over the outputs). Groups (embedded graphs), bypassed and frozen nodes are handled by the
engine without running user code.

Concurrency
-----------
Node code may print(); stdout is process-global, so executions are serialised by one re-entrant
lock (``_capture``). The Flask server is threaded, but model execution is one-at-a-time.

Performance (0.5, 0.7)
----------------------
The hot loop precomputes argument-binding plans, gather plans and loop flags, reuses Ctx objects
and routes stdout through a single router instead of a redirect per call. The scheduler is linear
in the number of edges. See bench/bench_engine.py for measurements (2–3× faster simulations,
~10× faster scheduling of large models) and tests/test_perf.py for the equivalence checks.

0.7: studies (sweeps, Monte Carlo, scenarios, optimiser generations) run on a pool of worker processes
(``pmap``; automatic on multi-core machines, bit-identical to serial execution — tests/test_parallel.py);
traces are made JSON-safe in one pass (``_clean_traces``) instead of the generic recursive converter.

The engine accepts both the editor's execution payload (``{"nodes": {...}, "connections": [...]}``)
and the editor's export format (``{"nodes": {...}, "wires": [...]}``), so saved files run headlessly.
"""
from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import heapq
import inspect
import io
import json
import sys
import linecache
import math
import random
import re
import statistics
import threading
import time
import traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import knode_std as ks

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

__version__ = "0.7.0"

RESERVED = ("params", "state", "t", "dt", "step", "ctx")
_EXEC_LOCK = threading.RLock()          # stdout redirection is process-global
MAX_STDOUT = 20000


# ============================================================================
# graph model
# ============================================================================

@dataclass
class NodeSpec:
    """Everything the engine needs to know about one node, independent of the editor.

    Fields: id, display name, Python source, declared input/output port names, parameters
    (``params`` after '=expression' resolution, ``raw_params`` as written), template id,
    ``stateful`` (evolves over simulation steps — scheduled first inside loops), an optional
    embedded ``subgraph`` (group node) and ``flags`` (bypass / frozen / break_if / cache).
    """
    id: str
    name: str
    code: str
    inputs: List[str]
    outputs: List[str]
    params: Dict[str, Any] = field(default_factory=dict)
    template: Optional[str] = None
    stateful: bool = False
    subgraph: Optional[dict] = None         # group node: an embedded graph (editor snapshot format)
    flags: Dict[str, Any] = field(default_factory=dict)   # bypass, frozen, break_if, cache
    raw_params: Dict[str, Any] = field(default_factory=dict)  # params before "=expression" resolution


@dataclass
class Edge:
    """A wire: value of output ``sport`` of node ``src`` flows into input ``dport`` of ``dst``.

    ``kind`` is "data" for real wires and "relation" for dummy-port wires (structure only, never
    executed). ``order`` (the editor's wire id) fixes the order of fan-in lists.
    """
    src: str
    sport: str
    dst: str
    dport: str
    kind: str = "data"        # "data" | "relation" (dummy wires)
    order: int = 0


@dataclass
class Graph:
    """Parsed model: ``nodes`` by id and the list of ``edges`` (including wireless Send→Receive links)."""
    nodes: Dict[str, NodeSpec]
    edges: List[Edge]

    @property
    def data_edges(self):
        """Edges that carry values (excludes 'relation' edges from dummy ports).

        Cached (0.5): the list was rebuilt on every access, and the scheduler and Run access it
        thousands of times. The cache is keyed on the edge count, so appending edges invalidates it.
        """
        cache = self.__dict__.get("_data_cache")
        if cache is None or cache[0] != len(self.edges):
            cache = self.__dict__["_data_cache"] = (len(self.edges), [e for e in self.edges if e.kind == "data"])
        return cache[1]


def _port_names(ports, want_input=None):
    """Extract enabled, non-dummy port names from editor port dicts (or pass plain strings through).

    ``want_input`` filters by direction when the list mixes inputs and outputs.
    """
    names = []
    for p in ports or []:
        if isinstance(p, str):
            names.append(p)
            continue
        if p.get("isDummy") or p.get("enabled", True) is False:
            continue
        if want_input is not None and p.get("isInput", want_input) != want_input:
            continue
        names.append(p.get("name"))
    return [n for n in names if n]


def parse_graph(payload: dict) -> Graph:
    """Build a Graph from an execution payload or an exported editor file."""
    raw_nodes = payload.get("nodes") or {}
    if isinstance(raw_nodes, list):
        raw_nodes = {str(n.get("id")): n for n in raw_nodes}
    nodes: Dict[str, NodeSpec] = {}
    for nid, n in raw_nodes.items():
        nid = str(n.get("id", nid)) if isinstance(n.get("id"), (int, str)) else str(nid)
        props = n.get("properties") or {}
        params = n.get("params", props.get("params")) or {}
        template = n.get("template", props.get("template"))
        code = n.get("code") or "def process():\n    return {}\n"
        subgraph = n.get("subgraph", props.get("subgraph"))
        stateful = bool(n.get("stateful")) or bool(re.search(r"\bstate\b", code)) or subgraph is not None
        flags = {k: props.get(k, n.get(k)) for k in ("bypass", "frozen", "break_if", "cache") if props.get(k, n.get(k)) is not None}
        nodes[nid] = NodeSpec(nid, n.get("name") or f"Node{nid}", code,
                              _port_names(n.get("inputs"), True), _port_names(n.get("outputs"), False),
                              dict(params), template, stateful, subgraph, flags, copy.deepcopy(dict(params)))
    raw_edges = payload.get("connections")
    if raw_edges is None:
        raw_edges = payload.get("wires") or []
    if isinstance(raw_edges, dict):
        raw_edges = list(raw_edges.values())
    edges = []
    for i, w in enumerate(raw_edges):
        if w.get("enabled", True) is False:
            continue
        kind = w.get("kind") or ("relation" if w.get("wireClass") == "dummy" else "data")
        e = Edge(str(w.get("from")), w.get("fromPort"), str(w.get("to")), w.get("toPort"), kind,
                 int(w.get("id", i)) if str(w.get("id", i)).lstrip("-").isdigit() else i)
        if e.src in nodes and e.dst in nodes:
            edges.append(e)
    # wireless links (Node-RED "link" nodes): Send(channel) → every Receive(channel)
    senders = defaultdict(list)
    for nid, sp in nodes.items():
        if sp.template == "send":
            senders[str(sp.params.get("channel", ""))].append(nid)
    for nid, sp in nodes.items():
        if sp.template == "receive":
            for src in senders.get(str(sp.params.get("channel", "")), []):
                edges.append(Edge(src, "value", nid, "_wireless", "data", 10 ** 9 + len(edges)))
    edges.sort(key=lambda e: e.order)
    return Graph(nodes, edges)


# ============================================================================
# parameter expressions & globals (Houdini ch(), Blender drivers, Simulink model workspace)
# ============================================================================

def resolve_params(g: "Graph"):
    """Evaluate every string parameter that starts with '=' against the Globals nodes.

    Globals nodes' params are evaluated in order (later ones may use earlier ones).
    ``P("Node name", "param")`` reads another node's (resolved) parameter.
    Returns {node_id: error message} for expressions that failed.
    """
    errors = {}
    env = {}
    by_name = {sp.name: sp for sp in g.nodes.values()}

    def P(node_name, param):
        """Expression helper: P("Node name", "param") reads another node's (resolved) parameter."""
        sp = by_name.get(node_name)
        if sp is None:
            raise NameError(f"P(): no node named {node_name!r}")
        v = sp.params.get(param)
        if isinstance(v, str) and v.startswith("="):
            v = ks.eval_expr(v[1:], dict(env, P=P))
        return v

    def ev(v):
        """Evaluate a parameter value: strings starting with '=' are expressions, everything else is returned as is."""
        if isinstance(v, str) and v.startswith("=") and not v.startswith("=="):
            return ks.eval_expr(v[1:].strip(), dict(env, P=P))
        return v

    for nid in sorted(g.nodes, key=_idkey):
        sp = g.nodes[nid]
        sp.params = copy.deepcopy(sp.raw_params)
    for nid in sorted(g.nodes, key=_idkey):
        sp = g.nodes[nid]
        if sp.template != "globals":
            continue
        for k, v in sp.raw_params.items():
            try:
                env[k] = sp.params[k] = ev(v)
            except Exception as e:
                errors[nid] = f"global '{k}': {type(e).__name__}: {e}"
    for nid, sp in g.nodes.items():
        if sp.template == "globals":
            continue
        for k, v in sp.raw_params.items():
            try:
                sp.params[k] = ev(v)
            except Exception as e:
                errors[nid] = f"parameter '{k}' = {v!r}: {type(e).__name__}: {e}"
    return errors


# ============================================================================
# incremental cache (ComfyUI / Houdini cooking): unchanged node + unchanged inputs → reuse
# ============================================================================

_CACHE: "OrderedDict[str, dict]" = None
_CACHE_MAX = 512
_IMPURE = re.compile(r"\brandom\b|np\.random|\btime\.|datetime|uuid|\bopen\(|requests|urllib|input\(")


def _cache_key(spec, inputs):
    """Content hash of (code, resolved params, inputs) — the identity of a pure computation.

    Returns None when inputs cannot be serialised; such calls are simply not cached.
    """
    try:
        blob = json.dumps([spec.code, spec.params, to_jsonable(inputs)], sort_keys=True, default=repr)
    except Exception:
        return None
    return hashlib.sha1(blob.encode()).hexdigest()


def clear_cache():
    """Empty the incremental result cache (Run ▸ Clear result cache; tests call it for isolation)."""
    global _CACHE
    from collections import OrderedDict
    _CACHE = OrderedDict()


clear_cache()


# ============================================================================
# compilation
# ============================================================================

def sanitize(name: str) -> str:
    """Turn a node name into a valid Python identifier (used to find a function named after its node)."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name or "")
    s = re.sub(r"^[0-9]", "_", s)
    s = re.sub(r"_{2,}", "_", s)
    return s or "process"


class CompileError(Exception):
    """Raised when a node's code does not compile or defines no function; ``line`` points into the node source."""
    def __init__(self, message, line=None):
        super().__init__(message)
        self.line = line


@dataclass
class CompiledNode:
    """A node's code after compilation: the callable, its signature and a synthetic filename.

    The filename ``<knode:id:name:hash>`` is registered with linecache so tracebacks show node
    source lines; ``var_kw`` records whether the function accepts ``**inputs``.
    """
    spec: NodeSpec
    func: Any
    signature: inspect.Signature
    filename: str

    def __post_init__(self):
        # computed once — 0.4 re-scanned the signature on every call
        self.var_kw = any(p.kind == p.VAR_KEYWORD for p in self.signature.parameters.values())


def base_namespace(filename: str) -> dict:
    """Globals every node's code starts with: math, random, statistics, json, re, ks (knode_std), np."""
    ns = {"__name__": filename, "__builtins__": __builtins__, "math": math, "random": random,
          "statistics": statistics, "json": json, "re": re, "ks": ks}
    if np is not None:
        ns["np"] = np
    return ns


_COMPILE_CACHE: Dict[Tuple[str, str], CompiledNode] = {}


def compile_node(spec: NodeSpec) -> CompiledNode:
    """Compile a node's source and pick its entry function (cached per id + code hash + name).

    The entry function is, in order: a function named after the node, ``process``, or the last
    function defined in the cell. Only functions defined in the node's own code qualify, so
    imported or builtin callables (``print``, ``len`` …) are never picked by accident — a bug in 0.1.
    """
    digest = hashlib.sha1(spec.code.encode()).hexdigest()[:12]
    key = (spec.id, digest + spec.name)
    hit = _COMPILE_CACHE.get(key)
    if hit is not None:
        hit.spec = spec
        return hit
    filename = f"<knode:{spec.id}:{spec.name}:{digest}>"
    lines = spec.code.splitlines(True)
    linecache.cache[filename] = (len(spec.code), None, lines, filename)
    try:
        code_obj = compile(spec.code, filename, "exec")
    except SyntaxError as e:
        raise CompileError(f"SyntaxError: {e.msg} (line {e.lineno})", e.lineno) from None
    ns = base_namespace(filename)
    try:
        exec(code_obj, ns)
    except Exception as e:  # error at module level of the node
        raise CompileError(f"{type(e).__name__} while loading code: {e}") from None
    own = [v for v in ns.values() if inspect.isfunction(v) and v.__code__.co_filename == filename]
    func = None
    for cand in (sanitize(spec.name), "process"):
        f = ns.get(cand)
        if inspect.isfunction(f) and f.__code__.co_filename == filename:
            func = f
            break
    if func is None and own:
        func = own[-1]                  # last function defined in the cell
    if func is None:
        raise CompileError("no function defined (define `def process(...)`)")
    cn = CompiledNode(spec, func, inspect.signature(func), filename)
    if len(_COMPILE_CACHE) > 2000:
        _COMPILE_CACHE.clear()
    _COMPILE_CACHE[key] = cn
    return cn


# ============================================================================
# JSON-safe conversion
# ============================================================================

def to_jsonable(v, depth=0, max_items=20000):
    """Convert any Python value into something ``json.dumps(allow_nan=False)`` accepts.

    NaN → None, ±inf → "Infinity"/"-Infinity", complex → {re, im}, numpy arrays/scalars → lists/
    numbers, sets/tuples → lists, bytes → base64, dataclasses → dicts, anything else → repr().
    Long sequences are truncated to ``max_items`` with a marker string (traces pass a huge limit).
    """
    if depth > 12:
        return repr(v)
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v if abs(v) < 2 ** 53 else str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return None
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        return v
    if isinstance(v, complex):
        return {"re": to_jsonable(v.real), "im": to_jsonable(v.imag)}
    if np is not None:
        if isinstance(v, np.ndarray):
            return to_jsonable(v.tolist(), depth + 1, max_items)
        if isinstance(v, np.generic):
            return to_jsonable(v.item(), depth + 1)
    if isinstance(v, dict):
        return {str(k): to_jsonable(x, depth + 1, max_items) for k, x in list(v.items())[:max_items]}
    if isinstance(v, (list, tuple, set, frozenset, deque)):
        seq = list(v)
        out = [to_jsonable(x, depth + 1, max_items) for x in seq[:max_items]]
        if len(seq) > max_items:
            out.append(f"… {len(seq) - max_items} more")
        return out
    if isinstance(v, (bytes, bytearray)):
        return {"__bytes__": base64.b64encode(bytes(v)).decode()}
    if hasattr(v, "__dataclass_fields__"):
        from dataclasses import asdict
        return to_jsonable(asdict(v), depth + 1)
    return repr(v)


_INF = float("inf")


def _clean_series(s):
    """JSON-safe copy of a trace (floats and None): NaN → None, ±inf → "Infinity"/"-Infinity".

    Fast path (0.7): traces are almost always finite, so the list is returned unchanged after one
    cheap scan instead of being rebuilt value by value by the generic to_jsonable().
    """
    for v in s:
        if v is not None and (v != v or v == _INF or v == -_INF):
            break
    else:
        return s
    return [None if (v is None or v != v) else ("Infinity" if v == _INF else "-Infinity" if v == -_INF else v) for v in s]


def _clean_traces(tr):
    """Apply _clean_series to every series of a {"t": [...], "node.port": [...]} trace dict."""
    return {k: _clean_series(v) for k, v in tr.items()}


def _is_number(v):
    """True for real numbers (Python or numpy), False for bools and everything else."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) or (np is not None and isinstance(v, np.number))


# ============================================================================
# graph algorithms
# ============================================================================

def tarjan_scc(nodes: List[str], adj: Dict[str, List[str]]) -> List[List[str]]:
    """Iterative Tarjan; returns SCCs in reverse topological order."""
    index, low, onstack, stack, out = {}, {}, set(), [], []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                onstack.add(v)
            recurse = False
            nbrs = adj.get(v, [])
            for j in range(i, len(nbrs)):
                w = nbrs[j]
                if w not in index:
                    work.append((v, j + 1))
                    work.append((w, 0))
                    recurse = True
                    break
                if w in onstack:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    onstack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(comp)
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return out


def _idkey(x):
    """Sort key that orders numeric ids numerically and text ids alphabetically after them."""
    return (0, int(x)) if str(x).lstrip("-").isdigit() else (1, str(x))


def schedule(graph: Graph, subset=None):
    """Return (blocks, back_edges, cycles).

    blocks: list of lists of node ids in execution order; a block of size > 1
    (or a self-loop) is a cyclic SCC. Inside a block, nodes are ordered with
    stateful nodes first (they have no feed-through), then by id, and edges
    pointing backwards in that order are back edges.
    """
    ids = sorted(subset if subset is not None else graph.nodes.keys(), key=_idkey)
    idset = set(ids)
    data = [e for e in graph.data_edges if e.src in idset and e.dst in idset]
    out_edges = defaultdict(list)                 # node → its outgoing data edges (for back-edge search)
    for e in data:
        out_edges[e.src].append(e)
    selfloops = {e.src for e in data if e.src == e.dst}
    adj = defaultdict(list)
    for e in data:
        if e.dst not in adj[e.src]:
            adj[e.src].append(e.dst)
    for k in adj:
        adj[k].sort(key=_idkey)
    sccs = tarjan_scc(ids, adj)
    comp_of = {v: i for i, c in enumerate(sccs) for v in c}
    # Kahn over condensation, deterministic by min id
    cadj = defaultdict(set)
    indeg = defaultdict(int)
    for u in ids:
        for v in adj.get(u, []):
            cu, cv = comp_of[u], comp_of[v]
            if cu != cv and cv not in cadj[cu]:
                cadj[cu].add(cv)
                indeg[cv] += 1
    heap = [(min(map(_idkey, sccs[c])), c) for c in range(len(sccs)) if indeg[c] == 0]
    heapq.heapify(heap)
    blocks, back, cycles = [], set(), []
    while heap:
        _, c = heapq.heappop(heap)
        comp = sorted(sccs[c], key=lambda n: (not graph.nodes[n].stateful, _idkey(n)))
        pos = {n: i for i, n in enumerate(comp)}
        # 0.5: only this component's own edges are examined (0.4 scanned every edge of the
        # graph for every component — quadratic in model size)
        if len(comp) > 1 or comp[0] in selfloops:
            cycles.append(comp)
            for n in comp:
                for e in out_edges[n]:
                    if e.dst in pos and pos[n] >= pos[e.dst]:
                        back.add(id(e))
        blocks.append(comp)
        for d in cadj[c]:
            indeg[d] -= 1
            if indeg[d] == 0:
                heapq.heappush(heap, (min(map(_idkey, sccs[d])), d))
    return blocks, back, cycles


def ancestors(graph: Graph, target: str) -> set:
    """All nodes a target depends on through data edges (including the target) — 'Run to here'."""
    radj = defaultdict(list)
    for e in graph.data_edges:
        radj[e.dst].append(e.src)
    seen, q = {target}, deque([target])
    while q:
        v = q.popleft()
        for u in radj[v]:
            if u not in seen:
                seen.add(u)
                q.append(u)
    return seen


# ============================================================================
# execution
# ============================================================================

class StopSimulation(Exception):
    """Reserved for nodes that want to end a simulation by raising (ctx.stop() is preferred)."""
    pass


class _Flagged:
    """Placeholder for a bypassed or frozen node: its code is never compiled or executed."""
    def __init__(self, spec):
        self.spec = spec


class _Group:
    """Compiled form of a group node: its spec plus the parsed inner graph (executed by Run._call_group)."""

    def __init__(self, spec, graph):
        self.spec, self.graph = spec, graph


# ============================================================================
# stdout routing
# ============================================================================
# Nodes may print(). In 0.4 every single node call created a StringIO and a
# contextlib.redirect_stdout context — about a third of the per-call overhead
# for cheap nodes. Now one router object replaces sys.stdout for the whole run
# (installed once by _capture()) and each call only sets two attributes saying
# which Run/node is currently executing.

class _StdoutRouter(io.TextIOBase):
    """sys.stdout stand-in that appends text to ``run.stdout[node]`` of the node now executing."""

    def __init__(self):
        super().__init__()
        self.run = None       # the Run whose node is executing
        self.node = None      # that node's id

    def writable(self):
        """File-protocol flag: this stream accepts writes."""
        return True

    def write(self, s):
        """Append printed text to the executing node's buffer (capped at MAX_STDOUT characters per node)."""
        run, node = self.run, self.node
        if run is None:                          # printed outside any node: drop silently
            return len(s)
        cur = run.stdout.get(node, "")
        room = MAX_STDOUT - len(cur)
        if room > 0:                             # cap per node so a print-loop cannot exhaust memory
            run.stdout[node] = cur + s[:room]
        return len(s)


_ROUTER = _StdoutRouter()


@contextlib.contextmanager
def _capture():
    """Serialise execution (stdout is process-global) and route print() output to nodes."""
    with _EXEC_LOCK, contextlib.redirect_stdout(_ROUTER):
        prev = (_ROUTER.run, _ROUTER.node)     # re-entrant: sweeps call run() inside a capture
        try:
            yield
        finally:
            _ROUTER.run, _ROUTER.node = prev


# Names a node function can request as arguments; they are injected, not wired.
_SPECIALS = frozenset(RESERVED)
# Argument-binding kinds in a call plan (see Run._make_plan).
_ARG_INPUT, _ARG_SPECIAL, _ARG_PARAM, _ARG_NONE = 0, 1, 2, 3


class Ctx:
    """The ``ctx`` argument: a node's handle to its run (logging, stopping, group ports).

    One Ctx is created per node per Run and reused for every call (0.4 created one per call).
    """

    __slots__ = ("_run", "node_id")

    def __init__(self, run, nid):
        self._run, self.node_id = run, nid

    def inp(self, name, default=None):
        """Group Input: value of the enclosing group's input port ``name`` (``default`` when absent)."""
        v = self._run.external_in.get(name)
        return default if v is None else v

    def out(self, name, value):
        """Group Output: publish ``value`` on the enclosing group's output port ``name``."""
        self._run.external_out[name] = value

    def log(self, *msg):
        """Append a line to this node's log (shown in the State panel and returned in reports)."""
        self._run.node_logs[self.node_id].append(" ".join(map(str, msg)))

    def stop(self):
        """Ask the simulation to stop after the current step (e.g. when an event has occurred)."""
        self._run.stop_requested = True

    @property
    def t(self):
        """Current simulation time."""
        return self._run.t


class Run:
    """One execution session: a single pass (``run``) or a whole simulation (``simulate``/``Session``).

    A Run owns everything that changes while a model executes: compiled nodes, per-node
    ``state`` dicts, the current and previous step's outputs, statuses, errors, captured
    stdout, logs and profiling counters.

    Performance notes (0.5)
    -----------------------
    The inner loop is ``execute_pass → _exec_one → gather → call``. Everything that does not
    change between steps is computed once and cached on the Run:

    * ``_plans``     how to bind each node function's arguments (was: walk the signature every call)
    * ``_gplans``    per-node list of incoming edges with their back-edge flag (was: rebuilt per call)
    * ``_cyclic``    which blocks are loops (was: recomputed every step)
    * ``_ctxs``      one Ctx per node (was: one per call)
    * ``_breaks``    nodes that carry a break_if condition
    * stdout is routed by one ``_StdoutRouter`` for the whole run (was: redirect per call)
    """

    def __init__(self, graph: Graph, time_limit=60.0):
        self.graph = graph
        self.compiled: Dict[str, Any] = {}               # node id → CompiledNode | _Group | _Flagged
        self.state: Dict[str, dict] = defaultdict(dict)  # node id → persistent state dict
        self.outputs: Dict[str, dict] = {}               # this step's outputs
        self.prev_outputs: Dict[str, dict] = {}          # last step's outputs (feed back edges)
        self.status: Dict[str, str] = {}                 # ok | error | blocked
        self.errors: Dict[str, dict] = {}
        self.stdout: Dict[str, str] = {}
        self.node_logs: Dict[str, List[str]] = defaultdict(list)
        self.logs: List[str] = []
        self.warnings: List[str] = []
        self.profile: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0])   # id → [calls, seconds]
        self.t, self.dt, self.step = 0.0, 0.01, 0
        self.stop_requested = False
        self.deadline = time.monotonic() + time_limit
        self.in_edges = defaultdict(list)
        for e in graph.data_edges:
            self.in_edges[e.dst].append(e)
        self.simulating = False
        self.use_cache = False
        self.cached: List[str] = []
        self.breakpoint = None
        self.external_in: Dict[str, Any] = {}            # group ports, when this Run is a group's inside
        self.external_out: Dict[str, Any] = {}
        self.group_reports: Dict[str, dict] = {}
        # --- caches for the hot loop (see class docstring)
        self._plans: Dict[str, tuple] = {}
        self._gplans: Dict[str, tuple] = {}
        self._gplan_back = None                          # the back-edge set the gather plans were built for
        self._cyclic_for, self._cyclic = None, None
        self._ctxs: Dict[str, Ctx] = {}
        self._breaks = {nid: sp.flags["break_if"] for nid, sp in graph.nodes.items() if sp.flags.get("break_if")}
        # parameters written as "=expression" are resolved before anything runs
        for nid, msg in resolve_params(graph).items():
            self.status[nid] = "error"
            self.errors[nid] = {"error": msg, "line": None, "traceback": "", "phase": "parameters"}

    # ---------------------------------------------------------------- compile
    def compile_all(self, ids):
        """Compile the given nodes. Returns the ids that compiled; failures are recorded as errors.

        Bypassed/frozen nodes are wrapped without compiling (their code never runs), groups are
        parsed into ``_Group`` objects, everything else goes through the global compile cache.
        """
        ok = []
        for nid in ids:
            if nid in self.errors:
                continue
            spec = self.graph.nodes[nid]
            if spec.flags.get("bypass") or spec.flags.get("frozen") is not None:
                self.compiled[nid] = _Flagged(spec)
                ok.append(nid)
                continue
            if spec.subgraph is not None:
                try:
                    self.compiled[nid] = _Group(spec, parse_graph(spec.subgraph))
                    ok.append(nid)
                except Exception as e:
                    self.status[nid] = "error"
                    self.errors[nid] = {"error": f"invalid group: {e}", "line": None, "traceback": "", "phase": "compile"}
                continue
            try:
                cn = self.compiled[nid] = compile_node(spec)
                ok.append(nid)
                if not cn.var_kw:
                    accepted = cn.signature.parameters
                    for p in spec.inputs:
                        if p not in accepted:
                            self.warnings.append(f"{spec.name}: input port '{p}' is not a parameter of {cn.func.__name__}() and will be ignored")
            except CompileError as e:
                self.status[nid] = "error"
                self.errors[nid] = {"error": str(e), "line": e.line, "traceback": "", "phase": "compile"}
        return ok

    # ---------------------------------------------------------------- inputs
    def _gather_plan(self, nid, back):
        """Pre-resolve a node's incoming edges: ((dport, src, sport, is_back), ...) and a fan-in flag."""
        edges = tuple((e.dport, e.src, e.sport, id(e) in back) for e in self.in_edges[nid])
        ports = [d for d, _, _, _ in edges]
        return edges, len(ports) != len(set(ports))

    def gather(self, nid, back_edges, use_prev_for_back):
        """Collect the values arriving at a node's input ports.

        A back edge (one that closes a loop) reads the *previous* step's output when
        ``use_prev_for_back`` is true (simulation) — this is the one-step delay that makes
        feedback loops computable. Several wires into one port arrive as a list (fan-in).
        """
        if back_edges is not self._gplan_back:           # schedule changed → rebuild plans
            self._gplans, self._gplan_back = {}, back_edges
        gp = self._gplans.get(nid)
        if gp is None:
            gp = self._gplans[nid] = self._gather_plan(nid, back_edges)
        edges, fan_in = gp
        outs, prev = self.outputs, self.prev_outputs
        if not fan_in:                                   # common case: one wire per port → no lists
            res = {}
            for dport, src, sport, is_back in edges:
                if is_back and use_prev_for_back:
                    so = prev.get(src)
                else:
                    so = outs.get(src)
                    if so is None and is_back:
                        so = prev.get(src)
                res[dport] = None if so is None else so.get(sport)
            return res
        vals = defaultdict(list)
        for dport, src, sport, is_back in edges:
            if is_back and use_prev_for_back:
                so = prev.get(src)
            else:
                so = outs.get(src)
                if so is None and is_back:
                    so = prev.get(src)
            vals[dport].append(None if so is None else so.get(sport))
        return {k: (v[0] if len(v) == 1 else v) for k, v in vals.items()}

    # ---------------------------------------------------------------- call
    def call(self, nid, inputs):
        """Execute one node with the given inputs and return its normalised outputs dict.

        Order of precedence: frozen outputs → bypass pass-through → result cache → real call.
        """
        cn = self.compiled[nid]
        if isinstance(cn, _Flagged):
            spec = cn.spec
            if spec.flags.get("frozen") is not None:          # pinned data (n8n) / locked node (Houdini)
                return self.normalize(spec, copy.deepcopy(spec.flags["frozen"]))
            out = {}                                          # bypass: pass inputs through by name, else by position
            ins = [inputs.get(p) for p in spec.inputs]
            for i, o in enumerate(spec.outputs):
                out[o] = inputs[o] if o in inputs else (ins[i] if i < len(ins) else (ins[0] if ins else None))
            return self.normalize(spec, out)
        if self.use_cache and not self.simulating and not isinstance(cn, _Group):
            spec = cn.spec
            if spec.flags.get("cache", True) is not False and not _IMPURE.search(spec.code):
                key = _cache_key(spec, inputs)
                if key and key in _CACHE:                     # unchanged code + params + inputs → reuse
                    _CACHE.move_to_end(key)
                    self.cached.append(nid)
                    return copy.deepcopy(_CACHE[key])         # deep copies: downstream may mutate results
                res = self._call_uncached(nid, cn, inputs)
                if key:
                    _CACHE[key] = copy.deepcopy(res)
                    while len(_CACHE) > _CACHE_MAX:           # LRU eviction
                        _CACHE.popitem(last=False)
                return res
        return self._call_uncached(nid, cn, inputs)

    def _make_plan(self, cn):
        """Decide once how each argument of the node function is filled.

        Each entry is (name, kind, has_default):
          _ARG_INPUT   – an input port (wired value, or the function default when unconnected)
          _ARG_SPECIAL – params / state / t / dt / step / ctx
          _ARG_PARAM   – a parameter of the same name (``def f(k)`` receives params["k"])
          _ARG_NONE    – nothing matches and there is no default → None
        Arguments with a default that match nothing are simply left to their default.
        """
        spec, plan = cn.spec, []
        for pname, p in cn.signature.parameters.items():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            has_default = p.default is not p.empty
            if pname in spec.inputs:
                plan.append((pname, _ARG_INPUT, has_default))
            elif pname in _SPECIALS:
                plan.append((pname, _ARG_SPECIAL, has_default))
            elif pname in spec.params:
                plan.append((pname, _ARG_PARAM, has_default))
            elif not has_default:
                plan.append((pname, _ARG_NONE, has_default))
            else:
                plan.append((pname, -1, has_default))        # may still receive an undeclared wire
        return tuple(plan)

    def _call_uncached(self, nid, cn, inputs):
        """Bind arguments using the cached plan, call the node function, time it, normalise the result."""
        if isinstance(cn, _Group):
            t0 = time.perf_counter()
            res = self._call_group(nid, cn, inputs)
            prof = self.profile[nid]
            prof[0] += 1
            prof[1] += time.perf_counter() - t0
            return res
        spec = cn.spec
        plan = self._plans.get(nid)
        if plan is None:
            plan = self._plans[nid] = self._make_plan(cn)
        kwargs = {}
        for pname, kind, has_default in plan:
            if kind == _ARG_INPUT or pname in inputs:         # wired value wins over everything else
                v = inputs.get(pname)
                if v is None and has_default:
                    continue                                   # unconnected → function default
                kwargs[pname] = v
            elif kind == _ARG_SPECIAL:
                if pname == "params":
                    kwargs[pname] = spec.params
                elif pname == "state":
                    kwargs[pname] = self.state[nid]
                elif pname == "t":
                    kwargs[pname] = self.t
                elif pname == "dt":
                    kwargs[pname] = self.dt
                elif pname == "step":
                    kwargs[pname] = self.step
                else:                                          # ctx
                    c = self._ctxs.get(nid)
                    if c is None:
                        c = self._ctxs[nid] = Ctx(self, nid)
                    kwargs[pname] = c
            elif kind == _ARG_PARAM:
                kwargs[pname] = spec.params[pname]
            elif kind == _ARG_NONE:
                kwargs[pname] = None
        if cn.var_kw:                                          # **inputs receives every wired value
            for k, v in inputs.items():
                if k not in kwargs:
                    kwargs[k] = v
        router = _ROUTER
        router.run, router.node = self, nid                    # attribute print() output to this node
        t0 = time.perf_counter()
        result = cn.func(**kwargs)
        prof = self.profile[nid]
        prof[0] += 1
        prof[1] += time.perf_counter() - t0
        return self.normalize(spec, result)

    def _call_group(self, nid, grp, inputs):
        """Execute an embedded graph as one node; its state persists across simulation steps.

        The inner graph gets its own Run (created on first call and kept in this node's state),
        so each copy of a group has independent state. Group Input/Output nodes talk to this
        call through ``external_in`` / ``external_out``.
        """
        st = self.state[nid]
        inner = st.get("_run")
        if inner is None:
            g = copy.deepcopy(grp.graph)
            inner = Run(g)
            inner.deadline = self.deadline
            inner._blocks, inner._back, _ = schedule(g)
            inner.compile_all([n for b in inner._blocks for n in b])
            if inner.errors:
                k, e = next(iter(inner.errors.items()))
                raise RuntimeError(f"inside group, node '{g.nodes[k].name}': {e['error']}")
            st["_run"] = inner
        inner.simulating = self.simulating
        inner.t, inner.dt, inner.step = self.t, self.dt, self.step
        inner.external_in, inner.external_out = dict(inputs), {}
        inner.prev_outputs = inner.outputs if self.simulating else {}
        inner.outputs = {}
        inner.execute_pass(inner._blocks, inner._back, simulate=self.simulating)
        _ROUTER.run, _ROUTER.node = self, nid                  # inner prints resurface on the group node
        for k, txt in list(inner.stdout.items()):
            if txt:
                print(f"[{inner.graph.nodes[k].name}] {txt}", end="" if txt.endswith("\n") else "\n")
        inner.stdout.clear()
        self.group_reports[nid] = {"outputs": inner.outputs, "status": dict(inner.status),
                                   "errors": inner.errors, "groups": inner.group_reports}
        if inner.errors:
            k, e = next(iter(inner.errors.items()))
            line = f" (line {e['line']})" if e.get("line") else ""
            raise RuntimeError(f"inside group, node '{inner.graph.nodes[k].name}'{line}: {e['error']}")
        return self.normalize(grp.spec, dict(inner.external_out))

    @staticmethod
    def normalize(spec, result):
        """Turn whatever a node returned into ``{port: value}`` with every declared output present.

        dict → copied; tuple matching the output count → zipped; anything else → first output.
        """
        if result is None:
            result = {}
        elif type(result) is dict:
            result = result.copy()
        elif isinstance(result, dict):
            result = dict(result)
        elif isinstance(result, tuple) and len(spec.outputs) > 1 and len(result) == len(spec.outputs):
            result = dict(zip(spec.outputs, result))
        else:
            result = {(spec.outputs[0] if spec.outputs else "result"): result}
        for o in spec.outputs:
            if o not in result:
                result[o] = None
        return result

    def fail(self, nid, exc):
        """Record an exception raised by a node, keeping only frames from node code (with line numbers)."""
        tb = exc.__traceback__
        frames = [f for f in traceback.extract_tb(tb) if f.filename.startswith("<knode:")]
        line = frames[-1].lineno if frames else None
        tb_text = "".join(traceback.format_list(frames)) + f"{type(exc).__name__}: {exc}"
        self.status[nid] = "error"
        self.errors[nid] = {"error": f"{type(exc).__name__}: {exc}", "line": line, "traceback": tb_text,
                            "phase": "run", "step": self.step, "t": self.t}

    def check_time(self):
        """Raise TimeoutError once the run's wall-clock budget is spent."""
        if time.monotonic() > self.deadline:
            raise TimeoutError("time limit exceeded")

    # ---------------------------------------------------------------- one pass
    def execute_pass(self, blocks, back, *, simulate, tol=1e-9, max_iter=100):
        """Evaluate every block once, in schedule order. Returns info about algebraic loops.

        ``blocks`` come from ``schedule()``: single nodes, or strongly connected components
        (loops). In a simulation loops are evaluated once per step with their back edges
        delayed; in a single run they are iterated until their outputs stop changing.
        """
        if self._cyclic_for is not blocks:                    # compute loop flags once per schedule
            self._cyclic_for = blocks
            self._cyclic = [len(b) > 1 or any(id(e) in back for n in b for e in self.in_edges[n]) for b in blocks]
        exec_one = self._exec_one
        loop_info = []
        for block, cyclic in zip(blocks, self._cyclic):
            if not cyclic or simulate:
                for nid in block:
                    exec_one(nid, back, simulate)
                continue
            # algebraic loop: fixed-point (Gauss–Seidel) iteration from the same starting state
            snapshot = {n: copy.deepcopy(self.state[n]) for n in block}
            last, converged, it = None, False, 0
            for it in range(1, max_iter + 1):
                for n in block:
                    self.state[n] = copy.deepcopy(snapshot[n])
                    exec_one(n, back, False)
                cur = {n: self.outputs.get(n) for n in block}
                if last is not None and _close(cur, last, tol):
                    converged = True
                    break
                last = copy.deepcopy(cur)
                for n in block:
                    self.prev_outputs[n] = cur[n]
            loop_info.append({"nodes": block, "converged": converged, "iterations": it})
            if not converged:
                self.warnings.append(f"loop {[self.graph.nodes[n].name for n in block]} did not converge in {max_iter} iterations")
        return loop_info

    def _exec_one(self, nid, back, use_prev):
        """Run one node inside a pass: skip it if an upstream node failed, catch its errors, check breakpoints."""
        if nid not in self.compiled:
            if nid not in self.status:
                self.status[nid] = "error"
            return
        if self.errors:                                       # only look for failed parents when something failed
            status = self.status
            for e in self.in_edges[nid]:
                if status.get(e.src) in ("error", "blocked") and id(e) not in back:
                    status[nid] = "blocked"
                    self.outputs.pop(nid, None)
                    return
        if time.monotonic() > self.deadline:
            raise TimeoutError("time limit exceeded")
        try:
            out = self.outputs[nid] = self.call(nid, self.gather(nid, back, use_prev))
            self.status[nid] = "ok"
            cond = self._breaks.get(nid)
            if cond is not None and self.breakpoint is None:  # Blueprint-style conditional breakpoint
                env = dict(out)
                env["t"], env["step"] = self.t, self.step
                try:
                    hit = bool(ks.eval_expr(cond, env))
                except Exception as e:
                    raise RuntimeError(f"break_if {cond!r}: {e}")
                if hit:
                    self.breakpoint = {"node": nid, "name": self.graph.nodes[nid].name, "condition": cond,
                                       "t": self.t, "step": self.step, "outputs": to_jsonable(out)}
                    self.stop_requested = True
        except Exception as exc:
            self.fail(nid, exc)
            self.outputs.pop(nid, None)

    # ---------------------------------------------------------------- report
    def report(self, **extra):
        """Assemble the JSON-safe result dict returned by every public entry point."""
        prof = {n: {"calls": c, "total_ms": round(sec * 1000, 4), "mean_ms": round(sec * 1000 / c, 5) if c else 0}
                for n, (c, sec) in self.profile.items()}
        rep = {
            "success": not self.errors,
            "outputs": to_jsonable(self.outputs),
            "status": self.status,
            "errors": self.errors,
            "stdout": dict(self.stdout),
            "node_logs": {k: v for k, v in self.node_logs.items()},
            "logs": self.logs,
            "warnings": self.warnings,
            "profile": prof,
            "groups": to_jsonable(self.group_reports),
            "cached": self.cached,
            "breakpoint": self.breakpoint,
        }
        rep.update(extra)
        return rep


def _close(a, b, tol):
    """Recursive approximate equality used to detect convergence of algebraic loops (relative tolerance)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    if _is_number(a) and _is_number(b):
        return abs(a - b) <= tol * (1 + abs(a))
    try:
        return a == b
    except Exception:
        return False


# ============================================================================
# public API
# ============================================================================

def run(payload_or_graph, target=None, time_limit=60.0, overrides=None, dt=0.01, cache=False):
    """Single pass. ``target`` restricts execution to that node and its ancestors."""
    g = payload_or_graph if isinstance(payload_or_graph, Graph) else parse_graph(payload_or_graph)
    _apply_overrides(g, overrides)
    subset = ancestors(g, str(target)) if target is not None and str(target) in g.nodes else None
    blocks, back, cycles = schedule(g, subset)
    with _capture():
        r = Run(g, time_limit)
        r.dt = float(dt)
        r.use_cache = bool(cache)
        order = [n for b in blocks for n in b]
        r.compile_all(order)
        r.logs.append(f"order: {[g.nodes[n].name for n in order]}")
        try:
            loops = r.execute_pass(blocks, back, simulate=False)
        except TimeoutError as e:
            r.warnings.append(str(e))
            loops = []
        return r.report(order=order, cycles=cycles, loops=loops, mode="run")


def simulate(payload_or_graph, steps=1000, dt=0.01, t0=0.0, record=None, record_every=None,
             time_limit=120.0, overrides=None, max_points=5000):
    """Fixed-step simulation. Returns traces of every numeric output."""
    g = payload_or_graph if isinstance(payload_or_graph, Graph) else parse_graph(payload_or_graph)
    _apply_overrides(g, overrides)
    steps = int(steps)
    if record_every is None:
        record_every = max(1, math.ceil((steps + 1) / max_points))
    blocks, back, cycles = schedule(g)
    with _capture():
        r = Run(g, time_limit)
        r.dt = float(dt)
        r.simulating = True
        order = [n for b in blocks for n in b]
        r.compile_all(order)
        want = set(record) if record else None
        traces: Dict[str, List] = defaultdict(list)
        tvec: List[float] = []
        keycache: Dict[tuple, Any] = {}
        stopped, completed = None, 0
        wall0 = time.perf_counter()
        for k in range(steps + 1):
            r.step, r.t = k, t0 + k * r.dt
            r.prev_outputs = r.outputs
            r.outputs = {}
            try:
                r.execute_pass(blocks, back, simulate=True)
            except TimeoutError as e:
                stopped = str(e)
                break
            if k % record_every == 0 or k == steps:
                tvec.append(r.t)
                n_t = len(tvec)
                for nid, outs in r.outputs.items():
                    for port, v in outs.items():
                        tv = type(v)
                        # fast type test (0.5): plain floats/ints first, bools as 0/1, numpy scalars last
                        if tv is float or tv is int:
                            pass
                        elif tv is bool:
                            v = int(v)
                        elif not _is_number(v):
                            continue
                        ck = (nid, port)
                        key = keycache.get(ck)
                        if key is None:                        # build "node.port" once, not every step
                            key = keycache[ck] = f"{nid}.{port}"
                            if want is not None and key not in want and nid not in want:
                                keycache[ck] = key = False
                        if key is False:
                            continue
                        series = traces[key]
                        if len(series) < n_t - 1:              # output appeared late → pad with gaps
                            series.extend([None] * (n_t - 1 - len(series)))
                        series.append(float(v))
            completed = k
            if r.errors:
                stopped = f"error in {g.nodes[next(iter(r.errors))].name} at step {k} (t={r.t:g})"
                break
            if r.stop_requested:
                stopped = (f"breakpoint: {r.breakpoint['name']} — {r.breakpoint['condition']} at t={r.t:g}"
                           if r.breakpoint else f"ctx.stop() at step {k}")
                break
        for s in traces.values():
            if len(s) < len(tvec):
                s.extend([None] * (len(tvec) - len(s)))
        rep = r.report(order=order, cycles=cycles, mode="simulate", steps_completed=completed,
                       stopped=stopped, record_every=record_every,
                       wall_ms=round((time.perf_counter() - wall0) * 1000, 2))
        rep["traces"] = _clean_traces({"t": tvec, **traces})   # 0.7: single fast pass, no recursion
        rep["feedback_edges"] = [{"from": e.src, "fromPort": e.sport, "to": e.dst, "toPort": e.dport}
                                 for e in g.data_edges if id(e) in back]
        return rep


def _apply_overrides(g: Graph, overrides):
    """overrides: {node_id: {param: value}}"""
    for nid, kv in (overrides or {}).items():
        if str(nid) in g.nodes:
            g.nodes[str(nid)].raw_params.update(kv)
            g.nodes[str(nid)].params.update(kv)


def _extract(rep, target, reduce="last"):
    """Reduce a run/simulation report to one value of ``target=(node, port)``.

    reduce (simulation only): last | mean | max | min | integral (trapezoid over t) | argmax_t
    """
    nid, port = str(target[0]), target[1]
    if rep.get("mode") == "simulate":
        ts = rep["traces"].get("t", [])
        pairs = [(t, v) for t, v in zip(ts, rep["traces"].get(f"{nid}.{port}", [])) if v is not None]
        if pairs:
            vals = [v for _, v in pairs]
            if reduce == "mean":
                return ks.mean(vals)
            if reduce == "max":
                return max(vals)
            if reduce == "min":
                return min(vals)
            if reduce == "integral":
                return sum((t1 - t0) * (a + b) / 2 for (t0, a), (t1, b) in zip(pairs, pairs[1:]))
            if reduce == "argmax_t":
                return max(pairs, key=lambda p: p[1])[0]
            return vals[-1]
    out = (rep.get("outputs") or {}).get(nid) or {}
    return out.get(port)


# ============================================================================
# parallel evaluation — multi-core parameter studies (0.7)
# ============================================================================
# Sweeps, Monte-Carlo samples, scenarios and optimiser candidates are independent model runs, so
# they are farmed out to a persistent pool of worker *processes* (threads would not help: node code
# is Python and holds the GIL). Design decisions:
#
# * start method "forkserver" (Linux/macOS) or "spawn" (Windows): never plain "fork", because the
#   Flask server is multi-threaded and a forked child could inherit a held _EXEC_LOCK and deadlock.
# * the pool is created lazily on first use and reused (worker start-up costs ~0.2–0.5 s once).
# * one core is left for the server/UI; KNODE_WORKERS (or the Backend Manager) overrides the count.
# * on a single-core machine the pool is not used at all — serial execution is faster there.
# * results are identical to serial execution: every task is a pure function of its arguments
#   (random draws happen in the parent before tasks are dispatched), and map() preserves order.
# * any pool failure (e.g. a node that cannot be pickled, a killed worker) falls back to serial.

import atexit
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

WORKERS = int(os.environ.get("KNODE_WORKERS", "0") or 0)    # 0 = automatic, <0 = serial, >0 = fixed count
_POOL = None
_POOL_SIZE = 0
_POOL_LOCK = threading.Lock()


def worker_count():
    """Number of worker processes to use for studies (0 = run serially in this process).

    WORKERS > 0 forces that many workers, WORKERS < 0 forces serial execution, 0 means automatic.
    """
    if WORKERS < 0:
        return 0
    if WORKERS > 0:
        return WORKERS
    n = os.cpu_count() or 1
    return 0 if n <= 1 else min(n - 1, 32)


def _get_pool(n):
    """The shared process pool, (re)created when the requested size changes."""
    global _POOL, _POOL_SIZE
    with _POOL_LOCK:
        if _POOL is None or _POOL_SIZE != n:
            if _POOL is not None:
                _POOL.shutdown(wait=False, cancel_futures=True)
            methods = multiprocessing.get_all_start_methods()
            ctx = multiprocessing.get_context("forkserver" if "forkserver" in methods else "spawn")
            _POOL, _POOL_SIZE = ProcessPoolExecutor(max_workers=n, mp_context=ctx), n
        return _POOL


def shutdown_pool():
    """Stop the worker processes (at exit, or when the worker count changes)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.shutdown(wait=False, cancel_futures=True)
            _POOL = None


atexit.register(shutdown_pool)


def pmap(fn, items):
    """Order-preserving map over worker processes, or serially when that is not worthwhile.

    ``fn`` must be a module-level function and ``items`` picklable. The parent process does not
    hold the execution lock while waiting, so the server keeps answering other requests.
    """
    items = list(items)
    n = worker_count()
    if n >= 1 and len(items) >= 2:
        try:
            chunk = max(1, len(items) // (4 * n))            # a few chunks per worker balances load
            return list(_get_pool(n).map(fn, items, chunksize=chunk))
        except Exception as e:                               # broken pool / unpicklable data → serial
            print(f"[knode] parallel evaluation failed ({type(e).__name__}: {e}); running serially", file=sys.stderr)
            shutdown_pool()
    return [fn(it) for it in items]


def _first_error(rep):
    """Message of the first error in a report, or None when the run succeeded."""
    return next(iter(rep["errors"].values()))["error"] if rep.get("errors") else None


def _eval_task(args):
    """Worker task: run the model once with parameter overrides; return the reduced target value.

    args = (payload, overrides, mode, sim_options, target (node, port) | None, reduce, keep_traces)
    """
    payload, overrides, mode, sim, target, reduce, keep = args
    rep = run(payload, overrides=overrides, cache=True) if mode == "run" else simulate(payload, overrides=overrides, **(sim or {}))
    out = {"value": to_jsonable(_extract(rep, target, reduce)) if target else None, "error": _first_error(rep),
           "pid": os.getpid()}                                # which process ran it (diagnostics / tests)
    if keep:                                                 # scenarios need the whole result
        out["traces"], out["outputs"] = rep.get("traces"), rep.get("outputs")
    return out


def sweep(payload, node_id, param, values, target, mode="run", reduce="last", sim=None):
    """Evaluate ``target=(node, port)`` for each value of ``node.param`` (points run in parallel)."""
    parse_graph(payload)                                     # validate once, early, in this process
    values = list(values)
    tasks = [(payload, {str(node_id): {param: v}}, mode, sim, target, reduce, False) for v in values]
    res = pmap(_eval_task, tasks)
    return {"values": to_jsonable(values), "results": [r["value"] for r in res], "errors": [r["error"] for r in res],
            "param": f"{node_id}.{param}", "target": f"{target[0]}.{target[1]}", "reduce": reduce}


def _inv_cdf(dist, u, a, b):
    """Map a uniform sample u∈(0,1) to a distribution by inverse CDF (Latin-hypercube sampling).

    uniform(a=low, b=high) · normal(a=μ, b=σ) · lognormal(a=μ, b=σ of log x) · triangular(a=low, b=high, mode at the midpoint).
    """
    if dist == "uniform":
        return a + (b - a) * u
    if dist == "normal":
        return statistics.NormalDist(a, b).inv_cdf(min(max(u, 1e-12), 1 - 1e-12))
    if dist == "lognormal":           # a, b = mean and sigma of log(x)
        return math.exp(statistics.NormalDist(a, b).inv_cdf(min(max(u, 1e-12), 1 - 1e-12)))
    if dist == "triangular":          # a = low, b = high, mode at midpoint
        c = 0.5
        return a + (b - a) * (math.sqrt(u * c) if u < c else 1 - math.sqrt((1 - u) * (1 - c)))
    raise ValueError(f"unknown distribution {dist}")


def latin_hypercube(n, k, rng):
    """n samples in [0,1)^k with one sample per stratum per dimension."""
    cols = []
    for _ in range(k):
        perm = list(range(n))
        rng.shuffle(perm)
        cols.append([(perm[i] + rng.random()) / n for i in range(n)])
    return [[cols[j][i] for j in range(k)] for i in range(n)]


def montecarlo(payload, factors, target, n=100, mode="run", reduce="last", seed=0, sim=None):
    """Uncertainty propagation with LHS; sensitivity = Spearman rank correlation.

    factors: [{"node": id, "param": name, "dist": "uniform|normal|lognormal|triangular", "a": .., "b": ..}]
    """
    parse_graph(payload)
    rng = random.Random(seed)
    U = latin_hypercube(int(n), len(factors), rng)           # all random draws happen here, in order
    samples, tasks = [], []
    for row in U:
        xs = [_inv_cdf(f.get("dist", "uniform"), u, float(f["a"]), float(f["b"])) for f, u in zip(factors, row)]
        ov = {}
        for f, x in zip(factors, xs):
            ov.setdefault(str(f["node"]), {})[f["param"]] = x
        samples.append(xs)
        tasks.append((payload, ov, mode, sim, target, reduce, False))
    X, Y, errs = [], [], 0
    for xs, r in zip(samples, pmap(_eval_task, tasks)):     # model runs in parallel, results in order
        y = r["value"]
        if _is_number(y) and not (isinstance(y, float) and math.isnan(y)):
            X.append(xs)
            Y.append(float(y))
        else:
            errs += 1
    if not Y:
        return {"success": False, "error": "no numeric results — check the target port", "failed": errs}
    sens = []
    for j, f in enumerate(factors):
        col = [x[j] for x in X]
        sens.append({"factor": f"{f['node']}.{f['param']}", "spearman": ks.spearman(col, Y), "pearson": ks.pearson(col, Y)})
    stats_ = {"mean": ks.mean(Y), "std": ks.std(Y) if len(Y) > 1 else 0.0, "min": min(Y), "max": max(Y),
              "p05": ks.percentile(Y, 5), "p50": ks.percentile(Y, 50), "p95": ks.percentile(Y, 95),
              "n": len(Y), "failed": errs}
    return to_jsonable({"success": True, "samples": X, "y": Y, "stats": stats_, "sensitivity": sens,
                        "target": f"{target[0]}.{target[1]}", "method": "Latin hypercube + Spearman rank correlation"})


# ============================================================================
# graph analysis
# ============================================================================

def brandes_betweenness(ids, adj, normalized=True):
    """Betweenness centrality by Brandes' algorithm (O(V·E), unweighted, directed), normalised to [0, 1].

    High values mark bottleneck nodes that many dependency paths pass through.
    """
    cb = dict.fromkeys(ids, 0.0)
    for s in ids:
        stack, pred = [], {w: [] for w in ids}
        sigma = dict.fromkeys(ids, 0)
        dist = dict.fromkeys(ids, -1)
        sigma[s], dist[s] = 1, 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj.get(v, []):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = dict.fromkeys(ids, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    n = len(ids)
    if normalized and n > 2:
        for v in cb:
            cb[v] /= (n - 1) * (n - 2)
    return cb


def pagerank(ids, adj, d=0.85, tol=1e-10, max_iter=500):
    """PageRank by power iteration with damping ``d`` and uniform redistribution of dangling mass.

    On a model graph it ranks how much of the system's 'influence' flows through each node.
    """
    n = len(ids)
    if not n:
        return {}
    pr = dict.fromkeys(ids, 1.0 / n)
    for _ in range(max_iter):
        dangling = sum(pr[v] for v in ids if not adj.get(v))
        new = dict.fromkeys(ids, (1 - d) / n + d * dangling / n)
        for v in ids:
            out = adj.get(v, [])
            for w in out:
                new[w] += d * pr[v] / len(out)
        err = sum(abs(new[v] - pr[v]) for v in ids)
        pr = new
        if err < tol:
            break
    return pr


def lint(graph: Graph):
    """Static checks without running anything: syntax errors, wires to unknown ports, required inputs
    left unconnected, arguments with no matching port, and ports the function never reads.
    """
    issues = []
    connected_inputs = defaultdict(set)
    for e in graph.data_edges:
        connected_inputs[e.dst].add(e.dport)
        if e.dport not in graph.nodes[e.dst].inputs:
            issues.append({"node": e.dst, "level": "error", "msg": f"wire into unknown/disabled input '{e.dport}'"})
        if e.sport not in graph.nodes[e.src].outputs:
            issues.append({"node": e.src, "level": "error", "msg": f"wire from unknown/disabled output '{e.sport}'"})
    for nid, spec in graph.nodes.items():
        if spec.subgraph is not None:
            try:
                sub = lint(parse_graph(spec.subgraph))
                issues += [dict(i, node=nid, msg=f"inside group: {i['msg']}") for i in sub if i["level"] == "error"]
            except Exception as e:
                issues.append({"node": nid, "level": "error", "msg": f"invalid group: {e}"})
            continue
        try:
            cn = compile_node(spec)
        except CompileError as e:
            issues.append({"node": nid, "level": "error", "msg": str(e), "line": e.line})
            continue
        sig = cn.signature.parameters
        for pname, p in sig.items():
            if p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL) or pname in RESERVED or pname in spec.params:
                continue
            if pname in spec.inputs and pname not in connected_inputs[nid] and p.default is p.empty:
                issues.append({"node": nid, "level": "warning", "msg": f"required input '{pname}' is unconnected (will be None)"})
            if pname not in spec.inputs and p.default is p.empty:
                issues.append({"node": nid, "level": "warning", "msg": f"argument '{pname}' has no matching port"})
        if not cn.var_kw:
            for p in spec.inputs:
                if p not in sig:
                    issues.append({"node": nid, "level": "warning", "msg": f"input port '{p}' not used by {cn.func.__name__}()"})
    return issues


def analyze(payload, weights=None):
    """Structural analysis. ``weights`` (node → ms) enables a time-weighted critical path."""
    g = parse_graph(payload)
    ids = sorted(g.nodes, key=_idkey)
    adj = defaultdict(list)
    all_adj = defaultdict(set)
    for e in g.data_edges:
        if e.dst not in adj[e.src]:
            adj[e.src].append(e.dst)
    for e in g.edges:
        all_adj[e.src].add(e.dst)
        all_adj[e.dst].add(e.src)
    indeg = {v: 0 for v in ids}
    outdeg = {v: len(adj[v]) for v in ids}
    for u in ids:
        for v in adj[u]:
            indeg[v] += 1
    blocks, back, cycles = schedule(g)
    # DAG depth over the condensation (block index order is topological)
    comp_of = {v: i for i, b in enumerate(blocks) for v in b}
    w = {v: float((weights or {}).get(v, 1.0)) for v in ids}
    cw = [sum(w[v] for v in b) for b in blocks]
    level = [0] * len(blocks)
    best = list(cw)
    prev = [None] * len(blocks)
    for i, b in enumerate(blocks):
        for u in b:
            for v in adj[u]:
                j = comp_of[v]
                if j == i:
                    continue
                if level[i] + 1 > level[j]:
                    level[j] = level[i] + 1
                if best[i] + cw[j] > best[j]:
                    best[j] = best[i] + cw[j]
                    prev[j] = i
    path = []
    if blocks:
        j = max(range(len(blocks)), key=lambda k: best[k])
        crit_len = best[j]
        while j is not None:
            path.append(blocks[j])
            j = prev[j]
        path.reverse()
    else:
        crit_len = 0
    # weak components
    seen, n_wcc = set(), 0
    for v in ids:
        if v in seen:
            continue
        n_wcc += 1
        stack = [v]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(all_adj[x] - seen)
    bc = brandes_betweenness(ids, adj)
    pr = pagerank(ids, adj)
    n, m = len(ids), sum(len(v) for v in adj.values())
    per_node = {v: {"name": g.nodes[v].name, "in": indeg[v], "out": outdeg[v], "level": level[comp_of[v]],
                    "betweenness": bc[v], "pagerank": pr[v], "in_cycle": any(v in c for c in cycles)} for v in ids}
    return to_jsonable({
        "n_nodes": n, "n_edges": m, "n_relations": len(g.edges) - len(g.data_edges),
        "density": m / (n * (n - 1)) if n > 1 else 0.0,
        "sources": [v for v in ids if indeg[v] == 0], "sinks": [v for v in ids if outdeg[v] == 0],
        "isolated": [v for v in ids if indeg[v] == 0 and outdeg[v] == 0 and not all_adj[v]],
        "weak_components": n_wcc, "is_dag": not cycles, "cycles": cycles,
        "feedback_edges": [{"from": e.src, "fromPort": e.sport, "to": e.dst, "toPort": e.dport}
                           for e in g.data_edges if id(e) in back],
        "depth": (max(level) + 1) if level else 0,
        "critical_path": [v for b in path for v in b], "critical_path_cost": crit_len,
        "execution_order": [v for b in blocks for v in b],
        "nodes": per_node, "lint": lint(g),
    })


# ============================================================================
# live sessions (TouchDesigner / Max-MSP style): step a model incrementally,
# changing parameters while it runs
# ============================================================================

class Session:
    """A simulation that advances in chunks and accepts parameter changes between chunks."""

    def __init__(self, payload, dt=0.01, t0=0.0, time_limit=24 * 3600):
        self.graph = parse_graph(payload)
        self.blocks, self.back, self.cycles = schedule(self.graph)
        self.run = Run(self.graph, time_limit)
        self.run.dt, self.run.simulating = float(dt), True
        self.t0, self.k = float(t0), 0
        self.order = [n for b in self.blocks for n in b]
        self.run.compile_all(self.order)
        self.lock = threading.Lock()
        self.last_used = time.monotonic()
        self.stopped = None

    def set_params(self, params):
        """params: {node_id: {param: value}} — raw values, '=expressions' allowed."""
        changed = False
        for nid, kv in (params or {}).items():
            sp = self.graph.nodes.get(str(nid))
            if sp is not None and sp.subgraph is None:
                for k, v in kv.items():
                    if sp.raw_params.get(k) != v:
                        sp.raw_params[k] = v
                        changed = True
        if changed:
            errs = resolve_params(self.graph)
            for nid, msg in errs.items():
                self.run.status[nid] = "error"
                self.run.errors[nid] = {"error": msg, "line": None, "traceback": "", "phase": "parameters"}
        return changed

    def step(self, n=10, params=None, max_points=200):
        """Advance the live model by ``n`` steps, applying changed parameters first.

        Returns a normal report plus ``chunk`` — the new trace samples (≤ max_points) for the client
        to append. Stops early on an error, a breakpoint or ctx.stop().
        """
        self.last_used = time.monotonic()
        with self.lock, _capture():
            self.set_params(params)
            r = self.run
            r.stop_requested, r.breakpoint = False, None
            every = max(1, math.ceil(n / max_points))
            tvec, traces = [], defaultdict(list)
            done = 0
            for i in range(int(n)):
                if r.errors:
                    self.stopped = "error"
                    break
                r.step, r.t = self.k, self.t0 + self.k * r.dt
                r.prev_outputs, r.outputs = r.outputs, {}
                try:
                    r.execute_pass(self.blocks, self.back, simulate=True)
                except TimeoutError as e:
                    self.stopped = str(e)
                    break
                if i % every == 0 or i == n - 1 or r.errors or r.stop_requested:
                    tvec.append(r.t)
                    for nid, outs in r.outputs.items():
                        for port, v in outs.items():
                            if isinstance(v, bool):
                                v = int(v)
                            if _is_number(v):
                                s = traces[f"{nid}.{port}"]
                                s.extend([None] * (len(tvec) - 1 - len(s)))
                                s.append(float(v))
                self.k += 1
                done += 1
                if r.stop_requested:
                    self.stopped = (f"breakpoint: {r.breakpoint['name']} — {r.breakpoint['condition']}"
                                    if r.breakpoint else "ctx.stop()")
                    break
            for s in traces.values():
                s.extend([None] * (len(tvec) - len(s)))
            rep = r.report(mode="simulate", cycles=self.cycles, steps_done=done, step=self.k, t=r.t, stopped=self.stopped)
            rep["chunk"] = _clean_traces({"t": tvec, **traces})
            r.warnings = []
            return rep


_SESSIONS: Dict[str, Session] = {}
SESSION_IDLE_S = 1800            # live sessions idle longer than this are discarded (Backend Manager setting)


def session_start(payload, dt=0.01, t0=0.0):
    """Create a live Session (expired sessions idle > 30 min are dropped first). Returns (id, session)."""
    import uuid
    for sid in [k for k, s in _SESSIONS.items() if time.monotonic() - s.last_used > SESSION_IDLE_S]:
        _SESSIONS.pop(sid, None)                       # idle > 30 min
    s = Session(payload, dt, t0)
    sid = uuid.uuid4().hex[:12]
    _SESSIONS[sid] = s
    return sid, s


def session_get(sid):
    """Look up a live session by id; raises KeyError when it is unknown or expired."""
    s = _SESSIONS.get(sid)
    if s is None:
        raise KeyError("unknown or expired session")
    return s


def session_stop(sid):
    """Discard a live session and its state."""
    _SESSIONS.pop(sid, None)


# ============================================================================
# scenarios (Houdini takes): named parameter variants run side by side
# ============================================================================

def scenarios(payload, items, mode="simulate", steps=1000, dt=0.01, max_points=2000):
    """Run the model once per scenario (a named set of parameter overrides) and collect the results.

    Used for side-by-side comparison of variants (Houdini-style takes) in the plot; scenarios run in parallel.
    """
    sim = {"steps": steps, "dt": dt, "max_points": max_points}
    tasks = [(payload, sc.get("overrides") or {}, mode, sim, None, "last", True) for sc in items]
    out = [{"name": sc.get("name", "scenario"), "traces": r["traces"], "outputs": r["outputs"], "error": r["error"]}
           for sc, r in zip(items, pmap(_eval_task, tasks))]
    return {"success": all(o["error"] is None for o in out), "scenarios": out}


# ============================================================================
# calibration / optimisation (Grasshopper Galapagos, Simulink Design Optimization, COPASI)
# ============================================================================

def _series(rep, target):
    """(times, values) of one output from a simulation report, skipping gaps."""
    nid, port = str(target[0]), target[1]
    tr = rep.get("traces") or {}
    ts, ys = tr.get("t", []), tr.get(f"{nid}.{port}", [])
    pairs = [(t, y) for t, y in zip(ts, ys) if y is not None]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _objective_value(rep, spec):
    """Objective of one model report (lower is better); +inf when the model failed or gave no number.

    fit      : sum of squared errors between the data points and the model (trace interpolated at the
               data times in simulations; array element at index t in single runs)
    minimize : the reduced output;  maximize: its negation
    """
    if rep["errors"]:
        return float("inf")
    target, data = spec["target"], spec["data"]
    if spec["kind"] == "fit":
        dt_, dy = [float(v) for v in data.get("t", [])], [float(v) for v in data.get("y", [])]
        if spec["mode"] == "simulate":
            mt, my = _series(rep, target)
            if len(mt) < 2:
                return float("inf")
            pred = [ks.interp(mt, my, t) for t in dt_]
        else:
            arr = ks.as_list(((rep.get("outputs") or {}).get(target[0]) or {}).get(target[1]))
            pred = [arr[int(t)] if 0 <= int(t) < len(arr) else float("nan") for t in dt_]
        val = sum((p - y) ** 2 for p, y in zip(pred, dy))
    else:
        v = _extract(rep, target, spec["reduce"])
        if not _is_number(v):
            return float("inf")
        val = float(v) if spec["kind"] == "minimize" else -float(v)
    return float("inf") if math.isnan(val) else val


def _candidate_report(spec, x):
    """Run the model for one candidate parameter vector."""
    ov = {}
    for f, v in zip(spec["factors"], x):
        ov.setdefault(str(f["node"]), {})[f["param"]] = v
    if spec["mode"] == "simulate":
        return simulate(spec["payload"], steps=spec["steps"], dt=spec["dt"], overrides=ov, max_points=max(2000, spec["steps"] + 1))
    return run(spec["payload"], overrides=ov, cache=True)


def _objective_task(args):
    """Worker task: objective value of one candidate (only the number travels back, not the traces)."""
    spec, x = args
    return _objective_value(_candidate_report(spec, x), spec)


def optimize(payload, factors, objective, mode="simulate", steps=500, dt=0.01, method="de", budget=300, seed=0,
             time_limit=180.0):
    """Minimise an objective over node parameters within bounds.

    factors  : [{"node", "param", "lo", "hi"}]
    objective: {"type": "minimize"|"maximize", "node", "port", "reduce"}  or
               {"type": "fit", "node", "port", "data": {"t": [...], "y": [...]}}  (least squares on the trajectory,
                                                                                    or on array outputs vs index in run mode)
    method   : "de" — differential evolution (global); every generation's candidates are evaluated
                      in parallel. Generation-synchronous rand/1/bin (Storn & Price 1997): all trial
                      vectors are drawn before any is evaluated, so the result depends only on the seed.
               "nm" — Nelder–Mead (local, from the current parameter values); sequential by nature,
                      only its initial simplex is evaluated in parallel.
    """
    parse_graph(payload)
    lo = [float(f["lo"]) for f in factors]
    hi = [float(f["hi"]) for f in factors]
    d = len(factors)
    if d == 0:
        raise ValueError("add at least one parameter to vary")
    base = parse_graph(payload)
    deadline = time.monotonic() + time_limit
    target = (str(objective["node"]), objective["port"])
    kind = objective.get("type", "minimize")
    spec = {"payload": payload, "factors": factors, "mode": mode, "steps": int(steps), "dt": float(dt), "kind": kind,
            "target": target, "reduce": objective.get("reduce", "last"), "data": objective.get("data") or {}}
    evals, history = [0], []
    best = {"f": float("inf"), "x": None}

    def clip(x):
        """Clamp a candidate parameter vector into the search box [lo, hi]."""
        return [min(h, max(l, v)) for v, l, h in zip(x, lo, hi)]

    def evaluate(xs):
        """Objective values for a batch of candidates (parallel), within budget and time limit."""
        if time.monotonic() > deadline or evals[0] >= budget:
            raise StopIteration
        xs = [clip(x) for x in xs][: budget - evals[0]]
        vals = pmap(_objective_task, [(spec, x) for x in xs])
        evals[0] += len(xs)
        for x, v in zip(xs, vals):
            if v < best["f"]:
                best.update(f=v, x=list(x))
        if len(vals) < len(xs):
            raise StopIteration
        return vals

    rng = random.Random(seed)
    try:
        if method == "nm":
            x0 = clip([float(base.nodes[str(f["node"])].raw_params.get(f["param"], (l + h) / 2)) for f, l, h in zip(factors, lo, hi)])
            step = [0.2 * (h - l) for l, h in zip(lo, hi)]
            xtol = 1e-9 * max(h - l for l, h in zip(lo, hi))
            n = d
            pts = [x0] + [[x0[j] + (step[j] if j == i else 0) for j in range(n)] for i in range(n)]
            vals = evaluate(pts)                                 # initial simplex in parallel
            one = lambda x: evaluate([x])[0]                     # the rest of Nelder–Mead is sequential
            while True:
                order = sorted(range(n + 1), key=lambda i: vals[i])
                pts, vals = [pts[i] for i in order], [vals[i] for i in order]
                history.append(best["f"])
                # converged only when the values AND the simplex are small: equal values alone can
                # happen on a symmetric objective with vertices on both sides of the optimum
                spread_f = abs(vals[-1] - vals[0]) <= 1e-12 * (abs(vals[0]) + 1e-12)
                spread_x = max(abs(p[j] - pts[0][j]) for p in pts[1:] for j in range(n)) <= xtol
                if spread_f and spread_x:
                    break
                c = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
                xr = [c[j] + (c[j] - pts[-1][j]) for j in range(n)]
                fr = one(xr)
                if fr < vals[0]:
                    xe = [c[j] + 2 * (c[j] - pts[-1][j]) for j in range(n)]
                    fe = one(xe)
                    pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
                elif fr < vals[-2]:
                    pts[-1], vals[-1] = xr, fr
                else:
                    xc = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(n)]
                    fc = one(xc)
                    if fc < vals[-1]:
                        pts[-1], vals[-1] = xc, fc
                    else:                                        # shrink: n new points, evaluated together
                        pts = [pts[0]] + [[pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)] for i in range(1, n + 1)]
                        vals = [vals[0]] + evaluate(pts[1:])
        else:
            NP = max(8, min(40, 8 * d))                          # population size
            pop = [[l + rng.random() * (h - l) for l, h in zip(lo, hi)] for _ in range(NP)]
            fit = evaluate(pop)
            history.append(best["f"])
            F, CR = 0.7, 0.9                                     # differential weight, crossover rate
            while True:
                trials = []
                for i in range(NP):                              # draw the whole generation first …
                    a, b, c = rng.sample([j for j in range(NP) if j != i], 3)
                    jr = rng.randrange(d)
                    trial = []
                    for j in range(d):
                        if rng.random() < CR or j == jr:
                            v = pop[a][j] + F * (pop[b][j] - pop[c][j])
                            if v < lo[j] or v > hi[j]:           # bounce back inside the box
                                v = lo[j] + rng.random() * (hi[j] - lo[j])
                        else:
                            v = pop[i][j]
                        trial.append(v)
                    trials.append(trial)
                fts = evaluate(trials)                           # … then evaluate it in parallel
                for i, ft in enumerate(fts):                     # greedy one-to-one selection
                    if ft <= fit[i]:
                        pop[i], fit[i] = trials[i], ft
                history.append(best["f"])
                if max(fit) - min(fit) <= 1e-12 * (abs(min(fit)) + 1e-12):
                    break
    except StopIteration:
        pass
    if best["x"] is None:
        return {"success": False, "error": "no successful evaluation — check the objective node/port", "evaluations": evals[0]}
    res = {"success": True, "x": {f"{f['node']}.{f['param']}": v for f, v in zip(factors, best["x"])},
           "values": best["x"], "objective": best["f"] if kind != "maximize" else -best["f"],
           "evaluations": evals[0], "history": [h if h != float("inf") else None for h in history], "method": method,
           "workers": worker_count() or 1}
    if kind == "fit":
        ys = [float(v) for v in spec["data"].get("y", [])]
        n = len(ys)
        m = ks.mean(ys) if ys else 0.0
        sst = sum((y - m) ** 2 for y in ys)
        res["rmse"] = math.sqrt(best["f"] / n) if n else None
        res["r2"] = 1 - best["f"] / sst if sst else None
    rep = _candidate_report(spec, best["x"])                     # one extra run for the best fit's traces
    if rep.get("traces"):
        res["traces"] = rep["traces"]
    return to_jsonable(res)


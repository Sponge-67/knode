"""
knode_std — numerical helpers injected into every node namespace as ``ks``.

Pure Python (numpy is used opportunistically when present). Every routine here
is small, documented, and covered by tests/test_engine.py so that node authors
can rely on it for scientific work.
"""
from __future__ import annotations

import functools
import math
import random
from typing import Callable, Iterable, List, Sequence

try:  # optional acceleration
    import numpy as _np  # noqa: F401
    HAS_NUMPY = True
except Exception:  # pragma: no cover
    _np = None
    HAS_NUMPY = False


# ----------------------------------------------------------------------------
# small utilities
# ----------------------------------------------------------------------------

def pick(value, default):
    """Return ``value`` unless it is None (an unconnected input), else ``default``."""
    return default if value is None else value


def is_seq(x) -> bool:
    """True for lists, tuples and numpy arrays — the types broadcast() treats as element-wise data."""
    return isinstance(x, (list, tuple)) or (HAS_NUMPY and isinstance(x, _np.ndarray))


def as_list(x) -> list:
    """Coerce None / scalar / tuple / numpy array to a plain list (None → [])."""
    if x is None:
        return []
    if HAS_NUMPY and isinstance(x, _np.ndarray):
        return x.tolist()
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


_SEQ_TYPES = (list, tuple)


def broadcast(fn: Callable, *args):
    """Apply ``fn`` elementwise, broadcasting scalars against equal-length lists.

    ``broadcast(f, 2, 3)`` → ``f(2, 3)``;  ``broadcast(f, [1, 2], 10)`` → ``[f(1, 10), f(2, 10)]``.
    Lists of different lengths raise ValueError.
    """
    # fast path (0.5): all-scalar calls are by far the most common in simulations
    for a in args:
        if isinstance(a, _SEQ_TYPES) or (HAS_NUMPY and isinstance(a, _np.ndarray)):
            break
    else:
        return fn(*args)
    lengths = {len(a) for a in args if is_seq(a)}
    if not lengths:
        return fn(*args)
    if len(lengths) > 1:
        raise ValueError(f"broadcast: incompatible lengths {sorted(lengths)}")
    n = lengths.pop()
    cols = [as_list(a) if is_seq(a) else [a] * n for a in args]
    return [fn(*row) for row in zip(*cols)]


def parse_floats(text, sep=",") -> List[float]:
    """Parse '1, 2; 3' (or a number, or a list) into a list of floats."""
    if isinstance(text, (int, float)):
        return [float(text)]
    if is_seq(text):
        return [float(v) for v in text]
    return [float(t) for t in str(text).replace(";", sep).split(sep) if t.strip()]


def linspace(a: float, b: float, n: int) -> List[float]:
    """n evenly spaced values from a to b inclusive (numpy.linspace without numpy)."""
    n = int(n)
    if n < 2:
        return [float(a)]
    h = (b - a) / (n - 1)
    return [a + i * h for i in range(n)]


# ----------------------------------------------------------------------------
# safe expression evaluation (for expression-driven nodes)
# ----------------------------------------------------------------------------

MATH_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
MATH_NAMES.update({"abs": abs, "min": min, "max": max, "round": round, "sum": sum,
                   "len": len, "float": float, "int": int, "pow": pow})


@functools.lru_cache(maxsize=4096)
def _compile_cached(text):
    """LRU-cached compile() of an expression string (see compile_expr)."""
    return compile(text, "<expr>", "eval")


def compile_expr(expr: str):
    """Compile an arithmetic expression to a code object (cached: each distinct text compiles once).

    0.4 recompiled Expression/If-Else/Break-if strings on every call; compiling is ~50× slower
    than evaluating, so the cache matters inside simulations.
    """
    return _compile_cached(str(expr).strip())


_EXPR_GLOBALS = dict(MATH_NAMES)
_EXPR_GLOBALS["__builtins__"] = {}
_EXPR_GLOBALS.update({"clip": lambda x, a, b: min(b, max(a, x)), "sign": lambda x: (x > 0) - (x < 0),
                      "heaviside": lambda x: 1.0 if x >= 0 else 0.0, "bool": bool, "any": any, "all": all})


def eval_expr(expr, variables: dict):
    """Evaluate a compiled/str expression. Variables shadow math names; no builtins."""
    code = expr if not isinstance(expr, str) else compile_expr(expr)
    return eval(code, _EXPR_GLOBALS, variables)


@functools.lru_cache(maxsize=1024)
def _parse_assignments_cached(text):
    """Cached parse of constant definitions without a base environment (see parse_assignments)."""
    return _parse_assignments(text, None)


def parse_assignments(text, base=None) -> dict:
    """Parse ``"a=1, b=2.5; c=pi"`` into a dict (values may be expressions of earlier names).

    Without ``base`` the result is cached per text (universal nodes call this every step with the
    same constants) and a fresh copy is returned so callers may modify it.
    """
    if base is None:
        return dict(_parse_assignments_cached(str(text or "")))
    return _parse_assignments(text, base)


def _parse_assignments(text, base) -> dict:
    """Uncached worker: evaluate 'name = expr' items left to right; later items may use earlier names."""
    out = {}
    env = dict(base or {})
    for part in str(text or "").replace(";", ",").replace("\n", ",").split(","):
        part = part.split("#", 1)[0]
        if "=" in part:
            k, v = part.split("=", 1)
            val = eval_expr(v.strip(), env)
            out[k.strip()] = env[k.strip()] = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else val
    return out


# ----------------------------------------------------------------------------
# text specs for universal nodes (cached: parsing happens once per distinct text)
# ----------------------------------------------------------------------------
import re as _re

_IDENT = _re.compile(r"^[A-Za-z_]\w*$")
RESERVED_NAMES = {"params", "state", "t", "dt", "step", "ctx", "inputs"}


@functools.lru_cache(maxsize=1024)
def parse_names(text) -> tuple:
    """Split 'a, b\nc' into validated identifiers (cached). Raises ValueError for invalid names."""
    names = [n.strip() for n in str(text or "").replace("\n", ",").split(",") if n.strip()]
    for n in names:
        if not _IDENT.match(n):
            raise ValueError(f"invalid name {n!r} (use letters, digits, _)")
    return tuple(names)


@functools.lru_cache(maxsize=1024)
def parse_equations(text) -> tuple:
    """Lines ``name = expression`` (``#`` comments, ``;`` separators) → ((name, code), ...)."""
    out = []
    for raw in str(text or "").replace(";", "\n").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _re.match(r"^([A-Za-z_]\w*)\s*=(?!=)(.+)$", line)
        if not m:
            raise ValueError(f"cannot parse equation {raw.strip()!r} — expected 'name = expression'")
        try:
            out.append((m.group(1), compile_expr(m.group(2).strip())))
        except SyntaxError as e:
            raise ValueError(f"syntax error in {raw.strip()!r}: {e.msg}") from None
    return tuple(out)


@functools.lru_cache(maxsize=256)
def ode_system(states_text, equations_text, prefix="d"):
    """Cached (names, codes) for ``dname = expr`` systems; raises if a state has no equation.

    Used by the Dynamic System and 2-D Field nodes so their text is analysed once, not per step.
    """
    names = parse_names(states_text)
    rhs = {}
    for lhs, code in parse_equations(equations_text):
        key = lhs[len(prefix):] if lhs.startswith(prefix) and lhs[len(prefix):] in names else lhs
        rhs[key] = code
    missing = [n for n in names if n not in rhs]
    if missing:
        raise ValueError(f"no equation for state(s) {missing}: write '{prefix}{missing[0]} = …'")
    return names, tuple(rhs[n] for n in names)


@functools.lru_cache(maxsize=256)
def reaction_system(text):
    """Cached (species, reactions, stoichiometry matrix, species index) for a reaction network."""
    species, rxns = parse_reactions(text)
    idx = {sp: i for i, sp in enumerate(species)}
    stoich = []
    for reac, prod, _, _ in rxns:
        v = [0] * len(species)
        for sp, c in reac:
            v[idx[sp]] -= c
        for sp, c in prod:
            v[idx[sp]] += c
        stoich.append(tuple(v))
    return species, rxns, tuple(stoich), idx


def _species_terms(side):
    """Parse one side of a reaction ('2 A + B') into ((species, coefficient), …)."""
    terms = []
    for tok in [x.strip() for x in side.split("+") if x.strip()]:
        m = _re.match(r"^(\d*)\s*([A-Za-z_]\w*)$", tok)
        if not m:
            raise ValueError(f"bad species term {tok!r}")
        terms.append((m.group(2), int(m.group(1) or 1)))
    return terms


@functools.lru_cache(maxsize=256)
def parse_reactions(text) -> tuple:
    """``A + 2 B -> C, k`` (mass action) or ``S -> P, = Vmax*S/(Km+S)`` (custom rate law).

    Returns (species tuple, reactions tuple of (reactants, products, rate_code, mass_action)).
    """
    species, rxns = [], []
    for raw in str(text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "->" not in line or "," not in line:
            raise ValueError(f"cannot parse reaction {raw.strip()!r} — expected 'A + B -> C, rate'")
        eq, rate = line.split(",", 1)   # species terms never contain commas; rate laws may
        lhs, rhs = eq.split("->", 1)
        reac, prod = _species_terms(lhs), _species_terms(rhs)
        rate = rate.strip()
        mass_action = not rate.startswith("=")
        code = compile_expr(rate.lstrip("=").strip())
        for sp, _ in reac + prod:
            if sp not in species:
                species.append(sp)
        rxns.append((tuple(reac), tuple(prod), code, mass_action))
    return tuple(species), tuple(rxns)


@functools.lru_cache(maxsize=256)
def parse_state_machine(states_text, transitions_text, outputs_text):
    """States ``a, b``; transitions ``a -> b : condition``; outputs ``state: name = expr`` (``*`` = default)."""
    states = parse_names(states_text)
    trans = []
    for raw in str(transitions_text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _re.match(r"^(\*|[A-Za-z_]\w*)\s*->\s*([A-Za-z_]\w*)\s*:\s*(.+)$", line)
        if not m:
            raise ValueError(f"cannot parse transition {raw.strip()!r} — expected 'from -> to : condition'")
        for s in (m.group(1), m.group(2)):
            if s != "*" and s not in states:
                raise ValueError(f"unknown state {s!r} in {raw.strip()!r}")
        trans.append((m.group(1), m.group(2), compile_expr(m.group(3))))
    outs, names = [], []
    for raw in str(outputs_text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _re.match(r"^(\*|[A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*=(?!=)(.+)$", line)
        if not m:
            raise ValueError(f"cannot parse output {raw.strip()!r} — expected 'state: name = expression'")
        outs.append((m.group(1), m.group(2), compile_expr(m.group(3))))
        if m.group(2) not in names:
            names.append(m.group(2))
    return states, tuple(trans), tuple(outs), tuple(names)


def parse_table(text):
    """Two-column table (x, y per line; commas or whitespace) sorted by x."""
    rows = []
    for raw in str(text or "").splitlines():
        line = raw.split("#", 1)[0].strip().replace(",", " ").split()
        if len(line) >= 2:
            rows.append((float(line[0]), float(line[1])))
    rows.sort()
    if len(rows) < 1:
        raise ValueError("table needs at least one 'x, y' row")
    return [r[0] for r in rows], [r[1] for r in rows]


def interp(xs, ys, x, mode="linear"):
    """Interpolate y at x from sorted tables xs/ys: 'linear', 'step' (previous value) or 'nearest'; clamped at the ends."""
    import bisect as _b
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = _b.bisect_right(xs, x) - 1
    if mode == "step":
        return ys[i]
    if mode == "nearest":
        return ys[i] if x - xs[i] <= xs[i + 1] - x else ys[i + 1]
    f = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + f * (ys[i + 1] - ys[i])


def rng_functions(rng):
    """Seeded random functions for expression environments."""
    return {"random": rng.random, "uniform": rng.uniform, "gauss": rng.gauss,
            "bernoulli": lambda p: 1 if rng.random() < p else 0,
            "poisson": lambda lam: _poisson(rng, lam), "randint": rng.randint,
            "choice": rng.choice, "expovariate": rng.expovariate}


def _poisson(rng, lam):
    """Poisson sample: Knuth's multiplication method for small λ, normal approximation above λ = 50."""
    if lam <= 0:
        return 0
    if lam > 50:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


AGG_FUNCTIONS = {"mean": lambda v: mean(v), "sum": lambda v: sum(as_list(v)), "count": lambda v: sum(1 for x in as_list(v) if x),
                 "std": lambda v: std(v) if len(as_list(v)) > 1 else 0.0, "var": lambda v: var(v) if len(as_list(v)) > 1 else 0.0,
                 "minimum": lambda v: min(as_list(v)), "maximum": lambda v: max(as_list(v)), "median": lambda v: median(v),
                 "frac": lambda v: sum(1 for x in as_list(v) if x) / max(1, len(as_list(v))),
                 "tally": lambda v, value: sum(1 for x in as_list(v) if x == value)}


# ----------------------------------------------------------------------------
# populations (agent-based & network dynamics)
# ----------------------------------------------------------------------------

def net_ring(n, k):
    """Ring lattice: each node linked to its k nearest neighbours (k rounded down to even)."""
    k = max(2, int(k) // 2 * 2)
    return [sorted({(i + d) % n for d in range(-k // 2, k // 2 + 1) if d}) for i in range(n)]


def net_erdos_renyi(n, p, rng):
    """G(n, p) random graph: every pair connected independently with probability p."""
    adj = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p:
                adj[i].add(j); adj[j].add(i)
    return [sorted(a) for a in adj]


def net_watts_strogatz(n, k, p, rng):
    """Small-world graph: a ring lattice whose edges are rewired with probability p (Watts & Strogatz 1998)."""
    adj = [set(a) for a in net_ring(n, k)]
    for i in range(n):
        for j in [j for j in list(adj[i]) if j > i]:
            if rng.random() < p:
                cands = [c for c in range(n) if c != i and c not in adj[i]]
                if cands:
                    new = rng.choice(cands)
                    adj[i].discard(j); adj[j].discard(i); adj[i].add(new); adj[new].add(i)
    return [sorted(a) for a in adj]


def net_barabasi_albert(n, m, rng):
    """Scale-free graph by preferential attachment: each new node links to m existing nodes chosen
    proportionally to degree (Barabási & Albert 1999).
    """
    m = max(1, int(m))
    adj = [set() for _ in range(n)]
    targets, repeated = list(range(m)), []
    for v in range(m, n):
        for t in set(targets):
            adj[v].add(t); adj[t].add(v)
        repeated.extend(targets); repeated.extend([v] * m)
        chosen = set()
        while len(chosen) < m:
            chosen.add(rng.choice(repeated))
        targets = list(chosen)
    return [sorted(a) for a in adj]


def net_grid(n):
    """Periodic square lattice (torus) with 4-neighbourhoods; n is rounded to a square."""
    side = max(1, int(round(math.sqrt(n))))
    adj = []
    for i in range(side * side):
        r, c = divmod(i, side)
        adj.append(sorted(((r + dr) % side) * side + (c + dc) % side for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))))
    return adj


def make_network(kind, n, k=4, p=0.1, rng=None):
    """Build adjacency lists for a named topology: ring, erdos_renyi, watts_strogatz, barabasi_albert, grid, complete."""
    rng = rng or random.Random(0)
    n = int(n)
    if kind == "ring":
        return net_ring(n, k)
    if kind == "erdos_renyi":
        return net_erdos_renyi(n, p, rng)
    if kind == "watts_strogatz":
        return net_watts_strogatz(n, k, p, rng)
    if kind == "barabasi_albert":
        return net_barabasi_albert(n, max(1, int(k) // 2), rng)
    if kind == "grid":
        return net_grid(n)
    if kind == "complete":
        return [[j for j in range(n) if j != i] for i in range(n)]
    raise ValueError(f"unknown topology {kind!r}")


class Population:
    """N individuals with named attributes, updated synchronously by per-agent rules.

    init / rules / observables are equation texts. In rules and init each attribute
    is a scalar (this agent); in observables each attribute is the list over agents.
    With ``adj`` (adjacency lists) rules get nbr_sum/nbr_mean/nbr_max/nbr_count/deg/nbr.
    """

    def __init__(self, n, init_text, env, rng, adj=None):
        self.n, self.rng, self.adj = int(n), rng, adj
        init = parse_equations(init_text)
        self.names = [lhs for lhs, _ in init]
        self.cols = {nm: [0.0] * self.n for nm in self.names}
        base = dict(env)
        base.update(rng_functions(rng))
        base["N"] = self.n
        for i in range(self.n):
            e = dict(base)
            e["i"] = i
            if adj is not None:
                e["deg"] = len(adj[i])
            for lhs, code in init:
                e[lhs] = self.cols[lhs][i] = eval_expr(code, e)

    def observe(self, obs_text, env):
        """Evaluate population observables (e.g. 'I = tally(status, 1)'): each attribute is the list over all
        individuals, with aggregate helpers mean/sum/count/frac/tally/std/minimum/maximum/median.
        """
        e = dict(env)
        e.update(AGG_FUNCTIONS)
        e.update(self.cols)
        e["N"] = self.n
        out = {}
        for lhs, code in parse_equations(obs_text):
            e[lhs] = out[lhs] = eval_expr(code, e)
        return out

    def step(self, rules_text, env):
        """Advance every individual once. Updates are synchronous: all rules read last step's values.

        Performance (0.5): 0.4 copied the environment dict and created five closures *per
        individual*; now one environment and one set of neighbour functions are reused and a
        one-element list ``cur`` tells the closures which individual is being updated.
        Within one individual, later rules see the values assigned by earlier rules.
        """
        rules = parse_equations(rules_text)
        cols, adj, rng, n = self.cols, self.adj, self.rng, self.n
        new = {k: list(v) for k, v in cols.items()}
        for lhs, _ in rules:
            new.setdefault(lhs, [0.0] * n)
        names = list(new)
        e = dict(env)
        e.update(rng_functions(rng))
        e["N"] = n
        cur = [0]                                          # index of the individual being updated
        randrange = rng.randrange
        e["other"] = lambda a: cols[a][randrange(n)]
        if adj is not None:
            def nb():
                """Neighbour list of the individual currently being updated."""
                return adj[cur[0]]
            e["nbr_sum"] = lambda a: sum(cols[a][j] for j in adj[cur[0]])
            e["nbr_mean"] = lambda a: (sum(cols[a][j] for j in adj[cur[0]]) / len(adj[cur[0]])) if adj[cur[0]] else 0.0
            e["nbr_max"] = lambda a: max((cols[a][j] for j in adj[cur[0]]), default=0.0)
            e["nbr_count"] = lambda a: sum(1 for j in adj[cur[0]] if cols[a][j])
            e["nbr"] = lambda a: cols[a][rng.choice(nb())] if nb() else 0.0
        src = [(k, cols[k] if k in cols else new[k]) for k in names]   # column to read each name from
        for i in range(n):
            cur[0] = i
            for k, col in src:
                e[k] = col[i]
            e["i"] = i
            if adj is not None:
                e["deg"] = len(adj[i])
            for lhs, code in rules:
                e[lhs] = new[lhs][i] = eval(code, _EXPR_GLOBALS, e)
        self.cols = new


# ----------------------------------------------------------------------------
# linear systems
# ----------------------------------------------------------------------------

def tf_to_ss(num, den):
    """Controllable canonical realisation of G(s)=num(s)/den(s) (descending powers).

    Returns (A, B, C, D) as lists. Requires deg(num) <= deg(den).
    """
    num, den = [float(x) for x in num], [float(x) for x in den]
    while den and den[0] == 0:
        den.pop(0)
    if not den:
        raise ValueError("denominator is zero")
    n = len(den) - 1
    if len(num) > n + 1:
        raise ValueError("improper transfer function: deg(num) > deg(den)")
    a0 = den[0]
    den = [d / a0 for d in den]
    num = [0.0] * (n + 1 - len(num)) + [x / a0 for x in num]
    D = num[0]
    if n == 0:
        return [], [], [], D
    A = [[0.0] * n for _ in range(n)]
    for i in range(n - 1):
        A[i][i + 1] = 1.0
    A[n - 1] = [-den[n - j] for j in range(n)]
    B = [0.0] * (n - 1) + [1.0]
    C = [num[n - j] - den[n - j] * D for j in range(n)]
    return A, B, C, D


# ----------------------------------------------------------------------------
# 2-D fields (numpy)
# ----------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def field_namespace():
    """numpy-backed expression namespace for 2-D fields (lap, gx, gy, sin, exp, …); built once."""
    if not HAS_NUMPY:
        raise RuntimeError("the 2-D field node needs numpy (pip install numpy)")
    np_ = _np
    ns = {k: getattr(np_, k) for k in ("sin", "cos", "tan", "exp", "log", "sqrt", "tanh", "abs", "arctan2",
                                       "minimum", "maximum", "where", "clip", "pi", "e", "sinh", "cosh", "floor")}
    ns["lap"] = lambda f: np_.roll(f, 1, 0) + np_.roll(f, -1, 0) + np_.roll(f, 1, 1) + np_.roll(f, -1, 1) - 4 * f
    ns["gx"] = lambda f: (np_.roll(f, -1, 1) - np_.roll(f, 1, 1)) / 2
    ns["gy"] = lambda f: (np_.roll(f, -1, 0) - np_.roll(f, 1, 0)) / 2
    ns["__builtins__"] = {}
    return ns


# ----------------------------------------------------------------------------
# ODE integration
# ----------------------------------------------------------------------------

def _axpy(a, x, y):
    """y + a·x element-wise (the BLAS 'axpy' operation on lists)."""
    return [yi + a * xi for xi, yi in zip(x, y)]


def euler_step(f, t, y, dt):
    """One explicit Euler step y + dt·f(t, y) — first order; prefer rk4_step unless f is cheap and dt tiny."""
    return _axpy(dt, f(t, y), y)


def rk4_step(f: Callable, t: float, y: Sequence[float], dt: float) -> List[float]:
    """Classical 4th-order Runge–Kutta step for dy/dt = f(t, y).

    Works on lists (pure Python) and on numpy arrays (vectorised — used by large systems such as
    the Kuramoto node). The list path performs exactly the same floating-point operations in the
    same order as before 0.7 (results are bit-identical); it only hoists constants and inlines
    the ``y + a·k`` helper to save a function call and a zip per stage.
    """
    h2 = dt / 2
    if HAS_NUMPY and isinstance(y, _np.ndarray):              # vectorised path: whole-array arithmetic
        k1 = f(t, y)
        k2 = f(t + h2, y + h2 * k1)
        k3 = f(t + h2, y + h2 * k2)
        k4 = f(t + dt, y + dt * k3)
        return y + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    y = list(y)
    k1 = f(t, y)
    k2 = f(t + h2, [yi + h2 * k for k, yi in zip(k1, y)])
    k3 = f(t + h2, [yi + h2 * k for k, yi in zip(k2, y)])
    k4 = f(t + dt, [yi + dt * k for k, yi in zip(k3, y)])
    d6 = dt / 6
    return [yi + d6 * (a + 2 * b + 2 * c + d) for yi, a, b, c, d in zip(y, k1, k2, k3, k4)]


def rk4_advance(f, t, y, dt, max_substep):
    """Advance ``dt`` using as many equal RK4 substeps as needed so h <= max_substep."""
    n = max(1, int(math.ceil(abs(dt) / max_substep))) if max_substep else 1
    h = dt / n
    for i in range(n):
        y = rk4_step(f, t + i * h, y, h)
    return y


# Dormand–Prince 5(4) coefficients
_DP_C = [0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1, 1]
_DP_A = [
    [],
    [1 / 5],
    [3 / 40, 9 / 40],
    [44 / 45, -56 / 15, 32 / 9],
    [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
    [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656],
    [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84],
]
_DP_B5 = [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84, 0]
_DP_B4 = [5179 / 57600, 0, 7571 / 16695, 393 / 640, -92097 / 339200, 187 / 2100, 1 / 40]


def solve_ivp(f, t0, t1, y0, rtol=1e-6, atol=1e-9, n_out=200, max_steps=200000):
    """Adaptive Dormand–Prince RK5(4) integrator with dense-ish output.

    Returns (t_list, Y) where Y[i] is the state at t_list[i]. Output points are
    produced by stepping exactly onto a uniform grid of ``n_out`` points.
    """
    y = [float(v) for v in y0]
    grid = linspace(t0, t1, max(2, int(n_out)))
    ts, ys = [grid[0]], [list(y)]
    t = t0
    h = (t1 - t0) / 100 or 1e-3
    steps = 0
    for target in grid[1:]:
        while t < target - 1e-15 * max(1.0, abs(target)):
            h = min(h, target - t)
            k = [f(t, y)]
            for s in range(1, 7):
                yi = list(y)
                for j, a in enumerate(_DP_A[s]):
                    if a:
                        yi = _axpy(h * a, k[j], yi)
                k.append(f(t + _DP_C[s] * h, yi))
            y5 = list(y)
            y4 = list(y)
            for j in range(7):
                if _DP_B5[j]:
                    y5 = _axpy(h * _DP_B5[j], k[j], y5)
                if _DP_B4[j]:
                    y4 = _axpy(h * _DP_B4[j], k[j], y4)
            err = 0.0
            for a, b, y_old in zip(y5, y4, y):
                sc = atol + rtol * max(abs(a), abs(y_old))
                err = max(err, abs(a - b) / sc)
            steps += 1
            if steps > max_steps:
                raise RuntimeError("solve_ivp: max_steps exceeded (stiff system?)")
            if err <= 1.0:
                t += h
                y = y5
            factor = 0.9 * (1.0 / err) ** 0.2 if err > 0 else 5.0
            h *= min(5.0, max(0.2, factor))
        ts.append(target)
        ys.append(list(y))
    return ts, ys


# ----------------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------------

def mean(xs):
    """Arithmetic mean (NaN for an empty input)."""
    xs = as_list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def var(xs, ddof=1):
    """Variance with ``ddof`` degrees of freedom removed (1 = unbiased sample variance)."""
    xs = as_list(xs)
    n = len(xs)
    if n - ddof <= 0:
        return float("nan")
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - ddof)


def std(xs, ddof=1):
    """Standard deviation (sample, ddof = 1 by default)."""
    return math.sqrt(var(xs, ddof))


def median(xs):
    """Median (average of the two middle values for even counts)."""
    s = sorted(as_list(xs))
    n = len(s)
    if not n:
        return float("nan")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def percentile(xs, q):
    """Linear-interpolated percentile, q in [0, 100]."""
    s = sorted(as_list(xs))
    if not s:
        return float("nan")
    pos = (len(s) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def pearson(x, y):
    """Pearson product-moment correlation of the paired prefix of x and y (NaN if either is constant)."""
    x, y = as_list(x), as_list(y)
    n = min(len(x), len(y))
    if n < 2:
        return float("nan")
    x, y = x[:n], y[:n]
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def ranks(xs):
    """Average ranks (ties share the mean rank), 1-based."""
    xs = as_list(xs)
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(x, y):
    """Spearman rank correlation: Pearson on average ranks — measures any monotonic relationship."""
    n = min(len(as_list(x)), len(as_list(y)))
    return pearson(ranks(as_list(x)[:n]), ranks(as_list(y)[:n]))


def linregress(x, y):
    """Ordinary least squares y = a + b x. Returns dict(slope, intercept, r2, stderr_slope)."""
    x, y = as_list(x), as_list(y)
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    if n < 2:
        raise ValueError("linregress needs >= 2 points")
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        raise ValueError("linregress: x has zero variance")
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    b = sxy / sxx
    a = my - b * mx
    ss_res = sum((yi - (a + b * xi)) ** 2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - my) ** 2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    se = math.sqrt(ss_res / (n - 2) / sxx) if n > 2 else float("nan")
    return {"slope": b, "intercept": a, "r2": r2, "stderr_slope": se}


def histogram(xs, bins=10, lo=None, hi=None):
    """Equal-width histogram → (counts, edges); values equal to ``hi`` fall in the last bin."""
    xs = as_list(xs)
    if not xs:
        return [0] * bins, linspace(0, 1, bins + 1)
    lo = min(xs) if lo is None else lo
    hi = max(xs) if hi is None else hi
    if hi == lo:
        hi = lo + 1
    edges = linspace(lo, hi, bins + 1)
    counts = [0] * bins
    w = (hi - lo) / bins
    for v in xs:
        if lo <= v <= hi:
            counts[min(bins - 1, int((v - lo) / w))] += 1
    return counts, edges


def rfft_mag(signal, sample_rate=1.0):
    """One-sided amplitude spectrum. Returns (freqs, magnitudes)."""
    x = as_list(signal)
    n = len(x)
    if n == 0:
        return [], []
    if HAS_NUMPY:
        spec = _np.fft.rfft(_np.asarray(x, dtype=float))
        mags = (_np.abs(spec) / n).tolist()
        freqs = _np.fft.rfftfreq(n, d=1.0 / sample_rate).tolist()
    else:  # O(n^2) DFT fallback
        m = n // 2 + 1
        mags, freqs = [], []
        for k in range(m):
            re = sum(x[t] * math.cos(2 * math.pi * k * t / n) for t in range(n))
            im = -sum(x[t] * math.sin(2 * math.pi * k * t / n) for t in range(n))
            mags.append(math.hypot(re, im) / n)
            freqs.append(k * sample_rate / n)
    # one-sided: double all but DC (and Nyquist for even n)
    for k in range(1, len(mags)):
        if not (n % 2 == 0 and k == len(mags) - 1):
            mags[k] *= 2
    return freqs, mags


# ----------------------------------------------------------------------------
# random sampling
# ----------------------------------------------------------------------------

def binomial(rng: random.Random, n: int, p: float) -> int:
    """Exact binomial draw (numpy if available, else inversion / sum of Bernoullis)."""
    n = int(n)
    p = min(1.0, max(0.0, p))
    if HAS_NUMPY:
        seed = rng.getrandbits(63)
        return int(_np.random.default_rng(seed).binomial(n, p))
    return sum(1 for _ in range(n) if rng.random() < p)


# ----------------------------------------------------------------------------
# optimisation
# ----------------------------------------------------------------------------

def nelder_mead(f, x0, step=0.5, tol=1e-9, max_iter=2000, xtol=1e-9):
    """Derivative-free minimisation. Returns (x_best, f_best, iterations)."""
    n = len(x0)
    pts = [list(map(float, x0))]
    for i in range(n):
        p = list(map(float, x0))
        p[i] += step if p[i] == 0 else step * abs(p[i])
        pts.append(p)
    vals = [f(p) for p in pts]
    it = 0
    for it in range(1, max_iter + 1):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        # stop only when values AND vertices have converged (equal values alone can occur on a
        # symmetric objective with vertices on opposite sides of the optimum)
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol) and \
                max(abs(p[j] - pts[0][j]) for p in pts[1:] for j in range(n)) <= xtol * (1 + max(abs(v) for v in pts[0])):
            break
        c = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        xr = [c[j] + (c[j] - pts[-1][j]) for j in range(n)]
        fr = f(xr)
        if fr < vals[0]:
            xe = [c[j] + 2 * (c[j] - pts[-1][j]) for j in range(n)]
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(n)]
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    best = min(range(n + 1), key=lambda i: vals[i])
    return pts[best], vals[best], it


def bisect(f, a, b, tol=1e-12, max_iter=200):
    """Root of f on [a, b] by bisection (guaranteed for a sign change; error halves each iteration).
    Returns (root, iterations).
    """
    fa, fb = f(a), f(b)
    if fa == 0:
        return a, 0
    if fb == 0:
        return b, 0
    if fa * fb > 0:
        raise ValueError("bisect: f(a) and f(b) must have opposite signs")
    for i in range(1, max_iter + 1):
        m = 0.5 * (a + b)
        fm = f(m)
        if fm == 0 or (b - a) / 2 < tol:
            return m, i
        if fa * fm < 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    return 0.5 * (a + b), max_iter


# ----------------------------------------------------------------------------
# colour (design helpers)
# ----------------------------------------------------------------------------

def hex_to_rgb(h: str):
    """'#rrggbb' or '#rgb' → (r, g, b) with components in [0, 1]."""
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    """(r, g, b) in [0, 1] → '#rrggbb' (components clipped)."""
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def relative_luminance(hexcolor: str) -> float:
    """WCAG 2.x relative luminance."""
    def ch(c):
        """WCAG channel linearisation: sRGB component → linear light."""
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(hexcolor)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two colours (1–21; ≥ 4.5 passes AA for body text)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

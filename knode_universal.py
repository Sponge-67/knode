"""
knode_universal — highly configurable "universal" nodes.

Each of these nodes is a *modelling formalism* rather than a single model:
you describe the system in its parameters (equations, reactions, rules, states…)
and the node's ports are derived from that description automatically.

Port rules (``ports``) are evaluated identically in Python (derive_ports) and in
the editor (knode_science.js):  list:<param>  lhs:<param>  species:<param>
smout:<param>  const:a,b  suffix:<param>:<text>

``schema`` describes parameter widgets: {"kind": "text|code|number|select|bool",
"min", "max", "step", "unit", "options", "doc"}.
"""
from __future__ import annotations

import re
import textwrap

UNIVERSAL_COLORS = {
    "Universal": "#8c7ae6",
    "Logic & Signals": "#00d2d3",
    "Structure": "#95a5a6",
}

U = []


def T(id, category, name, inputs, outputs, params, code, description, sim=False, ports=None, schema=None, refs=None):
    """Register a template: ports, default params, node code (dedented), description, and whether it is
    stateful (evolves over simulation steps). Optional: dynamic port rules, parameter widget schema, references.
    """
    U.append({"id": id, "category": category, "name": name, "inputs": inputs, "outputs": outputs,
              "params": params, "code": textwrap.dedent(code).strip() + "\n", "description": description,
              "stateful": sim, "ports": ports, "schema": schema or {}, "refs": refs or [],
              "color": UNIVERSAL_COLORS[category], "universal": True, "open_params": id in ("globals", "script")})


EQ_DOC = "One per line: name = expression. math functions, a if c else b, and earlier lines are available."
CODE = {"kind": "code"}

# ---------------------------------------------------------------------------- Formula
T("formula", "Universal", "Formula Block", ["a", "b", "x"], ["y", "z"],
  {"inputs": "a, b, x", "equations": "y = a*x + b\nz = sqrt(abs(y))", "constants": "a=2, b=1"}, """
    def process(params, t=0.0, dt=0.01, step=0, **inputs):
        consts = ks.parse_assignments(params["constants"])
        names = ks.parse_names(params["inputs"])
        eqs = ks.parse_equations(params["equations"])
        vals = {n: ks.pick(inputs.get(n), consts.get(n, 0.0)) for n in names}
        def row(v):
            env = dict(consts); env.update(v); env.update(t=t, dt=dt, step=step)
            out = {}
            for lhs, code in eqs:
                env[lhs] = out[lhs] = ks.eval_expr(code, env)
            return out
        seqs = [n for n in names if ks.is_seq(vals[n])]
        if not seqs:
            return row(vals)
        n = len(ks.as_list(vals[seqs[0]]))
        rows = [row({k: (ks.as_list(v)[i] if ks.is_seq(v) else v) for k, v in vals.items()}) for i in range(n)]
        return {lhs: [r[lhs] for r in rows] for lhs, _ in eqs}
""", "Any number of named inputs → any number of equations. Each left-hand side becomes an output port. "
     "Unconnected inputs fall back to a constant of the same name. Lists are processed element-wise.",
  ports={"inputs": ["list:inputs"], "outputs": ["lhs:equations"]},
  schema={"inputs": {"kind": "text", "doc": "comma-separated input port names"},
          "equations": dict(CODE, doc=EQ_DOC), "constants": {"kind": "text", "doc": "name=value, …"}})

# ---------------------------------------------------------------------------- Continuous dynamics
T("dynamic_system", "Universal", "Dynamic System (ODE)", ["F"], ["x", "v", "E"],
  {"inputs": "F", "states": "x, v", "equations": "dx = v\ndv = (F - c*v - k*x - beta*x**3)/m",
   "initial": "x = 1, v = 0", "constants": "m=1, c=0.2, k=1, beta=0.5, F=0",
   "observables": "E = 0.5*m*v**2 + 0.5*k*x**2 + 0.25*beta*x**4", "method": "rk4", "max_substep": 0.01}, """
    def process(params, state, t=0.0, dt=0.01, **inputs):
        p = params
        names, codes = ks.ode_system(p["states"], p["equations"])   # parsed once per distinct text
        consts = ks.parse_assignments(p["constants"])
        if "y" not in state:
            init = ks.parse_assignments(p["initial"], consts)
            state["y"] = [float(init.get(n, 0.0)) for n in names]
        env0 = dict(consts)
        for n in ks.parse_names(p["inputs"]):
            env0[n] = ks.pick(inputs.get(n), consts.get(n, 0.0))
        def f(tt, y):
            env = dict(env0); env.update(zip(names, y)); env["t"] = tt
            return [ks.eval_expr(c, env) for c in codes]
        y = state["y"]
        env = dict(env0); env.update(zip(names, y)); env["t"] = t
        out = dict(zip(names, y))
        for lhs, code in ks.parse_equations(p["observables"]):
            env[lhs] = out[lhs] = ks.eval_expr(code, env)
        if p["method"] == "euler":
            n = max(1, math.ceil(dt / p["max_substep"])); h = dt / n
            for i in range(n):
                y = ks.euler_step(f, t + i * h, y, h)
            state["y"] = y
        else:
            state["y"] = ks.rk4_advance(f, t, y, dt, p["max_substep"])
        return out
""", "Continuous-time system dx/dt = f(x, u, t) with any states, external inputs and observables — "
     "mechanics, circuits, pharmacokinetics, ecology, neurons… Default: forced Duffing oscillator.",
  sim=True, ports={"inputs": ["list:inputs"], "outputs": ["list:states", "lhs:observables"]},
  schema={"inputs": {"kind": "text", "doc": "input port names (connected values override constants)"},
          "states": {"kind": "text", "doc": "state variable names"},
          "equations": dict(CODE, doc="dname = expression for every state"),
          "initial": {"kind": "text"}, "constants": {"kind": "text"},
          "observables": dict(CODE, doc="extra outputs computed from states: name = expression"),
          "method": {"kind": "select", "options": ["rk4", "euler"]},
          "max_substep": {"kind": "number", "min": 1e-5, "max": 1, "step": 0.001, "unit": "time"}})

# ---------------------------------------------------------------------------- Discrete dynamics
T("discrete_map", "Universal", "Difference Equations", ["r"], ["x", "y"],
  {"inputs": "r", "states": "x, y", "update": "x = 1 - r*x**2 + y\ny = b*x", "initial": "x = 0.1, y = 0.1",
   "constants": "r=1.4, b=0.3", "observables": ""}, """
    def process(params, state, step=0, t=0.0, **inputs):
        p = params
        names = ks.parse_names(p["states"])
        consts = ks.parse_assignments(p["constants"])
        if "x" not in state:
            init = ks.parse_assignments(p["initial"], consts)
            state["x"] = {n: float(init.get(n, 0.0)) for n in names}
        env = dict(consts)
        for n in ks.parse_names(p["inputs"]):
            env[n] = ks.pick(inputs.get(n), consts.get(n, 0.0))
        env.update(state["x"]); env.update(t=t, step=step)
        out = dict(state["x"])
        for lhs, code in ks.parse_equations(p["observables"]):
            env[lhs] = out[lhs] = ks.eval_expr(code, env)
        nxt = {}
        for lhs, code in ks.parse_equations(p["update"]):
            nxt[lhs] = ks.eval_expr(code, env)        # simultaneous update: all read the old state
        state["x"].update(nxt)
        return out
""", "Discrete-time system x[k+1] = f(x[k], u): population genetics, economics, iterated maps, digital filters. "
     "All updates are simultaneous. Default: Hénon map.",
  sim=True, ports={"inputs": ["list:inputs"], "outputs": ["list:states", "lhs:observables"]},
  schema={"update": dict(CODE, doc="state = next value (simultaneous)"), "observables": dict(CODE), "states": {"kind": "text"},
          "inputs": {"kind": "text"}, "initial": {"kind": "text"}, "constants": {"kind": "text"}})

# ---------------------------------------------------------------------------- Reaction network
T("reaction_network", "Universal", "Reaction Network", [], ["S", "I", "R"],
  {"reactions": "S + I -> 2 I, beta/N\nI -> R, gamma", "initial": "S = 990, I = 10, R = 0",
   "constants": "beta=0.3, gamma=0.1, N=1000", "inputs": "", "method": "ode", "seed": 1, "max_substep": 0.05}, """
    def falling(x, s):
        r = 1.0
        for j in range(s):
            r *= (x - j)
        return r

    def process(params, state, t=0.0, dt=0.1, **inputs):
        p = params
        species, rxns, stoich, idx = ks.reaction_system(p["reactions"])   # parsed once per distinct text
        consts = ks.parse_assignments(p["constants"])
        for n in ks.parse_names(p["inputs"]):
            if inputs.get(n) is not None:
                consts[n] = inputs[n]
        if "x" not in state:
            init = ks.parse_assignments(p["initial"], consts)
            state["x"] = [float(init.get(s, 0.0)) for s in species]
            state["rng"] = random.Random(p["seed"])
            if p["method"] == "ssa":
                state["x"] = [float(round(v)) for v in state["x"]]
        x = state["x"]
        out = dict(zip(species, x))
        def rates(xx, tt, stochastic=False):
            env = dict(consts); env.update(zip(species, xx)); env["t"] = tt
            r = []
            for reac, prod, code, mass in rxns:
                k = ks.eval_expr(code, env)
                if mass:
                    for s, c in reac:
                        k *= falling(xx[idx[s]], c) if stochastic else xx[idx[s]] ** c
                r.append(max(0.0, k) if stochastic else k)
            return r
        if p["method"] == "ssa":                           # exact Gillespie direct method
            rng, tt, t_end, events = state["rng"], t, t + dt, 0
            while True:
                a = rates(x, tt, True); a0 = sum(a)
                if a0 <= 0:
                    break
                tt += rng.expovariate(a0)
                if tt > t_end:
                    break
                r, acc, j = rng.random() * a0, 0.0, 0
                for j, aj in enumerate(a):
                    acc += aj
                    if acc >= r:
                        break
                x = [xi + d for xi, d in zip(x, stoich[j])]
                events += 1
                if events > 2_000_000:
                    raise RuntimeError("SSA: too many events in one step — reduce dt or populations")
            state["x"] = x
        else:
            def f(tt, xx):
                r = rates(xx, tt)
                return [sum(stoich[j][i] * r[j] for j in range(len(r))) for i in range(len(species))]
            state["x"] = ks.rk4_advance(f, t, x, dt, p["max_substep"])
        return out
""", "Chemical-reaction notation for any interacting populations: biochemistry, gene expression, epidemics, ecology. "
     "Mass action by default (rate = k·Πreactants); write '= expression' for a custom rate law. "
     "method 'ode' = deterministic, 'ssa' = exact stochastic Gillespie simulation.",
  sim=True, ports={"inputs": ["list:inputs"], "outputs": ["species:reactions"]},
  schema={"reactions": dict(CODE, doc="A + 2 B -> C, k    (mass action)\nS -> P, = Vmax*S/(Km+S)    (custom law)\n-> A, k0  (source)   A ->, d  (decay)"),
          "initial": {"kind": "text"}, "constants": {"kind": "text"}, "inputs": {"kind": "text", "doc": "connected inputs override constants"},
          "method": {"kind": "select", "options": ["ode", "ssa"]}, "seed": {"kind": "number", "step": 1},
          "max_substep": {"kind": "number", "min": 1e-5, "max": 10, "step": 0.01}},
  refs=["Gillespie, J Phys Chem 81:2340 (1977)"])

# ---------------------------------------------------------------------------- State machine
T("state_machine", "Universal", "State Machine", ["T"], ["state", "state_name", "time_in_state", "power"],
  {"inputs": "T", "states": "idle, heating, cooling",
   "transitions": "idle -> heating : T < 19\nheating -> idle : T > 21\nidle -> cooling : T > 24\ncooling -> idle : T < 22",
   "outputs": "*: power = 0\nheating: power = 2000\ncooling: power = -1500", "constants": "T=20"}, """
    def process(params, state, t=0.0, dt=0.01, **inputs):
        p = params
        states, trans, outs, names = ks.parse_state_machine(p["states"], p["transitions"], p["outputs"])
        consts = ks.parse_assignments(p["constants"])
        env = dict(consts)
        for n in ks.parse_names(p["inputs"]):
            env[n] = ks.pick(inputs.get(n), consts.get(n, 0.0))
        if "s" not in state:
            state["s"], state["since"] = states[0], t
        env.update(t=t, dt=dt, tau=t - state["since"], state=state["s"])
        for src, dst, cond in trans:                      # first matching transition fires
            if src in (state["s"], "*") and dst != state["s"] and ks.eval_expr(cond, env):
                state["s"], state["since"] = dst, t
                break
        cur = state["s"]
        env.update(tau=t - state["since"], state=cur)
        out = {"state": states.index(cur), "state_name": cur, "time_in_state": t - state["since"]}
        for which in ("*", cur):
            for st, lhs, code in outs:
                if st == which:
                    env[lhs] = out[lhs] = ks.eval_expr(code, env)
        for n in names:
            out.setdefault(n, None)
        return out
""", "Finite-state machine: controllers, protocols, cell-cycle phases, behaviour modes. Conditions may use inputs, "
     "constants, t and tau (time in the current state). Outputs are assigned per state ('*' = default).",
  sim=True, ports={"inputs": ["list:inputs"], "outputs": ["const:state,state_name,time_in_state", "smout:outputs"]},
  schema={"states": {"kind": "text", "doc": "first state is the initial one"},
          "transitions": dict(CODE, doc="from -> to : condition     (from may be *)"),
          "outputs": dict(CODE, doc="state: name = expression   (* = default for all states)"),
          "inputs": {"kind": "text"}, "constants": {"kind": "text"}})

# ---------------------------------------------------------------------------- Agent-based
T("agent_based", "Universal", "Agent-Based Model", ["beta"], ["S", "I", "R"],
  {"N": 300, "inputs": "beta", "constants": "beta=0.5, gamma=0.1",
   "init": "status = 1 if i < 5 else 0        # 0 = S, 1 = I, 2 = R",
   "rules": "status = (1 if bernoulli(beta*I/N*dt) else 0) if status == 0 else ((2 if bernoulli(gamma*dt) else 1) if status == 1 else 2)",
   "observables": "S = tally(status, 0)\nI = tally(status, 1)\nR = tally(status, 2)",
   "seed": 3}, """
    def process(params, state, t=0.0, dt=0.1, step=0, **inputs):
        p = params
        consts = ks.parse_assignments(p["constants"])
        env = dict(consts)
        for n in ks.parse_names(p["inputs"]):
            env[n] = ks.pick(inputs.get(n), consts.get(n, 0.0))
        env.update(t=t, dt=dt, step=step)
        if "pop" not in state:
            state["pop"] = ks.Population(p["N"], p["init"], env, random.Random(p["seed"]))
        pop = state["pop"]
        obs = pop.observe(p["observables"], env)
        env.update(obs)                                   # rules see this step's aggregates
        pop.step(p["rules"], env)
        return obs
""", "N individuals with attributes (init), per-individual rules (evaluated synchronously each step) and population "
     "observables (outputs). Rules can use bernoulli(p), gauss(m,s), uniform(a,b), other('attr') (a random individual) "
     "and any observable. Default: stochastic individual-based SIR.",
  sim=True, ports={"inputs": ["list:inputs"], "outputs": ["lhs:observables"]},
  schema={"N": {"kind": "number", "min": 1, "max": 20000, "step": 1},
          "init": dict(CODE, doc="per-agent initial attributes; i = index"),
          "rules": dict(CODE, doc="per-agent update; attributes are this agent's values"),
          "observables": dict(CODE, doc="population outputs; attributes are lists here. mean, sum, count, frac, tally(list, value), std, minimum, maximum, median"),
          "inputs": {"kind": "text"}, "constants": {"kind": "text"}, "seed": {"kind": "number", "step": 1}})

# ---------------------------------------------------------------------------- Network dynamics
T("network_dynamics", "Universal", "Network Dynamics", [], ["adopters", "mean_opinion"],
  {"topology": "watts_strogatz", "N": 200, "k": 6, "p": 0.1, "seed": 2, "inputs": "", "constants": "q=0.3, theta=0.25",
   "init": "adopted = 1 if i < 4 else 0\nopinion = uniform(-1, 1)",
   "rules": "adopted = 1 if adopted or nbr_mean('adopted') > theta else 0\nopinion = opinion + q*(nbr_mean('opinion') - opinion)",
   "observables": "adopters = frac(adopted)\nmean_opinion = mean(opinion)"}, """
    def process(params, state, t=0.0, dt=0.1, step=0, **inputs):
        p = params
        consts = ks.parse_assignments(p["constants"])
        env = dict(consts)
        for n in ks.parse_names(p["inputs"]):
            env[n] = ks.pick(inputs.get(n), consts.get(n, 0.0))
        env.update(t=t, dt=dt, step=step)
        if "pop" not in state:
            rng = random.Random(p["seed"])
            adj = ks.make_network(p["topology"], p["N"], p["k"], p["p"], rng)
            state["pop"] = ks.Population(len(adj), p["init"], env, rng, adj)
        pop = state["pop"]
        obs = pop.observe(p["observables"], env)
        env.update(obs)
        pop.step(p["rules"], env)
        return obs
""", "Dynamics on a network: contagion, opinion formation, diffusion, synchronisation, cascades. Rules see "
     "nbr_mean/nbr_sum/nbr_max/nbr_count('attr'), nbr('attr') (random neighbour) and deg. Topologies: ring, "
     "erdos_renyi, watts_strogatz (small world), barabasi_albert (scale free), grid, complete. "
     "Default: threshold cascade (Watts 2002) + DeGroot opinion averaging.",
  sim=True, ports={"inputs": ["list:inputs"], "outputs": ["lhs:observables"]},
  schema={"topology": {"kind": "select", "options": ["ring", "erdos_renyi", "watts_strogatz", "barabasi_albert", "grid", "complete"]},
          "N": {"kind": "number", "min": 2, "max": 20000, "step": 1}, "k": {"kind": "number", "min": 1, "max": 100, "step": 1, "doc": "mean degree"},
          "p": {"kind": "number", "min": 0, "max": 1, "step": 0.01, "doc": "rewiring / edge probability"},
          "init": dict(CODE), "rules": dict(CODE), "observables": dict(CODE),
          "inputs": {"kind": "text"}, "constants": {"kind": "text"}, "seed": {"kind": "number", "step": 1}},
  refs=["Watts & Strogatz, Nature 393:440 (1998); Watts, PNAS 99:5766 (2002)"])

# ---------------------------------------------------------------------------- Spatial fields (PDE)
T("field2d", "Universal", "2-D Field (PDE)", [], ["u", "v", "u_mean", "v_mean"],
  {"fields": "u, v", "equations": "du = Du*lap(u) - u*v*v + F*(1 - u)\ndv = Dv*lap(v) + u*v*v - (F + k)*v",
   "initial": "seed = (abs(X - 0.5) < 0.08)*(abs(Y - 0.5) < 0.08)\nu = 1 - 0.5*seed\nv = 0.25*seed + 0.02*rand",
   "constants": "Du=0.16, Dv=0.08, F=0.04, k=0.06", "size": 96, "max_substep": 1.0, "seed": 0, "output_size": 96}, """
    def process(params, state, t=0.0, dt=1.0):
        p = params
        names, codes = ks.ode_system(p["fields"], p["equations"])
        rhs = dict(zip(names, codes))
        consts = ks.parse_assignments(p["constants"])
        ns = ks.field_namespace()
        if "F" not in state:
            n = int(p["size"])
            g = np.linspace(0, 1, n, endpoint=False)
            X, Y = np.meshgrid(g, g)
            rng = np.random.default_rng(int(p["seed"]))
            env = dict(consts); env.update(X=X, Y=Y, rand=rng.random((n, n)))
            F = {}
            for lhs, code in ks.parse_equations(p["initial"]):
                env[lhs] = F[lhs] = np.broadcast_to(np.asarray(eval(code, ns, env), dtype=float), (n, n)).copy()
            state["F"] = {k: F.get(k, np.zeros((n, n))) for k in names}
        F = state["F"]
        stride = max(1, int(p["size"]) // max(4, int(p["output_size"])))
        out = {}
        for k in names:
            out[k] = F[k][::stride, ::stride]
            out[k + "_mean"] = float(F[k].mean())
        m = max(1, math.ceil(dt / p["max_substep"])); h = dt / m
        for _ in range(m):                                # explicit Euler, periodic boundaries
            env = dict(consts); env.update(F); env["t"] = t
            d = {k: eval(rhs[k], ns, env) for k in names}
            for k in names:
                F[k] = F[k] + h * d[k]
        if not all(np.isfinite(F[k]).all() for k in names):
            raise FloatingPointError("field became non-finite — reduce max_substep")
        return out
""", "Reaction–diffusion / any PDE on a periodic 2-D grid: lap(f), gx(f), gy(f), X, Y. Pattern formation, heat, "
     "chemical waves, morphogenesis, excitable media. Default: Gray–Scott labyrinth (try F=0.03, k=0.062 for spots). Plot panel shows fields as heat-maps. Needs numpy.",
  sim=True, ports={"inputs": [], "outputs": ["list:fields", "suffix:fields:_mean"]},
  schema={"equations": dict(CODE, doc="dfield = expression (lap, gx, gy, numpy math)"),
          "initial": dict(CODE, doc="field = expression of X, Y in [0,1) and rand"),
          "fields": {"kind": "text"}, "constants": {"kind": "text"},
          "size": {"kind": "number", "min": 8, "max": 512, "step": 8}, "max_substep": {"kind": "number", "min": 0.001, "max": 5, "step": 0.01},
          "output_size": {"kind": "number", "min": 8, "max": 256, "step": 8}, "seed": {"kind": "number", "step": 1}},
  refs=["Pearson, Science 261:189 (1993)"])

# ---------------------------------------------------------------------------- Transfer function
T("transfer_function", "Universal", "Transfer Function", ["u"], ["y"],
  {"num": "1", "den": "1, 0.8, 1", "u": 1.0, "max_substep": 0.005}, """
    def process(u=None, params=None, state=None, t=0.0, dt=0.01):
        A, B, C, D = ks.tf_to_ss(ks.parse_floats(params["num"]), ks.parse_floats(params["den"]))
        uu = ks.pick(u, params["u"])
        x = state.setdefault("x", [0.0] * len(A))
        y = sum(c * xi for c, xi in zip(C, x)) + D * uu
        if A:
            f = lambda _t, z: [sum(a * zi for a, zi in zip(row, z)) + b * uu for row, b in zip(A, B)]
            state["x"] = ks.rk4_advance(f, t, x, dt, params["max_substep"])
        return {"y": y}
""", "Any linear time-invariant system G(s) = num(s)/den(s), coefficients in descending powers of s. "
     "Controllers, filters, plants, pharmacokinetics. Default: under-damped 2nd order (ζ = 0.4).",
  sim=True, schema={"num": {"kind": "text", "doc": "e.g. 2, 1  →  2s + 1"}, "den": {"kind": "text"},
                    "max_substep": {"kind": "number", "min": 1e-5, "max": 1, "step": 0.001}})

# ---------------------------------------------------------------------------- Lookup table
T("lookup", "Universal", "Lookup Table", ["x"], ["y"],
  {"table": "0, 0\n1, 0.8\n2, 1.5\n4, 2\n8, 2.2", "mode": "linear", "x": 0.0}, """
    def process(x=None, params=None):
        xs, ys = ks.parse_table(params["table"])
        return {"y": ks.broadcast(lambda v: ks.interp(xs, ys, v, params["mode"]), ks.pick(x, params["x"]))}
""", "Empirical relationship from data: piecewise-linear, step or nearest interpolation (clamped at the ends).",
  schema={"table": dict(CODE, doc="x, y per line"), "mode": {"kind": "select", "options": ["linear", "step", "nearest"]}})

# ---------------------------------------------------------------------------- Script
T("script", "Universal", "Python Script", ["a", "b"], ["y"], {"inputs": "a, b", "outputs": "y", "k": 1.0}, """
    def process(params, state, t=0.0, dt=0.01, step=0, **inputs):
        # inputs  : dict of the values arriving on this node's input ports (missing = unconnected)
        # params  : this node's parameters (edit them in the Properties panel, add your own)
        # state   : dict that persists across simulation steps
        # return  : a dict with one entry per output port
        a = inputs.get("a") or 0.0
        b = inputs.get("b") or 0.0
        return {"y": params["k"] * (a + b)}
""", "Blank universal node: ports come from the 'inputs'/'outputs' parameters, behaviour from the code (⚙). "
     "Save it as a reusable type with Node Designer.",
  ports={"inputs": ["list:inputs"], "outputs": ["list:outputs"]},
  schema={"inputs": {"kind": "text"}, "outputs": {"kind": "text"}})

# ---------------------------------------------------------------------------- Logic & signals
T("condition", "Logic & Signals", "If / Else", ["x", "a", "b"], ["y", "flag"],
  {"condition": "x > 0.5", "a": 1.0, "b": 0.0, "x": 0.0}, """
    def process(x=None, a=None, b=None, params=None, t=0.0):
        p = params
        env = {"x": ks.pick(x, p["x"]), "t": t}
        flag = bool(ks.eval_expr(p["condition"], env))
        return {"y": ks.pick(a, p["a"]) if flag else ks.pick(b, p["b"]), "flag": flag}
""", "Routes a or b depending on a condition of x (and t).", schema={"condition": {"kind": "text"}})

T("event", "Logic & Signals", "Event Detector", ["x"], ["event", "count", "last_time", "period", "rate"],
  {"threshold": 0.0, "direction": "rising", "hysteresis": 0.0}, """
    def process(x=None, params=None, state=None, t=0.0):
        p = params
        x = ks.pick(x, 0.0)
        prev = state.get("x")
        state["x"] = x
        th, hy = p["threshold"], p["hysteresis"]
        armed = state.get("armed", True)
        ev = False
        if prev is not None:
            up = prev < th <= x and armed
            down = prev > th >= x and armed
            ev = (p["direction"] in ("rising", "both") and up) or (p["direction"] in ("falling", "both") and down)
        if ev:
            state["armed"] = False
            state["times"] = (state.get("times", []) + [t])[-50:]
            state["count"] = state.get("count", 0) + 1
        elif abs(x - th) > hy:
            state["armed"] = True
        times = state.get("times", [])
        period = (times[-1] - times[-2]) if len(times) > 1 else None
        return {"event": int(ev), "count": state.get("count", 0), "last_time": times[-1] if times else None,
                "period": period, "rate": 1 / period if period else 0.0}
""", "Threshold crossings with hysteresis: spike counting, oscillation period & frequency, alarms.",
  sim=True, schema={"direction": {"kind": "select", "options": ["rising", "falling", "both"]}})

T("sample_hold", "Logic & Signals", "Sample & Hold", ["x", "trigger"], ["y"], {"init": 0.0}, """
    def process(x=None, trigger=None, params=None, state=None):
        if trigger:
            state["y"] = x
        return {"y": state.get("y", params["init"])}
""", "Holds x whenever trigger is truthy (use with Event Detector or Pulse).", sim=True)

T("mux", "Logic & Signals", "Selector", ["inputs", "index"], ["y", "n"], {"index": 0}, """
    def process(inputs=None, index=None, params=None):
        xs = ks.as_list(inputs)
        i = int(ks.pick(index, params["index"]))
        return {"y": xs[max(0, min(len(xs) - 1, i))] if xs else None, "n": len(xs)}
""", "Picks one of several fan-in wires by index (wires arrive in connection order).")

T("accumulator", "Logic & Signals", "Accumulator", ["x", "reset"], ["total", "mean", "n"], {}, """
    def process(x=None, reset=None, state=None):
        if reset:
            state.clear()
        if x is not None:
            state["s"] = state.get("s", 0.0) + x
            state["n"] = state.get("n", 0) + 1
        n = state.get("n", 0)
        return {"total": state.get("s", 0.0), "mean": state.get("s", 0.0) / n if n else None, "n": n}
""", "Running sum / mean over simulation steps (e.g. cost, energy, cumulative cases).", sim=True)

# ---------------------------------------------------------------------------- Structure
T("graph_in", "Structure", "Group Input", [], ["value"], {"name": "in", "default": 0.0}, """
    def process(params, ctx):
        return {"value": ctx.inp(params["name"], params["default"])}
""", "Inside a group: receives the group's input port called 'name' (or 'default' when run on its own).")

T("graph_out", "Structure", "Group Output", ["value"], ["value"], {"name": "out"}, """
    def process(value=None, params=None, ctx=None):
        ctx.out(params["name"], value)
        return {"value": value}
""", "Inside a group: publishes 'value' as the group's output port called 'name'.")

T("send", "Structure", "Send", ["value"], [], {"channel": "signal"}, """
    def process(value=None, params=None):
        return {"value": value}
""", "Wireless link (Node-RED link-out / Houdini Object Merge): broadcasts 'value' on a named channel to every "
     "Receive node with the same channel — no wire needed. Keeps large models tidy.",
  schema={"channel": {"kind": "text", "doc": "channel name shared with Receive nodes"}})

T("receive", "Structure", "Receive", [], ["value"], {"channel": "signal", "default": 0.0}, """
    def process(params=None, **inputs):
        v = inputs.get("_wireless")
        return {"value": params["default"] if v is None else v}
""", "Wireless link: outputs whatever a Send node with the same channel transmits (a list if several Send).",
  schema={"channel": {"kind": "text"}})

T("globals", "Structure", "Globals", [], [], {"g": 9.81, "scale": "=g * 2"}, """
    def process():
        return {}
""", "Model-wide variables (Houdini ch() / Simulink model workspace). Any parameter of any node written as "
     "'=expression' is evaluated against these, e.g. '=scale/2' or '=P(\"Room\", \"C\")'. Sweeping a global "
     "changes every parameter that refers to it. Add variables with + new param.")

T("reroute", "Structure", "Reroute", ["in"], ["out"], {}, """
    def process(**inputs):
        # 'in' is a Python keyword, so the value arrives through **inputs
        return {"out": inputs.get("in")}
""", "Wire dot (Blender / Unreal / Nuke reroute): passes its input through unchanged. Double-click a wire or use "
     "its context menu to insert one, then drag it to route wires around other nodes.")

T("note", "Structure", "Note", [], [], {"text": "Describe this part of the model…"}, """
    def process():
        return {}
""", "Documentation node: no ports, never affects results.")


# ============================================================================ port derivation

def _names(text):
    """Port rule 'list:': comma/newline separated names."""
    return [n.strip() for n in str(text or "").replace("\n", ",").split(",") if n.strip()]


def _lhs(text):
    """Port rule 'lhs:': left-hand sides of 'name = expression' lines, in order, without duplicates."""
    out = []
    for line in str(text or "").replace(";", "\n").splitlines():
        m = re.match(r"^\s*([A-Za-z_]\w*)\s*=(?!=)", line.split("#", 1)[0])
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _species(text):
    """Port rule 'species:': every species appearing in 'A + B -> C, k' reaction lines."""
    out = []
    for line in str(text or "").splitlines():
        line = line.split("#", 1)[0]
        if "->" not in line:
            continue
        eq = line.split(",", 1)[0]
        for side in eq.split("->"):
            for tok in side.split("+"):
                m = re.match(r"^\s*\d*\s*([A-Za-z_]\w*)\s*$", tok)
                if m and m.group(1) not in out:
                    out.append(m.group(1))
    return out


def _smout(text):
    """Port rule 'smout:': output names assigned in state-machine lines 'state: name = expression'."""
    out = []
    for line in str(text or "").splitlines():
        m = re.match(r"^\s*(\*|[A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*=(?!=)", line.split("#", 1)[0])
        if m and m.group(2) not in out:
            out.append(m.group(2))
    return out


def derive_ports(tpl, params):
    """Evaluate a template's port rules against parameter values → (inputs, outputs)."""
    rules = tpl.get("ports")
    if not rules:
        return list(tpl["inputs"]), list(tpl["outputs"])
    res = []
    for side in ("inputs", "outputs"):
        names = []
        for tok in rules.get(side, []):
            kind, _, arg = tok.partition(":")
            if kind == "list":
                new = _names(params.get(arg))
            elif kind == "lhs":
                new = _lhs(params.get(arg))
            elif kind == "species":
                new = _species(params.get(arg))
            elif kind == "smout":
                new = _smout(params.get(arg))
            elif kind == "const":
                new = [x for x in arg.split(",") if x]
            elif kind == "suffix":
                p, _, sfx = arg.partition(":")
                new = [n + sfx for n in _names(params.get(p))]
            else:
                new = []
            names += [n for n in new if n not in names]
        res.append(names)
    return res[0], res[1]

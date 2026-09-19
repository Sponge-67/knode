"""
knode_library — curated node templates.

Every template is plain data: ports, default parameters and a Python ``process``
function. The same code runs in the editor, in the CLI and in the tests.

Conventions (see README "Writing nodes"):
  * input ports map to function arguments by name; an unconnected input is None,
    so templates fall back to the parameter of the same name via ks.pick().
  * reserved argument names are injected on request:
        params  – this node's parameter dict (editable in the Properties panel)
        state   – dict persisting across simulation steps (reset per run)
        t, dt, step – simulation clock
        ctx     – run context (ctx.log(...), ctx.stop())
  * stateful dynamical nodes follow "output, then advance": the value emitted at
    step k is the state at t_k. They therefore have no direct feed-through and
    can safely close feedback loops (like integrator blocks in Simulink).
"""
from __future__ import annotations

import copy
import textwrap

CATEGORY_COLORS = {
    "Sources": "#4ecdc4",
    "Math": "#a29bfe",
    "Dynamics & Control": "#ff9f43",
    "Engineering & Physics": "#54a0ff",
    "Biology & Chemistry": "#1dd1a1",
    "Complex Systems": "#ff6b6b",
    "Statistics & Data": "#feca57",
    "Optimisation": "#ee5a24",
    "Design": "#ff9ff3",
    "Text & Code": "#c8d6e5",
}

TEMPLATES = []


def T(id, category, name, inputs, outputs, params, code, description, sim=False, refs=None):
    """Register a template: ports, default params, node code (dedented), description, and whether it is
    stateful (evolves over simulation steps). Optional: dynamic port rules, parameter widget schema, references.
    """
    TEMPLATES.append({
        "id": id, "category": category, "name": name,
        "inputs": inputs, "outputs": outputs, "params": params,
        "code": textwrap.dedent(code).strip() + "\n",
        "description": description, "stateful": sim,
        "refs": refs or [], "color": CATEGORY_COLORS[category],
    })


# ============================================================================
# SOURCES
# ============================================================================
T("const", "Sources", "Constant", [], ["value"], {"value": 1.0}, """
    def process(params):
        return {"value": params["value"]}
""", "Emits a constant (number, string, list or JSON object).")

T("clock", "Sources", "Clock", [], ["t", "step"], {}, """
    def process(t, step):
        return {"t": t, "step": step}
""", "Simulation time t and step index.", sim=True)

T("sine", "Sources", "Sine Wave", ["time"], ["y"],
  {"amplitude": 1.0, "frequency": 1.0, "phase": 0.0, "offset": 0.0}, """
    def process(time=None, params=None, t=0.0):
        tt = ks.pick(time, t)
        p = params
        f = lambda s: p["offset"] + p["amplitude"] * math.sin(2 * math.pi * p["frequency"] * s + p["phase"])
        return {"y": ks.broadcast(f, tt)}
""", "y = offset + A·sin(2πft + φ). Uses the simulation clock when time is unconnected; accepts a list (e.g. from Linspace).")

T("step_signal", "Sources", "Step", [], ["y"], {"t_step": 1.0, "before": 0.0, "after": 1.0}, """
    def process(t, params):
        return {"y": params["after"] if t >= params["t_step"] else params["before"]}
""", "Heaviside step at t_step. Useful for interventions (e.g. lockdowns, set-point changes).", sim=True)

T("pulse", "Sources", "Pulse Train", [], ["y"], {"period": 1.0, "width": 0.1, "amplitude": 1.0, "delay": 0.0}, """
    def process(t, params):
        p = params
        if t < p["delay"]:
            return {"y": 0.0}
        phase = (t - p["delay"]) % p["period"]
        return {"y": p["amplitude"] if phase < p["width"] else 0.0}
""", "Rectangular pulse train (e.g. periodic stimulus current).", sim=True)

T("noise", "Sources", "Gaussian Noise", [], ["y"], {"mean": 0.0, "sigma": 1.0, "seed": 42}, """
    def process(params, state):
        if "rng" not in state:
            state["rng"] = random.Random(params["seed"])
        return {"y": state["rng"].gauss(params["mean"], params["sigma"])}
""", "Seeded i.i.d. normal samples — reproducible across runs.", sim=True)

T("linspace", "Sources", "Linspace", [], ["x"], {"start": 0.0, "stop": 1.0, "n": 50}, """
    def process(params):
        return {"x": ks.linspace(params["start"], params["stop"], params["n"])}
""", "n evenly spaced samples in [start, stop].")

T("text", "Sources", "Text", [], ["text"], {"text": "ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG"}, """
    def process(params):
        return {"text": params["text"]}
""", "Emits a text string.")

T("csv_parse", "Sources", "CSV Parse", ["text"], ["table", "columns", "rows"],
  {"delimiter": ",", "header": True, "text": "x,y\n1,2.1\n2,3.9\n3,6.2\n4,8.1"}, """
    import csv, io
    def process(text=None, params=None):
        src = ks.pick(text, params["text"])
        rows = list(csv.reader(io.StringIO(src), delimiter=params["delimiter"]))
        rows = [r for r in rows if r]
        if params["header"]:
            names, body = rows[0], rows[1:]
        else:
            names, body = [f"c{i}" for i in range(len(rows[0]))], rows
        def conv(v):
            try:
                return float(v)
            except ValueError:
                return v
        table = {n: [conv(r[i]) for r in body if i < len(r)] for i, n in enumerate(names)}
        return {"table": table, "columns": names, "rows": len(body)}
""", "Parses CSV text into a column dict (numbers auto-converted).")

T("column", "Sources", "Pick Column", ["table"], ["values"], {"name": "y"}, """
    def process(table=None, params=None):
        return {"values": (table or {}).get(params["name"], [])}
""", "Extracts one column from a table dict.")

# ============================================================================
# MATH
# ============================================================================
T("expr", "Math", "Expression", ["a", "b", "c", "x"], ["y"], {"expr": "a*x + b"}, """
    def process(a=None, b=None, c=None, x=None, params=None, t=0.0):
        code = ks.compile_expr(params["expr"])
        f = lambda a, b, c, x: ks.eval_expr(code, {"a": a, "b": b, "c": c, "x": x, "t": t})
        vals = [ks.pick(v, 0.0) for v in (a, b, c, x)]
        return {"y": ks.broadcast(f, *vals)}
""", "Arbitrary math expression of a, b, c, x, t (all of math.* available). Lists broadcast elementwise.")

T("add", "Math", "Add", ["a", "b"], ["y"], {}, """
    def process(a=0.0, b=0.0):
        return {"y": ks.broadcast(lambda p, q: p + q, ks.pick(a, 0.0), ks.pick(b, 0.0))}
""", "a + b (elementwise on lists). Fan-in wires into one port arrive as a list.")

T("multiply", "Math", "Multiply", ["a", "b"], ["y"], {}, """
    def process(a=1.0, b=1.0):
        return {"y": ks.broadcast(lambda p, q: p * q, ks.pick(a, 1.0), ks.pick(b, 1.0))}
""", "a · b (elementwise on lists).")

T("gain", "Math", "Gain", ["x"], ["y"], {"k": 2.0}, """
    def process(x=None, params=None):
        return {"y": ks.broadcast(lambda v: params["k"] * v, ks.pick(x, 0.0))}
""", "y = k·x")

T("clamp", "Math", "Clamp", ["x"], ["y"], {"lo": 0.0, "hi": 1.0}, """
    def process(x=None, params=None):
        return {"y": ks.broadcast(lambda v: min(params["hi"], max(params["lo"], v)), ks.pick(x, 0.0))}
""", "Saturation / limiter.")

T("sum_list", "Math", "Reduce", ["values"], ["sum", "product", "count"], {}, """
    def process(values=None):
        xs = ks.as_list(values)
        prod = 1.0
        for v in xs:
            prod *= v
        return {"sum": sum(xs), "product": prod, "count": len(xs)}
""", "Sum / product / count of a list (or of fan-in wires).")

# ============================================================================
# DYNAMICS & CONTROL
# ============================================================================
T("integrator", "Dynamics & Control", "Integrator", ["u"], ["y"], {"y0": 0.0}, """
    def process(u=None, params=None, state=None, dt=0.01):
        if "y" not in state:
            state["y"], state["u_prev"] = params["y0"], None
        y = state["y"]
        u = ks.pick(u, 0.0)
        up = u if state["u_prev"] is None else state["u_prev"]
        state["y"] = y + 0.5 * (u + up) * dt      # trapezoidal rule
        state["u_prev"] = u
        return {"y": y}
""", "y(t) = y0 + ∫u dt (trapezoidal). No feed-through → safe inside feedback loops.", sim=True)

T("derivative", "Dynamics & Control", "Derivative", ["x"], ["dx"], {}, """
    def process(x=None, state=None, dt=0.01):
        x = ks.pick(x, 0.0)
        prev = state.get("x", x)
        state["x"] = x
        return {"dx": (x - prev) / dt}
""", "Backward-difference derivative dx/dt.", sim=True)

T("delay", "Dynamics & Control", "Unit Delay z⁻¹", ["x"], ["y"], {"init": 0.0}, """
    def process(x=None, params=None, state=None):
        y = state.get("x", params["init"])
        state["x"] = x
        return {"y": y}
""", "Outputs last step's input. Explicitly breaks algebraic loops.", sim=True)

T("lowpass", "Dynamics & Control", "Low-pass Filter", ["x"], ["y"], {"tau": 0.5}, """
    def process(x=None, params=None, state=None, dt=0.01):
        x = ks.pick(x, 0.0)
        y = state.get("y", x)
        a = 1.0 - math.exp(-dt / params["tau"])     # exact ZOH discretisation
        state["y"] = y + a * (x - y)
        return {"y": state["y"]}
""", "First-order low-pass, τ·dy/dt = x − y (exact zero-order-hold discretisation).", sim=True)

T("pid", "Dynamics & Control", "PID Controller", ["setpoint", "measurement"], ["u", "error"],
  {"kp": 2.0, "ki": 1.0, "kd": 0.5, "u_min": -100.0, "u_max": 100.0, "setpoint": 1.0}, """
    def process(setpoint=None, measurement=None, params=None, state=None, dt=0.01):
        p = params
        r = ks.pick(setpoint, p["setpoint"])
        y = ks.pick(measurement, 0.0)
        e = r - y
        integ = state.get("i", 0.0)
        dmeas = (y - state.get("y", y)) / dt          # derivative on measurement: no set-point kick
        state["y"] = y
        u_unsat = p["kp"] * e + p["ki"] * integ - p["kd"] * dmeas
        u = min(p["u_max"], max(p["u_min"], u_unsat))
        if u == u_unsat or (u_unsat > u and e < 0) or (u_unsat < u and e > 0):
            state["i"] = integ + e * dt                # conditional integration anti-windup
        return {"u": u, "error": e}
""", "Parallel PID with derivative-on-measurement, output saturation and conditional-integration anti-windup.", sim=True)

T("mass_spring_damper", "Dynamics & Control", "Mass–Spring–Damper", ["F"], ["x", "v"],
  {"m": 1.0, "c": 0.5, "k": 4.0, "x0": 0.0, "v0": 0.0}, """
    def process(F=None, params=None, state=None, t=0.0, dt=0.01):
        p = params
        if "s" not in state:
            state["s"] = [p["x0"], p["v0"]]
        x, v = state["s"]
        force = ks.pick(F, 0.0)
        f = lambda _t, s: [s[1], (force - p["c"] * s[1] - p["k"] * s[0]) / p["m"]]
        omega = math.sqrt(p["k"] / p["m"])
        state["s"] = ks.rk4_advance(f, t, state["s"], dt, 0.05 / omega)
        return {"x": x, "v": v}
""", "m·x'' + c·x' + k·x = F, integrated with RK4 (substeps ≤ 0.05/ω₀). Natural frequency ω₀ = √(k/m).", sim=True)

T("rc_circuit", "Dynamics & Control", "RC Circuit", ["V_in"], ["V_c", "I"], {"R": 1000.0, "C": 1e-3, "V0": 0.0, "V_in": 5.0}, """
    def process(V_in=None, params=None, state=None, dt=0.01):
        p = params
        vin = ks.pick(V_in, p["V_in"])
        vc = state.get("vc", p["V0"])
        i = (vin - vc) / p["R"]
        state["vc"] = vin + (vc - vin) * math.exp(-dt / (p["R"] * p["C"]))   # exact for piecewise-constant input
        return {"V_c": vc, "I": i}
""", "Series RC charging; time constant τ = RC. Exact exponential update.", sim=True)

# ============================================================================
# ENGINEERING & PHYSICS
# ============================================================================
T("rect_section", "Engineering & Physics", "Rectangular Section", ["b", "h"], ["A", "I", "Z", "c"],
  {"b": 0.05, "h": 0.1}, """
    def process(b=None, h=None, params=None):
        b, h = ks.pick(b, params["b"]), ks.pick(h, params["h"])
        I = b * h ** 3 / 12
        return {"A": b * h, "I": I, "Z": I / (h / 2), "c": h / 2}
""", "Area, second moment I = bh³/12, section modulus Z and extreme-fibre distance (SI units).")

T("cantilever", "Engineering & Physics", "Cantilever Beam", ["F", "L", "I", "c"],
  ["deflection", "stress", "safety_factor"],
  {"F": 1000.0, "L": 2.0, "E": 200e9, "I": 4.17e-6, "c": 0.05, "yield_strength": 250e6}, """
    def process(F=None, L=None, I=None, c=None, params=None):
        p = params
        F, L = ks.pick(F, p["F"]), ks.pick(L, p["L"])
        I, c = ks.pick(I, p["I"]), ks.pick(c, p["c"])
        delta = F * L ** 3 / (3 * p["E"] * I)
        sigma = F * L * c / I
        return {"deflection": delta, "stress": sigma, "safety_factor": p["yield_strength"] / sigma if sigma else float("inf")}
""", "End-loaded cantilever (Euler–Bernoulli): δ = FL³/3EI, σ_max = FLc/I. Defaults: structural steel.")

T("ohms_law", "Engineering & Physics", "Ohm's Law", ["V", "R"], ["I", "P"], {"V": 12.0, "R": 100.0}, """
    def process(V=None, R=None, params=None):
        V, R = ks.pick(V, params["V"]), ks.pick(R, params["R"])
        return {"I": V / R, "P": V * V / R}
""", "I = V/R, P = V²/R")

T("projectile", "Engineering & Physics", "Projectile", ["v0", "angle_deg"], ["range", "max_height", "flight_time"],
  {"v0": 20.0, "angle_deg": 45.0, "g": 9.81, "h0": 0.0}, """
    def process(v0=None, angle_deg=None, params=None):
        p = params
        v, th = ks.pick(v0, p["v0"]), math.radians(ks.pick(angle_deg, p["angle_deg"]))
        vx, vy, g, h0 = v * math.cos(th), v * math.sin(th), p["g"], p["h0"]
        T = (vy + math.sqrt(vy * vy + 2 * g * h0)) / g
        return {"range": vx * T, "max_height": h0 + vy * vy / (2 * g), "flight_time": T}
""", "Drag-free ballistic flight from launch height h0.")

T("heat1d", "Engineering & Physics", "1-D Heat Conduction", ["T_left", "T_right"], ["profile", "T_mid", "x"],
  {"n": 41, "length": 1.0, "alpha": 1e-2, "T0": 20.0, "T_left": 100.0, "T_right": 20.0}, """
    def process(T_left=None, T_right=None, params=None, state=None, dt=0.01):
        p = params
        n = int(p["n"]); dx = p["length"] / (n - 1)
        if "T" not in state:
            state["T"] = [p["T0"]] * n
        T = state["T"]
        T[0], T[-1] = ks.pick(T_left, p["T_left"]), ks.pick(T_right, p["T_right"])
        out = {"profile": list(T), "T_mid": T[n // 2], "x": ks.linspace(0, p["length"], n)}
        # explicit FTCS, sub-stepped to satisfy the stability bound r = αΔt/Δx² ≤ 1/2
        h_max = 0.4 * dx * dx / p["alpha"]
        m = max(1, math.ceil(dt / h_max)); h = dt / m; r = p["alpha"] * h / (dx * dx)
        for _ in range(m):
            T = [T[0]] + [T[i] + r * (T[i+1] - 2*T[i] + T[i-1]) for i in range(1, n - 1)] + [T[-1]]
        state["T"] = T
        return out
""", "∂T/∂t = α ∂²T/∂x², Dirichlet ends, FTCS with automatic sub-stepping for stability (r ≤ 0.4).", sim=True)

# ============================================================================
# BIOLOGY & CHEMISTRY
# ============================================================================
T("logistic_growth", "Biology & Chemistry", "Logistic Growth", [], ["N"], {"r": 0.5, "K": 100.0, "N0": 5.0}, """
    def process(params, state, dt=0.01):
        p = params
        N = state.get("N", p["N0"])
        state["N"] = p["K"] / (1 + (p["K"] - N) / N * math.exp(-p["r"] * dt))   # exact solution step
        return {"N": N}
""", "dN/dt = rN(1 − N/K), advanced with the closed-form solution (no discretisation error).", sim=True)

T("lotka_volterra", "Biology & Chemistry", "Lotka–Volterra", [], ["prey", "predator", "invariant"],
  {"alpha": 1.1, "beta": 0.4, "delta": 0.1, "gamma": 0.4, "x0": 10.0, "y0": 10.0}, """
    def process(params, state, t=0.0, dt=0.01):
        a, b, d, g = params["alpha"], params["beta"], params["delta"], params["gamma"]
        s = state.setdefault("s", [params["x0"], params["y0"]])
        x, y = s
        V = d * x - g * math.log(x) + b * y - a * math.log(y)   # conserved quantity: drift = numerical error
        f = lambda _t, u: [a*u[0] - b*u[0]*u[1], d*u[0]*u[1] - g*u[1]]
        state["s"] = ks.rk4_advance(f, t, s, dt, 0.01)
        return {"prey": x, "predator": y, "invariant": V}
""", "Predator–prey ODEs (RK4). 'invariant' is the first integral V; its drift measures integration error.", sim=True,
  refs=["Lotka 1925; Volterra 1926"])

T("sir", "Biology & Chemistry", "SIR Epidemic", ["beta"], ["S", "I", "R", "R_eff"],
  {"beta": 0.3, "gamma": 0.1, "N": 1000.0, "I0": 1.0}, """
    def process(beta=None, params=None, state=None, t=0.0, dt=0.1):
        p = params
        b, g, N = ks.pick(beta, p["beta"]), p["gamma"], p["N"]
        s = state.setdefault("s", [N - p["I0"], p["I0"], 0.0])
        S, I, R = s
        f = lambda _t, u: [-b*u[0]*u[1]/N, b*u[0]*u[1]/N - g*u[1], g*u[1]]
        state["s"] = ks.rk4_advance(f, t, s, dt, 0.1)
        return {"S": S, "I": I, "R": R, "R_eff": b / g * S / N}
""", "Kermack–McKendrick SIR (RK4). S+I+R = N is conserved. Wire a Step into 'beta' to model interventions. R₀ = β/γ.",
  sim=True, refs=["Kermack & McKendrick 1927"])

T("seir", "Biology & Chemistry", "SEIR Epidemic", ["beta"], ["S", "E", "I", "R"],
  {"beta": 0.5, "sigma": 0.2, "gamma": 0.1, "N": 1e6, "I0": 10.0}, """
    def process(beta=None, params=None, state=None, t=0.0, dt=0.1):
        p = params
        b, sg, g, N = ks.pick(beta, p["beta"]), p["sigma"], p["gamma"], p["N"]
        s = state.setdefault("s", [N - p["I0"], 0.0, p["I0"], 0.0])
        out = dict(zip(["S", "E", "I", "R"], s))
        f = lambda _t, u: [-b*u[0]*u[2]/N, b*u[0]*u[2]/N - sg*u[1], sg*u[1] - g*u[2], g*u[2]]
        state["s"] = ks.rk4_advance(f, t, s, dt, 0.1)
        return out
""", "SEIR with latent period 1/σ (RK4).", sim=True)

T("michaelis_menten", "Biology & Chemistry", "Michaelis–Menten", ["S"], ["v"], {"Vmax": 1.0, "Km": 0.5, "S": 1.0}, """
    def process(S=None, params=None):
        return {"v": ks.broadcast(lambda s: params["Vmax"] * s / (params["Km"] + s), ks.pick(S, params["S"]))}
""", "Enzyme kinetics v = Vmax·S/(Km + S). Accepts a list of substrate concentrations.")

T("hill", "Biology & Chemistry", "Hill Function", ["x"], ["activation", "repression"], {"K": 1.0, "n": 2.0, "ymax": 1.0, "x": 1.0}, """
    def process(x=None, params=None):
        K, n, ym = params["K"], params["n"], params["ymax"]
        xv = ks.pick(x, params["x"])
        act = ks.broadcast(lambda v: ym * v**n / (K**n + v**n), xv)
        rep = ks.broadcast(lambda v: ym * K**n / (K**n + v**n), xv)
        return {"activation": act, "repression": rep}
""", "Cooperative binding / gene regulation input functions with Hill coefficient n.")

T("toggle_switch", "Biology & Chemistry", "Genetic Toggle Switch", ["inducer_u", "inducer_v"], ["u", "v"],
  {"alpha1": 156.25, "alpha2": 15.6, "beta": 2.5, "gamma": 1.0, "u0": 0.1, "v0": 10.0}, """
    def process(inducer_u=None, inducer_v=None, params=None, state=None, t=0.0, dt=0.05):
        p = params
        iu, iv = ks.pick(inducer_u, 0.0), ks.pick(inducer_v, 0.0)
        s = state.setdefault("s", [p["u0"], p["v0"]])
        u, v = s
        # an inducer transiently knocks down the opposing repressor (pulse it to flip the switch)
        f = lambda _t, z: [p["alpha1"] / (1 + (z[1] * (1 - min(1, iv)))**p["beta"]) - z[0],
                           p["alpha2"] / (1 + (z[0] * (1 - min(1, iu)))**p["gamma"]) - z[1]]
        state["s"] = ks.rk4_advance(f, t, s, dt, 0.01)
        return {"u": u, "v": v}
""", "Bistable mutual-repression circuit (Gardner, Cantor & Collins 2000). Pulse an inducer to flip states.", sim=True,
  refs=["Gardner et al., Nature 403:339 (2000)"])

T("hodgkin_huxley", "Biology & Chemistry", "Hodgkin–Huxley Neuron", ["I_ext"], ["V", "m", "h", "n"],
  {"I_ext": 10.0, "C_m": 1.0, "g_Na": 120.0, "g_K": 36.0, "g_L": 0.3, "E_Na": 50.0, "E_K": -77.0, "E_L": -54.387}, """
    def _ratio(x, y):                     # x / (1 - exp(-x/y)) with its limit y at x = 0
        return y if abs(x) < 1e-7 else x / (1 - math.exp(-x / y))

    def rates(V):
        am = 0.1 * _ratio(V + 40, 10);  bm = 4 * math.exp(-(V + 65) / 18)
        ah = 0.07 * math.exp(-(V + 65) / 20); bh = 1 / (1 + math.exp(-(V + 35) / 10))
        an = 0.01 * _ratio(V + 55, 10); bn = 0.125 * math.exp(-(V + 65) / 80)
        return am, bm, ah, bh, an, bn

    def process(I_ext=None, params=None, state=None, t=0.0, dt=0.05):
        p = params
        I = ks.pick(I_ext, p["I_ext"])
        if "s" not in state:
            V0 = -65.0; am, bm, ah, bh, an, bn = rates(V0)
            state["s"] = [V0, am/(am+bm), ah/(ah+bh), an/(an+bn)]   # resting steady state
        s = state["s"]
        def f(_t, z):
            V, m, h, n = z
            am, bm, ah, bh, an, bn = rates(V)
            I_ion = p["g_Na"]*m**3*h*(V - p["E_Na"]) + p["g_K"]*n**4*(V - p["E_K"]) + p["g_L"]*(V - p["E_L"])
            return [(I - I_ion) / p["C_m"], am*(1-m) - bm*m, ah*(1-h) - bh*h, an*(1-n) - bn*n]
        state["s"] = ks.rk4_advance(f, t, s, dt, 0.01)
        return dict(zip(["V", "m", "h", "n"], s))
""", "Squid giant-axon model (units: mV, ms, µA/cm²). Use dt in ms, e.g. 0.05. Spikes for I_ext ≳ 6.3.",
  sim=True, refs=["Hodgkin & Huxley, J Physiol 117:500 (1952)"])

T("wright_fisher", "Biology & Chemistry", "Wright–Fisher Drift", [], ["p", "fixed"], {"N": 100, "p0": 0.5, "s": 0.0, "seed": 1}, """
    def process(params, state):
        if "p" not in state:
            state["p"], state["rng"] = params["p0"], random.Random(params["seed"])
        p = state["p"]
        s = params["s"]
        p_sel = p * (1 + s) / (1 + s * p)                  # haploid selection, then drift
        state["p"] = ks.binomial(state["rng"], params["N"], p_sel) / params["N"]
        return {"p": p, "fixed": p in (0.0, 1.0)}
""", "Allele frequency under genetic drift (+ optional selection coefficient s) in a population of N. One step = one generation.", sim=True)

T("dna_tools", "Biology & Chemistry", "DNA Tools", ["seq"], ["length", "gc", "revcomp", "protein", "orfs"], {"frame": 0}, """
    BASES = "TCAG"
    AA = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
    CODON = {a + b + c: AA[16*i + 4*j + k] for i, a in enumerate(BASES) for j, b in enumerate(BASES) for k, c in enumerate(BASES)}

    def translate(s):
        return "".join(CODON.get(s[i:i+3], "X") for i in range(0, len(s) - 2, 3))

    def process(seq=None, params=None):
        s = "".join(ch for ch in str(seq or "").upper() if ch.isalpha()).replace("U", "T")
        gc = (s.count("G") + s.count("C")) / len(s) if s else 0.0
        rc = s[::-1].translate(str.maketrans("ACGTN", "TGCAN"))
        prot = translate(s[int(params["frame"]):])
        orfs = []
        for strand in (s, rc):
            for f in range(3):
                aa = translate(strand[f:])
                for chunk in aa.split("*"):
                    i = chunk.find("M")
                    if i >= 0 and len(chunk) - i >= 10:
                        orfs.append(chunk[i:])
        return {"length": len(s), "gc": gc, "revcomp": rc, "protein": prot, "orfs": sorted(orfs, key=len, reverse=True)[:5]}
""", "GC content, reverse complement, translation (standard code) and ORFs ≥ 10 aa on both strands.")

T("arrhenius", "Biology & Chemistry", "Arrhenius Rate", ["T"], ["k"], {"A": 1e13, "Ea": 75000.0, "T": 298.15}, """
    def process(T=None, params=None):
        R = 8.314462618
        return {"k": ks.broadcast(lambda TT: params["A"] * math.exp(-params["Ea"] / (R * TT)), ks.pick(T, params["T"]))}
""", "k = A·exp(−Ea/RT); Ea in J/mol, T in K.")

# ============================================================================
# COMPLEX SYSTEMS
# ============================================================================
T("logistic_map", "Complex Systems", "Logistic Map", ["r"], ["x", "lyapunov"], {"r": 3.9, "x0": 0.2}, """
    def process(r=None, params=None, state=None, step=0):
        r = ks.pick(r, params["r"])
        x = state.get("x", params["x0"])
        state["x"] = r * x * (1 - x)
        d = abs(r * (1 - 2 * x))
        state["lsum"] = state.get("lsum", 0.0) + (math.log(d) if d > 0 else -30.0)
        return {"x": x, "lyapunov": state["lsum"] / (step + 1)}
""", "x ← r·x(1−x). Running Lyapunov exponent estimate: λ > 0 ⇒ chaos (onset near r ≈ 3.5699).", sim=True)

T("lorenz", "Complex Systems", "Lorenz System", [], ["x", "y", "z"],
  {"sigma": 10.0, "rho": 28.0, "beta": 2.6666667, "x0": 1.0, "y0": 1.0, "z0": 1.0}, """
    def process(params, state, t=0.0, dt=0.01):
        p = params
        s = state.setdefault("s", [p["x0"], p["y0"], p["z0"]])
        f = lambda _t, u: [p["sigma"]*(u[1]-u[0]), u[0]*(p["rho"]-u[2]) - u[1], u[0]*u[1] - p["beta"]*u[2]]
        state["s"] = ks.rk4_advance(f, t, s, dt, 0.005)
        return dict(zip("xyz", s))
""", "Deterministic chaos (RK4, substeps ≤ 5 ms). Plot x vs z for the butterfly attractor.", sim=True,
  refs=["Lorenz, J Atmos Sci 20:130 (1963)"])

T("kuramoto", "Complex Systems", "Kuramoto Oscillators", ["K"], ["r", "psi"],
  {"N": 100, "K": 2.5, "omega_sigma": 1.0, "seed": 7}, """
    def process(K=None, params=None, state=None, t=0.0, dt=0.05):
        p = params
        N = int(p["N"]); Kc = ks.pick(K, p["K"])
        if "th" not in state:
            rng = random.Random(p["seed"])
            w = [rng.gauss(0, p["omega_sigma"]) for _ in range(N)]
            th = [rng.uniform(0, 2*math.pi) for _ in range(N)]
            if ks.HAS_NUMPY:                                  # vectorised: O(N) numpy ops per RK4 stage
                w, th = ks._np.array(w), ks._np.array(th)
            state["w"], state["th"] = w, th
        w, th = state["w"], state["th"]
        if ks.HAS_NUMPY:
            xp = ks._np
            def f(_t, th):
                # mean field: r·e^{iψ} = mean(e^{iθ}) = c + i·s, and K·r·sin(ψ − θ) = K·(s·cos θ − c·sin θ)
                cs, sn = xp.cos(th), xp.sin(th)
                return w + Kc * (sn.mean() * cs - cs.mean() * sn)
            c, s_ = float(xp.cos(th).mean()), float(xp.sin(th).mean())
        else:
            def f(_t, th):
                c = sum(math.cos(a) for a in th) / N; s_ = sum(math.sin(a) for a in th) / N
                return [w[i] + Kc * (s_ * math.cos(th[i]) - c * math.sin(th[i])) for i in range(N)]
            c, s_ = sum(math.cos(a) for a in th) / N, sum(math.sin(a) for a in th) / N
        r, psi = math.hypot(c, s_), math.atan2(s_, c)
        state["th"] = ks.rk4_advance(f, t, th, dt, 0.05)
        return {"r": r, "psi": psi}
""", "Mean-field Kuramoto model. Order parameter r∈[0,1]; for Gaussian ω the critical coupling is K_c = σ·√(8/π) ≈ 1.6σ. Vectorised with numpy when available.",
  sim=True, refs=["Kuramoto 1975; Strogatz, Physica D 143:1 (2000)"])

T("elementary_ca", "Complex Systems", "Elementary Cellular Automaton", [], ["row", "density"],
  {"rule": 110, "width": 101, "init": "single", "seed": 3}, """
    def process(params, state):
        W, rule = int(params["width"]), int(params["rule"])
        if "row" not in state:
            if params["init"] == "random":
                rng = random.Random(params["seed"]); state["row"] = [rng.randint(0, 1) for _ in range(W)]
            else:
                state["row"] = [0] * W; state["row"][W // 2] = 1
        row = state["row"]
        state["row"] = [(rule >> (row[(i-1) % W] << 2 | row[i] << 1 | row[(i+1) % W])) & 1 for i in range(W)]
        return {"row": row, "density": sum(row) / W}
""", "Wolfram elementary CA with periodic boundaries (rule 30: chaos, 110: universal).", sim=True)

T("random_walk", "Complex Systems", "Brownian Motion", [], ["x", "msd_theory"], {"D": 1.0, "x0": 0.0, "seed": 11}, """
    def process(params, state, t=0.0, dt=0.01):
        if "x" not in state:
            state["x"], state["rng"] = params["x0"], random.Random(params["seed"])
        x = state["x"]
        state["x"] = x + math.sqrt(2 * params["D"] * dt) * state["rng"].gauss(0, 1)
        return {"x": x, "msd_theory": 2 * params["D"] * t}
""", "Wiener process with diffusion coefficient D. Theory: ⟨(x−x0)²⟩ = 2Dt — compare using a Monte-Carlo run.", sim=True)

T("ode", "Complex Systems", "ODE Solver (RK45)", [], ["t", "Y"],
  {"equations": "dx = y\ndy = mu*(1 - x**2)*y - x", "variables": "x, y", "initial": "2, 0",
   "constants": "mu=1.5", "t_end": 30.0, "points": 600}, """
    def process(params):
        names = [v.strip() for v in params["variables"].split(",")]
        consts = ks.parse_assignments(params["constants"])
        rhs = {}
        for line in params["equations"].replace(";", "\\n").splitlines():
            if "=" in line:
                lhs, expr = line.split("=", 1)
                rhs[lhs.strip().lstrip("d")] = ks.compile_expr(expr.strip())
        missing = [n for n in names if n not in rhs]
        if missing:
            raise ValueError(f"no equation for: {missing} (write e.g. 'd{missing[0]} = ...')")
        def f(t, y):
            env = dict(consts); env.update(zip(names, y)); env["t"] = t
            return [ks.eval_expr(rhs[n], env) for n in names]
        ts, ys = ks.solve_ivp(f, 0.0, params["t_end"], ks.parse_floats(params["initial"]), n_out=params["points"])
        return {"t": ts, "Y": {n: [row[i] for row in ys] for i, n in enumerate(names)}}
""", "Solve any ODE system you type (adaptive Dormand–Prince). Default: Van der Pol oscillator. Outputs arrays for plotting.")

# ============================================================================
# STATISTICS & DATA
# ============================================================================
T("stats", "Statistics & Data", "Descriptive Stats", ["data"], ["mean", "std", "median", "min", "max", "n", "ci95"], {}, """
    def process(data=None):
        xs = [float(v) for v in ks.as_list(data)]
        n = len(xs); m = ks.mean(xs); sd = ks.std(xs)
        half = 1.96 * sd / math.sqrt(n) if n > 1 else float("nan")
        return {"mean": m, "std": sd, "median": ks.median(xs), "min": min(xs) if xs else None,
                "max": max(xs) if xs else None, "n": n, "ci95": [m - half, m + half]}
""", "Sample statistics (std uses n−1). ci95 is the normal-approximation 95% CI of the mean.")

T("linreg", "Statistics & Data", "Linear Regression", ["x", "y"], ["slope", "intercept", "r2", "stderr_slope", "fit"], {}, """
    def process(x=None, y=None):
        r = ks.linregress(x, y)
        r["fit"] = [r["intercept"] + r["slope"] * v for v in ks.as_list(x)]
        return r
""", "Ordinary least squares with R² and the standard error of the slope.")

T("correlation", "Statistics & Data", "Correlation", ["x", "y"], ["pearson", "spearman"], {}, """
    def process(x=None, y=None):
        return {"pearson": ks.pearson(x, y), "spearman": ks.spearman(x, y)}
""", "Pearson (linear) and Spearman (rank, monotonic) correlation.")

T("histogram", "Statistics & Data", "Histogram", ["data"], ["counts", "centers"], {"bins": 20}, """
    def process(data=None, params=None):
        counts, edges = ks.histogram(ks.as_list(data), int(params["bins"]))
        return {"counts": counts, "centers": [(a + b) / 2 for a, b in zip(edges, edges[1:])]}
""", "Equal-width histogram.")

T("moving_average", "Statistics & Data", "Moving Average", ["data"], ["y"], {"window": 5}, """
    def process(data=None, params=None):
        xs = ks.as_list(data); w = max(1, int(params["window"]))
        out, acc = [], 0.0
        for i, v in enumerate(xs):
            acc += v
            if i >= w: acc -= xs[i - w]
            out.append(acc / min(i + 1, w))
        return {"y": out}
""", "Trailing moving average (O(n)).")

T("fft", "Statistics & Data", "Spectrum (FFT)", ["signal"], ["freqs", "magnitude", "peak_freq"], {"sample_rate": 100.0}, """
    def process(signal=None, params=None):
        fr, mag = ks.rfft_mag(ks.as_list(signal), params["sample_rate"])
        k = max(range(1, len(mag)), key=lambda i: mag[i]) if len(mag) > 1 else 0
        return {"freqs": fr, "magnitude": mag, "peak_freq": fr[k] if fr else None}
""", "One-sided amplitude spectrum and dominant frequency (numpy FFT, DFT fallback).")

T("recorder", "Statistics & Data", "Recorder", ["x"], ["series", "count"], {"max_len": 100000}, """
    def process(x=None, params=None, state=None):
        buf = state.setdefault("buf", [])
        if x is not None:
            buf.append(x)
            if len(buf) > params["max_len"]: del buf[0]
        return {"series": buf, "count": len(buf)}
""", "Accumulates a signal over a simulation into a list (feed it into Stats / FFT / Regression).", sim=True)

# ============================================================================
# OPTIMISATION
# ============================================================================
T("minimize", "Optimisation", "Minimise (Nelder–Mead)", [], ["x_opt", "f_opt", "iterations"],
  {"objective": "(1 - x)**2 + 100*(y - x**2)**2", "variables": "x, y", "x0": "-1.2, 1", "tol": 1e-12}, """
    def process(params):
        names = [v.strip() for v in params["variables"].split(",")]
        code = ks.compile_expr(params["objective"])
        f = lambda v: ks.eval_expr(code, dict(zip(names, v)))
        x, fx, it = ks.nelder_mead(f, ks.parse_floats(params["x0"]), tol=params["tol"], max_iter=5000)
        return {"x_opt": dict(zip(names, x)), "f_opt": fx, "iterations": it}
""", "Derivative-free minimisation of any expression. Default: Rosenbrock function (minimum at (1, 1)).")

T("root", "Optimisation", "Root Finder", [], ["root", "iterations", "residual"],
  {"f": "x**3 - 2*x - 5", "a": 2.0, "b": 3.0}, """
    def process(params):
        code = ks.compile_expr(params["f"])
        f = lambda x: ks.eval_expr(code, {"x": x})
        x, it = ks.bisect(f, params["a"], params["b"])
        return {"root": x, "iterations": it, "residual": f(x)}
""", "Bisection on a sign-changing bracket [a, b]. Default: Wallis' cubic (root ≈ 2.0945515).")

# ============================================================================
# DESIGN
# ============================================================================
T("modular_scale", "Design", "Modular Scale", ["base"], ["sizes"], {"base": 16.0, "ratio": 1.618034, "steps_down": 2, "steps_up": 6}, """
    def process(base=None, params=None):
        b, r = ks.pick(base, params["base"]), params["ratio"]
        return {"sizes": [round(b * r ** k, 3) for k in range(-int(params["steps_down"]), int(params["steps_up"]) + 1)]}
""", "Typographic / spatial scale b·rᵏ (golden ratio by default; try 1.25 major third, 1.5 perfect fifth).")

T("color_harmony", "Design", "Colour Harmony", [], ["palette", "contrast_on_white", "contrast_on_black"],
  {"base": "#667eea", "scheme": "triadic"}, """
    import colorsys
    SCHEMES = {"complementary": [0, 180], "triadic": [0, 120, 240], "analogous": [-30, 0, 30],
               "split": [0, 150, 210], "tetradic": [0, 90, 180, 270], "monochrome": [0, 0, 0, 0]}
    def process(params):
        r, g, b = ks.hex_to_rgb(params["base"])
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        offs = SCHEMES.get(params["scheme"], SCHEMES["triadic"])
        pal = []
        for i, d in enumerate(offs):
            ll = l if params["scheme"] != "monochrome" else min(0.9, max(0.1, 0.25 + 0.2 * i))
            pal.append(ks.rgb_to_hex(colorsys.hls_to_rgb((h + d / 360) % 1, ll, s)))
        return {"palette": pal,
                "contrast_on_white": [round(ks.contrast_ratio(c, "#ffffff"), 2) for c in pal],
                "contrast_on_black": [round(ks.contrast_ratio(c, "#000000"), 2) for c in pal]}
""", "Hue-rotation palettes with WCAG contrast ratios (≥ 4.5 passes AA for body text).")

T("bezier", "Design", "Bézier Curve", [], ["x", "y", "length"], {"points": "0,0; 0.2,1; 0.8,-0.5; 1,1", "samples": 100}, """
    def process(params):
        P = [ks.parse_floats(p) for p in params["points"].split(";") if p.strip()]
        n = len(P) - 1
        def at(t):                       # de Casteljau: numerically stable
            pts = [list(p) for p in P]
            for r in range(1, n + 1):
                pts = [[(1-t)*a[0] + t*b[0], (1-t)*a[1] + t*b[1]] for a, b in zip(pts, pts[1:])]
            return pts[0]
        ts = ks.linspace(0, 1, int(params["samples"]))
        C = [at(t) for t in ts]
        L = sum(math.dist(a, b) for a, b in zip(C, C[1:]))
        return {"x": [c[0] for c in C], "y": [c[1] for c in C], "length": L}
""", "Arbitrary-degree Bézier via de Casteljau, with polyline arc length.")

T("golden_rect", "Design", "Proportion Grid", ["width"], ["height", "columns"], {"width": 1200.0, "ratio": 1.618034, "n_columns": 12, "gutter": 24.0}, """
    def process(width=None, params=None):
        W = ks.pick(width, params["width"]); n = int(params["n_columns"]); g = params["gutter"]
        col = (W - g * (n - 1)) / n
        return {"height": W / params["ratio"], "columns": [round(i * (col + g), 2) for i in range(n)]}
""", "Layout helper: proportional height and column x-positions for an n-column grid.")

# ============================================================================
# TEXT & CODE
# ============================================================================
T("regex", "Text & Code", "Regex", ["text"], ["matches", "count"], {"pattern": r"[ACGT]{3}", "ignore_case": False}, """
    import re
    def process(text=None, params=None):
        flags = re.I if params["ignore_case"] else 0
        m = re.findall(params["pattern"], str(text or ""), flags)
        return {"matches": m, "count": len(m)}
""", "re.findall over the input text.")

T("json_parse", "Text & Code", "JSON Parse", ["text"], ["data"], {}, """
    import json
    def process(text=None):
        return {"data": json.loads(text) if isinstance(text, str) else text}
""", "Parse a JSON string.")

T("json_get", "Text & Code", "Get Path", ["data"], ["value"], {"path": "a.b.0"}, """
    def process(data=None, params=None):
        cur = data
        for key in [k for k in str(params["path"]).split(".") if k]:
            cur = cur[int(key)] if isinstance(cur, list) else cur[key]
        return {"value": cur}
""", "Navigate nested dicts/lists with a dotted path (list indices are integers).")

T("template", "Text & Code", "Format String", ["a", "b", "c"], ["text"], {"template": "a={a}, b={b}, c={c}"}, """
    def process(a=None, b=None, c=None, params=None):
        return {"text": params["template"].format(a=a, b=b, c=c)}
""", "Python str.format with a, b, c.")

T("word_stats", "Text & Code", "Text Statistics", ["text"], ["words", "chars", "lines", "top_words", "entropy_bits"], {"top": 5}, """
    import re, collections
    def process(text=None, params=None):
        s = str(text or "")
        words = re.findall(r"[\\w']+", s.lower())
        cnt = collections.Counter(s)
        n = len(s) or 1
        H = -sum(c / n * math.log2(c / n) for c in cnt.values())
        return {"words": len(words), "chars": len(s), "lines": s.count("\\n") + 1 if s else 0,
                "top_words": collections.Counter(words).most_common(int(params["top"])),
                "entropy_bits": H}
""", "Counts plus Shannon character entropy (bits/char).")

T("hash", "Text & Code", "Hash", ["data"], ["sha256", "md5"], {}, """
    import hashlib, json
    def process(data=None):
        b = data.encode() if isinstance(data, str) else json.dumps(data, sort_keys=True, default=str).encode()
        return {"sha256": hashlib.sha256(b).hexdigest(), "md5": hashlib.md5(b).hexdigest()}
""", "Content hashes (for provenance / cache keys).")


# ============================================================================
# universal templates + user library
# ============================================================================
import json as _json
import os as _os
import re as _re

import knode_universal as _U

CATEGORY_COLORS.update(_U.UNIVERSAL_COLORS)
for _t in _U.U:
    TEMPLATES.append(_t)
for _t in TEMPLATES:
    _t.setdefault("ports", None)
    _t.setdefault("schema", {})
    _t.setdefault("universal", False)

derive_ports = _U.derive_ports
USER_DIR = _os.environ.get("KNODE_USER_LIBRARY", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "user_library"))
_ID = _re.compile(r"^[a-z0-9_\-]{1,64}$")


def load_user_templates():
    """Read every *.json node type from the user library folder; broken files are skipped with a message."""
    out = []
    if not _os.path.isdir(USER_DIR):
        return out
    for fn in sorted(_os.listdir(USER_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(_os.path.join(USER_DIR, fn)) as f:
                t = _json.load(f)
            t = normalize_user_template(t)
            out.append(t)
        except Exception as e:  # a broken file must not take the library down
            print(f"user library: skipped {fn}: {e}")
    return out


def normalize_user_template(t):
    """Validate and complete a user node type (id format, no clash with built-ins, defaults for missing fields)."""
    t = dict(t)
    t["id"] = str(t.get("id", "")).strip().lower()
    if not _ID.match(t["id"]):
        raise ValueError("type id must be 1–64 chars of a-z, 0-9, _ or -")
    if any(b["id"] == t["id"] for b in TEMPLATES):
        raise ValueError(f"'{t['id']}' is a built-in type id — choose another")
    t.setdefault("name", t["id"])
    t["category"] = str(t.get("category") or "My Nodes")
    t.setdefault("description", "")
    t["inputs"] = [str(x) for x in t.get("inputs", [])]
    t["outputs"] = [str(x) for x in t.get("outputs", [])]
    t["params"] = dict(t.get("params", {}))
    t.setdefault("code", "def process():\n    return {}\n")
    t["stateful"] = bool(t.get("stateful"))
    t.setdefault("ports", None)
    t.setdefault("schema", {})
    t.setdefault("refs", [])
    t.setdefault("color", "#e1b12c")
    t["user"] = True
    return t


def save_user_template(t):
    """Validate and write a user node type to user_library/<id>.json; returns the normalised template."""
    t = normalize_user_template(t)
    _os.makedirs(USER_DIR, exist_ok=True)
    with open(_os.path.join(USER_DIR, t["id"] + ".json"), "w") as f:
        _json.dump(t, f, indent=2)
    return t


def delete_user_template(tid):
    """Remove a user node type file; KeyError if the id is invalid or unknown."""
    path = _os.path.join(USER_DIR, str(tid) + ".json")
    if not _ID.match(str(tid)) or not _os.path.exists(path):
        raise KeyError(tid)
    _os.remove(path)


def get_library():
    """All templates (built-in + user) and the category → colour map served to the editor."""
    user = load_user_templates()
    cats = dict(CATEGORY_COLORS)
    for t in user:
        cats.setdefault(t["category"], t.get("color", "#e1b12c"))
    return {"categories": cats, "templates": TEMPLATES + user}


def get_template(tid):
    """Look up a template by id among built-in and user types (KeyError if missing)."""
    for t in TEMPLATES + load_user_templates():
        if t["id"] == tid:
            return t
    raise KeyError(tid)


def instantiate(tid, nid, params=None, name=None):
    """Node payload (engine format) for template ``tid``; dynamic ports follow the params."""
    t = get_template(tid)
    if t.get("open_params") and params:          # user-defined parameter sets replace the demo defaults
        p = copy.deepcopy(params)
    else:
        p = copy.deepcopy(t["params"])
        p.update(params or {})
    ins, outs = derive_ports(t, p)
    return {"id": str(nid), "name": name or t["name"], "code": t["code"], "inputs": ins,
            "outputs": outs, "params": p, "template": tid, "stateful": t["stateful"]}


def build(nodes, wires=()):
    """build([("sir", {...}), ("step_signal", {...})], [(1, "y", 0, "beta")]) → payload"""
    payload = {"nodes": {}, "connections": []}
    for i, spec in enumerate(nodes):
        tid, params = spec[0], (spec[1] if len(spec) > 1 else None)
        payload["nodes"][str(i)] = instantiate(tid, i, params)
    for a, ap, b, bp in wires:
        payload["connections"].append({"from": str(a), "fromPort": ap, "to": str(b), "toPort": bp})
    return payload

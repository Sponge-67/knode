"""
Verification suite: every numerical claim made in the library is checked
against an analytic solution, a conservation law, or a published value.

Run:  python -m pytest tests -q      (or simply: python tests/test_engine.py)
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E          # noqa: E402
import knode_library as L         # noqa: E402
import knode_std as ks            # noqa: E402


def approx(a, b, rel=1e-6, abs_=1e-12):
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def one(tid, params=None, **inputs):
    """Run a single template with constant inputs and return its outputs."""
    nodes = [(tid, params or {})]
    wires = []
    for k, v in inputs.items():
        nodes.append(("const", {"value": v}))
        wires.append((len(nodes) - 1, "value", 0, k))
    rep = E.run(L.build(nodes, wires))
    assert rep["success"], rep["errors"]
    return rep["outputs"]["0"]


def sim(tid, params=None, steps=1000, dt=0.01, **kw):
    rep = E.simulate(L.build([(tid, params or {})]), steps=steps, dt=dt, max_points=10 ** 7, **kw)
    assert rep["success"], rep["errors"]
    return rep["traces"]


# --------------------------------------------------------------------- std lib

def test_rk4_exponential_decay_order4():
    f = lambda t, y: [-y[0]]
    errs = []
    for h in (0.1, 0.05):
        y = [1.0]
        for i in range(int(round(1 / h))):
            y = ks.rk4_step(f, i * h, y, h)
        errs.append(abs(y[0] - math.exp(-1)))
    order = math.log(errs[0] / errs[1], 2)
    assert 3.8 < order < 4.2, order


def test_dormand_prince_harmonic_oscillator():
    ts, ys = ks.solve_ivp(lambda t, y: [y[1], -y[0]], 0, 2 * math.pi, [1.0, 0.0], rtol=1e-9, atol=1e-12, n_out=50)
    assert abs(ys[-1][0] - 1.0) < 1e-7 and abs(ys[-1][1]) < 1e-7


def test_stats_and_regression():
    xs = [1, 2, 3, 4, 5]
    assert approx(ks.std(xs), math.sqrt(2.5))
    r = ks.linregress(xs, [2 * x + 1 for x in xs])
    assert approx(r["slope"], 2) and approx(r["intercept"], 1) and approx(r["r2"], 1)
    assert approx(ks.spearman([1, 2, 3, 4], [1, 8, 27, 64]), 1.0)
    assert approx(ks.percentile([1, 2, 3, 4], 50), 2.5)


def test_fft_peak():
    fs, f0 = 100.0, 7.0
    sig = [3 * math.sin(2 * math.pi * f0 * i / fs) for i in range(200)]
    fr, mag = ks.rfft_mag(sig, fs)
    k = max(range(1, len(mag)), key=lambda i: mag[i])
    assert approx(fr[k], f0) and abs(mag[k] - 3) < 1e-6


def test_nelder_mead_rosenbrock():
    out = one("minimize")
    assert abs(out["x_opt"]["x"] - 1) < 1e-4 and abs(out["x_opt"]["y"] - 1) < 1e-4


def test_root_wallis_cubic():
    assert abs(one("root")["root"] - 2.0945514815423265) < 1e-10


def test_wcag_contrast():
    assert approx(ks.contrast_ratio("#000000", "#ffffff"), 21.0)


# -------------------------------------------------------------- engineering

def test_cantilever_and_section():
    s = one("rect_section", {"b": 0.05, "h": 0.1})
    assert approx(s["I"], 0.05 * 0.1 ** 3 / 12)
    c = one("cantilever", {"F": 1000, "L": 2, "E": 200e9, "I": s["I"], "c": 0.05})
    assert approx(c["deflection"], 1000 * 8 / (3 * 200e9 * s["I"]))


def test_projectile_range_formula():
    o = one("projectile", {"v0": 20, "angle_deg": 45, "g": 9.81, "h0": 0})
    assert approx(o["range"], 400 / 9.81, rel=1e-9)


def test_rc_circuit_exact():
    tr = sim("rc_circuit", {"R": 1000, "C": 1e-3, "V_in": 5, "V0": 0}, steps=100, dt=0.01)
    assert approx(tr["0.V_c"][-1], 5 * (1 - math.exp(-1)), rel=1e-9)


def test_mass_spring_undamped_period():
    tr = sim("mass_spring_damper", {"m": 1, "c": 0, "k": 4, "x0": 1, "v0": 0}, steps=int(math.pi / 0.001), dt=0.001)
    # period = 2π/ω = π ; after one period x returns to 1
    assert abs(tr["0.x"][-1] - 1) < 1e-3


def test_heat_equation_steady_state_linear():
    tr = E.simulate(L.build([("heat1d", {"alpha": 0.05, "n": 21})]), steps=400, dt=0.5)
    prof = tr["outputs"]["0"]["profile"]
    lin = ks.linspace(100, 20, 21)
    assert max(abs(a - b) for a, b in zip(prof, lin)) < 0.05


# ------------------------------------------------------------------ biology

def test_logistic_growth_exact():
    p = {"r": 0.5, "K": 100, "N0": 5}
    tr = sim("logistic_growth", p, steps=1000, dt=0.01)
    exact = 100 / (1 + (100 - 5) / 5 * math.exp(-0.5 * 10))
    assert approx(tr["0.N"][-1], exact, rel=1e-9)


def test_sir_conservation_and_final_size():
    tr = sim("sir", {"beta": 0.3, "gamma": 0.1, "N": 1000, "I0": 1}, steps=3000, dt=0.1)
    for s, i, r in zip(tr["0.S"], tr["0.I"], tr["0.R"]):
        assert abs(s + i + r - 1000) < 1e-8
    # final-size relation: ln(S∞/S0) = −R0 (1 − S∞/N)
    s_inf = tr["0.S"][-1]
    assert abs(math.log(s_inf / 999) + 3 * (1 - s_inf / 1000)) < 1e-3


def test_lotka_volterra_invariant():
    tr = sim("lotka_volterra", {}, steps=5000, dt=0.01)
    V = tr["0.invariant"]
    assert max(V) - min(V) < 1e-6


def test_michaelis_menten_half_max():
    assert approx(one("michaelis_menten", {"Vmax": 2, "Km": 0.5, "S": 0.5})["v"], 1.0)


def test_hodgkin_huxley_spikes():
    tr = sim("hodgkin_huxley", {"I_ext": 10}, steps=1000, dt=0.05)   # 50 ms
    V = tr["0.V"]
    spikes = sum(1 for a, b in zip(V, V[1:]) if a < 0 <= b)
    assert 3 <= spikes <= 6 and max(V) > 30
    rest = sim("hodgkin_huxley", {"I_ext": 0}, steps=400, dt=0.05)["0.V"]
    assert abs(rest[-1] + 65) < 0.5


def test_toggle_switch_bistable():
    hi = sim("toggle_switch", {"u0": 10, "v0": 0.1}, steps=600, dt=0.05)
    lo = sim("toggle_switch", {"u0": 0.1, "v0": 10}, steps=600, dt=0.05)
    assert hi["0.u"][-1] > 100 and lo["0.u"][-1] < 1


def test_dna_tools():
    o = one("dna_tools", seq="ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG")
    assert o["protein"].startswith("MAIVMGR*")
    assert o["revcomp"].startswith("CTATCGGGCACCC")
    assert approx(o["gc"], 22 / 39)


def test_wright_fisher_absorbs():
    tr = sim("wright_fisher", {"N": 20, "p0": 0.5, "seed": 3}, steps=2000, dt=1)
    assert tr["0.p"][-1] in (0.0, 1.0)


# ------------------------------------------------------------ complex systems

def test_logistic_map_lyapunov():
    chaos = sim("logistic_map", {"r": 4.0, "x0": 0.2}, steps=20000)["0.lyapunov"][-1]
    stable = sim("logistic_map", {"r": 2.8, "x0": 0.2}, steps=5000)["0.lyapunov"][-1]
    assert abs(chaos - math.log(2)) < 0.05 and stable < 0


def test_lorenz_stays_on_attractor():
    tr = sim("lorenz", {}, steps=3000, dt=0.01)
    assert max(tr["0.z"]) < 50 and min(tr["0.z"]) > 0 and max(abs(v) for v in tr["0.x"]) > 10


def test_kuramoto_transition():
    lo = sim("kuramoto", {"K": 0.5, "N": 200}, steps=600, dt=0.05)["0.r"]
    hi = sim("kuramoto", {"K": 4.0, "N": 200}, steps=600, dt=0.05)["0.r"]
    assert ks.mean(hi[-100:]) > 0.8 > 0.3 > ks.mean(lo[-100:])


def test_rule90_sierpinski():
    rep = E.simulate(L.build([("elementary_ca", {"rule": 90, "width": 65})]), steps=16, dt=1)
    assert sum(rep["outputs"]["0"]["row"]) == 2        # row 16 of Pascal mod 2 → 2 cells


def test_brownian_msd():
    msd = []
    for seed in range(200):
        rep = E.simulate(L.build([("random_walk", {"D": 0.5, "seed": seed})]), steps=100, dt=0.01)
        msd.append(rep["traces"]["0.x"][-1] ** 2)
    assert abs(ks.mean(msd) - 2 * 0.5 * 1.0) < 0.25


def test_ode_van_der_pol_limit_cycle():
    o = one("ode")
    assert 1.9 < max(o["Y"]["x"][-200:]) < 2.1          # amplitude ≈ 2


# ---------------------------------------------------------------- engine

def test_fan_in_and_chain():
    g = L.build([("const", {"value": 2}), ("const", {"value": 3}), ("sum_list", {})],
                [(0, "value", 2, "values"), (1, "value", 2, "values")])
    assert E.run(g)["outputs"]["2"]["sum"] == 5


def test_target_restricts_to_ancestors():
    g = L.build([("const", {"value": 2}), ("gain", {"k": 3}), ("const", {"value": 9})], [(0, "value", 1, "x")])
    rep = E.run(g, target="1")
    assert rep["outputs"]["1"]["y"] == 6 and "2" not in rep["outputs"]


def test_algebraic_loop_fixed_point():
    # x = 0.5 x + 1  →  x = 2
    g = L.build([("expr", {"expr": "0.5*x + 1"})], [(0, "y", 0, "x")])
    rep = E.run(g)
    assert approx(rep["outputs"]["0"]["y"], 2.0, rel=1e-8) and rep["loops"][0]["converged"]


def test_closed_loop_pid_tracks_setpoint():
    g = L.build([("pid", {"kp": 20, "ki": 10, "kd": 2, "setpoint": 1.0}), ("mass_spring_damper", {"k": 4, "c": 1})],
                [(1, "x", 0, "measurement"), (0, "u", 1, "F")])
    rep = E.simulate(g, steps=2000, dt=0.005)
    assert rep["success"] and abs(rep["traces"]["1.x"][-1] - 1.0) < 0.01
    assert rep["feedback_edges"]


def test_errors_are_localised_with_line_numbers():
    payload = {"nodes": {"1": {"name": "bad", "code": "def process():\n    return 1/0\n", "inputs": [], "outputs": ["y"]},
                         "2": {"name": "down", "code": "def process(x):\n    return x\n", "inputs": ["x"], "outputs": ["y"]}},
               "connections": [{"from": "1", "fromPort": "y", "to": "2", "toPort": "x"}]}
    rep = E.run(payload)
    assert rep["status"] == {"1": "error", "2": "blocked"} and rep["errors"]["1"]["line"] == 2


def test_function_finder_ignores_builtins():
    payload = {"nodes": {"1": {"name": "Renamed Node", "code": "def my_logic():\n    return {'o': 7}\n",
                               "inputs": [], "outputs": ["o"]}}, "connections": []}
    assert E.run(payload)["outputs"]["1"]["o"] == 7


def test_json_safety():
    payload = {"nodes": {"1": {"name": "n", "code": "def process():\n    return {'a': float('nan'), 'b': float('inf'), 'c': {1,2}, 'd': 1j}\n",
                               "inputs": [], "outputs": ["a"]}}, "connections": []}
    import json
    out = E.run(payload)
    json.loads(json.dumps(out, allow_nan=False))


def test_sweep_and_montecarlo():
    g = L.build([("projectile", {})])
    sw = E.sweep(g, "0", "angle_deg", [15, 30, 45, 60, 75], ("0", "range"))
    assert max(range(5), key=lambda i: sw["results"][i]) == 2
    mc = E.montecarlo(g, [{"node": "0", "param": "v0", "dist": "uniform", "a": 10, "b": 30},
                          {"node": "0", "param": "g", "dist": "uniform", "a": 9.7, "b": 9.9}],
                      ("0", "range"), n=200, seed=1)
    s = {x["factor"]: x["spearman"] for x in mc["sensitivity"]}
    assert s["0.v0"] > 0.95 and abs(s["0.g"]) < 0.3


def test_analysis():
    g = L.build([("pid", {}), ("mass_spring_damper", {}), ("const", {}), ("gain", {})],
                [(1, "x", 0, "measurement"), (0, "u", 1, "F"), (2, "value", 3, "x")])
    a = E.analyze(g)
    assert not a["is_dag"] and sorted(a["cycles"][0]) == ["0", "1"] and a["weak_components"] == 2
    assert approx(sum(v["pagerank"] for v in a["nodes"].values()), 1.0)


def test_every_template_compiles_and_runs():
    for t in L.TEMPLATES:
        rep = E.simulate(L.build([(t["id"], {})]), steps=3, dt=0.01) if t["stateful"] else E.run(L.build([(t["id"], {})]))
        if t["id"] in ("json_parse", "json_get", "linreg", "correlation", "stats", "histogram", "fft"):
            continue  # need connected data
        assert rep["success"], (t["id"], rep["errors"])


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"  ok    {name}")
            except Exception as e:
                fails += 1
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)

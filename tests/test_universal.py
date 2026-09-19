"""
Verification of the universal nodes: each formalism is checked against an exact
solution, a conservation law, or cross-validated against an independent node.

Run:  python tests/test_universal.py      (or pytest tests)
"""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E      # noqa: E402
import knode_library as L     # noqa: E402
import knode_std as ks        # noqa: E402


def sim(nodes, wires=(), steps=100, dt=0.01):
    rep = E.simulate(L.build(nodes, wires), steps=steps, dt=dt, max_points=10 ** 7)
    assert rep["success"], rep["errors"]
    return rep


def run(nodes, wires=()):
    rep = E.run(L.build(nodes, wires))
    assert rep["success"], rep["errors"]
    return rep["outputs"]


# ------------------------------------------------------------------ formula / lookup / logic

def test_formula_scalar_list_and_defaults():
    o = run([("formula", {"inputs": "x, a", "equations": "y = a*x + 1\nz = y**2", "constants": "a=3"}),
             ("linspace", {"start": 0, "stop": 2, "n": 3})], [(1, "x", 0, "x")])["0"]
    assert o["y"] == [1.0, 4.0, 7.0] and o["z"] == [1.0, 16.0, 49.0]


def test_ports_follow_parameters():
    p = L.instantiate("formula", 0, {"inputs": "p, q", "equations": "s = p + q\nd = p - q"})
    assert p["inputs"] == ["p", "q"] and p["outputs"] == ["s", "d"]
    r = L.instantiate("reaction_network", 0, {"reactions": "E + S -> ES, kf\nES -> E + P, kc"})
    assert r["outputs"] == ["E", "S", "ES", "P"]


def test_lookup_interpolation():
    assert run([("lookup", {"x": 1.5})])["0"]["y"] == 0.8 + 0.5 * 0.7


def test_event_detector_measures_period():
    rep = sim([("sine", {"frequency": 2.0}), ("event", {})], [(0, "y", 1, "x")], steps=400, dt=0.005)
    assert abs(rep["outputs"]["1"]["period"] - 0.5) < 0.01 and rep["outputs"]["1"]["count"] == 3   # crossings at t = 0.5, 1.0, 1.5


# ------------------------------------------------------------------ continuous & discrete dynamics

def test_dynamic_system_harmonic_period_and_energy():
    p = {"inputs": "", "states": "x, v", "equations": "dx = v\ndv = -x", "initial": "x=1, v=0",
         "constants": "", "observables": "E = 0.5*(x*x + v*v)", "max_substep": 0.001}
    rep = sim([("dynamic_system", p)], steps=int(round(2 * math.pi / 0.01)), dt=0.01)
    E_ = rep["traces"]["0.E"]
    assert abs(rep["traces"]["0.x"][-1] - math.cos(rep["traces"]["t"][-1])) < 1e-6
    assert max(E_) - min(E_) < 1e-9


def test_dynamic_system_matches_mass_spring_damper():
    """Cross-validation: the generic ODE node reproduces the dedicated model under forcing."""
    ds = {"inputs": "F", "states": "x, v", "equations": "dx = v\ndv = (F - c*v - k*x)/m",
          "initial": "x=0, v=0", "constants": "m=1, c=0.5, k=4, F=0", "observables": "", "max_substep": 0.001}
    rep = sim([("sine", {"frequency": 0.3}), ("dynamic_system", ds), ("mass_spring_damper", {"c": 0.5, "k": 4})],
              [(0, "y", 1, "F"), (0, "y", 2, "F")], steps=1000, dt=0.01)
    a, b = rep["traces"]["1.x"], rep["traces"]["2.x"]
    assert max(abs(x - y) for x, y in zip(a, b)) < 1e-6


def test_discrete_map_fixed_point():
    p = {"inputs": "", "states": "x", "update": "x = r*x*(1 - x)", "initial": "x=0.1", "constants": "r=2.5", "observables": ""}
    rep = sim([("discrete_map", p)], steps=200, dt=1)
    assert abs(rep["traces"]["0.x"][-1] - 0.6) < 1e-9


def test_transfer_function_first_and_second_order():
    rep = sim([("transfer_function", {"num": "1", "den": "1, 1", "u": 1.0})], steps=100, dt=0.01)
    assert abs(rep["traces"]["0.y"][-1] - (1 - math.exp(-1))) < 1e-8
    rep = sim([("transfer_function", {"num": "3", "den": "1, 2, 2", "u": 1.0})], steps=2000, dt=0.01)
    assert abs(rep["traces"]["0.y"][-1] - 1.5) < 1e-6          # DC gain = 3/2


# ------------------------------------------------------------------ reaction networks

def test_reaction_network_ode_equals_sir_model():
    rn = {"reactions": "S + I -> 2 I, beta/N\nI -> R, gamma", "initial": "S=999, I=1, R=0",
          "constants": "beta=0.3, gamma=0.1, N=1000", "max_substep": 0.1}
    rep = sim([("reaction_network", rn), ("sir", {"beta": 0.3, "gamma": 0.1, "N": 1000, "I0": 1})], steps=1500, dt=0.1)
    assert max(abs(a - b) for a, b in zip(rep["traces"]["0.I"], rep["traces"]["1.I"])) < 1e-6


def test_reaction_network_ssa_mean_matches_exponential_decay():
    finals = []
    for seed in range(60):
        rep = sim([("reaction_network", {"reactions": "A ->, k", "initial": "A=200", "constants": "k=1",
                                         "method": "ssa", "seed": seed})], steps=10, dt=0.1)
        finals.append(rep["traces"]["0.A"][-1])
        assert float(finals[-1]).is_integer()
    assert abs(ks.mean(finals) - 200 * math.exp(-1)) < 3.0


def test_reaction_network_custom_rate_law():
    rn = {"reactions": "S -> P, = Vmax*S/(Km + S)", "initial": "S=10, P=0", "constants": "Vmax=1, Km=2", "max_substep": 0.01}
    rep = sim([("reaction_network", rn)], steps=500, dt=0.1)
    tr = rep["traces"]
    assert all(abs(s + p - 10) < 1e-9 for s, p in zip(tr["0.S"], tr["0.P"]))
    # integrated Michaelis–Menten: Km ln(S0/S) + (S0 - S) = Vmax t
    S, t = tr["0.S"][-1], tr["t"][-1]
    assert abs(2 * math.log(10 / S) + (10 - S) - t) < 1e-6


# ------------------------------------------------------------------ hybrid: state machine + physics

def test_thermostat_hybrid_system_regulates():
    room = {"inputs": "P", "states": "T", "equations": "dT = (P/C) - (T - T_out)/tau", "initial": "T=15",
            "constants": "C=1000, tau=500, T_out=5, P=0", "observables": "", "max_substep": 1}
    sm = {"inputs": "T", "states": "idle, heating", "transitions": "idle -> heating : T < 19\nheating -> idle : T > 21",
          "outputs": "*: power = 0\nheating: power = 60", "constants": "T=20"}
    rep = sim([("dynamic_system", room), ("state_machine", sm)], [(1, "power", 0, "P"), (0, "T", 1, "T")], steps=3000, dt=1)
    late = rep["traces"]["0.T"][1500:]
    assert 18.5 < min(late) and max(late) < 21.5 and rep["feedback_edges"]


# ------------------------------------------------------------------ populations

def test_agent_based_sir_conserves_population_and_spreads():
    rep = sim([("agent_based", {"N": 300, "constants": "beta=0.6, gamma=0.1"})], steps=600, dt=0.1)
    tr = rep["traces"]
    assert all(s + i + r == 300 for s, i, r in zip(tr["0.S"], tr["0.I"], tr["0.R"]))
    assert tr["0.R"][-1] > 200                                  # R0 = 6 → large outbreak


def test_network_consensus_on_complete_graph():
    p = {"topology": "complete", "N": 30, "init": "x = i", "rules": "x = nbr_mean('x')", "observables": "spread = maximum(x) - minimum(x)\nm = mean(x)"}
    rep = sim([("network_dynamics", p)], steps=30, dt=1)
    assert rep["traces"]["0.spread"][-1] < 1e-6
    # averaging over all *other* nodes preserves the mean on a complete graph
    assert abs(rep["traces"]["0.m"][-1] - 14.5) < 1e-9


def test_network_threshold_cascade_is_monotone():
    rep = sim([("network_dynamics", {})], steps=60, dt=1)
    a = rep["traces"]["0.adopters"]
    assert all(y >= x for x, y in zip(a, a[1:]))


def test_field_diffusion_conserves_mass():
    p = {"fields": "u", "equations": "du = D*lap(u)", "initial": "u = exp(-((X-0.5)**2 + (Y-0.5)**2)/0.01)",
         "constants": "D=0.2", "size": 32, "max_substep": 1.0, "output_size": 32}
    rep = sim([("field2d", p)], steps=50, dt=1)
    m = rep["traces"]["0.u_mean"]
    assert max(m) - min(m) < 1e-12 and len(rep["outputs"]["0"]["u"]) == 32


def test_gray_scott_forms_pattern():
    rep = sim([("field2d", {"size": 64})], steps=1500, dt=1.0)
    v = [x for row in rep["outputs"]["0"]["v"] for x in row]
    assert ks.std(v) > 0.05                                     # spots, not a uniform field


# ------------------------------------------------------------------ groups (hierarchical models)

def _group(inner_payload, inputs, outputs, gid="9"):
    """Wrap an engine payload as a group node."""
    return {"id": gid, "name": "Group", "code": "def process():\n    return {}\n",
            "inputs": inputs, "outputs": outputs, "subgraph": inner_payload}


def test_group_equals_flat_graph_and_nests():
    inner = L.build([("graph_in", {"name": "x"}), ("gain", {"k": 3}), ("graph_out", {"name": "y"})],
                    [(0, "value", 1, "x"), (1, "y", 2, "value")])
    outer = {"nodes": {"0": L.instantiate("const", 0, {"value": 2}), "9": _group(inner, ["x"], ["y"])},
             "connections": [{"from": "0", "fromPort": "value", "to": "9", "toPort": "x"}]}
    assert E.run(outer)["outputs"]["9"]["y"] == 6
    # nest the group inside another group
    wrapper = {"nodes": {"a": L.instantiate("graph_in", "a", {"name": "x"}), "9": _group(inner, ["x"], ["y"]),
                         "b": L.instantiate("graph_out", "b", {"name": "y"})},
               "connections": [{"from": "a", "fromPort": "value", "to": "9", "toPort": "x"},
                               {"from": "9", "fromPort": "y", "to": "b", "toPort": "value"}]}
    outer2 = {"nodes": {"0": L.instantiate("const", 0, {"value": 5}), "8": _group(wrapper, ["x"], ["y"], "8")},
              "connections": [{"from": "0", "fromPort": "value", "to": "8", "toPort": "x"}]}
    rep = E.run(outer2)
    assert rep["outputs"]["8"]["y"] == 15 and "9" in rep["groups"]["8"]["groups"]


def test_group_keeps_state_across_simulation_steps():
    inner = L.build([("graph_in", {"name": "u"}), ("integrator", {}), ("graph_out", {"name": "y"})],
                    [(0, "value", 1, "u"), (1, "y", 2, "value")])
    outer = {"nodes": {"0": L.instantiate("const", 0, {"value": 1.0}), "9": _group(inner, ["u"], ["y"]),
                       "1": L.instantiate("integrator", 1)},
             "connections": [{"from": "0", "fromPort": "value", "to": "9", "toPort": "u"},
                             {"from": "0", "fromPort": "value", "to": "1", "toPort": "u"}]}
    rep = E.simulate(outer, steps=100, dt=0.01)
    assert rep["success"] and abs(rep["traces"]["9.y"][-1] - 1.0) < 1e-9
    assert rep["traces"]["9.y"] == rep["traces"]["1.y"]


def test_group_errors_name_the_inner_node():
    inner = L.build([("formula", {"inputs": "", "equations": "y = 1/0", "constants": ""}), ("graph_out", {"name": "y"})],
                    [(0, "y", 1, "value")])
    rep = E.run({"nodes": {"9": _group(inner, [], ["y"])}, "connections": []})
    assert "inside group" in rep["errors"]["9"]["error"] and "Formula Block" in rep["errors"]["9"]["error"]


# ------------------------------------------------------------------ user library

def test_user_template_roundtrip():
    old = L.USER_DIR
    with tempfile.TemporaryDirectory() as d:
        L.USER_DIR = d
        try:
            L.save_user_template({"id": "my_decay", "name": "My Decay", "inputs": ["x"], "outputs": ["y"],
                                  "params": {"k": 0.5}, "code": "def process(x=0.0, params=None):\n    return {'y': x*params['k']}\n"})
            assert any(t["id"] == "my_decay" for t in L.get_library()["templates"])
            assert E.run(L.build([("my_decay", {"k": 2}), ("const", {"value": 3})], [(1, "value", 0, "x")]))["outputs"]["0"]["y"] == 6
            try:
                L.save_user_template({"id": "sir"})
                raise AssertionError("built-in id accepted")
            except ValueError:
                pass
            L.delete_user_template("my_decay")
            assert not any(t["id"] == "my_decay" for t in L.get_library()["templates"])
        finally:
            L.USER_DIR = old


def test_every_universal_default_runs():
    for t in L.TEMPLATES:
        if not t.get("universal"):
            continue
        rep = E.simulate(L.build([(t["id"], {})]), steps=3, dt=0.01) if t["stateful"] else E.run(L.build([(t["id"], {})]))
        if t["id"] in ("sample_hold", "mux"):
            continue
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
                import traceback
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
                traceback.print_exc(limit=3)
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)

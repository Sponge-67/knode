"""
Tests for features adopted from other node systems (knode 0.4):
flags (bypass / freeze / break-if), incremental cache, wireless links, globals &
parameter expressions, live sessions, scenarios and calibration.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E      # noqa: E402
import knode_library as L     # noqa: E402


def with_props(payload, nid, **props):
    payload["nodes"][str(nid)].update(props)
    return payload


# ------------------------------------------------------------------ flags

def test_bypass_passes_input_through():
    g = L.build([("const", {"value": 5}), ("gain", {"k": 10}), ("gain", {"k": 2})], [(0, "value", 1, "x"), (1, "y", 2, "x")])
    assert E.run(g)["outputs"]["2"]["y"] == 100
    assert E.run(with_props(g, 1, bypass=True))["outputs"]["2"]["y"] == 10


def test_freeze_uses_pinned_outputs_without_executing():
    g = L.build([("formula", {"inputs": "", "equations": "y = 1/0", "constants": ""}), ("gain", {"k": 3})], [(0, "y", 1, "x")])
    assert not E.run(g)["success"]
    rep = E.run(with_props(g, 0, frozen={"y": 7}))
    assert rep["success"] and rep["outputs"]["1"]["y"] == 21


def test_break_if_stops_simulation_at_condition():
    g = with_props(L.build([("logistic_growth", {})]), 0, break_if="N > 50")
    rep = E.simulate(g, steps=5000, dt=0.01)
    bp = rep["breakpoint"]
    # analytic crossing time of N = 50: t = ln((K-N0)/N0 * N/(K-N)) / r = ln(19)/0.5
    assert bp and abs(bp["t"] - math.log(19) / 0.5) < 0.011 and "breakpoint" in rep["stopped"]


# ------------------------------------------------------------------ incremental cache

def test_cache_skips_unchanged_nodes_but_respects_changes():
    E.clear_cache()
    g = L.build([("const", {"value": 2}), ("minimize", {}), ("gain", {"k": 3})], [(0, "value", 2, "x")])
    r1 = E.run(g, cache=True)
    r2 = E.run(g, cache=True)
    assert r1["cached"] == [] and set(r2["cached"]) == {"0", "1", "2"}
    g["nodes"]["0"]["params"]["value"] = 5
    r3 = E.run(g, cache=True)
    assert set(r3["cached"]) == {"1"} and r3["outputs"]["2"]["y"] == 15


def test_cache_ignores_impure_code():
    E.clear_cache()
    payload = {"nodes": {"1": {"name": "rnd", "code": "import random\ndef process():\n    return {'x': random.random()}\n",
                               "inputs": [], "outputs": ["x"]}}, "connections": []}
    a, b = E.run(payload, cache=True), E.run(payload, cache=True)
    assert b["cached"] == [] and a["outputs"]["1"]["x"] != b["outputs"]["1"]["x"]


# ------------------------------------------------------------------ wireless + globals

def test_send_receive_links_by_channel():
    g = L.build([("const", {"value": 4}), ("send", {"channel": "load"}), ("receive", {"channel": "load"}), ("gain", {"k": 2})],
                [(0, "value", 1, "value"), (2, "value", 3, "x")])
    rep = E.run(g)
    assert rep["outputs"]["3"]["y"] == 8
    assert E.analyze(g)["n_edges"] == 3                   # the wireless link is a real dependency


def test_globals_and_parameter_expressions():
    g = L.build([("globals", {"g": 9.81, "v": "=10*2"}),
                 ("projectile", {"v0": "=v", "angle_deg": 45, "g": "=g"}),
                 ("gain", {"k": '=P("Projectile", "angle_deg") / 45'})])
    rep = E.run(g)
    assert rep["success"], rep["errors"]
    assert abs(rep["outputs"]["1"]["range"] - 400 / 9.81) < 1e-9 and rep["outputs"]["2"]["y"] == 0.0
    # sweeping the global changes every parameter that refers to it
    sw = E.sweep(g, "0", "v", [10, 20], ("1", "range"))
    assert abs(sw["results"][1] / sw["results"][0] - 4) < 1e-9


def test_bad_expression_is_reported_on_its_node():
    g = L.build([("gain", {"k": "=nope * 2"})])
    rep = E.run(g)
    assert rep["status"]["0"] == "error" and "nope" in rep["errors"]["0"]["error"]


# ------------------------------------------------------------------ live sessions

def test_session_chunks_equal_batch_simulation():
    g = L.build([("lotka_volterra", {})])
    batch = E.simulate(g, steps=299, dt=0.01, max_points=10 ** 6)["traces"]["0.prey"]
    sid, s = E.session_start(g, dt=0.01)
    got = []
    for _ in range(3):
        got += s.step(100, max_points=10 ** 6)["chunk"]["0.prey"]
    E.session_stop(sid)
    assert max(abs(a - b) for a, b in zip(got, batch)) < 1e-12 and len(got) == 300


def test_session_hot_parameter_change_keeps_state():
    g = L.build([("const", {"value": 1.0}), ("integrator", {})], [(0, "value", 1, "u")])
    sid, s = E.session_start(g, dt=0.1)
    s.step(10)                                            # y = 1.0 after 10 steps of u = 1
    rep = s.step(10, params={"0": {"value": 3.0}})        # continue with u = 3 without restarting
    E.session_stop(sid)
    # trapezoid: 10 steps at u=1 → 1.0; then 0.5*(3+1)*0.1 = 0.2, then 8 × 0.3 before the last output
    # (a restart would give 2.7) — state survived the parameter change
    assert abs(rep["outputs"]["1"]["y"] - 3.6) < 1e-9


# ------------------------------------------------------------------ scenarios & optimisation

def test_scenarios_compare_variants():
    g = L.build([("sir", {})])
    res = E.scenarios(g, [{"name": "base"}, {"name": "distancing", "overrides": {"0": {"beta": 0.15}}}], steps=1500, dt=0.1)
    peaks = [max(sc["traces"]["0.I"]) for sc in res["scenarios"]]
    assert res["success"] and peaks[1] < peaks[0] / 3


def test_optimize_maximise_projectile_range():
    g = L.build([("projectile", {})])
    r = E.optimize(g, [{"node": "0", "param": "angle_deg", "lo": 5, "hi": 85}], {"type": "maximize", "node": "0", "port": "range"},
                   mode="run", method="de", budget=200, seed=1)
    assert abs(r["values"][0] - 45) < 0.5 and abs(r["objective"] - 400 / 9.81) < 1e-3


def test_calibrate_to_data_recovers_parameters():
    """Generate data from logistic growth (r=0.8, K=150), then fit r and K back."""
    t = [0.5 * i for i in range(1, 30)]
    y = [150 / (1 + (150 - 5) / 5 * math.exp(-0.8 * ti)) for ti in t]
    g = L.build([("logistic_growth", {"r": 0.3, "K": 80, "N0": 5})])
    r = E.optimize(g, [{"node": "0", "param": "r", "lo": 0.05, "hi": 2}, {"node": "0", "param": "K", "lo": 50, "hi": 300}],
                   {"type": "fit", "node": "0", "port": "N", "data": {"t": t, "y": y}}, mode="simulate", steps=1500, dt=0.01,
                   method="de", budget=400, seed=3)
    assert abs(r["values"][0] - 0.8) < 0.01 and abs(r["values"][1] - 150) < 1 and r["r2"] > 0.9999


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"  ok    {name}")
            except Exception as e:
                import traceback
                fails += 1
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
                traceback.print_exc(limit=4)
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)

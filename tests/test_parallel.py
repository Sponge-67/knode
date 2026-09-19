"""
Parallel studies (knode 0.7): results with worker processes must be bit-identical to serial runs,
and the work must really happen in other processes.

    python tests/test_parallel.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E      # noqa: E402
import knode_library as L     # noqa: E402

SIR = L.build([("sir", {})])


def both(fn):
    """Run fn serially and with 2 workers; return (serial, parallel)."""
    E.WORKERS = -1
    a = fn()
    E.WORKERS = 2
    try:
        b = fn()
    finally:
        E.WORKERS = 0
    return a, b


def test_workers_are_other_processes():
    E.WORKERS = 2
    try:
        res = E.pmap(E._eval_task, [(SIR, {"0": {"beta": b}}, "simulate", {"steps": 50, "dt": 0.1}, ("0", "I"), "max", False) for b in (0.2, 0.3, 0.4, 0.5)])
    finally:
        E.WORKERS = 0
    pids = {r["pid"] for r in res}
    assert os.getpid() not in pids and len(pids) >= 1


def test_sweep_identical():
    f = lambda: E.sweep(SIR, "0", "beta", [0.1 + 0.05 * i for i in range(8)], ("0", "I"), mode="simulate", reduce="max", sim={"steps": 600, "dt": 0.1})
    a, b = both(f)
    assert a["results"] == b["results"] and a["errors"] == b["errors"]


def test_montecarlo_identical():
    fac = [{"node": "0", "param": "beta", "dist": "uniform", "a": 0.2, "b": 0.4}, {"node": "0", "param": "gamma", "dist": "normal", "a": 0.1, "b": 0.01}]
    f = lambda: E.montecarlo(SIR, fac, ("0", "I"), n=24, mode="simulate", reduce="max", seed=5, sim={"steps": 400, "dt": 0.1})
    a, b = both(f)
    assert a["y"] == b["y"] and a["samples"] == b["samples"] and a["sensitivity"] == b["sensitivity"]


def test_scenarios_identical():
    items = [{"name": "base"}, {"name": "low", "overrides": {"0": {"beta": 0.15}}}, {"name": "high", "overrides": {"0": {"beta": 0.5}}}]
    a, b = both(lambda: E.scenarios(SIR, items, steps=300, dt=0.1))
    assert [s["traces"] for s in a["scenarios"]] == [s["traces"] for s in b["scenarios"]]


def test_differential_evolution_identical_and_correct():
    g = L.build([("projectile", {})])
    f = lambda: E.optimize(g, [{"node": "0", "param": "angle_deg", "lo": 5, "hi": 85}], {"type": "maximize", "node": "0", "port": "range"},
                           mode="run", method="de", budget=160, seed=2)
    a, b = both(f)
    assert a["values"] == b["values"] and a["history"] == b["history"] and abs(a["values"][0] - 45) < 0.5


def test_nelder_mead_identical():
    g = L.build([("projectile", {"angle_deg": 20})])
    f = lambda: E.optimize(g, [{"node": "0", "param": "angle_deg", "lo": 5, "hi": 85}], {"type": "maximize", "node": "0", "port": "range"},
                           mode="run", method="nm", budget=80)
    a, b = both(f)
    assert a["values"] == b["values"] and abs(a["values"][0] - 45) < 0.1


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
                traceback.print_exc(limit=3)
    E.shutdown_pool()
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)

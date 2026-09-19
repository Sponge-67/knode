"""
knode engine benchmark — reproducible timings for the optimisation work.

    python bench/bench_engine.py            # prints a table
    python bench/bench_engine.py --json     # machine-readable

Each case is chosen to stress a different part of the engine:

  overhead  : many cheap nodes → per-node dispatch cost (argument binding, input gathering,
              stdout capture, scheduling bookkeeping) dominates
  ode       : a few nodes doing RK4 → numerical kernels in knode_std dominate
  text      : universal nodes that re-read their text specification every step
  population: agent-based / network rules → per-individual expression evaluation dominates
  field     : numpy 2-D PDE → vectorised numpy dominates (should barely change)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E      # noqa: E402
import knode_library as L     # noqa: E402


def chain(n):
    nodes = [("const", {"value": 1.0})] + [("gain", {"k": 1.0001}) for _ in range(n)]
    wires = [(0, "value", 1, "x")] + [(i, "y", i + 1, "x") for i in range(1, n)]
    return L.build(nodes, wires)


def fanout_dag(n):
    """Wide layered DAG for single-run (``Run once``) cost."""
    nodes, wires = [("const", {"value": 2.0})], []
    for i in range(1, n):
        nodes.append(("add", {}))
        wires.append((max(0, i - 1), "value" if i == 1 else "y", i, "a"))
        wires.append((max(0, i // 2 - 1) if i > 2 else 0, "value" if i <= 2 else "y", i, "b"))
    return L.build(nodes, wires)


CASES = [
    ("overhead", "gain chain ×50, 2 000 steps", lambda: chain(50), dict(steps=2000, dt=0.01), "sim"),
    ("overhead", "DAG 400 nodes, single run", lambda: fanout_dag(400), {}, "run"),
    ("overhead", "PID ↔ plant loop, 20 000 steps",
     lambda: L.build([("step_signal", {}), ("pid", {}), ("mass_spring_damper", {})],
                     [(0, "y", 1, "setpoint"), (1, "u", 2, "F"), (2, "x", 1, "measurement")]), dict(steps=20000, dt=0.005), "sim"),
    ("ode", "Lotka–Volterra RK4, 20 000 steps", lambda: L.build([("lotka_volterra", {})]), dict(steps=20000, dt=0.01), "sim"),
    ("ode", "Hodgkin–Huxley, 4 000 steps", lambda: L.build([("hodgkin_huxley", {})]), dict(steps=4000, dt=0.05), "sim"),
    ("text", "Dynamic System (Duffing), 10 000 steps", lambda: L.build([("dynamic_system", {})]), dict(steps=10000, dt=0.02), "sim"),
    ("text", "Reaction network ODE, 5 000 steps", lambda: L.build([("reaction_network", {})]), dict(steps=5000, dt=0.1), "sim"),
    ("text", "Formula block ×20 chain, 2 000 steps",
     lambda: L.build([("formula", {"inputs": "x", "equations": "y = sin(x) + 0.5*x", "constants": "x=1"}) for _ in range(20)],
                     [(i, "y", i + 1, "x") for i in range(19)]), dict(steps=2000, dt=0.01), "sim"),
    ("population", "Agent-based SIR N=1000, 200 steps", lambda: L.build([("agent_based", {"N": 1000})]), dict(steps=200, dt=0.1), "sim"),
    ("population", "Network dynamics N=1000, 60 steps", lambda: L.build([("network_dynamics", {"N": 1000})]), dict(steps=60, dt=1), "sim"),
    ("ode", "Kuramoto N=200, 400 steps", lambda: L.build([("kuramoto", {"N": 200})]), dict(steps=400, dt=0.05), "sim"),
    ("field", "Gray–Scott 96×96, 500 steps", lambda: L.build([("field2d", {})]), dict(steps=500, dt=1), "sim"),
]


def bench(repeat=3):
    rows = []
    for group, name, make, kw, mode in CASES:
        best = float("inf")
        for _ in range(repeat):
            payload = make()
            E.clear_cache()
            t0 = time.perf_counter()
            rep = E.simulate(payload, **kw) if mode == "sim" else E.run(payload)
            dt = time.perf_counter() - t0
            assert rep["success"], (name, rep["errors"])
            best = min(best, dt)
        rows.append({"group": group, "case": name, "seconds": best,
                     "rate": (kw.get("steps", 1) + 1) / best if mode == "sim" else len(payload["nodes"]) / best,
                     "unit": "steps/s" if mode == "sim" else "nodes/s"})
    return rows


if __name__ == "__main__":
    rows = bench()
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=1))
    else:
        print(f"{'group':<11} {'case':<40} {'time':>9} {'rate':>14}")
        for r in rows:
            print(f"{r['group']:<11} {r['case']:<40} {r['seconds']*1000:>7.1f}ms {r['rate']:>10,.0f} {r['unit']}")

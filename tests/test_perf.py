"""
Tests guarding the 0.5 performance work: every optimisation must keep results identical.

  * stdout routing       print() output is attributed to the right node, also inside groups
  * argument binding     precomputed call plans reproduce every binding rule
  * fan-in               several wires into one port still arrive as an ordered list
  * scheduler            linear-time back-edge search: large models schedule quickly, loops still found
  * caches               cached expression/constant parsing returns independent copies
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E      # noqa: E402
import knode_library as L     # noqa: E402
import knode_std as ks        # noqa: E402


def node(name, code, inputs=(), outputs=("y",), params=None):
    return {"name": name, "code": code, "inputs": list(inputs), "outputs": list(outputs), "params": params or {}}


def test_stdout_is_attributed_per_node_and_step():
    p = {"nodes": {"1": node("a", "def process(step):\n    print('a', step)\n    return {'y': step}\n"),
                   "2": node("b", "def process(x):\n    print('b', x)\n    return {'y': x}\n", ["x"])},
         "connections": [{"from": "1", "fromPort": "y", "to": "2", "toPort": "x"}]}
    rep = E.simulate(p, steps=2, dt=1)
    assert rep["stdout"]["1"] == "a 0\na 1\na 2\n" and rep["stdout"]["2"] == "b 0\nb 1\nb 2\n"
    assert sys.stdout is sys.__stdout__ or not isinstance(sys.stdout, E._StdoutRouter)


def test_stdout_inside_group_surfaces_on_group_node():
    inner = {"nodes": {"1": node("printer", "def process():\n    print('inside')\n    return {}\n", outputs=[])}, "connections": []}
    rep = E.run({"nodes": {"9": dict(node("G", "def process():\n    return {}\n", outputs=[]), subgraph=inner)}, "connections": []})
    assert rep["stdout"]["9"] == "[printer] inside\n"


def test_argument_binding_rules():
    code = ("def process(x=5, y=None, params=None, t=0.0, k=None, missing, **inp):\n"
            "    return {'y': (x, y, params['k'], k, missing, sorted(inp))}\n").replace("missing, **inp", "missing=None, **inp")
    # x unconnected → default 5; y wired; k is a parameter bound by name; extra wire arrives in **inp
    p = {"nodes": {"1": node("n", code, ["x", "y"], params={"k": 3}),
                   "2": node("c", "def process():\n    return {'y': 7}\n")},
         "connections": [{"from": "2", "fromPort": "y", "to": "1", "toPort": "y"},
                         {"from": "2", "fromPort": "y", "to": "1", "toPort": "extra"}]}
    out = E.run(p)["outputs"]["1"]["y"]
    assert out == [5, 7, 3, 3, None, ["extra"]]


def test_fan_in_order_is_preserved():
    nodes = {str(i): node(f"c{i}", f"def process():\n    return {{'y': {i}}}\n") for i in range(4)}
    nodes["9"] = node("sum", "def process(v=None):\n    return {'y': v}\n", ["v"])
    # fan-in lists follow wire creation order (wire id), whatever order the payload lists them in
    conns = [{"id": 10 + k, "from": str(i), "fromPort": "y", "to": "9", "toPort": "v"} for k, i in enumerate((2, 0, 3, 1))]
    conns.reverse()
    assert E.run({"nodes": nodes, "connections": conns})["outputs"]["9"]["y"] == [2, 0, 3, 1]


def test_scheduler_scales_linearly_and_still_finds_loops():
    n = 4000
    nodes = [("const", {"value": 1.0})] + [("gain", {"k": 1.0}) for _ in range(n)]
    wires = [(0, "value", 1, "x")] + [(i, "y", i + 1, "x") for i in range(1, n)]
    g = E.parse_graph(L.build(nodes, wires))
    t0 = time.perf_counter()
    blocks, back, cycles = E.schedule(g)
    assert time.perf_counter() - t0 < 2.0 and not cycles and len(blocks) == n + 1
    # close a loop at the end: exactly one component, one back edge
    g2 = E.parse_graph(L.build(nodes[:4], [(0, "value", 1, "x"), (1, "y", 2, "x"), (2, "y", 3, "x"), (3, "y", 2, "x")]))
    blocks, back, cycles = E.schedule(g2)
    assert [sorted(c) for c in cycles] == [["2", "3"]] and len(back) == 1


def test_expression_and_constant_caches_return_independent_copies():
    a = ks.parse_assignments("k=2, m=k*3")
    a["k"] = 99
    assert ks.parse_assignments("k=2, m=k*3") == {"k": 2.0, "m": 6.0}
    assert ks.compile_expr("x + 1") is ks.compile_expr(" x + 1 ")


def test_broadcast_fast_path_matches_general_path():
    f = lambda a, b: a * 10 + b
    assert ks.broadcast(f, 1, 2) == 12
    assert ks.broadcast(f, [1, 2], 3) == [13, 23]
    assert ks.broadcast(f, (1, 2), [3, 4]) == [13, 24]


def test_optimised_engine_matches_reference_values():
    """Values recorded by running the unmodified 0.4 engine: the optimised engine must reproduce them.

    The agent-based value is an exact integer — it also proves the rewritten population loop draws
    random numbers in exactly the same order as before.
    """
    rep = E.simulate(L.build([("lotka_volterra", {})]), steps=1000, dt=0.01)
    assert abs(rep["traces"]["0.prey"][-1] - 1.122646177468935) < 1e-12
    rep = E.simulate(L.build([("hodgkin_huxley", {})]), steps=400, dt=0.05)
    assert abs(rep["traces"]["0.V"][-1] - (-74.64332145180637)) < 1e-9
    rep = E.simulate(L.build([("agent_based", {})]), steps=100, dt=0.1)
    assert rep["traces"]["0.R"][-1] == 41.0


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
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)

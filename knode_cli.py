"""
knode CLI — run graphs without the editor (reproducible batch science / CI).

  python knode_cli.py run graph.json [--target ID]
  python knode_cli.py simulate graph.json --steps 2000 --dt 0.01 --csv out.csv
  python knode_cli.py analyze graph.json
  python knode_cli.py sweep graph.json --node 3 --param k --values 0:10:21 --target 5.y [--simulate ...]
  python knode_cli.py example pid_control --csv pid.csv
  python knode_cli.py library
  python knode_cli.py examples

graph.json is the editor's JSON export (Export → JSON) or an engine payload.
"""
import argparse
import csv
import json
import sys

import knode_engine as E
import knode_examples as X
import knode_library as L


def load(path):
    """Read a graph JSON file (editor export or engine payload)."""
    with open(path) as f:
        return json.load(f)


def parse_values(spec):
    """Sweep values: 'a:b:n' (n evenly spaced points) or an explicit comma list."""
    if ":" in spec:
        a, b, n = spec.split(":")
        return [float(v) for v in __import__("knode_std").linspace(float(a), float(b), int(n))]
    return [float(v) for v in spec.split(",")]


def write_csv(traces, path):
    """Write simulation traces as CSV with t in the first column (gaps become empty cells)."""
    keys = ["t"] + [k for k in traces if k != "t"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(keys)
        for row in zip(*(traces[k] for k in keys)):
            w.writerow(["" if v is None else v for v in row])
    print(f"wrote {len(traces['t'])} rows × {len(keys)} columns → {path}", file=sys.stderr)


def summarize(rep):
    """Human-readable per-node summary of a run report (✓ ok, ✗ error, · blocked) plus warnings."""
    for nid, st in rep["status"].items():
        mark = {"ok": "✓", "error": "✗", "blocked": "·"}.get(st, "?")
        print(f"{mark} [{nid}] {json.dumps(rep['outputs'].get(nid), default=str)[:300] if st == 'ok' else ''}")
        if st == "error":
            print("   " + rep["errors"][nid]["error"])
    for w in rep.get("warnings", []):
        print("warning:", w, file=sys.stderr)


def main(argv=None):
    """Entry point: sub-commands run / simulate / analyze / sweep / example / library / examples."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run"); p.add_argument("file"); p.add_argument("--target"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("simulate"); p.add_argument("file"); p.add_argument("--steps", type=int, default=1000)
    p.add_argument("--dt", type=float, default=0.01); p.add_argument("--csv"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("analyze"); p.add_argument("file")
    p = sub.add_parser("sweep"); p.add_argument("file"); p.add_argument("--node", required=True)
    p.add_argument("--param", required=True); p.add_argument("--values", required=True)
    p.add_argument("--target", required=True, help="NODE.PORT"); p.add_argument("--simulate", action="store_true")
    p.add_argument("--steps", type=int, default=500); p.add_argument("--dt", type=float, default=0.01)
    p.add_argument("--reduce", default="last")
    p = sub.add_parser("example"); p.add_argument("id"); p.add_argument("--csv"); p.add_argument("--save")
    sub.add_parser("library"); sub.add_parser("examples")
    a = ap.parse_args(argv)

    if a.cmd == "library":
        for t in L.TEMPLATES:
            print(f"{t['category']:<24} {t['id']:<20} {t['name']}")
        return 0
    if a.cmd == "examples":
        for e in X.EXAMPLES:
            print(f"{e['domain']:<16} {e['id']:<18} {e['title']}")
        return 0
    if a.cmd == "example":
        ex = X.get_example(a.id)
        payload = X.to_payload(ex)
        if a.save:
            json.dump(payload, open(a.save, "w"), indent=2)
        if ex["mode"] == "simulate":
            rep = E.simulate(payload, steps=ex["steps"], dt=ex["dt"])
            if a.csv:
                write_csv(rep["traces"], a.csv)
        else:
            rep = E.run(payload)
        summarize(rep)
        return 0 if rep["success"] else 1
    payload = load(a.file)
    if a.cmd == "run":
        rep = E.run(payload, target=a.target)
        print(json.dumps(rep, indent=2)) if a.json else summarize(rep)
    elif a.cmd == "simulate":
        rep = E.simulate(payload, steps=a.steps, dt=a.dt)
        if a.csv:
            write_csv(rep["traces"], a.csv)
        print(json.dumps(rep, indent=2)) if a.json else summarize(rep)
    elif a.cmd == "analyze":
        print(json.dumps(E.analyze(payload), indent=2))
        return 0
    elif a.cmd == "sweep":
        node, port = a.target.split(".", 1)
        r = E.sweep(payload, a.node, a.param, parse_values(a.values), (node, port),
                    mode="simulate" if a.simulate else "run", reduce=a.reduce, sim={"steps": a.steps, "dt": a.dt})
        print(f"{r['param']},{r['target']}")
        for v, y in zip(r["values"], r["results"]):
            print(f"{v},{y}")
        return 0
    return 0 if rep["success"] else 1


if __name__ == "__main__":
    sys.exit(main())

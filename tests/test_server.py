"""
Tests for the HTTP API and the backend-manager endpoints (knode 0.6), using Flask's test client —
no network, no real restarts.

    python tests/test_server.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_library as L     # noqa: E402
import server                 # noqa: E402

C = server.app.test_client()
REMOTE = {"REMOTE_ADDR": "10.1.2.3"}


def test_health_reports_process_identity():
    h = C.get("/api/health").get_json()
    assert h["ok"] and h["pid"] == os.getpid() and "started" in h and "supervised" in h


def test_execute_simulate_and_reroute_through_http():
    g = L.build([("const", {"value": 7}), ("reroute", {}), ("gain", {"k": 3})], [(0, "value", 1, "in"), (1, "out", 2, "x")])
    assert C.post("/graph/execute", json=g).get_json()["outputs"]["2"]["y"] == 21
    rep = C.post("/graph/simulate", json=dict(L.build([("logistic_growth", {})]), steps=10, dt=0.1)).get_json()
    assert rep["success"] and len(rep["traces"]["t"]) == 11


def test_admin_info_and_settings_roundtrip():
    info = C.get("/admin/info").get_json()
    assert info["pid"] == os.getpid() and "packages" in info and "sessions" in info
    s = C.post("/admin/settings", json={"cache_size": 64, "session_idle_minutes": 3, "time_limit": 30}).get_json()["settings"]
    assert s["cache_size"] == 64 and abs(s["session_idle_minutes"] - 3) < 1e-9 and s["time_limit"] == 30
    C.post("/admin/settings", json={"cache_size": 512, "session_idle_minutes": 30, "time_limit": 120})


def test_parallel_worker_setting():
    info = C.post("/admin/settings", json={"workers": 2}).get_json()
    assert info["settings"]["workers"] == 2 and info["workers_in_use"] == 2 and info["cpu_count"] >= 1
    info = C.post("/admin/settings", json={"workers": 0}).get_json()
    assert info["settings"]["workers"] == 0
    import knode_engine as E
    E.shutdown_pool()


def test_logs_are_incremental():
    last = C.get("/admin/logs?since=0").get_json()["last"]
    C.post("/graph/execute", json=L.build([("const", {})]))
    new = C.get(f"/admin/logs?since={last}").get_json()["lines"]
    assert any("/graph/execute" in line[3] for line in new)


def test_install_allowlist():
    r = C.post("/admin/install", json={"package": "requests"})
    assert r.status_code == 400 and "only" in r.get_json()["error"]


def test_admin_is_refused_for_remote_clients():
    for method, path in [("get", "/admin/info"), ("get", "/admin/logs"), ("post", "/admin/restart"),
                         ("post", "/admin/shutdown"), ("post", "/admin/install"), ("post", "/admin/settings")]:
        r = getattr(C, method)(path, environ_base=REMOTE, json={} if method == "post" else None)
        assert r.status_code == 403, (path, r.status_code)
    # …while normal model execution still works for them
    assert C.post("/graph/execute", json=L.build([("const", {})]), environ_base=REMOTE).status_code == 200


def test_session_listing_and_kill():
    sid = C.post("/session/start", json=dict(L.build([("lotka_volterra", {})]), dt=0.01)).get_json()["id"]
    C.post("/session/step", json={"id": sid, "n": 5})
    assert any(s["id"] == sid and s["steps"] == 5 for s in C.get("/admin/info").get_json()["sessions"])
    assert C.delete(f"/admin/sessions/{sid}").get_json()["success"]
    assert C.post("/session/step", json={"id": sid, "n": 1}).status_code == 404


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

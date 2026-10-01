"""Network-device library verification for knode 0.8."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import knode_engine as E  # noqa: E402
import knode_library as L  # noqa: E402


def test_network_library_and_presets():
    lib = L.get_library()
    ids = {t["id"] for t in lib["templates"]}
    assert {"network_device", "network_router", "network_switch", "network_ap", "network_host", "network_monitor", "network_duplex_link"} <= ids
    presets = {p["id"]: p for p in lib["network_presets"]}
    assert len(presets["mikrotik_rb5009"]["all_interfaces"]) == 9
    assert len(presets["mikrotik_crs326"]["all_interfaces"]) == 26
    assert len(presets["cisco_c9200l_24t_4g"]["all_interfaces"]) == 28


def test_switch_learns_and_ping_round_trips():
    h1 = L.instantiate("network_host", "h1", {"hostname": "pc1", "ip": "192.168.1.10", "mac": "02:00:00:00:00:10", "ping_destination": "192.168.1.20", "send_every": 5})
    sw = L.instantiate("network_switch", "s1", {"interfaces": "eth1,eth2"})
    h2 = L.instantiate("network_host", "h2", {"hostname": "pc2", "ip": "192.168.1.20", "mac": "02:00:00:00:00:20", "ping_destination": ""})
    graph = {"nodes": {"h1": h1, "s1": sw, "h2": h2}, "connections": [
        {"from": "h1", "fromPort": "eth0", "to": "s1", "toPort": "eth1"},
        {"from": "s1", "fromPort": "eth1", "to": "h1", "toPort": "eth0"},
        {"from": "h2", "fromPort": "eth0", "to": "s1", "toPort": "eth2"},
        {"from": "s1", "fromPort": "eth2", "to": "h2", "toPort": "eth0"},
    ]}
    rep = E.simulate(graph, steps=35, dt=1, max_points=1000)
    assert rep["success"], rep["errors"]
    assert rep["outputs"]["h1"]["status"]["echo_replies"] > 0
    table = rep["outputs"]["s1"]["status"]["mac_table"]
    assert table["02:00:00:00:00:10"] == "eth1" and table["02:00:00:00:00:20"] == "eth2"


def test_router_longest_prefix_forwards_ping():
    h1 = L.instantiate("network_host", "h1", {"hostname": "pc1", "ip": "192.168.1.10", "mac": "02:00:00:00:00:10", "ping_destination": "192.168.2.20", "send_every": 6})
    router = L.instantiate("network_router", "r1", {"hostname": "r1", "interfaces": "lan0,wan0", "interface_ips": "lan0=192.168.1.1/24\nwan0=192.168.2.1/24", "routes": "0.0.0.0/0=wan0\n192.168.1.0/24=lan0\n192.168.2.0/24=wan0"})
    h2 = L.instantiate("network_host", "h2", {"hostname": "pc2", "ip": "192.168.2.20", "mac": "02:00:00:00:00:20", "ping_destination": ""})
    graph = {"nodes": {"h1": h1, "r1": router, "h2": h2}, "connections": [
        {"from": "h1", "fromPort": "eth0", "to": "r1", "toPort": "lan0"},
        {"from": "r1", "fromPort": "lan0", "to": "h1", "toPort": "eth0"},
        {"from": "h2", "fromPort": "eth0", "to": "r1", "toPort": "wan0"},
        {"from": "r1", "fromPort": "wan0", "to": "h2", "toPort": "eth0"},
    ]}
    rep = E.simulate(graph, steps=45, dt=1, max_points=1000)
    assert rep["success"], rep["errors"]
    st = rep["outputs"]["h1"]["status"]
    assert st["echo_replies"] > 0 and "r1" in st["last_trace"]
    assert rep["outputs"]["r1"]["status"]["no_route"] == 0


def test_duplex_link_delay():
    link = L.instantiate("network_duplex_link", "l", {"delay_steps": 2, "loss": 0.0})
    # Drive one side from a constant frame. The delayed output must eventually appear.
    src = L.instantiate("const", "c", {"value": {"kind": "ipv4", "bytes": 64}})
    graph = {"nodes": {"c": src, "l": link}, "connections": [{"from": "c", "fromPort": "value", "to": "l", "toPort": "a"}]}
    rep = E.simulate(graph, steps=5, dt=1, max_points=100)
    assert rep["success"], rep["errors"]
    assert rep["outputs"]["l"]["to_b"] == {"kind": "ipv4", "bytes": 64}
    assert rep["outputs"]["l"]["queued"] == 2


def test_internet_and_console_nodes_are_registered():
    lib = L.get_library()
    ids = {t["id"] for t in lib["templates"]}
    assert {"network_internet", "network_console"} <= ids


def test_console_is_allowlisted_and_not_a_shell():
    import knode_network as N
    help_result = N.run_console_command("help")
    assert help_result["success"] and "ping HOST" in help_result["stdout"]
    denied = N.run_console_command("sh -c whoami")
    assert not denied["success"]
    assert "unsupported syntax" in denied["stderr"]


def test_internet_disabled_by_default_does_not_probe():
    internet = L.instantiate("network_internet", "net")
    src = L.instantiate("const", "c", {"value": {"protocol": "icmp", "icmp_type": "echo-request", "src_ip": "10.0.0.2", "dst_ip": "1.1.1.1"}})
    graph = {"nodes": {"c": src, "net": internet}, "connections": [
        {"from": "c", "fromPort": "value", "to": "net", "toPort": "lan"},
    ]}
    rep = E.simulate(graph, steps=2, dt=1, max_points=20)
    assert rep["success"], rep["errors"]
    assert rep["outputs"]["net"]["lan"] is None
    assert rep["outputs"]["net"]["status"]["enabled"] is False


def test_internet_translates_real_probe_result(monkeypatch):
    import knode_network as N

    def fake_probe(frame, timeout=4.0, allow_private=False):
        return {"success": True, "tool": "ping", "rtt_ms": 12.5, "stdout": "ok", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(N, "host_network_probe", fake_probe)
    internet = L.instantiate("network_internet", "net", {"enabled": True, "cache_seconds": 0})
    src = L.instantiate("const", "c", {"value": {"protocol": "icmp", "icmp_type": "echo-request", "src_ip": "192.0.2.10", "src_mac": "02:00:00:00:00:10", "dst_ip": "1.1.1.1", "trace": ["pc"]}})
    graph = {"nodes": {"c": src, "net": internet}, "connections": [
        {"from": "c", "fromPort": "value", "to": "net", "toPort": "lan"},
    ]}
    rep = E.simulate(graph, steps=2, dt=1, max_points=20)
    assert rep["success"], rep["errors"]
    f = rep["outputs"]["net"]["lan"]
    assert f["icmp_type"] == "echo-reply"
    assert f["real_host_network"] is True
    assert f["rtt_ms"] == 12.5


def test_more_network_templates_are_registered():
    lib = L.get_library()
    ids = {t["id"] for t in lib["templates"]}
    assert {
        "network_hub", "network_bridge", "network_server", "network_laptop",
        "network_mikrotik_rb5009", "network_mikrotik_crs326", "network_mikrotik_cap_ax",
        "network_cisco_isr4331", "network_cisco_c9200l_24t_4g", "network_cisco_c9115",
    } <= ids


def test_idle_network_nodes_use_sparse_fast_path():
    nodes = {str(i): L.instantiate("network_switch", str(i), {"interfaces": "eth1,eth2,eth3,eth4"}) for i in range(12)}
    rep = E.simulate({"nodes": nodes, "connections": []}, steps=100, dt=1, max_points=20)
    assert rep["success"], rep["errors"]
    assert sum(rep["idle_skips"].values()) >= 12 * 99
    assert sum(p["calls"] for p in rep["profile"].values()) == 12


def test_new_network_examples_execute_and_deliver_ping():
    import knode_examples as X

    for eid in ("network_two_subnets", "network_wifi_lan", "network_wan_delay_loss", "network_packet_monitor", "network_mixed_vendor"):
        ex = X.get_example(eid)
        rep = E.simulate(X.to_payload(ex), steps=ex["steps"], dt=ex["dt"], max_points=1000)
        assert rep["success"], (eid, rep["errors"])
        assert rep["outputs"]["0"]["status"]["echo_replies"] > 0, eid

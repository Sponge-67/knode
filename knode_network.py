"""Network-device modelling nodes and hardware presets for knode.

This is deliberately a packet-level *teaching / topology* simulator rather than an
emulator of RouterOS or IOS.  A network frame is a normal Python dict flowing over
knode wires.  Stateful network nodes forward one hop per simulation step, which
makes packet paths, switching tables and routing decisions observable in the same
execution engine used by every other knode model. In 0.8.2 these built-ins also cooperate
with the engine's event-driven idle fast path, so quiet network topologies do not burn CPU.
"""
from __future__ import annotations

import ipaddress
import os
import re
import shlex
import shutil
import socket
import subprocess
import time

NETWORK_COLOR = "#18a6a6"


def _eth(prefix: str, n: int):
    return [f"{prefix}{i}" for i in range(1, n + 1)]


# Presets have two interface lists: ``interfaces`` is a compact useful default so
# large switches remain readable on the canvas; ``all_interfaces`` can be applied
# from the Properties panel when every physical port should be exposed.
PRESETS = [
    {
        "id": "generic_router", "vendor": "Generic", "model": "Custom Router", "role": "router",
        "os": "custom", "interfaces": ["wan0", "lan0", "lan1"],
        "all_interfaces": ["wan0", "lan0", "lan1"],
        "physical_ports": "user-defined logical interfaces",
    },
    {
        "id": "generic_switch", "vendor": "Generic", "model": "Custom L2 Switch", "role": "switch",
        "os": "custom", "interfaces": ["eth1", "eth2", "eth3", "eth4"],
        "all_interfaces": _eth("eth", 8), "physical_ports": "user-defined Ethernet ports",
    },
    {
        "id": "generic_ap", "vendor": "Generic", "model": "Custom Access Point", "role": "access_point",
        "os": "custom", "interfaces": ["ether1", "wlan2g", "wlan5g"],
        "all_interfaces": ["ether1", "wlan2g", "wlan5g"], "physical_ports": "Ethernet + wireless bridge interfaces",
    },
    {
        "id": "mikrotik_rb5009", "vendor": "MikroTik", "model": "RB5009UG+S+IN", "role": "router",
        "os": "RouterOS v7", "interfaces": ["ether1", "ether2", "ether3", "ether8-2.5G", "sfp-sfpplus1"],
        "all_interfaces": _eth("ether", 7) + ["ether8-2.5G", "sfp-sfpplus1"],
        "physical_ports": "7×1G Ethernet + 1×2.5G Ethernet + 1×10G SFP+",
        "source": "https://mikrotik.com/product/rb5009ug_s_in",
    },
    {
        "id": "mikrotik_crs326", "vendor": "MikroTik", "model": "CRS326-24G-2S+RM", "role": "switch",
        "os": "RouterOS / SwitchOS", "interfaces": ["ether1", "ether2", "ether3", "ether4", "sfp-sfpplus1", "sfp-sfpplus2"],
        "all_interfaces": _eth("ether", 24) + ["sfp-sfpplus1", "sfp-sfpplus2"],
        "physical_ports": "24×1G Ethernet + 2×SFP+",
        "source": "https://mikrotik.com/product/CRS326-24G-2SplusRM",
    },
    {
        "id": "mikrotik_cap_ax", "vendor": "MikroTik", "model": "cAP ax", "role": "access_point",
        "os": "RouterOS v7", "interfaces": ["ether1", "ether2", "wlan2g", "wlan5g"],
        "all_interfaces": ["ether1", "ether2", "wlan2g", "wlan5g"],
        "physical_ports": "2×1G Ethernet + dual-band Wi-Fi 6 radios",
        "source": "https://mikrotik.com/product/cap_ax",
    },
    {
        "id": "cisco_isr4331", "vendor": "Cisco", "model": "ISR 4331", "role": "router",
        "os": "IOS XE", "interfaces": ["Gi0/0/0", "Gi0/0/1", "Gi0/0/2"],
        "all_interfaces": ["Gi0/0/0", "Gi0/0/1", "Gi0/0/2"],
        "physical_ports": "3 onboard 10/100/1000 WAN/LAN interfaces (plus modular expansion)",
        "source": "https://www.cisco.com/c/en/us/products/collateral/routers/4000-series-integrated-services-routers-isr/data_sheet-c78-732542.html",
    },
    {
        "id": "cisco_c9200l_24t_4g", "vendor": "Cisco", "model": "Catalyst C9200L-24T-4G", "role": "switch",
        "os": "IOS XE", "interfaces": ["Gi1/0/1", "Gi1/0/2", "Gi1/0/3", "Gi1/0/4", "Gi1/1/1", "Gi1/1/2", "Gi1/1/3", "Gi1/1/4"],
        "all_interfaces": [f"Gi1/0/{i}" for i in range(1, 25)] + [f"Gi1/1/{i}" for i in range(1, 5)],
        "physical_ports": "24×1G access ports + 4×1G SFP fixed uplinks",
        "source": "https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9200/hardware/install/b-c9200-hig/product_overview.html",
    },
    {
        "id": "cisco_c9115", "vendor": "Cisco", "model": "Catalyst 9115", "role": "access_point",
        "os": "Cisco wireless", "interfaces": ["mGig0", "wlan2g", "wlan5g"],
        "all_interfaces": ["mGig0", "wlan2g", "wlan5g"],
        "physical_ports": "1×100/1000/2500 Multigigabit Ethernet + 2.4/5 GHz Wi-Fi 6 radios",
        "source": "https://www.cisco.com/c/en/us/products/collateral/wireless/catalyst-9100ax-access-points/datasheet-c78-741988.html",
    },
]

# ---------------------------------------------------------------------------
# Host-network bridge helpers
# ---------------------------------------------------------------------------
# These helpers deliberately do not use a shell. They are shared by the
# Internet and Console nodes and by the localhost-only convenience endpoint.


def _public_or_allowed_target(target: str, allow_private: bool = False):
    """Resolve target and reject local/private addresses unless explicitly allowed."""
    target = str(target or "").strip()
    if not target or len(target) > 253 or any(c.isspace() for c in target):
        raise ValueError("target must be one hostname or IP address")
    try:
        infos = socket.getaddrinfo(target, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"cannot resolve {target}: {e}") from None
    addrs = []
    for info in infos:
        a = info[4][0].split("%", 1)[0]
        if a not in addrs:
            addrs.append(a)
    if not addrs:
        raise ValueError(f"cannot resolve {target}")
    if not allow_private:
        for raw in addrs:
            ip = ipaddress.ip_address(raw)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
                raise ValueError(f"{target} resolves to non-public address {raw}; enable private/LAN targets explicitly")
    return target, addrs


def _bounded_run(argv, timeout=5.0, max_output=16000):
    """Run one already-tokenised diagnostic command without a shell and return bounded output."""
    timeout = max(0.2, min(30.0, float(timeout or 5.0)))
    max_output = max(1000, min(100000, int(max_output or 16000)))
    t0 = time.perf_counter()
    try:
        cp = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, errors="replace", timeout=timeout,
                            env=dict(os.environ, LC_ALL="C", LANG="C"))
        out, err, rc = cp.stdout or "", cp.stderr or "", int(cp.returncode)
        timed_out = False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ((e.stdout or b"").decode(errors="replace"))
        err = (e.stderr or "") if isinstance(e.stderr, str) else ((e.stderr or b"").decode(errors="replace"))
        err = (err + f"\nTimed out after {timeout:g} s").strip()
        rc, timed_out = 124, True
    return {"success": rc == 0, "exit_code": rc, "stdout": out[:max_output], "stderr": err[:max_output],
            "duration_ms": round((time.perf_counter() - t0) * 1000, 2), "argv": list(argv), "timed_out": timed_out}


def _ping(target, count=1, timeout=5.0, allow_private=False):
    target, addrs = _public_or_allowed_target(target, allow_private)
    exe = shutil.which("ping")
    if not exe:
        raise RuntimeError("ping executable is not installed")
    count = max(1, min(10, int(count or 1)))
    if os.name == "nt":
        argv = [exe, "-n", str(count), "-w", str(max(250, int(float(timeout) * 1000))), target]
    else:
        argv = [exe, "-c", str(count), target]
    r = _bounded_run(argv, timeout=max(float(timeout), count * 0.5 + 0.5))
    times = [float(x) for x in re.findall(r"time[=<]([0-9.]+)\s*ms", r["stdout"], re.I)]
    r.update(tool="ping", target=target, resolved=addrs, count=count,
             rtt_ms=(round(sum(times) / len(times), 3) if times else None))
    return r


def _dns(target, allow_private=True):
    t0 = time.perf_counter()
    target = str(target or "").strip()
    if not target or any(c.isspace() for c in target):
        raise ValueError("dns needs one hostname or IP address")
    try:
        ip = ipaddress.ip_address(target.split("%", 1)[0])
        if not allow_private and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved):
            raise PermissionError(f"non-public address {ip}; enable private/LAN targets explicitly")
        host, aliases, addrs = socket.gethostbyaddr(str(ip))
        answers = [host] + aliases + addrs
    except ValueError:
        _, answers = _public_or_allowed_target(target, allow_private)
    except (socket.herror, socket.gaierror) as e:
        return {"success": False, "exit_code": 1, "stdout": "", "stderr": str(e), "tool": "dns", "target": target,
                "answers": [], "duration_ms": round((time.perf_counter() - t0) * 1000, 2)}
    answers = list(dict.fromkeys(map(str, answers)))
    return {"success": True, "exit_code": 0, "stdout": "\n".join(answers) + ("\n" if answers else ""), "stderr": "",
            "tool": "dns", "target": target, "answers": answers,
            "duration_ms": round((time.perf_counter() - t0) * 1000, 2)}


def _tcp_probe(target, port=443, timeout=5.0, allow_private=False):
    target, addrs = _public_or_allowed_target(target, allow_private)
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("TCP port must be 1..65535")
    timeout = max(0.2, min(30.0, float(timeout or 5.0)))
    t0 = time.perf_counter()
    try:
        with socket.create_connection((target, port), timeout=timeout) as sock:
            peer = sock.getpeername()[0]
        ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"success": True, "exit_code": 0, "stdout": f"Connected to {target}:{port} ({peer}) in {ms} ms\n", "stderr": "",
                "tool": "tcp", "target": target, "resolved": addrs, "port": port, "peer": peer, "duration_ms": ms}
    except OSError as e:
        ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"success": False, "exit_code": 1, "stdout": "", "stderr": str(e), "tool": "tcp", "target": target,
                "resolved": addrs, "port": port, "duration_ms": ms}


def _trace(target, timeout=10.0, max_hops=20, allow_private=False):
    target, addrs = _public_or_allowed_target(target, allow_private)
    max_hops = max(1, min(64, int(max_hops or 20)))
    if os.name == "nt":
        exe = shutil.which("tracert")
        if not exe:
            raise RuntimeError("tracert is not installed")
        argv = [exe, "-d", "-h", str(max_hops), target]
        tool = "tracert"
    else:
        exe = shutil.which("traceroute")
        if exe:
            argv, tool = [exe, "-n", "-m", str(max_hops), target], "traceroute"
        else:
            exe = shutil.which("tracepath")
            if not exe:
                raise RuntimeError("neither traceroute nor tracepath is installed")
            argv, tool = [exe, "-n", "-m", str(max_hops), target], "tracepath"
    r = _bounded_run(argv, timeout=timeout)
    r.update(tool=tool, target=target, resolved=addrs, max_hops=max_hops)
    return r


def _ip_show(section):
    aliases = {"addr": "addr", "address": "addr", "route": "route", "neigh": "neigh", "neighbor": "neigh", "link": "link"}
    sec = aliases.get(str(section or "").lower())
    if not sec:
        raise ValueError("ip supports only: addr, route, neigh, link")
    exe = shutil.which("ip")
    if exe:
        argv = [exe, sec, "show"]
        shown_as = "ip"
    elif os.name == "nt":
        if sec in ("addr", "link"):
            exe = shutil.which("ipconfig")
            argv = [exe, "/all"] if exe else None
        elif sec == "route":
            exe = shutil.which("route")
            argv = [exe, "print"] if exe else None
        else:
            exe = shutil.which("arp")
            argv = [exe, "-a"] if exe else None
        shown_as = "windows-network"
    else:
        if sec in ("addr", "link"):
            exe = shutil.which("ifconfig")
            argv = [exe, "-a"] if exe else None
        elif sec == "route":
            exe = shutil.which("netstat")
            argv = [exe, "-rn"] if exe else None
        else:
            exe = shutil.which("arp")
            argv = [exe, "-a"] if exe else None
        shown_as = "posix-network"
    if not argv:
        raise RuntimeError("no supported read-only interface/route utility is installed")
    r = _bounded_run(argv, timeout=5.0)
    r.update(tool=shown_as, section=sec)
    return r


def run_console_command(command: str, timeout=8.0, allow_private=True):
    """Run one bounded network diagnostic; no shell or arbitrary executables are accepted."""
    parts = shlex.split(str(command or "").strip())
    if not parts:
        return {"success": True, "exit_code": 0, "stdout": "Type 'help' for supported commands.\n", "stderr": "", "tool": "help"}
    tool = parts[0].lower()
    try:
        if tool == "help":
            return {"success": True, "exit_code": 0, "stdout":
                    "ping HOST [COUNT]\ntraceroute HOST [MAX_HOPS]\ntracepath HOST [MAX_HOPS]\ndns HOST\ntcp HOST PORT\nip addr|route|neigh|link\nhostname\n",
                    "stderr": "", "tool": "help"}
        if tool == "ping" and 2 <= len(parts) <= 3:
            return _ping(parts[1], int(parts[2]) if len(parts) == 3 else 4, timeout, allow_private)
        if tool in ("traceroute", "tracert", "tracepath") and 2 <= len(parts) <= 3:
            return _trace(parts[1], timeout, int(parts[2]) if len(parts) == 3 else 20, allow_private)
        if tool in ("dns", "resolve", "nslookup", "host", "dig") and len(parts) == 2:
            return _dns(parts[1], allow_private)
        if tool in ("tcp", "connect") and len(parts) == 3:
            return _tcp_probe(parts[1], int(parts[2]), timeout, allow_private)
        if tool == "ip" and len(parts) == 2:
            return _ip_show(parts[1])
        if tool in ("route", "routes") and len(parts) == 1:
            return _ip_show("route")
        if tool in ("interfaces", "ifaces") and len(parts) == 1:
            return _ip_show("addr")
        if tool == "hostname" and len(parts) == 1:
            h = socket.gethostname()
            return {"success": True, "exit_code": 0, "stdout": h + "\n", "stderr": "", "tool": "hostname", "hostname": h}
        raise ValueError("unsupported syntax; type 'help'")
    except Exception as e:
        return {"success": False, "exit_code": 2, "stdout": "", "stderr": f"{type(e).__name__}: {e}", "tool": tool}


def host_network_probe(frame: dict, timeout=4.0, allow_private=False):
    """Translate one simulated diagnostic frame into a real host-network probe."""
    if not isinstance(frame, dict):
        return {"success": False, "error": "frame must be an object", "tool": "unknown"}
    proto = str(frame.get("protocol", "")).lower()
    if proto == "icmp" and frame.get("icmp_type") == "echo-request":
        return _ping(frame.get("dst_ip") or frame.get("host"), 1, timeout, allow_private)
    if proto in ("dns", "dns-query"):
        return _dns(frame.get("query") or frame.get("host") or frame.get("dst_ip"), allow_private)
    if proto in ("tcp", "tcp-probe"):
        return _tcp_probe(frame.get("host") or frame.get("dst_ip"), frame.get("dst_port", frame.get("port", 443)), timeout, allow_private)
    return {"success": False, "exit_code": 2, "tool": proto or "unknown", "stderr": "Internet node supports ICMP echo, DNS query, and TCP probe frames"}


DEVICE_CODE = r'''
# Packet-level network device.  Frames are dicts and a port may carry one frame
# or a list of frames.  Use Simulate: every stateful device advances traffic by
# one hop per step, avoiding zero-time forwarding loops.
import ipaddress

BCAST = "ff:ff:ff:ff:ff:ff"


def _items(v):
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for x in v:
            out.extend(_items(x))
        return out
    return [v]


def _ports(params):
    return [x.strip() for x in str(params.get("interfaces", "")).replace("\n", ",").split(",") if x.strip()]


def _emit(out, port, frame):
    if port not in out or frame is None:
        return
    if out[port] is None:
        out[port] = frame
    elif isinstance(out[port], list):
        out[port].append(frame)
    else:
        out[port] = [out[port], frame]


def _route_table(text):
    rows = []
    for raw in str(text or "").replace(";", "\n").splitlines():
        raw = raw.split("#", 1)[0].strip()
        if not raw or "=" not in raw:
            continue
        net, rhs = [x.strip() for x in raw.split("=", 1)]
        parts = [x.strip() for x in rhs.split(",")]
        try:
            nw = ipaddress.ip_network(net, strict=False)
            rows.append((nw.prefixlen, nw, parts[0], parts[1] if len(parts) > 1 else ""))
        except Exception:
            pass
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def _if_ips(text):
    out = {}
    for raw in str(text or "").replace(";", "\n").splitlines():
        raw = raw.split("#", 1)[0].strip()
        if not raw or "=" not in raw:
            continue
        p, addr = [x.strip() for x in raw.split("=", 1)]
        try:
            out[p] = ipaddress.ip_interface(addr)
        except Exception:
            pass
    return out


def _switch_frame(out, ports, ingress, f, mac):
    src = str(f.get("src_mac", "")).lower()
    dst = str(f.get("dst_mac", BCAST)).lower()
    if src:
        mac[src] = ingress
    target = mac.get(dst)
    if target in ports and target != ingress and dst != BCAST:
        _emit(out, target, f)
    else:
        for p in ports:
            if p != ingress:
                _emit(out, p, f)


def _router_frame(out, ports, ingress, f, routes, locals_, state, params):
    if not isinstance(f, dict) or not f.get("dst_ip"):
        state["dropped"] = state.get("dropped", 0) + 1
        return
    try:
        dst = ipaddress.ip_address(str(f["dst_ip"]))
    except Exception:
        state["dropped"] = state.get("dropped", 0) + 1
        return

    # ICMP echo to a router interface: reply out the ingress port.  This is a
    # compact substitute for a complete ARP/ND/control-plane implementation.
    local_ips = {str(v.ip) for v in locals_.values()}
    if str(dst) in local_ips and f.get("protocol") == "icmp" and f.get("icmp_type") == "echo-request":
        r = dict(f)
        r["src_ip"], r["dst_ip"] = f.get("dst_ip"), f.get("src_ip")
        r["src_mac"], r["dst_mac"] = f.get("dst_mac", ""), f.get("src_mac", BCAST)
        r["icmp_type"] = "echo-reply"
        r["ttl"] = int(params.get("ttl", 64))
        r["trace"] = list(f.get("trace", [])) + [params.get("hostname", params.get("model", "router"))]
        _emit(out, ingress, r)
        state["local_replies"] = state.get("local_replies", 0) + 1
        return

    ttl = int(f.get("ttl", params.get("ttl", 64))) - 1
    if ttl <= 0:
        state["ttl_expired"] = state.get("ttl_expired", 0) + 1
        return
    target = None; next_hop = ""
    for _, net, port, nh in routes:
        if dst in net:
            target, next_hop = port, nh
            break
    if target not in ports:
        state["no_route"] = state.get("no_route", 0) + 1
        return
    r = dict(f)
    r["ttl"] = ttl
    if next_hop: r["next_hop"] = next_hop
    r["trace"] = list(f.get("trace", [])) + [params.get("hostname", params.get("model", "router"))]
    _emit(out, target, r)


def process(params=None, state=None, **inputs):
    params = params or {}
    state = state if state is not None else {}
    # Parsing CIDRs/interfaces on every simulation tick was expensive in large topologies.
    # Cache the derived configuration until one of the source parameters changes.
    cfg_key = (str(params.get("interfaces", "")), str(params.get("role", "switch")).lower(),
               str(params.get("routes", "")), str(params.get("interface_ips", "")))
    if state.get("_cfg_key") != cfg_key:
        state["_cfg_key"] = cfg_key
        state["_ports"] = _ports(params)
        state["_role"] = cfg_key[1]
        state["_routes"] = _route_table(cfg_key[2])
        state["_locals"] = _if_ips(cfg_key[3])
    ports = state["_ports"]
    out = {p: None for p in ports}
    role = state["_role"]
    mac = state.setdefault("mac_table", {})
    routes = state["_routes"]
    locals_ = state["_locals"]
    rx = tx = 0

    for ingress in ports:
        for f in _items(inputs.get(ingress)):
            if not isinstance(f, dict):
                continue
            rx += 1
            if role in ("switch", "access_point", "bridge"):
                _switch_frame(out, ports, ingress, f, mac)
            elif role == "router":
                _router_frame(out, ports, ingress, f, routes, locals_, state, params)
            elif role == "hub":
                for p in ports:
                    if p != ingress:
                        _emit(out, p, f)
            else:  # custom device defaults to transparent learning bridge
                _switch_frame(out, ports, ingress, f, mac)

    for p in ports:
        if out[p] is not None:
            tx += len(out[p]) if isinstance(out[p], list) else 1
    state["rx"] = state.get("rx", 0) + rx
    state["tx"] = state.get("tx", 0) + tx
    out["status"] = {
        "vendor": params.get("vendor", "Generic"), "model": params.get("model", "Custom"),
        "role": role, "rx": state.get("rx", 0), "tx": state.get("tx", 0),
        "mac_table": dict(mac), "no_route": state.get("no_route", 0),
        "dropped": state.get("dropped", 0), "ttl_expired": state.get("ttl_expired", 0),
    }
    return out
'''.strip() + "\n"


HOST_CODE = r'''
# A small endpoint that can periodically originate ICMP echo requests and reply
# to requests addressed to itself.  It is enough to make end-to-end topology
# tests visible without implementing an entire operating-system network stack.
def _items(v):
    if v is None: return []
    if isinstance(v, list):
        out = []
        for x in v: out.extend(_items(x))
        return out
    return [v]


def process(params=None, state=None, step=0, **inputs):
    params = params or {}; state = state if state is not None else {}
    iface = str(params.get("interface", "eth0"))
    out = {iface: None}
    rx = _items(inputs.get(iface))
    replies = []
    received = state.get("received", 0)
    for f in rx:
        if not isinstance(f, dict): continue
        if str(f.get("dst_ip", "")) != str(params.get("ip", "")): continue
        received += 1
        if f.get("protocol") == "icmp" and f.get("icmp_type") == "echo-request":
            r = dict(f)
            r["src_ip"], r["dst_ip"] = params.get("ip", ""), f.get("src_ip", "")
            r["src_mac"], r["dst_mac"] = params.get("mac", ""), f.get("src_mac", "ff:ff:ff:ff:ff:ff")
            r["icmp_type"] = "echo-reply"; r["ttl"] = int(params.get("ttl", 64))
            r["trace"] = list(f.get("trace", [])) + [params.get("hostname", "host")]
            replies.append(r)
        elif f.get("protocol") == "icmp" and f.get("icmp_type") == "echo-reply":
            state["echo_replies"] = state.get("echo_replies", 0) + 1
            state["last_trace"] = list(f.get("trace", []))

    dest = str(params.get("ping_destination", "")).strip()
    every = max(1, int(params.get("send_every", 10) or 10))
    generated = None
    if dest and step % every == 0:
        seq = state.get("seq", 0) + 1; state["seq"] = seq
        generated = {"kind": "ipv4", "protocol": "icmp", "icmp_type": "echo-request", "seq": seq,
                     "src_ip": params.get("ip", ""), "dst_ip": dest,
                     "src_mac": params.get("mac", ""), "dst_mac": "ff:ff:ff:ff:ff:ff",
                     "ttl": int(params.get("ttl", 64)), "bytes": int(params.get("packet_bytes", 64)),
                     "trace": [params.get("hostname", "host")]}
        state["sent"] = state.get("sent", 0) + 1
    frames = replies + ([generated] if generated else [])
    out[iface] = frames[0] if len(frames) == 1 else (frames if frames else None)
    state["received"] = received
    out["status"] = {"sent": state.get("sent", 0), "received": received,
                     "echo_replies": state.get("echo_replies", 0), "last_trace": state.get("last_trace", [])}
    return out
'''.strip() + "\n"

INTERNET_CODE = r'''
# Real host-network gateway. Supported simulated probes are translated to the
# backend machine's actual network stack; this is not a raw Ethernet/TUN bridge.
import time
import knode_network as knet

def _items(v):
    if v is None: return []
    if isinstance(v, list):
        out=[]
        for x in v: out.extend(_items(x))
        return out
    return [v]

def process(lan=None, params=None, state=None):
    params = params or {}; state = state if state is not None else {}
    enabled = bool(params.get("enabled", False))
    if not enabled:
        return {"lan": None, "status": {"enabled": False, "message": "real host networking disabled"}, "last_result": state.get("last_result")}
    timeout = max(0.2, min(30.0, float(params.get("timeout", 4.0))))
    allow_private = bool(params.get("allow_private_targets", False))
    cache_s = max(0.0, float(params.get("cache_seconds", 2.0)))
    max_probes = max(1, min(16, int(params.get("max_probes_per_step", 2))))
    replies=[]; attempted=0
    cache = state.setdefault("cache", {})
    for f in _items(lan):
        if not isinstance(f, dict) or attempted >= max_probes: continue
        key = repr((f.get("protocol"), f.get("icmp_type"), f.get("dst_ip"), f.get("host"), f.get("query"), f.get("dst_port"), f.get("port")))
        now=time.monotonic(); hit=cache.get(key)
        if hit and now-hit[0] <= cache_s:
            r=hit[1]
        else:
            r=knet.host_network_probe(f, timeout=timeout, allow_private=allow_private)
            cache[key]=(now,r)
        attempted += 1; state["probes"] = state.get("probes",0)+1; state["last_result"] = r
        if r.get("success"):
            proto=str(f.get("protocol","")).lower()
            if proto=="icmp" and f.get("icmp_type")=="echo-request":
                q=dict(f); q["src_ip"],q["dst_ip"]=f.get("dst_ip"),f.get("src_ip"); q["src_mac"],q["dst_mac"]="host-internet",f.get("src_mac","ff:ff:ff:ff:ff:ff")
                q["icmp_type"]="echo-reply"; q["real_host_network"]=True; q["rtt_ms"]=r.get("rtt_ms"); q["trace"]=list(f.get("trace",[]))+[params.get("label","Internet (host)")]; replies.append(q)
            elif proto in ("dns","dns-query"):
                replies.append({"kind":"dns","protocol":"dns","dns_type":"response","query":f.get("query") or f.get("host"),"answers":r.get("answers",[]),"real_host_network":True})
            elif proto in ("tcp","tcp-probe"):
                replies.append({"kind":"tcp-probe","protocol":"tcp","host":f.get("host") or f.get("dst_ip"),"port":f.get("dst_port",f.get("port",443)),"connected":True,"duration_ms":r.get("duration_ms"),"real_host_network":True})
        else:
            state["failures"] = state.get("failures",0)+1
    out = replies[0] if len(replies)==1 else (replies if replies else None)
    return {"lan": out, "last_result": state.get("last_result"), "status": {"enabled":True,"backend_host":True,"probes":state.get("probes",0),"failures":state.get("failures",0),"last_tool":(state.get("last_result") or {}).get("tool"),"last_success":(state.get("last_result") or {}).get("success")}}
'''.strip() + "\n"


CONSOLE_CODE = r'''
# Read-only/bounded network diagnostics on the backend machine. The helper uses
# no shell and accepts only documented network-tool syntax.
import knode_network as knet

def process(command=None, trigger=None, params=None, state=None):
    params=params or {}; state=state if state is not None else {}
    cmd=str(command if command not in (None,"") else params.get("command","help")).strip()
    token=trigger if trigger is not None else params.get("run_token",0)
    enabled=bool(params.get("enabled",False))
    key=(cmd,repr(token),enabled,float(params.get("timeout",8.0)),bool(params.get("allow_private_targets",True)))
    if not enabled:
        return {"stdout":"","stderr":"Console disabled. Enable it or use Run command in Properties.","exit_code":None,"result":None,"status":{"enabled":False,"command":cmd}}
    if state.get("key") != key:
        state["key"]=key
        state["result"]=knet.run_console_command(cmd, timeout=params.get("timeout",8.0), allow_private=params.get("allow_private_targets",True))
        state["runs"]=state.get("runs",0)+1
    r=state.get("result") or {}
    return {"stdout":r.get("stdout",""),"stderr":r.get("stderr",""),"exit_code":r.get("exit_code"),"result":r,
            "status":{"enabled":True,"command":cmd,"runs":state.get("runs",0),"success":r.get("success"),"tool":r.get("tool"),"duration_ms":r.get("duration_ms")}}
'''.strip() + "\n"


MONITOR_CODE = r'''
def _items(v):
    if v is None: return []
    if isinstance(v, list):
        out=[]
        for x in v: out.extend(_items(x))
        return out
    return [v]

def process(rx=None, params=None, state=None):
    state = state if state is not None else {}
    xs = _items(rx)
    state["packets"] = state.get("packets", 0) + len(xs)
    state["bytes"] = state.get("bytes", 0) + sum(int(x.get("bytes", 0)) for x in xs if isinstance(x, dict))
    if xs: state["last"] = xs[-1]
    return {"tx": rx, "packets": state["packets"], "bytes": state["bytes"], "last": state.get("last")}
'''.strip() + "\n"


LINK_CODE = r'''
def _items(v):
    if v is None: return []
    if isinstance(v, list):
        out=[]
        for x in v: out.extend(_items(x))
        return out
    return [v]

def _dir(v, loss, rng, q, delay_steps, step):
    # Queue by due simulation step so one isolated frame advances with time too. The older
    # length-based queue only released packets when more packets arrived behind them.
    for f in _items(v):
        if rng.random() >= loss:
            q.append((step + delay_steps, f))
    ready=[]
    while q and q[0][0] <= step:
        ready.append(q.pop(0)[1])
    return ready[0] if len(ready) == 1 else (ready if ready else None)

def process(a=None, b=None, params=None, state=None, step=0):
    params = params or {}; state = state if state is not None else {}
    if "rng" not in state: state["rng"] = random.Random(int(params.get("seed", 1)))
    qa = state.setdefault("qa", []); qb = state.setdefault("qb", [])
    loss = max(0.0, min(1.0, float(params.get("loss", 0.0))))
    d = max(0, int(params.get("delay_steps", 0)))
    # input a travels to side B; input b travels to side A
    return {"to_b": _dir(a, loss, state["rng"], qa, d, step), "to_a": _dir(b, loss, state["rng"], qb, d, step),
            "queued": len(qa) + len(qb)}
'''.strip() + "\n"


def _schema(role: str):
    return {
        "role": {"kind": "select", "options": ["router", "switch", "access_point", "bridge", "hub"],
                 "doc": "Forwarding behaviour. Presets set this automatically."},
        "vendor": {"kind": "text"}, "model": {"kind": "text"}, "os": {"kind": "text"},
        "hostname": {"kind": "text"},
        "interfaces": {"kind": "text", "doc": "Comma-separated modelled interfaces; editing this regenerates node ports."},
        "interface_ips": {"kind": "code", "doc": "Router only. One interface=address/prefix per line, e.g. lan0=192.168.1.1/24"},
        "routes": {"kind": "code", "doc": "Router only. CIDR=interface[,next-hop] per line. Longest-prefix match is used."},
        "ssid": {"kind": "text", "doc": "Informational SSID for access-point presets."},
        "ttl": {"kind": "number", "min": 1, "max": 255, "step": 1},
    }


def _device_template(tid: str, name: str, role: str, interfaces: str):
    return {
        "id": tid, "category": "Networking", "name": name,
        "inputs": [x.strip() for x in interfaces.split(",") if x.strip()],
        "outputs": [x.strip() for x in interfaces.split(",") if x.strip()] + ["status"],
        "params": {"role": role, "vendor": "Generic", "model": name, "os": "custom", "hostname": name.lower().replace(" ", "-"),
                   "interfaces": interfaces, "interface_ips": "", "routes": "", "ssid": "knode", "ttl": 64},
        "code": DEVICE_CODE,
        "description": "Packet-level network device with dynamic interface ports. Switch/AP modes learn MAC addresses; router mode uses longest-prefix IPv4 routes. Use ▶▶ Simulate to move traffic hop by hop.",
        "stateful": True, "ports": {"inputs": ["list:interfaces"], "outputs": ["list:interfaces", "const:status"]},
        "schema": _schema(role), "refs": [], "color": NETWORK_COLOR, "network": {"kind": "device", "role": role},
    }


def _preset_template(preset_id: str, tid: str, name: str):
    """Expose a hardware preset as a one-click palette template in addition to the preset selector."""
    p = next(x for x in PRESETS if x["id"] == preset_id)
    t = _device_template(tid, name, p["role"], ",".join(p["interfaces"]))
    t["params"].update({"vendor": p["vendor"], "model": p["model"], "os": p["os"]})
    if p["role"] == "access_point":
        t["params"]["ssid"] = "knode-wifi"
    t["description"] = f"Ready-to-place {p['vendor']} {p['model']} ({p['physical_ports']}). Uses the same packet-level model as the generic device; choose All physical ports in Properties when needed."
    t["network"]["preset"] = preset_id
    return t


def _host_template(tid: str, name: str, interface: str, ip: str, mac: str, description: str):
    return {
        "id": tid, "category": "Networking", "name": name, "inputs": [interface],
        "outputs": [interface, "status"],
        "params": {"hostname": name.lower().replace(" ", "-"), "interface": interface, "ip": ip, "mac": mac,
                   "gateway": "192.168.1.1", "ping_destination": "", "send_every": 10, "ttl": 64, "packet_bytes": 64},
        "code": HOST_CODE, "description": description, "stateful": True,
        "ports": {"inputs": ["list:interface"], "outputs": ["list:interface", "const:status"]},
        "schema": {"hostname": {"kind": "text"}, "interface": {"kind": "text", "doc": "Interface name; changing it regenerates ports."},
                   "ip": {"kind": "text"}, "mac": {"kind": "text"}, "gateway": {"kind": "text"},
                   "ping_destination": {"kind": "text", "doc": "Leave blank for receive-only; otherwise an echo request is generated every send_every steps."},
                   "send_every": {"kind": "number", "min": 1, "max": 10000, "step": 1},
                   "ttl": {"kind": "number", "min": 1, "max": 255, "step": 1}, "packet_bytes": {"kind": "number", "min": 1, "max": 65535, "step": 1}},
        "refs": [], "color": NETWORK_COLOR, "network": {"kind": "host"},
    }


TEMPLATES = [
    _device_template("network_device", "Network Device", "switch", "eth1,eth2,eth3,eth4"),
    _device_template("network_router", "Router", "router", "wan0,lan0,lan1"),
    _device_template("network_switch", "Ethernet Switch", "switch", "eth1,eth2,eth3,eth4"),
    _device_template("network_ap", "Wireless Access Point", "access_point", "ether1,wlan2g,wlan5g"),
    _device_template("network_hub", "Ethernet Hub", "hub", "eth1,eth2,eth3,eth4"),
    _device_template("network_bridge", "Network Bridge", "bridge", "port1,port2"),
    {
        "id": "network_host", "category": "Networking", "name": "Network Host / PC", "inputs": ["eth0"],
        "outputs": ["eth0", "status"],
        "params": {"hostname": "pc1", "interface": "eth0", "ip": "192.168.1.10", "mac": "02:00:00:00:00:10",
                   "gateway": "192.168.1.1", "ping_destination": "", "send_every": 10, "ttl": 64, "packet_bytes": 64},
        "code": HOST_CODE,
        "description": "Endpoint/PC that can originate periodic ICMP echo requests and answer pings. Connect its interface in both directions for full-duplex topology tests.",
        "stateful": True, "ports": {"inputs": ["list:interface"], "outputs": ["list:interface", "const:status"]},
        "schema": {"hostname": {"kind": "text"}, "interface": {"kind": "text", "doc": "Interface name; changing it regenerates ports."},
                   "ip": {"kind": "text"}, "mac": {"kind": "text"}, "gateway": {"kind": "text"},
                   "ping_destination": {"kind": "text", "doc": "Leave blank for receive-only; otherwise an echo request is generated every send_every steps."},
                   "send_every": {"kind": "number", "min": 1, "max": 10000, "step": 1},
                   "ttl": {"kind": "number", "min": 1, "max": 255, "step": 1}, "packet_bytes": {"kind": "number", "min": 1, "max": 65535, "step": 1}},
        "refs": [], "color": NETWORK_COLOR, "network": {"kind": "host"},
    },
    _host_template("network_server", "Network Server", "eth0", "192.168.1.100", "02:00:00:00:01:00",
                   "Server endpoint using the host packet model. Useful as a ping target in LAN and routed examples."),
    _host_template("network_laptop", "Wireless Laptop", "wlan0", "192.168.1.50", "02:00:00:00:00:50",
                   "Wireless client endpoint. Connect wlan0 to an AP radio port to model a Wi-Fi station."),
    {
        "id": "network_internet", "category": "Networking", "name": "Internet (Real Host)", "inputs": ["lan"],
        "outputs": ["lan", "status", "last_result"],
        "params": {"enabled": False, "label": "Internet (host)", "timeout": 4.0, "cache_seconds": 2.0,
                   "max_probes_per_step": 2, "allow_private_targets": False, "test_target": "1.1.1.1"},
        "code": INTERNET_CODE,
        "description": "Opt-in gateway to the backend machine's real network. Translates simulated ICMP echo, DNS-query and TCP-probe frames into actual host-network operations and returns measured replies; it is not a raw Ethernet/TUN bridge.",
        "stateful": True, "ports": None,
        "schema": {"enabled": {"kind": "bool", "doc": "Must be enabled explicitly before a graph can access the host network."},
                   "label": {"kind": "text"}, "timeout": {"kind": "number", "min": 0.2, "max": 30, "step": 0.2},
                   "cache_seconds": {"kind": "number", "min": 0, "max": 60, "step": 0.5},
                   "max_probes_per_step": {"kind": "number", "min": 1, "max": 16, "step": 1},
                   "allow_private_targets": {"kind": "bool", "doc": "Allow probing private/loopback/link-local destinations. Off by default."},
                   "test_target": {"kind": "text", "doc": "Target used by the Properties-panel connection test."}},
        "refs": [], "color": NETWORK_COLOR, "network": {"kind": "internet"},
    },
    {
        "id": "network_console", "category": "Networking", "name": "Network Console", "inputs": ["command", "trigger"],
        "outputs": ["stdout", "stderr", "exit_code", "result", "status"],
        "params": {"enabled": False, "command": "ping 1.1.1.1 4", "run_token": 0, "timeout": 8.0, "allow_private_targets": True},
        "code": CONSOLE_CODE,
        "description": "Bounded network diagnostics on the backend host. Supports ping, traceroute/tracepath, DNS resolve, TCP connect tests and read-only ip addr/route/neigh/link. No shell is used.",
        "stateful": True, "ports": None,
        "schema": {"enabled": {"kind": "bool"}, "command": {"kind": "code", "doc": "Examples: ping 1.1.1.1 4 | traceroute example.com 20 | dns example.com | tcp example.com 443 | ip route"},
                   "run_token": {"kind": "number", "step": 1, "doc": "Increment to force another execution during a persistent simulation."},
                   "timeout": {"kind": "number", "min": 0.2, "max": 30, "step": 0.2},
                   "allow_private_targets": {"kind": "bool", "doc": "Permit diagnostics to LAN/private addresses."}},
        "refs": [], "color": NETWORK_COLOR, "network": {"kind": "console"},
    },
    {
        "id": "network_monitor", "category": "Networking", "name": "Packet Monitor", "inputs": ["rx"],
        "outputs": ["tx", "packets", "bytes", "last"], "params": {}, "code": MONITOR_CODE,
        "description": "Inline packet tap: passes traffic through while counting frames/bytes and exposing the last packet.",
        "stateful": True, "ports": None, "schema": {}, "refs": [], "color": NETWORK_COLOR, "network": {"kind": "monitor"},
    },
    {
        "id": "network_duplex_link", "category": "Networking", "name": "Duplex Link", "inputs": ["a", "b"],
        "outputs": ["to_a", "to_b", "queued"], "params": {"delay_steps": 0, "loss": 0.0, "seed": 1}, "code": LINK_CODE,
        "description": "Bidirectional link impairment model. a→to_b and b→to_a, with optional integer-step delay and random packet loss.",
        "stateful": True, "ports": None,
        "schema": {"delay_steps": {"kind": "number", "min": 0, "max": 1000, "step": 1, "doc": "Simulation-step propagation delay."},
                   "loss": {"kind": "number", "min": 0, "max": 1, "step": 0.01, "doc": "Independent packet loss probability (0..1)."},
                   "seed": {"kind": "number", "step": 1}},
        "refs": [], "color": NETWORK_COLOR, "network": {"kind": "link"},
    },
    _preset_template("mikrotik_rb5009", "network_mikrotik_rb5009", "MikroTik RB5009"),
    _preset_template("mikrotik_crs326", "network_mikrotik_crs326", "MikroTik CRS326-24G-2S+RM"),
    _preset_template("mikrotik_cap_ax", "network_mikrotik_cap_ax", "MikroTik cAP ax"),
    _preset_template("cisco_isr4331", "network_cisco_isr4331", "Cisco ISR 4331"),
    _preset_template("cisco_c9200l_24t_4g", "network_cisco_c9200l_24t_4g", "Cisco C9200L-24T-4G"),
    _preset_template("cisco_c9115", "network_cisco_c9115", "Cisco Catalyst 9115"),
]

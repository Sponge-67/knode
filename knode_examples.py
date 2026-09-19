"""
Example graphs spanning biology, engineering, complex systems, data, design and
code. Each example is layout + template references, so the editor can build it
visually and the CLI can run it headlessly (``python knode_cli.py example sir``).

Node references in ``wires`` and ``plot`` are indices into ``nodes``.
"""
import knode_library as L

EXAMPLES = [
    {
        "id": "sir_intervention", "domain": "Biology", "title": "Epidemic with intervention (SIR)",
        "description": "Transmission rate β drops from 0.3 to 0.12 at day 25 (e.g. distancing). Compare peak I with/without by sweeping Step.after.",
        "mode": "simulate", "steps": 1600, "dt": 0.1,
        "nodes": [
            {"tpl": "step_signal", "x": 60, "y": 120, "params": {"t_step": 25, "before": 0.3, "after": 0.12}, "name": "β schedule"},
            {"tpl": "sir", "x": 320, "y": 100, "params": {"N": 10000, "I0": 5}},
        ],
        "wires": [[0, "y", 1, "beta"]],
        "plot": {"x": "t", "y": [[1, "S"], [1, "I"], [1, "R"]]},
    },
    {
        "id": "pid_control", "domain": "Engineering", "title": "PID position control (closed loop)",
        "description": "PID drives a mass–spring–damper to a set-point that steps at t = 1 s. The loop is broken automatically at a back edge.",
        "mode": "simulate", "steps": 2000, "dt": 0.005,
        "nodes": [
            {"tpl": "step_signal", "x": 40, "y": 80, "params": {"t_step": 1.0, "before": 0.0, "after": 1.0}, "name": "Set-point"},
            {"tpl": "pid", "x": 300, "y": 80, "params": {"kp": 20, "ki": 10, "kd": 2}},
            {"tpl": "mass_spring_damper", "x": 560, "y": 80, "params": {"m": 1, "c": 1, "k": 4}},
        ],
        "wires": [[0, "y", 1, "setpoint"], [1, "u", 2, "F"], [2, "x", 1, "measurement"]],
        "plot": {"x": "t", "y": [[0, "y"], [2, "x"], [1, "error"]]},
    },
    {
        "id": "predator_prey", "domain": "Biology", "title": "Predator–prey cycles (Lotka–Volterra)",
        "description": "Neutral cycles. The 'invariant' trace should stay flat — its drift is a direct measure of integration error.",
        "mode": "simulate", "steps": 5000, "dt": 0.01,
        "nodes": [{"tpl": "lotka_volterra", "x": 200, "y": 120, "params": {}}],
        "wires": [],
        "plot": {"x": [0, "prey"], "y": [[0, "predator"]]},
    },
    {
        "id": "neuron", "domain": "Biology", "title": "Hodgkin–Huxley neuron under pulsed current",
        "description": "5 ms current pulses every 20 ms. Try amplitude 5 (sub-threshold) vs 10 µA/cm².",
        "mode": "simulate", "steps": 2000, "dt": 0.05,
        "nodes": [
            {"tpl": "pulse", "x": 40, "y": 100, "params": {"period": 20, "width": 5, "amplitude": 10, "delay": 5}, "name": "Stimulus"},
            {"tpl": "hodgkin_huxley", "x": 300, "y": 100, "params": {}},
        ],
        "wires": [[0, "y", 1, "I_ext"]],
        "plot": {"x": "t", "y": [[1, "V"], [0, "y"]]},
    },
    {
        "id": "toggle", "domain": "Biology", "title": "Synthetic genetic toggle switch",
        "description": "A transient inducer pulse (t = 10–12) flips the bistable circuit — cellular memory.",
        "mode": "simulate", "steps": 600, "dt": 0.05,
        "nodes": [
            {"tpl": "pulse", "x": 40, "y": 60, "params": {"period": 1000, "width": 2, "amplitude": 1, "delay": 10}, "name": "Inducer pulse"},
            {"tpl": "toggle_switch", "x": 300, "y": 60, "params": {"u0": 0.1, "v0": 10}},
        ],
        "wires": [[0, "y", 1, "inducer_v"]],
        "plot": {"x": "t", "y": [[1, "u"], [1, "v"]]},
    },
    {
        "id": "lorenz", "domain": "Complex systems", "title": "Lorenz attractor",
        "description": "Sensitive dependence on initial conditions. Plot is x vs z (phase portrait).",
        "mode": "simulate", "steps": 5000, "dt": 0.01,
        "nodes": [{"tpl": "lorenz", "x": 200, "y": 120, "params": {}}],
        "wires": [],
        "plot": {"x": [0, "x"], "y": [[0, "z"]]},
    },
    {
        "id": "kuramoto", "domain": "Complex systems", "title": "Synchronisation transition (Kuramoto)",
        "description": "Coupling K ramps from 0 to 4; order parameter r jumps near K_c ≈ 1.6. Coupling is driven by an Expression of t.",
        "mode": "simulate", "steps": 800, "dt": 0.1,
        "nodes": [
            {"tpl": "expr", "x": 40, "y": 100, "params": {"expr": "min(4, t/20)"}, "name": "K(t) ramp"},
            {"tpl": "kuramoto", "x": 300, "y": 100, "params": {"N": 150}},
        ],
        "wires": [[0, "y", 1, "K"]],
        "plot": {"x": [0, "y"], "y": [[1, "r"]]},
    },
    {
        "id": "chaos", "domain": "Complex systems", "title": "Route to chaos (logistic map)",
        "description": "Running Lyapunov exponent: negative = periodic, positive = chaotic. Sweep r from 2.8 to 4 with reduce=last.",
        "mode": "simulate", "steps": 3000, "dt": 1,
        "nodes": [{"tpl": "logistic_map", "x": 200, "y": 120, "params": {"r": 3.9}}],
        "wires": [],
        "plot": {"x": "t", "y": [[0, "lyapunov"]]},
    },
    {
        "id": "beam", "domain": "Engineering", "title": "Beam design check",
        "description": "Section → cantilever → safety factor. Run a Monte-Carlo on F and h to see which drives risk.",
        "mode": "run",
        "nodes": [
            {"tpl": "rect_section", "x": 40, "y": 80, "params": {"b": 0.05, "h": 0.12}},
            {"tpl": "const", "x": 40, "y": 260, "params": {"value": 5000}, "name": "Load F [N]"},
            {"tpl": "cantilever", "x": 330, "y": 120, "params": {"L": 2.0}},
        ],
        "wires": [[0, "I", 2, "I"], [0, "c", 2, "c"], [1, "value", 2, "F"]],
    },
    {
        "id": "vdp", "domain": "Mathematics", "title": "Any ODE: Van der Pol oscillator",
        "description": "Edit the equations in the ODE node's parameters — e.g. a Duffing or Brusselator system.",
        "mode": "run",
        "nodes": [{"tpl": "ode", "x": 200, "y": 120, "params": {}}],
        "wires": [],
        "plot": {"arrays": [[0, "t"], [0, "Y.x"], [0, "Y.y"]]},
    },
    {
        "id": "data", "domain": "Data", "title": "Signal analysis pipeline",
        "description": "Sine + noise recorded over time, then spectrum (FFT) and summary statistics at the end.",
        "mode": "simulate", "steps": 511, "dt": 0.01,
        "nodes": [
            {"tpl": "sine", "x": 40, "y": 40, "params": {"frequency": 5, "amplitude": 2}},
            {"tpl": "noise", "x": 40, "y": 200, "params": {"sigma": 0.5}},
            {"tpl": "add", "x": 280, "y": 110, "params": {}},
            {"tpl": "recorder", "x": 500, "y": 110, "params": {}},
            {"tpl": "fft", "x": 740, "y": 40, "params": {"sample_rate": 100}},
            {"tpl": "stats", "x": 740, "y": 220, "params": {}},
        ],
        "wires": [[0, "y", 2, "a"], [1, "y", 2, "b"], [2, "y", 3, "x"], [3, "series", 4, "signal"], [3, "series", 5, "data"]],
        "plot": {"x": "t", "y": [[2, "y"]]},
    },
    {
        "id": "regression", "domain": "Data", "title": "CSV → regression",
        "description": "Paste your own CSV into the CSV Parse node's text parameter.",
        "mode": "run",
        "nodes": [
            {"tpl": "csv_parse", "x": 40, "y": 100, "params": {}},
            {"tpl": "column", "x": 300, "y": 40, "params": {"name": "x"}, "name": "x column"},
            {"tpl": "column", "x": 300, "y": 200, "params": {"name": "y"}, "name": "y column"},
            {"tpl": "linreg", "x": 560, "y": 100, "params": {}},
        ],
        "wires": [[0, "table", 1, "table"], [0, "table", 2, "table"], [1, "values", 3, "x"], [2, "values", 3, "y"]],
    },
    {
        "id": "dna", "domain": "Biology", "title": "Sequence analysis",
        "description": "GC content, translation, ORFs and motif search on a DNA sequence.",
        "mode": "run",
        "nodes": [
            {"tpl": "text", "x": 40, "y": 100, "params": {}, "name": "Sequence"},
            {"tpl": "dna_tools", "x": 300, "y": 40, "params": {}},
            {"tpl": "regex", "x": 300, "y": 240, "params": {"pattern": "GG[ACGT]C", "ignore_case": True}, "name": "Motif search"},
        ],
        "wires": [[0, "text", 1, "seq"], [0, "text", 2, "text"]],
    },
    {
        "id": "design", "domain": "Design", "title": "Design system tokens",
        "description": "Palette with WCAG contrast, a modular type scale and a 12-column grid.",
        "mode": "run",
        "nodes": [
            {"tpl": "color_harmony", "x": 40, "y": 40, "params": {"base": "#667eea", "scheme": "split"}},
            {"tpl": "modular_scale", "x": 40, "y": 220, "params": {"ratio": 1.25}},
            {"tpl": "golden_rect", "x": 320, "y": 220, "params": {}},
            {"tpl": "bezier", "x": 320, "y": 40, "params": {}, "name": "Easing curve"},
        ],
        "wires": [],
        "plot": {"arrays": [[3, "x"], [3, "y"]]},
    },
    {
        "id": "optimise", "domain": "Mathematics", "title": "Optimisation & root finding",
        "description": "Nelder–Mead on Rosenbrock's valley; bisection on Wallis' cubic.",
        "mode": "run",
        "nodes": [{"tpl": "minimize", "x": 60, "y": 60, "params": {}}, {"tpl": "root", "x": 60, "y": 240, "params": {}}],
        "wires": [],
    },
]


EXAMPLES += [
    {
        "id": "u_metapop", "domain": "Universal", "title": "Hierarchical: two coupled epidemic patches (groups)",
        "description": "Each patch is a GROUP containing a Dynamic System; patches exchange infection pressure through a feedback loop. Double-click a patch to go inside.",
        "mode": "simulate", "steps": 2000, "dt": 0.1,
        "nodes": [
            {"group": "patch", "x": 80, "y": 60, "name": "Patch A (seeded)", "inner_params": {"1": {"initial": "S = 999, I = 1, R = 0"}}},
            {"group": "patch", "x": 80, "y": 280, "name": "Patch B"},
        ],
        "wires": [[0, "I", 1, "I_other"], [1, "I", 0, "I_other"]],
        "groups": {"patch": {
            "inputs": ["I_other"], "outputs": ["I"],
            "nodes": [
                {"tpl": "graph_in", "x": 20, "y": 80, "params": {"name": "I_other"}},
                {"tpl": "dynamic_system", "x": 260, "y": 60, "params": {
                    "inputs": "I_other", "states": "S, I, R",
                    "equations": "dS = -beta*S*(I + eps*I_other)/N\ndI = beta*S*(I + eps*I_other)/N - gamma*I\ndR = gamma*I",
                    "initial": "S = 1000, I = 0, R = 0", "constants": "beta=0.4, gamma=0.1, eps=0.02, N=1000, I_other=0",
                    "observables": "", "max_substep": 0.1}},
                {"tpl": "graph_out", "x": 520, "y": 80, "params": {"name": "I"}},
            ],
            "wires": [[0, "value", 1, "I_other"], [1, "I", 2, "value"]]}},
        "plot": {"x": "t", "y": [[0, "I"], [1, "I"]]},
    },
    {
        "id": "u_ssa", "domain": "Universal", "title": "Reaction network: deterministic vs stochastic",
        "description": "The same reactions solved as ODEs and by exact Gillespie SSA. Small populations make chance matter.",
        "mode": "simulate", "steps": 1500, "dt": 0.1,
        "nodes": [
            {"tpl": "reaction_network", "x": 60, "y": 60, "name": "SIR · ODE", "params": {"initial": "S = 95, I = 5, R = 0", "constants": "beta=0.3, gamma=0.1, N=100"}},
            {"tpl": "reaction_network", "x": 60, "y": 280, "name": "SIR · SSA", "params": {"initial": "S = 95, I = 5, R = 0", "constants": "beta=0.3, gamma=0.1, N=100", "method": "ssa", "seed": 4}},
        ],
        "wires": [],
        "plot": {"x": "t", "y": [[0, "I"], [1, "I"]]},
    },
    {
        "id": "u_gene", "domain": "Universal", "title": "Stochastic gene expression (bursts)",
        "description": "Transcription, translation and decay as a reaction network with SSA: protein noise from few mRNAs.",
        "mode": "simulate", "steps": 2000, "dt": 0.5,
        "nodes": [{"tpl": "reaction_network", "x": 160, "y": 100, "name": "Gene → mRNA → protein", "params": {
            "reactions": "-> M, km\nM -> M + P, kp\nM ->, dm\nP ->, dp", "initial": "M = 0, P = 0",
            "constants": "km=0.1, kp=2, dm=0.1, dp=0.01", "method": "ssa", "seed": 7}}],
        "wires": [],
        "plot": {"x": "t", "y": [[0, "P"], [0, "M"]]},
    },
    {
        "id": "u_thermostat", "domain": "Universal", "title": "Hybrid system: thermostat + room physics",
        "description": "A State Machine (discrete logic) controls a Dynamic System (continuous heat balance) — hysteresis control.",
        "mode": "simulate", "steps": 3000, "dt": 1,
        "nodes": [
            {"tpl": "dynamic_system", "x": 380, "y": 80, "name": "Room", "params": {
                "inputs": "P", "states": "T", "equations": "dT = P/C - (T - T_out)/tau", "initial": "T = 15",
                "constants": "C=1000, tau=500, T_out=5, P=0", "observables": "", "max_substep": 1}},
            {"tpl": "state_machine", "x": 60, "y": 80, "name": "Thermostat", "params": {
                "inputs": "T", "states": "idle, heating", "transitions": "idle -> heating : T < 19\nheating -> idle : T > 21",
                "outputs": "*: power = 0\nheating: power = 60", "constants": "T=20"}},
        ],
        "wires": [[1, "power", 0, "P"], [0, "T", 1, "T"]],
        "plot": {"x": "t", "y": [[0, "T"], [1, "state"]]},
    },
    {
        "id": "u_abm", "domain": "Universal", "title": "Agent-based epidemic",
        "description": "300 individuals, each with its own status and random contacts — compare with the reaction-network model.",
        "mode": "simulate", "steps": 800, "dt": 0.1,
        "nodes": [{"tpl": "agent_based", "x": 160, "y": 100, "params": {}}],
        "wires": [],
        "plot": {"x": "t", "y": [[0, "S"], [0, "I"], [0, "R"]]},
    },
    {
        "id": "u_network", "domain": "Universal", "title": "Cascades & consensus on a small-world network",
        "description": "Threshold adoption cascade and opinion averaging on a Watts–Strogatz graph. Try topology = barabasi_albert.",
        "mode": "simulate", "steps": 60, "dt": 1,
        "nodes": [{"tpl": "network_dynamics", "x": 160, "y": 100, "params": {}}],
        "wires": [],
        "plot": {"x": "t", "y": [[0, "adopters"], [0, "mean_opinion"]]},
    },
    {
        "id": "u_turing", "domain": "Universal", "title": "Turing patterns (Gray–Scott PDE)",
        "description": "Reaction–diffusion on a 96×96 grid; the plot shows the v field as a heat-map. Edit F and k for spots, stripes, waves.",
        "mode": "simulate", "steps": 3000, "dt": 1,
        "nodes": [{"tpl": "field2d", "x": 160, "y": 100, "params": {}}],
        "wires": [],
        "plot": {"fields": [0, "v"]},
    },
    {
        "id": "u_duffing", "domain": "Universal", "title": "Custom ODE with forcing: Duffing oscillator",
        "description": "A Dynamic System driven by a Sine source — edit the equations to model any continuous system.",
        "mode": "simulate", "steps": 6000, "dt": 0.02,
        "nodes": [
            {"tpl": "sine", "x": 40, "y": 100, "params": {"amplitude": 0.4, "frequency": 0.2}, "name": "Drive"},
            {"tpl": "dynamic_system", "x": 300, "y": 80, "params": {"constants": "m=1, c=0.2, k=-1, beta=1, F=0"}},
        ],
        "wires": [[0, "y", 1, "F"]],
        "plot": {"x": [1, "x"], "y": [[1, "v"]]},
    },
    {
        "id": "u_tf", "domain": "Universal", "title": "Control loop with a transfer-function plant",
        "description": "PID + G(s) = 1/(s² + 0.8 s + 1). Swap in any plant by editing num/den.",
        "mode": "simulate", "steps": 3000, "dt": 0.005,
        "nodes": [
            {"tpl": "step_signal", "x": 40, "y": 80, "params": {"t_step": 1}, "name": "Reference"},
            {"tpl": "pid", "x": 300, "y": 80, "params": {"kp": 3, "ki": 2, "kd": 1}},
            {"tpl": "transfer_function", "x": 560, "y": 80, "params": {}, "name": "Plant G(s)"},
        ],
        "wires": [[0, "y", 1, "setpoint"], [1, "u", 2, "u"], [2, "y", 1, "measurement"]],
        "plot": {"x": "t", "y": [[0, "y"], [2, "y"]]},
    },
    {
        "id": "u_henon", "domain": "Universal", "title": "Strange attractor from difference equations",
        "description": "Hénon map written as two update equations. Plot is x vs y.",
        "mode": "simulate", "steps": 5000, "dt": 1,
        "nodes": [{"tpl": "discrete_map", "x": 160, "y": 100, "params": {}}],
        "wires": [],
        "plot": {"x": [0, "x"], "y": [[0, "y"]]},
    },
]


EXAMPLES += [
    {
        "id": "x_live_pid", "domain": "Live & interactive", "title": "Tune a controller live (dashboard)",
        "description": "Press ● Live (or Space), then drag the dashboard sliders: gains change while the simulation keeps running.",
        "mode": "simulate", "steps": 2000, "dt": 0.005,
        "nodes": [
            {"tpl": "pulse", "x": 40, "y": 90, "params": {"period": 6, "width": 3, "amplitude": 1, "delay": 0.5}, "name": "Set-point"},
            {"tpl": "pid", "x": 320, "y": 90, "params": {"kp": 8, "ki": 2, "kd": 1}},
            {"tpl": "mass_spring_damper", "x": 620, "y": 90, "params": {"m": 1, "c": 0.4, "k": 4}, "name": "Plant"},
        ],
        "wires": [[0, "y", 1, "setpoint"], [1, "u", 2, "F"], [2, "x", 1, "measurement"]],
        "frames": [{"title": "Controller", "nodes": [0, 1], "color": "#7c8cff"}, {"title": "Plant", "nodes": [2], "color": "#1dd1a1"}],
        "dashboard": [{"node": 1, "key": "kp", "kind": "slider", "min": 0, "max": 60}, {"node": 1, "key": "ki", "kind": "slider", "min": 0, "max": 30},
                      {"node": 1, "key": "kd", "kind": "slider", "min": 0, "max": 10}, {"node": 2, "key": "c", "kind": "slider", "min": 0, "max": 4},
                      {"node": 2, "key": "x", "kind": "spark"}, {"node": 1, "key": "error", "kind": "readout"}],
        "plot": {"x": "t", "y": [[0, "y"], [2, "x"]]},
    },
    {
        "id": "x_globals", "domain": "Live & interactive", "title": "Globals, expressions & wireless links",
        "description": "One Globals node drives two models through '=expressions'; a Send/Receive pair carries cases to a detector without a wire. Sweep a global in ∿ Study.",
        "mode": "simulate", "steps": 1600, "dt": 0.1,
        "nodes": [
            {"tpl": "globals", "x": 40, "y": 40, "params": {"R0": 3.0, "gamma": 0.1, "N": 10000}, "name": "Globals"},
            {"tpl": "sir", "x": 300, "y": 40, "params": {"beta": "=R0*gamma", "gamma": "=gamma", "N": "=N", "I0": 5}},
            {"tpl": "send", "x": 580, "y": 40, "params": {"channel": "cases"}},
            {"tpl": "receive", "x": 300, "y": 300, "params": {"channel": "cases"}},
            {"tpl": "event", "x": 560, "y": 300, "params": {"threshold": 1000, "direction": "rising"}, "name": "1000-case alarm"},
            {"tpl": "reaction_network", "x": 40, "y": 300, "name": "Same model as reactions", "params": {
                "reactions": "S + I -> 2 I, b/N\nI -> R, g", "initial": "S = 9995, I = 5, R = 0", "constants": "b=0.3, g=0.1, N=10000"}},
        ],
        "wires": [[1, "I", 2, "value"], [3, "value", 4, "x"]],
        "frames": [{"title": "Surveillance (wireless)", "nodes": [3, 4], "color": "#48c9e0"}],
        "plot": {"x": "t", "y": [[1, "I"], [5, "I"]]},
    },
    {
        "id": "x_calibrate", "domain": "Live & interactive", "title": "Calibrate a model to data",
        "description": "Run ▸ Calibrate / optimise: the data is pre-filled — fit r and K of the growth model (differential evolution), then 'Show best fit'.",
        "mode": "simulate", "steps": 2000, "dt": 0.01,
        "nodes": [{"tpl": "logistic_growth", "x": 200, "y": 120, "params": {"r": 0.3, "K": 80, "N0": 5}, "name": "Bacterial growth"}],
        "wires": [],
        "calibration": {"node": 0, "port": "N", "params": [["r", 0.05, 2], ["K", 50, 300]],
                        "data": "1, 10.5\n2, 21.2\n3, 40.1\n4, 64.8\n5, 92.9\n6, 114.2\n8, 138.3\n10, 146.6\n12, 149.2\n15, 150.1\n20, 149.7"},
        "plot": {"x": "t", "y": [[0, "N"]]},
    },
]


def _group_payload(ex, node):
    """Build the inner engine payload of a group used in an example, applying per-instance parameter overrides."""
    g = ex["groups"][node["group"]]
    inner = []
    for j, n in enumerate(g["nodes"]):
        params = dict(n.get("params", {}))
        params.update(node.get("inner_params", {}).get(str(j), {}))
        inner.append((n["tpl"], params))
    return L.build(inner, [tuple(w) for w in g["wires"]])


def to_payload(ex):
    """Engine payload for an example (template nodes and group nodes) — used by the CLI and tests."""
    payload = {"nodes": {}, "connections": []}
    for i, n in enumerate(ex["nodes"]):
        if "group" in n:
            g = ex["groups"][n["group"]]
            payload["nodes"][str(i)] = {"id": str(i), "name": n.get("name", "Group"), "code": "def process():\n    return {}\n",
                                        "inputs": g["inputs"], "outputs": g["outputs"], "subgraph": _group_payload(ex, n)}
        else:
            payload["nodes"][str(i)] = L.instantiate(n["tpl"], i, n.get("params", {}))
    for a, ap, b, bp in ex["wires"]:
        payload["connections"].append({"from": str(a), "fromPort": ap, "to": str(b), "toPort": bp})
    return payload


def get_example(eid):
    """Look up an example by id (KeyError if missing)."""
    for e in EXAMPLES:
        if e["id"] == eid:
            return e
    raise KeyError(eid)

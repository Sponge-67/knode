#!/usr/bin/env python3
"""
knode launcher — start the backend and open the editor with one command.

    python knode.py                  # start on http://127.0.0.1:5000 and open the browser
    python knode.py --port 8080      # another port (the next free port is used if it is taken)
    python knode.py --no-browser     # headless start (e.g. on a remote machine you tunnel to)

What it does
------------
* finds a free port, starts ``server.py`` as a child process with KNODE_SUPERVISED=1
* waits until the server answers /api/health, then opens the editor in the default browser
* supervises the server:
    - exit code 3 (Backend Manager ▸ Restart)  → start it again immediately
    - exit code 0 (Backend Manager ▸ Stop)     → the launcher exits too
    - any other exit (a crash)                 → restart with back-off, up to 5 times in a row
* Ctrl+C stops everything.

Only the Python standard library is used, so the launcher works before any package is installed;
if Flask is missing it says how to install it.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
EXIT_RESTART = 3


def port_free(host, port):
    """True if nothing is listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) != 0


def healthy(url, timeout=0.5):
    """True once the knode server answers its health endpoint."""
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    """Parse arguments, start and supervise the server (see the module docstring for the exit-code protocol)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    try:
        import flask  # noqa: F401
    except ImportError:
        print("knode needs Flask:   python -m pip install flask   (numpy and h5py are optional)")
        return 1

    browse_host = "127.0.0.1" if a.host in ("0.0.0.0", "::") else a.host
    port = a.port
    if healthy(f"http://{browse_host}:{port}"):
        print(f"knode is already running on port {port} — opening it.")
        if not a.no_browser:
            webbrowser.open(f"http://{browse_host}:{port}/")
        return 0
    while not port_free(browse_host, port):
        port += 1
    url = f"http://{browse_host}:{port}"

    env = dict(os.environ, KNODE_SUPERVISED="1")
    cmd = [sys.executable, os.path.join(HERE, "server.py"), "--host", a.host, "--port", str(port)]
    opened, crashes = a.no_browser, 0
    print(f"knode launcher → {url}   (Ctrl+C to stop)")
    while True:
        proc = subprocess.Popen(cmd, env=env, cwd=HERE)
        t0 = time.time()
        while proc.poll() is None and not healthy(url):
            if time.time() - t0 > 30:
                print("server did not become healthy within 30 s")
                break
            time.sleep(0.2)
        if proc.poll() is None and not opened:
            webbrowser.open(url + "/")
            opened = True
        try:
            code = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("\nknode stopped.")
            return 0
        if code == EXIT_RESTART:
            print("↻ restarting knode server (requested from the UI)")
            crashes = 0
            continue
        if code == 0:
            print("knode server stopped from the UI.")
            return 0
        crashes = crashes + 1 if time.time() - t0 < 60 else 1
        if crashes > 5:
            print(f"server exited with code {code} five times in a row — giving up.")
            return code
        wait = min(10, 2 ** crashes)
        print(f"server exited with code {code}; restarting in {wait} s …")
        time.sleep(wait)


if __name__ == "__main__":
    sys.exit(main())

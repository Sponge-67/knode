#!/bin/sh
# Double-click (macOS: start-mac.command) or run ./start.sh to start knode (server + browser)
cd "$(dirname "$0")"
exec python3 knode.py "$@"

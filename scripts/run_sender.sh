#!/bin/bash
# Spusti sender (doska 1). Pouzitie: scripts/run_sender.sh [config.toml] [dalsie argumenty]
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
CONF="${1:-$HERE/config/board1.toml}"
shift || true
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 -m kd240sync sender --config "$CONF" "$@"

#!/bin/bash
# Zmeria mrtvy cas motora po prikaze momentu (skok z pokoja).
# Pouzitie:
#   ./scripts/run_measure_delay.sh --lib-config config/anaheim_torque.config
#   ./scripts/run_measure_delay.sh --backend sim
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 tools/measure_delay.py "$@"

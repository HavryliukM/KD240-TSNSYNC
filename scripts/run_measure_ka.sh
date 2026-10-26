#!/bin/bash
# Spusti automaticke odmeranie konstanty Ka motora.
# Pouzitie:
#   ./scripts/run_measure_ka.sh
#   ./scripts/run_measure_ka.sh --current 0.3 --duration 0.2
#   ./scripts/run_measure_ka.sh --backend sim
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 tools/measure_ka.py "$@"


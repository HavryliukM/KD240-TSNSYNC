#!/bin/bash
# Skokova odozva rychlosti v rezime Speed kniznice AMD na jednom motore, zaznam 2 kHz do CSV.
# Motor musi byt volny. Pouzitie:
#   ./scripts/run_speed_test.sh --steps 300:2,600:2,0:1.5
#   ./scripts/run_speed_test.sh --steps 300:2,600:2,0:1.5 --repeat 3 --out spd.csv
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 tools/test_speed_step.py --lib-config config/anaheim_torque.config "$@"

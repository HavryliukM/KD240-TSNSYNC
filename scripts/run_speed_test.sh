#!/bin/bash
# Skokova odozva rychlosti na jednom motore (vlastny PI cez napatie, alebo --mode library), zaznam 2 kHz.
# Motor musi byt volny. Pouzitie:
#   ./scripts/run_speed_test.sh --steps 200:2,400:2,0:1.5 --out spd_pi.csv
#   ./scripts/run_speed_test.sh --mode library --steps 300:2,600:2,0:1.5 --dbg-div 10 --out spd_lib.csv
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 tools/test_speed_step.py --lib-config config/anaheim_torque.config "$@"

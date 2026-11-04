#!/bin/bash
# Skokova odozva polohoveho servopohonu na jednom motore (voltage_pd), zaznam 2 kHz do CSV.
# Motor musi byt volny. Pouzitie:
#   ./scripts/run_position_test.sh --steps 20:2,0:2
#   ./scripts/run_position_test.sh --steps 90:2,0:2 --ramp-dps 360 --out ramp.csv
#   ./scripts/run_position_test.sh --backend sim --steps 30:1,0:1
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 tools/test_position_step.py --config config/board2_loopback_real.toml \
     --lib-config config/anaheim_torque.config "$@"

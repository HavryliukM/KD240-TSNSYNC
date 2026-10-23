#!/bin/bash
# Spusti samostatne ovladanie motora bez dashboardu.
# Pouzitie: scripts/run_motor_cli.sh [argumenty]
# Napr.:
#   scripts/run_motor_cli.sh                 # interaktivne menu
#   scripts/run_motor_cli.sh --monitor       # len citanie polohy/otacok
#   scripts/run_motor_cli.sh --speed 500     # rozbeh na 500 RPM
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"
exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
     python3 tools/motor_cli.py "$@"

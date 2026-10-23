#!/bin/bash
# Spusti moderny webovy dashboard pre KD240 TSN synchronizaciu.
# Pouzitie:
#   scripts/run_dashboard.sh               # predvoleny rezim (demo na PC / single na doske)
#   scripts/run_dashboard.sh --mode sender --backend foc_lib   # na Doske 1
#   scripts/run_dashboard.sh --mode receiver --backend foc_lib # na Doske 2
#   scripts/run_dashboard.sh --mode demo   # simulacia na PC bez dosky
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib
cd "$HERE"

# Ak sme root alebo existuje kniznica AMD, spustime s patricnymi cestami
if [ -d "$LIB" ]; then
    exec sudo env PYTHONPATH="$HERE:$LIB" LD_LIBRARY_PATH="$LIB" \
         python3 -m web.server "$@"
else
    exec python3 -m web.server "$@"
fi

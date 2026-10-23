#!/bin/bash
# Len cita: vypise stav dosky (cas, jadro, firmware, IIO, siet, TSN nastroje).
echo "== cas";            date
echo "== jadro";          uname -r
echo "== python";         python3 --version
echo "== firmware (xmutil)"; sudo xmutil listapps 2>&1 | sed 's/^/  /'
echo "== IIO zariadenia"
for d in /sys/bus/iio/devices/iio:device*; do
  [ -e "$d/name" ] && echo "  $(basename "$d"): $(cat "$d/name")"
done
echo "== UIO";            ls /dev/uio* 2>&1 | sed 's/^/  /'
echo "== siet";           ip -br addr | sed 's/^/  /'
echo "== TSN nastroje"
for t in ptp4l tsn_talker tsn_listener switch_prog switch_cam qbv_sched; do
  printf "  %-14s %s\n" "$t" "$(command -v $t || echo CHYBA)"
done
echo "== TSN skripty";    ls /usr/bin/net_setup.sh /usr/bin/start_ptp.sh 2>&1 | sed 's/^/  /'
echo "== tailscale";      (tailscale ip -4 2>&1 || true) | sed 's/^/  /'
echo "== motorova aplikacia"; ls /opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/bin 2>&1 | sed 's/^/  /'

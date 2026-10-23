#!/bin/bash
# Priprava cistej dosky KD240 (Ubuntu 24.04): zdroje balikov, firmware, aplikacia, TSN balicky.
# Najprv nastav cas (UTC):  sudo date --set "RRRR-MM-DD HH:MM:SS"
# Pouzitie: scripts/setup_board.sh [--hostname kria2] [--tailscale]
# Neupgraduje system (apt upgrade zamerne nerobi - jadro ma ostat 6.8.0-1015-xilinx).
set -euo pipefail

HOSTNAME_NEW=""
DO_TAILSCALE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --hostname)  HOSTNAME_NEW="$2"; shift 2 ;;
    --tailscale) DO_TAILSCALE=1; shift ;;
    *) echo "pouzitie: $0 [--hostname NAZOV] [--tailscale]"; exit 1 ;;
  esac
done

# 1790000000 s = cca september 2026; starsi cas znamena, ze hodiny dosky sa resetovali
if [ "$(date +%s)" -lt 1790000000 ]; then
  echo "Cas na doske vyzera zly: $(date)"
  echo "Nastav ho: sudo date --set 'RRRR-MM-DD HH:MM:SS'   (UTC; na Slovensku je to o 1-2 h menej)"
  exit 1
fi

[ -n "$HOSTNAME_NEW" ] && sudo hostnamectl set-hostname "$HOSTNAME_NEW"

sudo apt-get update
sudo apt-get install -y software-properties-common git python3

sudo add-apt-repository --yes ppa:xilinx-apps
sudo add-apt-repository --yes ppa:ubuntu-xilinx/sdk
sudo add-apt-repository --yes ppa:xilinx-apps/xilinx-drivers
sudo add-apt-repository --yes ppa:lely/ppa
sudo apt-get update

sudo apt-get install -y xlnx-firmware-kd240-motor-ctrl-qei
sudo apt-get install -y xlnx-app-kd240-foc-motor-ctrl
sudo apt-get install -y libiio-utils
sudo apt-get install -y xlnx-app-kr260-tsn-examples lldpad ethtool

if [ "$DO_TAILSCALE" -eq 1 ]; then
  curl -fsSL https://tailscale.com/install.sh | sh
  echo "Dokonci prihlasenie:  sudo tailscale up   (otvor odkaz a prihlas sa rovnakym uctom)"
fi

cat << 'MSG'

Hotovo. Dalsie kroky:
  sudo xmutil unloadapp
  sudo xmutil loadapp kd240-motor-ctrl-qei
  scripts/check_env.sh
MSG

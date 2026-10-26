#!/bin/bash
# Nahratie projektu na dosku KD240 cez rsync/scp (z Linux / WSL / Git Bash)
# Pouzitie:
#   ./scripts/upload_to_board.sh <IP_DOSKY> [POUZIVATEL]

set -e

BOARD_IP="${1}"
USER="${2:-ubuntu}"
REMOTE_DIR="/home/ubuntu/kd240-tsn-sync"

if [ -z "$BOARD_IP" ]; then
    read -p "Zadaj IP adresu dosky KD240: " BOARD_IP
fi

if [ -z "$BOARD_IP" ]; then
    echo "Chyba: IP adresa je povinna."
    exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Kopirujem projekt z $HERE na $USER@$BOARD_IP:$REMOTE_DIR ..."

if command -v rsync >/dev/null 2>&1; then
    rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='*.log' --exclude='*.csv' --exclude='reference' \
          "$HERE/" "$USER@$BOARD_IP:$REMOTE_DIR/"
else
    ssh "$USER@$BOARD_IP" "mkdir -p $REMOTE_DIR"
    scp -r "$HERE"/* "$USER@$BOARD_IP:$REMOTE_DIR/"
fi

ssh "$USER@$BOARD_IP" "chmod +x $REMOTE_DIR/scripts/*.sh $REMOTE_DIR/tools/*.py"

echo "Hotovo! Projekt bol uspesne nahraty."
echo "Na doske spustis samostatne ovladanie:"
echo "  ssh $USER@$BOARD_IP"
echo "  cd $REMOTE_DIR"
echo "  ./scripts/run_motor_cli.sh"

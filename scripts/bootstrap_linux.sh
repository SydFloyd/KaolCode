#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run this script as a non-root sudo-capable user."
  exit 1
fi

echo "[1/6] Installing baseline packages..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw tailscale jq

echo "[2/6] Installing Docker..."
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "${USER}"

echo "[3/6] Enabling firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 22/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 3000/tcp
sudo ufw --force enable

echo "[4/6] Enabling automatic security updates..."
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "[5/6] Starting tailscale..."
sudo systemctl enable tailscaled
sudo systemctl start tailscaled
echo "Run: sudo tailscale up"

echo "[6/6] Creating data directories..."
mkdir -p data/{postgres,redis,prometheus,loki,grafana,alertmanager,artifacts}

echo "Bootstrap complete. Log out and back in to refresh docker group membership."

#!/usr/bin/env bash
# Mirsad: self-hosted Certificate Transparency stream inside the sandbox VM.
#
# Installs certstream-server-go v1.10.1 (MIT, github.com/d-Rickyy-b/certstream-server-go), which reads
# the Chrome CT log list directly, including the Static CT logs that Google and Let's Encrypt now run.
# The binary's SHA-256 is checked against the release's checksums file before it is installed.
# It serves the "lite" websocket stream on port 8603; VirtualBox forwards host 127.0.0.1:8603 to it, and
# Mirsad connects with MIRSAD_CERTSTREAM_URL=ws://127.0.0.1:8603/ in .env.
#
# Run once inside the VM after setup.sh:  sudo bash certstream_setup.sh
set -euo pipefail

VERSION=1.10.1
BASE="https://github.com/d-Rickyy-b/certstream-server-go/releases/download/v${VERSION}"
BIN="certstream-server-go_${VERSION}_linux_amd64"
ROOT=/srv/scamshield/certstream
PORT=8603
RUN_USER=${SUDO_USER:-$(logname 2>/dev/null || echo root)}

log() { printf '[certstream] %s\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }
[ -d /srv/scamshield ] || { echo "Run setup.sh first (it mounts /srv/scamshield)"; exit 1; }

mkdir -p "$ROOT"
cd "$ROOT"
if [ ! -x "$ROOT/certstream-server-go" ]; then
  log "downloading $BIN and the checksums file"
  curl -fsSL -o "$BIN" "$BASE/$BIN"
  curl -fsSL -o checksums.txt "$BASE/certstream-server-go_${VERSION}_checksums.txt"
  grep " $BIN\$" checksums.txt | sha256sum -c -
  install -m 0755 "$BIN" "$ROOT/certstream-server-go"
  rm -f "$BIN"
else
  log "binary already installed"
fi

cat > "$ROOT/config.yaml" <<EOF
webserver:
  listen_addr: "0.0.0.0"
  listen_port: ${PORT}
  real_ip: false
  # 10.0.2.0/24 is VirtualBox NAT: connections forwarded from the Windows host arrive from 10.0.2.2.
  whitelist:
    - "127.0.0.1/8"
    - "10.0.2.0/24"
  full_url: "/full-stream"
  lite_url: "/"
  domains_only_url: "/domains-only"
  cert_path: ""
  cert_key_path: ""
  compression_enabled: false
prometheus:
  enabled: false
  listen_addr: "127.0.0.1"
  listen_port: 8604
  metrics_url: "/metrics"
EOF
chown -R "$RUN_USER" "$ROOT"

cat > /etc/systemd/system/mirsad-certstream.service <<EOF
[Unit]
Description=Mirsad Certificate Transparency stream (certstream-server-go ${VERSION})
After=network-online.target
Wants=network-online.target

[Service]
User=${RUN_USER}
WorkingDirectory=${ROOT}
ExecStart=${ROOT}/certstream-server-go -config ${ROOT}/config.yaml
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=${ROOT}

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now mirsad-certstream.service
sleep 5
if ss -ltn | grep -q ":${PORT} "; then
  log "listening on port ${PORT}. From Windows, set MIRSAD_CERTSTREAM_URL=ws://127.0.0.1:${PORT}/ in .env"
else
  log "not listening yet; check: journalctl -u mirsad-certstream -n 50"
  exit 1
fi

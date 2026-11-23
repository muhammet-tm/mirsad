#!/usr/bin/env bash
# Mirsad: remove the Certificate Transparency stream from the sandbox VM.
#
# The stream (certstream-server-go) receives every new certificate from every CT log, thousands a
# second. Inside the VM that traffic went through VirtualBox's NAT and starved the port forwards: on
# 23 November 2026 the sandbox (8601) and Falcon (8602) stopped answering until the stream was stopped.
# Mirsad now runs the same server on the host, bound to 127.0.0.1, only while a certificate run listens
# (mirsad/collectors/certstream_local.py). This script removes the VM copy so a reboot cannot start it.
#
# Run once inside the VM:  sudo bash certstream_remove.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }
systemctl disable --now mirsad-certstream.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/mirsad-certstream.service
systemctl daemon-reload
rm -rf /srv/scamshield/certstream
echo "[certstream] removed from the VM; the sandbox (8601) and Falcon (8602) services are untouched"

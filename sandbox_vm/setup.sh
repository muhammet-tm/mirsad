#!/usr/bin/env bash
# setup.sh: one-time setup of the Mirsad sandbox VM (ScamShield-Sandbox, Ubuntu 22.04).
#
# Run inside the VM, from the folder that holds this script:
#     sudo bash setup.sh
# Re-running is safe. Every step checks whether its work is already done and skips it, so after a
# failure (for example a Google Drive download limit) fix the cause and run the same command again.
#
# Steps
#    1  Data disk: format the empty 30 GB disk once and mount it at /srv/scamshield (by UUID in fstab).
#       A disk that has partitions, a partition table, or any filesystem signature is never touched.
#    2  apt packages
#    3  Folders, service files, and the host's SSH key
#    4  Python venv for the capture service (fastapi, uvicorn, playwright, pillow, httpx, tldextract)
#    5  Playwright Chromium with its system libraries
#    6  Phishpedia, CPU only, following its README and setup.sh at a pinned commit
#    7  llama.cpp llama-server, CPU build, at a pinned release
#    8  Falcon instruct GGUF from TII's Hugging Face organization
#    9  systemd services mirsad-sandbox (port 8601) and mirsad-falcon (port 8602)
#   10  Health check
#
# Egress note (no UFW). This script installs no firewall and changes no firewall rules. The rule that
# matters here, "a captured page must never reach a private network", is enforced in sandbox_service.py:
# a Playwright route handler resolves every request's host with getaddrinfo (IPv4 and IPv6) and aborts it
# if any address is private, loopback, link-local, multicast, reserved, or not global; and all Chromium
# traffic goes through the service's own SOCKS5 proxy, which checks the address again and connects only
# to the address it checked. Under VirtualBox NAT the host is 10.0.2.2 and the NAT DNS is 10.0.2.3, so
# this rule is what keeps a page away from the host's Mirsad API on 127.0.0.1:8600. Package downloads
# during setup (apt, pip, pixi, git, curl) are trusted traffic and are not filtered.
#
# Settings can be overridden with environment variables, for example:
#     sudo MIRSAD_DATA_DISK=/dev/sdc bash setup.sh
#     sudo FALCON_REPO=tiiuae/Falcon-H1-3B-Instruct-GGUF FALCON_FILE=Falcon-H1-3B-Instruct-Q4_K_M.gguf bash setup.sh

set -Eeuo pipefail

# ------------------------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------------------------
ROOT=${MIRSAD_ROOT:-/srv/scamshield}
FS_LABEL=scamshield
APP="$ROOT/app"
VENV="$ROOT/venv"
CACHE="$ROOT/cache"
TMP="$ROOT/tmp"
LOGS="$ROOT/logs"
SVC_HOME="$ROOT/home"
PW_DIR="$ROOT/ms-playwright"
BRANDS_DIR="$ROOT/brands"
PIXI_HOME="$ROOT/pixi"
PIXI_BIN="$PIXI_HOME/bin"
PIXI="$PIXI_BIN/pixi"
PP_DIR="$ROOT/Phishpedia"
PP_ENV="$PP_DIR/.pixi/envs/default"
PP_PY="$PP_ENV/bin/python"
LLAMA_DIR="$ROOT/llama.cpp"
LLAMA_SERVER="$LLAMA_DIR/build/bin/llama-server"
FALCON_DIR="$ROOT/models/falcon"
SETUP_LOG=/var/log/mirsad-setup.log

# Versions read on 23 November 2026 (see README.md). Override to move forward.
PHISHPEDIA_URL=https://github.com/lindsey98/Phishpedia.git
PHISHPEDIA_REF=${PHISHPEDIA_REF:-d030779aad0aebd224f2cb60ed1c1603a8efcb1f}   # main, 26 Jul 2025
DETECTRON2_REF=${DETECTRON2_REF:-247691a1c292654867deb35cabb27f18d75a1363}   # main, 27 Oct 2026
PIXI_VERSION=${PIXI_VERSION:-v0.84.2}
PIXI_SHA256=${PIXI_SHA256:-6d2a576bde0a7b26533a068fec0aea6e4ee21c36668efc1dc73fce90110906ae}
LLAMA_URL=https://github.com/ggml-org/llama.cpp.git
LLAMA_REF=${LLAMA_REF:-v1.0.0}                                                # release of 13 Nov 2026
FALCON_REPO=${FALCON_REPO:-tiiuae/Falcon3-3B-Instruct-GGUF}
FALCON_FILE=${FALCON_FILE:-Falcon3-3B-Instruct-q4_k_m.gguf}
FALCON_PINNED_SHA256=ac9bc2edb58a961f77db11ae89e7f23b610d8b15c2ef603d1e7cb390c50d1aad   # 2,005,684,448 bytes
FALCON_ALIAS=${FALCON_ALIAS:-falcon}
JOBS=${MIRSAD_JOBS:-$(nproc)}

# Phishpedia model files: Google Drive IDs exactly as in Phishpedia's setup.sh.
PP_FILES=(
  "1tE2Mu5WC8uqCxei3XqAd7AWaP5JTmVWH rcnn_bet365.pth"
  "1Q6lqjpl4exW7q_dPbComcj0udBMDl8CW faster_rcnn.yaml"
  "1H0Q_DbdKPLFcZee8I14K62qV7TTy7xvS resnetv2_rgb_new.pth.tar"
  "1fr5ZxBKyDiNZ_1B6rRAfZbAHBBoUjZ7I expand_targetlist.zip"
  "1qSdkSSoCYUkZMKs44Rup_1DPBxHnEKl1 domain_map.pkl"
)

# openssh-server ... ca-certificates were requested; the rest are needed by the steps below:
# unzip (Phishpedia's logo list), ninja-build (parallel Detectron2 build), libgl1 and libglib2.0-0
# (OpenCV inside Phishpedia), e2fsprogs (mkfs.ext4).
APT_PACKAGES=(openssh-server python3-venv python3-dev build-essential cmake git curl ca-certificates
              unzip ninja-build libgl1 libglib2.0-0 e2fsprogs)

# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------
CURRENT_STEP="start"
log()  { printf '%s [mirsad-setup] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
step() { CURRENT_STEP="$1"; log "=== Step $1: $2"; }
skip() { log "    skip: $*"; }
done_() { log "    done: $*"; }
warn() { log "    WARNING: $*"; }
die()  { log "ERROR in step ${CURRENT_STEP}: $*"; exit 1; }
trap 'rc=$?; log "FAILED (exit $rc) at line $LINENO in step ${CURRENT_STEP}. Fix the cause and re-run: sudo bash setup.sh (finished steps are skipped)."' ERR

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script with sudo: sudo bash setup.sh" >&2
  exit 1
fi

touch "$SETUP_LOG"
chmod 0640 "$SETUP_LOG"
exec > >(tee -a "$SETUP_LOG") 2>&1

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TARGET_USER=${MIRSAD_USER:-${SUDO_USER:-}}
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = root ]; then
  die "Run as your normal VM account with sudo (or set MIRSAD_USER). The services must not run as root: Chromium's sandbox is off for root."
fi
id "$TARGET_USER" >/dev/null 2>&1 || die "User $TARGET_USER does not exist"
TARGET_GROUP=$(id -gn "$TARGET_USER")
USER_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)

USER_ENV=(HOME="$SVC_HOME" XDG_CACHE_HOME="$CACHE/xdg" PIP_CACHE_DIR="$CACHE/pip" PIXI_CACHE_DIR="$CACHE/pixi"
          RATTLER_CACHE_DIR="$CACHE/rattler" UV_CACHE_DIR="$CACHE/uv" TMPDIR="$TMP" MPLCONFIGDIR="$CACHE/matplotlib"
          PLAYWRIGHT_BROWSERS_PATH="$PW_DIR" KMP_DUPLICATE_LIB_OK=TRUE LANG=C.UTF-8
          PATH="$PIXI_BIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
as_user()    { sudo -u "$TARGET_USER" -- env "${USER_ENV[@]}" "$@"; }
as_user_in() { local dir=$1; shift; as_user bash -c 'cd "$1" || exit 1; shift; exec "$@"' mirsad "$dir" "$@"; }

log "Mirsad sandbox setup; services will run as $TARGET_USER:$TARGET_GROUP; log file $SETUP_LOG"
for f in sandbox_service.py phishpedia_worker.py brands/uae_brands.json brands/install_brands.py; do
  [ -f "$SCRIPT_DIR/$f" ] || die "Missing $SCRIPT_DIR/$f. Copy the whole sandbox_vm folder into the VM."
done
if grep -q $'\r' "$SCRIPT_DIR/sandbox_service.py"; then
  warn "Files have Windows line endings; converting copies as they are installed."
fi
. /etc/os-release
[ "${VERSION_ID:-}" = "22.04" ] || warn "This script targets Ubuntu 22.04; found ${PRETTY_NAME:-unknown}."
[ "$(uname -m)" = x86_64 ] || die "Only x86_64 is supported (found $(uname -m))."

# ------------------------------------------------------------------------------------------------
# Step 1: data disk
# ------------------------------------------------------------------------------------------------
PREMOUNT=""

fstab_has_root() { awk -v m="$ROOT" '$1 !~ /^#/ && $2 == m { f = 1 } END { exit !f }' /etc/fstab; }

disk_is_blank() {
  local d=$1 name bytes
  [ -b "$d" ] || return 1
  name=$(basename "$d")
  [ "$(lsblk -nro NAME "$d" | wc -l)" -eq 1 ] || return 1                   # no partitions
  [ -z "$(blkid -p -o value -s TYPE "$d" 2>/dev/null || true)" ] || return 1 # no filesystem, LVM, or RAID
  if sfdisk -d "$d" >/dev/null 2>&1; then return 1; fi                       # no partition table at all
  [ -z "$(ls -A "/sys/block/$name/holders" 2>/dev/null)" ] || return 1      # not used by LVM or dm
  if grep -q "^$d " /proc/swaps; then return 1; fi
  if findmnt -rno SOURCE | grep -qx "$d"; then return 1; fi
  bytes=$(blockdev --getsize64 "$d")
  [ "$bytes" -ge $((8 * 1024 * 1024 * 1024)) ] || return 1                   # at least 8 GiB
  return 0
}

pick_data_disk() {
  local preferred=${MIRSAD_DATA_DISK:-/dev/sdb} d type ro
  if disk_is_blank "$preferred"; then echo "$preferred"; return 0; fi
  [ -z "${MIRSAD_DATA_DISK:-}" ] || return 1   # an explicit choice that fails the checks is not replaced
  while read -r d type ro; do
    [ "$type" = disk ] && [ "$ro" = 0 ] || continue
    if disk_is_blank "$d"; then echo "$d"; return 0; fi
  done < <(lsblk -dnpo NAME,TYPE,RO)
  return 1
}

move_aside_premount() {
  if [ -d "$ROOT" ] && ! mountpoint -q "$ROOT" && [ -n "$(ls -A "$ROOT" 2>/dev/null)" ]; then
    PREMOUNT="${ROOT}.premount-$(date +%Y%m%d%H%M%S)"
    mv "$ROOT" "$PREMOUNT"
    warn "$ROOT held files before the disk was mounted; moved them to $PREMOUNT"
  fi
}

ensure_fstab() {
  local dev=$1 uuid
  uuid=$(blkid -s UUID -o value "$dev" || true)
  [ -n "$uuid" ] || die "No UUID found for $dev"
  if grep -q "UUID=$uuid" /etc/fstab; then skip "fstab already mounts UUID=$uuid"; return 0; fi
  if fstab_has_root; then warn "/etc/fstab has another entry for $ROOT; leaving it as it is"; return 0; fi
  cp -a /etc/fstab "/etc/fstab.mirsad-$(date +%Y%m%d%H%M%S).bak"
  printf 'UUID=%s %s ext4 defaults,noatime,nofail 0 2\n' "$uuid" "$ROOT" >> /etc/fstab
  systemctl daemon-reload
  done_ "added UUID=$uuid to /etc/fstab (backup next to it)"
}

step_disk() {
  step 1 "data disk at $ROOT"
  if mountpoint -q "$ROOT"; then
    skip "$ROOT is already mounted from $(findmnt -no SOURCE "$ROOT")"
    ensure_fstab "$(findmnt -no SOURCE "$ROOT")"
    return 0
  fi
  if [ "${MIRSAD_NO_DATA_DISK:-0}" = 1 ]; then
    warn "MIRSAD_NO_DATA_DISK=1: using a folder on the system disk instead of a data disk"
    mkdir -p "$ROOT"
    return 0
  fi
  if fstab_has_root; then
    log "    /etc/fstab already lists $ROOT; mounting it"
    move_aside_premount
    mkdir -p "$ROOT"
    mount "$ROOT"
    done_ "mounted $ROOT"
  else
    local part disk size model answer
    part=$(blkid -L "$FS_LABEL" 2>/dev/null || true)
    if [ -n "$part" ]; then
      log "    found the filesystem labelled $FS_LABEL on $part from an earlier run"
    else
      disk=$(pick_data_disk) || die "No empty disk found. Attach the 30 GB data disk to the VM (it must have no partitions), or name it with MIRSAD_DATA_DISK=/dev/sdX. Disks now: $(lsblk -dno NAME,SIZE,TYPE | tr '\n' ';')"
      size=$(lsblk -dno SIZE "$disk" | tr -d ' ')
      model=$(lsblk -dno MODEL "$disk" | sed 's/ *$//')
      log "    candidate data disk: $disk, $size, ${model:-unknown model}, no partitions, no filesystem"
      if [ "${MIRSAD_ASSUME_YES:-0}" != 1 ]; then
        if [ -t 0 ]; then
          read -r -p "Format $disk ($size) as ext4 for $ROOT? Type yes to continue: " answer
          [ "$answer" = yes ] || die "Cancelled; nothing was changed"
        else
          die "No terminal for the confirmation. Re-run with MIRSAD_ASSUME_YES=1 to format $disk"
        fi
      fi
      printf 'label: gpt\n,,L\n' | sfdisk --quiet "$disk"
      blockdev --rereadpt "$disk" 2>/dev/null || true
      udevadm settle
      part=$(lsblk -nrpo NAME,TYPE "$disk" | awk '$2 == "part" { print $1; exit }')
      [ -n "$part" ] || die "The new partition on $disk did not appear"
      mkfs.ext4 -q -L "$FS_LABEL" -m 1 "$part"
      udevadm settle
      done_ "created ext4 on $part"
    fi
    ensure_fstab "$part"
    move_aside_premount
    mkdir -p "$ROOT"
    mount "$ROOT"
    done_ "mounted $part at $ROOT"
  fi
  if [ -n "$PREMOUNT" ] && [ -f "$PREMOUNT/host_key.pub" ] && [ ! -f "$ROOT/host_key.pub" ]; then
    cp "$PREMOUNT/host_key.pub" "$ROOT/host_key.pub"
    done_ "copied host_key.pub from $PREMOUNT"
  fi
}

# ------------------------------------------------------------------------------------------------
# Step 2: apt packages
# ------------------------------------------------------------------------------------------------
step_apt() {
  step 2 "apt packages"
  local missing=() p
  for p in "${APT_PACKAGES[@]}"; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || missing+=("$p")
  done
  if [ ${#missing[@]} -eq 0 ]; then skip "all ${#APT_PACKAGES[@]} packages installed"; return 0; fi
  log "    installing: ${missing[*]}"
  DEBIAN_FRONTEND=noninteractive apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends "${missing[@]}"
  done_ "installed ${#missing[@]} packages"
}

# ------------------------------------------------------------------------------------------------
# Step 3: folders, service files, SSH key
# ------------------------------------------------------------------------------------------------
APP_CHANGED=0
install_text() {  # install a text file root-owned and read-only, with Unix line endings
  local src=$1 dst=$2 tmp
  tmp=$(mktemp)
  tr -d '\r' < "$src" > "$tmp"
  if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then rm -f "$tmp"; return 0; fi
  install -m 0644 -o root -g root "$tmp" "$dst"
  rm -f "$tmp"
  APP_CHANGED=1
}

step_files() {
  step 3 "folders, service files, SSH key"
  install -d -m 0755 -o root -g root "$ROOT" "$APP" "$APP/brands" "$ROOT/models"
  local d
  # The top level stays root-owned; the service account owns only these working folders.
  for d in "$VENV" "$CACHE" "$TMP" "$LOGS" "$SVC_HOME" "$PW_DIR" "$PIXI_HOME" "$PIXI_BIN" "$FALCON_DIR" \
           "$BRANDS_DIR" "$BRANDS_DIR/logos" "$PP_DIR" "$LLAMA_DIR"; do
    install -d -m 0755 -o "$TARGET_USER" -g "$TARGET_GROUP" "$d"
  done
  install_text "$SCRIPT_DIR/sandbox_service.py" "$APP/sandbox_service.py"
  install_text "$SCRIPT_DIR/phishpedia_worker.py" "$APP/phishpedia_worker.py"
  for d in README.md uae_brands.json install_brands.py; do
    if [ -f "$SCRIPT_DIR/brands/$d" ]; then install_text "$SCRIPT_DIR/brands/$d" "$APP/brands/$d"; fi
  done
  if [ -f "$SCRIPT_DIR/README.md" ]; then install_text "$SCRIPT_DIR/README.md" "$APP/README.md"; fi
  if [ -d "$SCRIPT_DIR/brands/logos" ]; then  # logos the team collected (never in git)
    cp -rn "$SCRIPT_DIR/brands/logos/." "$BRANDS_DIR/logos/"
    chown -R "$TARGET_USER:$TARGET_GROUP" "$BRANDS_DIR/logos"
  fi
  if [ "$APP_CHANGED" = 1 ]; then done_ "service files installed in $APP"; else skip "service files unchanged"; fi

  systemctl enable --now ssh >/dev/null 2>&1 || warn "could not enable the ssh service"
  if [ ! -f "$ROOT/host_key.pub" ] && [ -f "$SCRIPT_DIR/host_key.pub" ]; then
    install -m 0644 -o root -g root "$SCRIPT_DIR/host_key.pub" "$ROOT/host_key.pub"
  fi
  if [ -f "$ROOT/host_key.pub" ]; then
    local keyfile auth line added=0
    keyfile=$(mktemp)
    tr -d '\r' < "$ROOT/host_key.pub" > "$keyfile"
    if ! ssh-keygen -l -f "$keyfile" >/dev/null 2>&1; then
      rm -f "$keyfile"
      warn "$ROOT/host_key.pub is not a valid public key; skipped"
      return 0
    fi
    auth="$USER_HOME/.ssh/authorized_keys"
    install -d -m 0700 -o "$TARGET_USER" -g "$TARGET_GROUP" "$USER_HOME/.ssh"
    [ -f "$auth" ] || install -m 0600 -o "$TARGET_USER" -g "$TARGET_GROUP" /dev/null "$auth"
    while IFS= read -r line; do
      case "$line" in ''|'#'*) continue ;; esac
      if ! grep -qxF -- "$line" "$auth"; then printf '%s\n' "$line" >> "$auth"; added=$((added + 1)); fi
    done < "$keyfile"
    rm -f "$keyfile"
    chown "$TARGET_USER:$TARGET_GROUP" "$auth"
    chmod 0600 "$auth"
    if [ "$added" -gt 0 ]; then done_ "added $added host key(s) to $auth"; else skip "host key already authorized"; fi
  else
    skip "no $ROOT/host_key.pub (optional; see README for SSH from Windows)"
  fi
}

# ------------------------------------------------------------------------------------------------
# Step 4: Python venv for the service
# ------------------------------------------------------------------------------------------------
step_venv() {
  step 4 "Python venv at $VENV"
  if [ ! -x "$VENV/bin/python" ]; then
    as_user python3 -m venv "$VENV"
    done_ "created venv ($("$VENV/bin/python" --version))"
  fi
  if as_user "$VENV/bin/python" -c 'import fastapi, uvicorn, playwright, PIL, httpx, tldextract' >/dev/null 2>&1; then
    skip "fastapi, uvicorn, playwright, pillow, httpx, tldextract already installed"
  else
    as_user "$VENV/bin/python" -m pip install -q --upgrade pip
    # tldextract is added to the requested list: the capture reports each form's registered domain.
    as_user "$VENV/bin/python" -m pip install -q fastapi uvicorn playwright pillow httpx tldextract
    done_ "installed the service packages"
  fi
  as_user "$VENV/bin/python" -m pip freeze > "$LOGS/venv-freeze.txt" 2>/dev/null || true
}

# ------------------------------------------------------------------------------------------------
# Step 5: Playwright Chromium
# ------------------------------------------------------------------------------------------------
step_chromium() {
  step 5 "Playwright Chromium"
  local ver marker
  ver=$("$VENV/bin/playwright" --version | awk '{print $2}')
  marker="$PW_DIR/.mirsad-installed-$ver"
  if [ -f "$marker" ]; then skip "Chromium for Playwright $ver already installed"; return 0; fi
  # --with-deps installs Chromium's system libraries with apt, so this one command runs as root.
  env PLAYWRIGHT_BROWSERS_PATH="$PW_DIR" "$VENV/bin/playwright" install --with-deps chromium
  touch "$marker"
  chown -R "$TARGET_USER:$TARGET_GROUP" "$PW_DIR"
  done_ "Chromium for Playwright $ver installed in $PW_DIR"
}

# ------------------------------------------------------------------------------------------------
# Step 6: Phishpedia (CPU)
# ------------------------------------------------------------------------------------------------
download_ok() {  # a real file, not an HTML error page from Google Drive
  local f=$1 head
  [ -s "$f" ] || return 1
  head=$(head -c 512 "$f" | tr -d '\0' | tr '[:upper:]' '[:lower:]')
  case "$head" in *'<!doctype'*|*'<html'*) return 1 ;; esac
  return 0
}

step_phishpedia() {
  step 6 "Phishpedia (CPU) in $PP_DIR"
  # 6a source at the pinned commit
  if [ ! -d "$PP_DIR/.git" ]; then
    [ -z "$(ls -A "$PP_DIR" 2>/dev/null)" ] || die "$PP_DIR is not empty and not a git checkout; move it away and re-run"
    as_user git clone --quiet "$PHISHPEDIA_URL" "$PP_DIR"
    done_ "cloned Phishpedia"
  fi
  if [ "$(as_user git -C "$PP_DIR" rev-parse HEAD)" != "$PHISHPEDIA_REF" ]; then
    as_user git -C "$PP_DIR" fetch --quiet origin
    as_user git -C "$PP_DIR" checkout --quiet "$PHISHPEDIA_REF"
    done_ "checked out $PHISHPEDIA_REF"
  else
    skip "Phishpedia source at $PHISHPEDIA_REF"
  fi

  # 6b pixi (Phishpedia's README: "Prerequisite: Pixi installed"), pinned release with checksum
  if [ -x "$PIXI" ] && "$PIXI" --version 2>/dev/null | grep -q "${PIXI_VERSION#v}"; then
    skip "pixi $PIXI_VERSION present"
  else
    local tmpd
    tmpd=$(mktemp -d)
    curl -fsSL --retry 3 -o "$tmpd/pixi.tar.gz" \
      "https://github.com/prefix-dev/pixi/releases/download/$PIXI_VERSION/pixi-x86_64-unknown-linux-musl.tar.gz"
    echo "$PIXI_SHA256  $tmpd/pixi.tar.gz" | sha256sum -c --quiet - || die "pixi download failed its checksum"
    tar -xzf "$tmpd/pixi.tar.gz" -C "$tmpd"
    install -m 0755 -o "$TARGET_USER" -g "$TARGET_GROUP" "$(find "$tmpd" -type f -name pixi | head -n 1)" "$PIXI"
    rm -rf "$tmpd"
    done_ "installed $("$PIXI" --version)"
  fi

  # 6c environment from pixi.toml (README: "pixi install"); torch and torchvision come from the CPU index
  if [ -x "$PP_PY" ] && as_user_in "$PP_DIR" "$PP_PY" -c 'import torch, torchvision, cv2, yaml, tldextract, gdown' >/dev/null 2>&1; then
    skip "pixi environment ready"
  else
    as_user_in "$PP_DIR" "$PIXI" install
    done_ "pixi environment installed"
  fi
  log "    Phishpedia Python: $(as_user_in "$PP_DIR" "$PP_PY" -c 'import sys, torch; print(sys.version.split()[0], "torch", torch.__version__, "cuda", torch.cuda.is_available())')"

  # 6d Detectron2 (setup.sh: pixi run pip install --no-build-isolation git+...detectron2.git), CPU build
  if as_user_in "$PP_DIR" "$PP_PY" -c 'import detectron2' >/dev/null 2>&1; then
    skip "Detectron2 installed"
  else
    log "    building Detectron2 for CPU with $JOBS jobs (10 to 25 minutes)"
    as_user_in "$PP_DIR" env FORCE_CUDA=0 MAX_JOBS="$JOBS" "$PIXI" run pip install --no-build-isolation \
      "git+https://github.com/facebookresearch/detectron2.git@$DETECTRON2_REF"
    done_ "Detectron2 built"
  fi

  # 6e model weights, logo list, and brand-domain map (setup.sh: gdown). Phishpedia's setup.sh uses
  # "gdown --id", which current gdown no longer accepts, so the ID is passed as the positional argument.
  as_user mkdir -p "$PP_DIR/models"
  local entry id name dst attempt
  for entry in "${PP_FILES[@]}"; do
    id=${entry%% *}
    name=${entry#* }
    dst="$PP_DIR/models/$name"
    if download_ok "$dst"; then skip "$name present ($(du -h "$dst" | cut -f1))"; continue; fi
    for attempt in 1 2 3; do
      rm -f "$dst.part"
      if as_user_in "$PP_DIR/models" "$PP_ENV/bin/gdown" "$id" -O "$dst.part" && download_ok "$dst.part"; then
        as_user mv -f "$dst.part" "$dst"
        break
      fi
      rm -f "$dst.part"
      warn "download of $name failed (attempt $attempt of 3)"
      if [ "$attempt" -lt 3 ]; then sleep $((attempt * 30)); fi
    done
    download_ok "$dst" || die "Could not download $name. Google Drive may be limiting downloads: wait and re-run, or open https://drive.google.com/uc?id=$id on the host, save it as $name, and copy it to $dst"
    done_ "downloaded $name ($(du -h "$dst" | cut -f1))"
  done

  # 6f unpack the reference logo list (setup.sh: unzip, then flatten a nested expand_targetlist/)
  local tl="$PP_DIR/models/expand_targetlist" count
  count=$(find "$tl" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || true)
  if [ "$count" -ge 100 ]; then
    skip "logo list unpacked ($count brand folders)"
  else
    as_user_in "$PP_DIR/models" unzip -q -o expand_targetlist.zip -d expand_targetlist
    if [ -d "$tl/expand_targetlist" ]; then
      as_user find "$tl/expand_targetlist" -mindepth 1 -maxdepth 1 -exec mv -t "$tl" {} +
      as_user rmdir "$tl/expand_targetlist"
    fi
    rm -rf "$tl/__MACOSX"
    count=$(find "$tl" -mindepth 1 -maxdepth 1 -type d | wc -l)
    done_ "unpacked $count brand folders"
  fi

  # 6g cache the reference logo embeddings once (configs.load_config writes LOGO_FEATS.npy)
  if [ -s "$PP_DIR/LOGO_FEATS.npy" ] && [ -s "$PP_DIR/LOGO_FILES.npy" ]; then
    skip "reference embeddings cached"
  else
    log "    computing reference logo embeddings on CPU (several minutes)"
    as_user_in "$PP_DIR" env PHISHPEDIA_DIR="$PP_DIR" "$PP_PY" "$APP/phishpedia_worker.py" --build-cache
    done_ "reference embeddings cached"
  fi
}

# ------------------------------------------------------------------------------------------------
# Step 7: llama.cpp (llama-server, CPU)
# ------------------------------------------------------------------------------------------------
step_llama() {
  step 7 "llama.cpp $LLAMA_REF in $LLAMA_DIR"
  local marker="$LLAMA_DIR/build/.mirsad-ref"
  if [ -x "$LLAMA_SERVER" ] && [ "$(cat "$marker" 2>/dev/null || true)" = "$LLAMA_REF" ]; then
    skip "llama-server built from $LLAMA_REF"
    return 0
  fi
  if [ ! -d "$LLAMA_DIR/.git" ]; then
    [ -z "$(ls -A "$LLAMA_DIR" 2>/dev/null)" ] || die "$LLAMA_DIR is not empty and not a git checkout; move it away and re-run"
    as_user git init -q "$LLAMA_DIR"
    as_user git -C "$LLAMA_DIR" remote add origin "$LLAMA_URL"
  fi
  as_user git -C "$LLAMA_DIR" fetch --quiet --depth 1 origin "$LLAMA_REF"
  as_user git -C "$LLAMA_DIR" checkout --quiet --force FETCH_HEAD
  log "    building llama-server with $JOBS jobs (5 to 15 minutes)"
  # README / docs/build.md: cmake -B build; cmake --build build --config Release. Only the server target
  # is built; the prebuilt web UI is skipped because the service runs with --no-ui.
  as_user_in "$LLAMA_DIR" cmake -B build -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_USE_PREBUILT_UI=OFF
  as_user_in "$LLAMA_DIR" cmake --build build --config Release -j "$JOBS" --target llama-server
  [ -x "$LLAMA_SERVER" ] || die "llama-server was not produced at $LLAMA_SERVER"
  as_user bash -c 'printf "%s\n" "$1" > "$2"' mirsad "$LLAMA_REF" "$marker"
  done_ "built $LLAMA_SERVER"
}

# ------------------------------------------------------------------------------------------------
# Step 8: Falcon GGUF
# ------------------------------------------------------------------------------------------------
FALCON_CHANGED=0
step_falcon() {
  step 8 "Falcon GGUF from $FALCON_REPO"
  local listing="$TMP/hf_tree.json" picker="$TMP/pick_gguf.py" picked="" name="" size="" sha="" dst
  cat > "$picker" <<'PY'
import json, sys
tree = json.load(open(sys.argv[1]))
want = sys.argv[2]
files = [f for f in tree if f.get("type") == "file"]
pick = next((f for f in files if f["path"] == want), None)
if pick is None:
    ggufs = [f for f in files if f["path"].lower().endswith(".gguf")]
    sys.stderr.write("    %s is not in the repo; GGUF files there:\n" % want)
    for f in ggufs:
        sys.stderr.write("      %s  %s bytes\n" % (f["path"], f.get("size")))
    q4 = [f for f in ggufs if "q4_k_m" in f["path"].lower()]
    pick = q4[0] if q4 else None
if pick is None:
    sys.exit(3)
lfs = pick.get("lfs") or {}
print("%s\t%s\t%s" % (pick["path"], lfs.get("size") or pick.get("size") or 0, lfs.get("oid", "")))
PY
  if curl -fsSL --retry 3 -m 60 -o "$listing" "https://huggingface.co/api/models/$FALCON_REPO/tree/main"; then
    picked=$(python3 "$picker" "$listing" "$FALCON_FILE") || picked=""
    IFS=$'\t' read -r name size sha <<< "$picked" || true
  else
    warn "Hugging Face listing unavailable"
  fi
  if [ -z "$name" ]; then
    if [ -L "$FALCON_DIR/current.gguf" ] && [ -s "$FALCON_DIR/current.gguf" ]; then
      warn "keeping the model already in place: $(readlink "$FALCON_DIR/current.gguf")"
      return 0
    fi
    die "Could not find a Q4_K_M GGUF in $FALCON_REPO"
  fi
  if [ "$name" = "Falcon3-3B-Instruct-q4_k_m.gguf" ] && [ "$sha" != "$FALCON_PINNED_SHA256" ]; then
    warn "the repo's checksum for $name changed since 23 Nov 2026; using the repo's current value"
  fi
  dst="$FALCON_DIR/$name"
  log "    model file: $name, $size bytes ($((size / 1024 / 1024)) MiB), sha256 ${sha:-unknown}"
  if [ -s "$dst" ] && [ "$(stat -c %s "$dst")" = "$size" ] && [ "$(cat "$dst.sha256" 2>/dev/null || true)" = "$sha" ]; then
    skip "$name already downloaded and verified"
  else
    if [ "$(stat -c %s "$dst.part" 2>/dev/null || echo 0)" != "$size" ]; then  # resumes a partial file
      as_user curl -fL --retry 5 --retry-delay 10 -C - -o "$dst.part" \
        "https://huggingface.co/$FALCON_REPO/resolve/main/$name"
    fi
    [ "$(stat -c %s "$dst.part")" = "$size" ] || die "size mismatch for $name; re-run to resume the download"
    if [ -n "$sha" ]; then
      echo "$sha  $dst.part" | sha256sum -c --quiet - || { rm -f "$dst.part"; die "checksum mismatch for $name; the partial file was deleted, re-run"; }
    fi
    as_user mv -f "$dst.part" "$dst"
    as_user bash -c 'printf "%s\n" "$1" > "$2"' mirsad "$sha" "$dst.sha256"
    FALCON_CHANGED=1
    done_ "downloaded and verified $name"
  fi
  if [ "$(readlink "$FALCON_DIR/current.gguf" 2>/dev/null || true)" != "$name" ]; then
    as_user ln -sfn "$name" "$FALCON_DIR/current.gguf"
    FALCON_CHANGED=1
  fi
}

# ------------------------------------------------------------------------------------------------
# Step 9: systemd services
# ------------------------------------------------------------------------------------------------
SANDBOX_UNIT_CHANGED=0
FALCON_UNIT_CHANGED=0
write_unit() {  # name, content; prints 1 if the file changed
  local dst="/etc/systemd/system/$1"
  if [ -f "$dst" ] && [ "$(cat "$dst")" = "$2" ]; then echo 0; return 0; fi
  printf '%s\n' "$2" > "$dst"
  chmod 0644 "$dst"
  echo 1
}

HARDENING="NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full
ProtectKernelModules=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes"

step_systemd() {
  step 9 "systemd services"
  local sandbox_unit falcon_unit svc
  sandbox_unit=$(cat <<EOF
[Unit]
Description=Mirsad sandbox: page capture and Phishpedia (port 8601)
Documentation=file://$APP/README.md
After=network-online.target
Wants=network-online.target
RequiresMountsFor=$ROOT

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_GROUP
WorkingDirectory=$APP
Environment=HOME=$SVC_HOME
Environment=XDG_CACHE_HOME=$CACHE/xdg
Environment=MPLCONFIGDIR=$CACHE/matplotlib
Environment=PLAYWRIGHT_BROWSERS_PATH=$PW_DIR
Environment=MIRSAD_ROOT=$ROOT
Environment=MIRSAD_LOG_DIR=$LOGS
Environment=PHISHPEDIA_DIR=$PP_DIR
Environment=PHISHPEDIA_PYTHON=$PP_PY
Environment=PHISHPEDIA_WORKER=$APP/phishpedia_worker.py
Environment=PHISHPEDIA_THREADS=2
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$VENV/bin/uvicorn sandbox_service:app --host 0.0.0.0 --port 8601 --workers 1 --no-access-log
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
# Chromium plus the Phishpedia worker; the cap keeps a heavy page from starving Falcon or sshd.
MemoryMax=3500M
$HARDENING

[Install]
WantedBy=multi-user.target
EOF
)
  falcon_unit=$(cat <<EOF
[Unit]
Description=Mirsad local Falcon model, OpenAI-compatible llama-server (port 8602)
After=network-online.target
RequiresMountsFor=$ROOT

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_GROUP
WorkingDirectory=$LLAMA_DIR
Environment=HOME=$SVC_HOME
ExecStart=$LLAMA_SERVER -m $FALCON_DIR/current.gguf --host 0.0.0.0 --port 8602 -c 4096 -t 4 --alias $FALCON_ALIAS --no-ui
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
$HARDENING

[Install]
WantedBy=multi-user.target
EOF
)
  SANDBOX_UNIT_CHANGED=$(write_unit mirsad-sandbox.service "$sandbox_unit")
  FALCON_UNIT_CHANGED=$(write_unit mirsad-falcon.service "$falcon_unit")
  systemctl daemon-reload
  systemctl enable mirsad-sandbox.service mirsad-falcon.service >/dev/null 2>&1
  if [ "$SANDBOX_UNIT_CHANGED" = 1 ] || [ "$APP_CHANGED" = 1 ] || ! systemctl is-active --quiet mirsad-sandbox; then
    systemctl restart mirsad-sandbox
    done_ "mirsad-sandbox (re)started"
  else
    skip "mirsad-sandbox running and unchanged"
  fi
  if [ "$FALCON_UNIT_CHANGED" = 1 ] || [ "$FALCON_CHANGED" = 1 ] || ! systemctl is-active --quiet mirsad-falcon; then
    systemctl restart mirsad-falcon
    done_ "mirsad-falcon (re)started"
  else
    skip "mirsad-falcon running and unchanged"
  fi
}

# ------------------------------------------------------------------------------------------------
# Step 10: health check
# ------------------------------------------------------------------------------------------------
json_get() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {"d": d}))' "$1" "$2" 2>/dev/null || echo "?"; }

post_json() {  # url, body-file, out-file, max-seconds; prints the HTTP status (000 if no answer)
  curl -s -o "$3" -w '%{http_code}' -m "$4" -H 'Content-Type: application/json' --data-binary @"$2" "$1" || true
}

step_health() {
  step 10 "health check"
  local i h="$TMP/health.json" result=0 code
  for ((i = 0; i < 60; i++)); do
    curl -fsS -m 5 -o "$h" http://127.0.0.1:8601/health 2>/dev/null && break
    sleep 3
  done
  if [ ! -s "$h" ]; then
    warn "mirsad-sandbox did not answer on 8601; see: journalctl -u mirsad-sandbox -n 80"
    result=1
  else
    log "    waiting for Phishpedia to load its models (up to 10 minutes)"
    for ((i = 0; i < 200; i++)); do
      curl -fsS -m 5 -o "$h" http://127.0.0.1:8601/health 2>/dev/null || true
      case "$(json_get "$h" 'd.get("phishpedia_state")')" in starting|not_started) sleep 3 ;; *) break ;; esac
    done
    log "    8601 /health: $(cat "$h")"
  fi

  printf '{"url": "http://10.0.2.2:8600/api/health"}' > "$TMP/req_block1.json"
  printf '{"url": "http://127.0.0.1:8602/health"}' > "$TMP/req_block2.json"
  printf '{"url": "http://169.254.169.254/latest/meta-data/"}' > "$TMP/req_block3.json"
  for i in 1 2 3; do
    code=$(post_json http://127.0.0.1:8601/capture "$TMP/req_block$i.json" "$TMP/res_block$i.json" 30)
    if [ "$code" = 403 ]; then
      log "    private-address block $i: refused as expected (403)"
    else
      warn "private-address block $i returned HTTP $code instead of 403: $(head -c 300 "$TMP/res_block$i.json" 2>/dev/null)"
      result=1
    fi
  done

  printf '{"url": "https://example.com/", "timeout_s": 15}' > "$TMP/req_capture.json"
  code=$(post_json http://127.0.0.1:8601/capture "$TMP/req_capture.json" "$TMP/res_capture.json" 120)
  log "    capture of https://example.com/: HTTP $code, ok=$(json_get "$TMP/res_capture.json" 'd.get("ok")'), status=$(json_get "$TMP/res_capture.json" 'd.get("status")'), title=$(json_get "$TMP/res_capture.json" 'repr(d.get("title"))'), screenshot=$(json_get "$TMP/res_capture.json" 'd.get("screenshot")'), error=$(json_get "$TMP/res_capture.json" 'd.get("error")')"

  local shot="$PP_DIR/datasets/test_sites/accounts.g.cdcde.com/shot.png"
  if [ -f "$shot" ]; then
    python3 - "$shot" > "$TMP/req_pp.json" <<'PY'
import base64, json, sys
print(json.dumps({"url": "https://accounts.g.cdcde.com/",
                  "screenshot_b64": base64.b64encode(open(sys.argv[1], "rb").read()).decode()}))
PY
    code=$(post_json http://127.0.0.1:8601/phishpedia "$TMP/req_pp.json" "$TMP/res_pp.json" 240)
    log "    Phishpedia on its own test page: HTTP $code, $(json_get "$TMP/res_pp.json" '{k: d.get(k) for k in ("available", "brand", "confidence", "domain_matches_brand", "verdict", "elapsed_ms", "reason")}')"
  fi

  log "    waiting for the Falcon model to load (up to 5 minutes)"
  for ((i = 0; i < 100; i++)); do
    curl -fsS -m 5 http://127.0.0.1:8602/health >/dev/null 2>&1 && break
    sleep 3
  done
  log "    8602 /health: $(curl -sS -m 5 http://127.0.0.1:8602/health 2>&1 || true)"
  printf '{"model": "%s", "messages": [{"role": "user", "content": "Reply with one word: ready"}], "max_tokens": 8, "temperature": 0}' "$FALCON_ALIAS" > "$TMP/req_llm.json"
  code=$(post_json http://127.0.0.1:8602/v1/chat/completions "$TMP/req_llm.json" "$TMP/res_llm.json" 180)
  log "    Falcon chat completion: HTTP $code, reply=$(json_get "$TMP/res_llm.json" 'repr(d["choices"][0]["message"]["content"])')"
  [ "$code" = 200 ] || result=1

  log "=== Summary"
  log "    Disk:      $(df -h "$ROOT" | awk 'NR == 2 { print $3 " used of " $2 " on " $1 }')"
  log "    Services:  mirsad-sandbox $(systemctl is-active mirsad-sandbox), mirsad-falcon $(systemctl is-active mirsad-falcon), ssh $(systemctl is-active ssh)"
  log "    Logs:      journalctl -u mirsad-sandbox -f   and   $LOGS/sandbox_requests.log"
  log "    Windows:   curl http://127.0.0.1:8601/health   and   curl http://127.0.0.1:8602/health"
  log "    Egress:    no firewall was configured; private-network blocking lives in sandbox_service.py (checked above)."
  if [ "$result" = 0 ]; then log "Setup finished. All checks passed."; else log "Setup finished with warnings; read the lines marked WARNING above."; fi
}

# ------------------------------------------------------------------------------------------------
step_disk
step_apt
step_files
step_venv
step_chromium
step_phishpedia
step_llama
step_falcon
step_systemd
step_health

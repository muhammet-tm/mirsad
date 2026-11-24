# Mirsad sandbox VM

This folder holds everything that runs inside ScamShield-Sandbox, the Ubuntu 22.04 VirtualBox VM that loads suspicious pages for Mirsad. The Windows host never opens a suspicious link itself. It sends the URL to the VM, and the VM returns a screenshot, the page facts, and a logo verdict.

## What runs in the VM and why

The VM runs three services, and the host reaches each one through a VirtualBox NAT port forward.

| Service | Guest port | Host address | Purpose |
|---|---|---|---|
| mirsad-sandbox | 8601 | 127.0.0.1:8601 | Page capture with Playwright Chromium, plus Phishpedia logo checks |
| mirsad-falcon | 8602 | 127.0.0.1:8602 | Falcon instruct model behind llama-server, OpenAI-compatible (`/v1/chat/completions`) |
| ssh | 22 | 127.0.0.1:2222 | Administration from Windows |

Mirsad uses a separate VM for two reasons. The first is isolation: a phishing page is hostile code, so it loads in a disposable linked clone that holds no credentials and cannot reach the host's private network. The second is Detectron2. Phishpedia needs it, and Detectron2 has no supported Windows build, while the laptop has no WSL, Docker, or CUDA (`01_Implementation_Plan.md`). On Linux, Phishpedia installs and runs on the CPU.

The Falcon model gives Mirsad a zero-egress mode for case summaries (`MIRSAD_LLM=falcon` on the host). It writes summaries only and never decides a case.

### The certificate stream does not run here

The live Certificate Transparency stream (certstream-server-go) first ran in this VM, and it broke the VM's other services. It downloads every new certificate from every log, thousands a second. All of that traffic passed through VirtualBox's NAT, which also carries the port forwards, so on 23 November 2026 ports 8601 and 8602 stopped answering until the team stopped the stream. Mirsad now starts the same server on the host, bound to 127.0.0.1, only for the minutes of a certificate run (`mirsad/collectors/certstream_local.py`); it downloads the official release once and checks it against a pinned SHA-256. If you installed the stream in the VM earlier, remove it with `sudo bash certstream_remove.sh`, and delete the old port forward on the host with `VBoxManage controlvm ScamShield-Sandbox natpf1 delete certstream` (already done on the development laptop).

## Files

| File | Role |
|---|---|
| `setup.sh` | One-time, idempotent setup. Run it with `sudo bash setup.sh`. |
| `sandbox_service.py` | FastAPI service on port 8601: `/health`, `/capture`, and `/phishpedia`. |
| `phishpedia_worker.py` | Runs inside Phishpedia's own Python environment as a child process of the service. |
| `brands/` | How to add UAE brand logos to Phishpedia, the brand-to-domain map, and the install script. |

The service and the Phishpedia worker run in separate processes and separate Python environments. The service uses a plain venv at `/srv/scamshield/venv`. Phishpedia uses the pixi environment that its README prescribes, at `/srv/scamshield/Phishpedia/.pixi/envs/default`. If the model crashes or runs out of memory, the service restarts the worker and page capture keeps working.

## One-time steps

Steps 1 to 5 are manual; setup does the rest.

1. With the VM powered off, check that the 30 GB data disk is attached and that the three port forwards exist. In PowerShell on Windows:

   ```powershell
   & "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" showvminfo ScamShield-Sandbox | Select-String "Rule|SATA"
   # add any missing rule (VM powered off); use "controlvm ScamShield-Sandbox natpf1 ..." while it runs
   & "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" modifyvm ScamShield-Sandbox --natpf1 "mirsad-sandbox,tcp,127.0.0.1,8601,,8601"
   & "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" modifyvm ScamShield-Sandbox --natpf1 "mirsad-falcon,tcp,127.0.0.1,8602,,8602"
   & "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" modifyvm ScamShield-Sandbox --natpf1 "mirsad-ssh,tcp,127.0.0.1,2222,,22"
   ```

   Keep the host IP as 127.0.0.1 in every rule. The services have no login of their own, so the forward must not listen on the LAN.

2. Optional, for SSH from Windows: create a key pair and put the public half in this folder as `host_key.pub`. Setup adds it to your account's `~/.ssh/authorized_keys`. The private key stays on Windows, and `.gitignore` keeps `host_key.pub` out of git.

   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\mirsad_sandbox"
   Copy-Item "$env:USERPROFILE\.ssh\mirsad_sandbox.pub" "D:\AD Police Hackathon\mirsad\sandbox_vm\host_key.pub"
   ```

3. Start the VM and log in with your normal account, which needs sudo rights. Setup refuses to run the services as root, because Chromium's sandbox is off for root.

4. Copy this folder into the VM. Use either method:

   - VirtualBox shared folder (needs Guest Additions): share `D:\AD Police Hackathon\mirsad\sandbox_vm` as `sandbox_vm`, then run `sudo mount -t vboxsf sandbox_vm /mnt && cp -r /mnt ~/sandbox_vm && sudo umount /mnt` in the VM (skip the mount if the share is already auto-mounted at `/media/sf_sandbox_vm`).
   - scp, if the VM already runs an SSH server: `scp -P 2222 -r "D:\AD Police Hackathon\mirsad\sandbox_vm" <vm-user>@127.0.0.1:~/`

5. Run setup inside the VM:

   ```bash
   cd ~/sandbox_vm
   sudo bash setup.sh
   ```

   Setup lists the empty disk it found and asks you to type `yes` before it formats the disk. It formats only a disk with no partitions, no partition table, and no filesystem signature. It mounts that disk at `/srv/scamshield` by UUID through `/etc/fstab` and backs up `fstab` first. If anything fails, fix the cause and run the same command again; setup skips the steps that already finished.

6. Read the summary at the end. The health check confirms that three private addresses are refused, captures `https://example.com/`, runs Phishpedia on its own bundled test page, and asks Falcon for a one-word reply. The full log is in `/var/log/mirsad-setup.log`.

Before capturing real suspicious links, connect the host to the network the organizers approved (for example a phone hotspot), because the VM's NAT traffic leaves through the host's connection.

## Download sizes and time

| Item | Size | Basis |
|---|---|---|
| Falcon3-3B-Instruct-q4_k_m.gguf | 2,005,684,448 bytes (1.87 GiB) | Hugging Face API, 23 November 2026 |
| Phishpedia models: `rcnn_bet365.pth`, `resnetv2_rgb_new.pth.tar`, `expand_targetlist.zip`, `faster_rcnn.yaml`, `domain_map.pkl` | 315 MB, 184 MB, 201 MB, 2 KB, and 211 KB (about 700 MB in total) | Google Drive download headers, 23 November 2026 |
| pixi v0.84.2 | 32.7 MB | GitHub release asset |
| Phishpedia's conda and PyPI packages (Python, CPU PyTorch, OpenCV, spaCy, SciPy, and others) | about 1.5 to 2.5 GB | Estimate |
| Playwright Chromium and the headless shell | about 300 MB | Estimate |
| apt packages, including Chromium's libraries | about 300 to 500 MB | Estimate |
| llama.cpp source (shallow clone) | under 100 MB | Estimate |

Expect about 5 to 6 GB of downloads and 10 to 13 GB of disk use on the 30 GB data disk. On a 50 Mbit/s connection with 4 vCPUs, a first run should take 45 to 90 minutes. Most of the CPU time goes to the Detectron2 build (10 to 25 minutes), the llama.cpp build (5 to 15 minutes), and the first computation of Phishpedia's reference logo embeddings (several minutes). The totals and all time figures are estimates; only the rows marked with a source above were measured.

Memory use with 6 GB of RAM: Falcon needs about 2.5 GB, an estimate for the model plus a 4,096-token context. The systemd unit caps the sandbox service, which runs Chromium and the Phishpedia worker, at 3.5 GB, so a heavy page always leaves about 2.5 GB for Falcon, the system, and sshd.

## Checking health from Windows

In PowerShell, use `curl.exe`, because plain `curl` is an alias for `Invoke-WebRequest` in Windows PowerShell 5.1:

```powershell
curl.exe http://127.0.0.1:8601/health
# {"ok":true,"phishpedia":true,"chromium":true,"phishpedia_state":"ready","version":"0.1.0"}
curl.exe http://127.0.0.1:8602/health
# {"status":"ok"}   (HTTP 503 "Loading model" for the first minute after a boot)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8601/capture -ContentType application/json `
  -Body '{"url": "https://example.com/", "timeout_s": 15}' | Select-Object ok, status, title, final_url
```

For a long session, connect with `ssh -i "$env:USERPROFILE\.ssh\mirsad_sandbox" -p 2222 <vm-user>@127.0.0.1` and run `journalctl -u mirsad-sandbox -f` to watch the request log live. After a boot, Phishpedia reports `"phishpedia": false` with `"phishpedia_state": "starting"` for a minute or two while its models load.

The host's settings already point at these ports: `MIRSAD_SANDBOX_URL=http://127.0.0.1:8601` and `FALCON_BASE_URL=http://127.0.0.1:8602/v1`. For the zero-egress summary mode, set `MIRSAD_LLM=falcon`. The model name that llama-server reports is `falcon` (set by `--alias`).

## Service API

All responses are JSON. The service treats a page that fails to load as a normal result and returns HTTP 200 with `"ok": false` and an error code. Bad input returns 422, a private target returns 403, and an unavailable browser or a full queue returns 503. No request crashes the service.

`GET /health` returns `{"ok", "phishpedia": bool, "chromium": bool, "phishpedia_state", "version"}`, plus `phishpedia_reason` or `chromium_reason` when a part is down.

`POST /capture` takes `{"url": "https://...", "timeout_s": 15, "device": "desktop" | "mobile"}`. The desktop profile is Chrome on Windows at 1440 x 900, and the mobile profile is Chrome on Android at 412 x 915. Both use the en-AE locale and the Asia/Dubai time zone. Some scam kits show a harmless page to visitors who do not look like their target (cloaking), so retry with `"device": "mobile"` when a desktop capture of an SMS link looks clean. The response fields are:

| Field | Content |
|---|---|
| `ok`, `error` | `error` is `{"code", "message"}`; codes include `dns_failed`, `navigation_timeout`, `connection_failed`, `tls_error`, `blocked_private_address`, `download_blocked`, and `capture_timeout` |
| `requested_url`, `final_url`, `final_ip` | `final_ip` is the address the egress proxy connected to |
| `redirect_chain` | Every main-frame hop in order: `{"url", "status", "via": "initial" \| "http_redirect" \| "navigation"}`; `navigation` covers JavaScript and meta-refresh hops |
| `status`, `title`, `tls` | `tls` is the certificate issuer, protocol, and validity period from Chromium |
| `language` | `{"declared": <html lang>, "script": "arabic" \| "latin" \| "mixed" \| null}`; the script is counted from the visible text |
| `forms` | One entry per form in every frame, plus one `formless` entry for inputs outside any form: `method`, `action`, `posts_to` (the registered domain), `posts_to_other_domain`, `has_password`, `has_card_like`, `has_otp_like`, and `fields` (`type`, `name`, `autocomplete`, `label`, and the three flags) |
| `has_password_field`, `has_card_field`, `has_otp_field` | Page-level summaries of the form flags |
| `external_resource_ratio`, `resources` | The share of subresource requests whose registered domain differs from the final page's, with the counts |
| `blocked_requests` | `{"host", "reason", "layer"}` for each refused request; a page that redirects to `10.0.2.2` shows up here as evidence |
| `visible_text` | The first 4,000 characters of the page's visible text |
| `screenshot_b64`, `screenshot` | A full-page PNG cropped to at most 1440 x 2000 CSS pixels, with its size and whether it was cut off |
| `network_idle`, `timing` | Whether the network went quiet before the timeout, plus `navigation_ms`, `settle_ms`, `extract_ms`, `screenshot_ms`, and `total_ms` |
| `note` | "Captured in sandbox, no form submitted" |

URLs in the response keep their query strings, because the host decides what to redact. The VM's logs never contain them.

`POST /phishpedia` takes `{"url": "...", "screenshot_b64": "<PNG or JPEG>"}`. It returns `{"brand": str | null, "confidence": float, "logo_box": [x1, y1, x2, y2] | null, "domain_matches_brand": bool, "elapsed_ms": int}` with `"available": true`, or `{"available": false, "reason"}` if Phishpedia is not installed or not loaded. Extra fields are `verdict` (`brand_mismatch`, `brand_match`, `no_brand`, or `no_logo`), `brand_domains`, `phishpedia_consistent`, `logos_detected`, and `threshold` (0.87, Phishpedia's default). The confidence is the Siamese cosine similarity of the best logo crop. The response names a brand only when that similarity reaches the threshold; otherwise `brand` is null, and `confidence` shows the best similarity found.

`domain_matches_brand` is stricter than upstream Phishpedia. It is true only when the page's registered domain is one of the brand's own domains. Upstream also treats a page as benign when only the second-level label matches on a country-code domain, so `salik.co.ae` would pass for `salik.ae`. A scammer can register exactly that kind of name, so the service reports upstream's relaxed verdict separately as `phishpedia_consistent` and does not let it set the match.

## Security rules

### No form submission

The service loads each page once and waits for the network to go quiet. It never types, clicks, or submits. A form that the page submits by itself is a POST navigation, and the route handler aborts every navigation that is not GET or HEAD, recording it in `blocked_requests`. The service refuses downloads (`accept_downloads=False`), closes popups, dismisses dialogs, and grants no browser permission such as location or notifications.

### Private-address block

The VM must never reach a private network. Setup installs no firewall; two layers in `sandbox_service.py` enforce the rule instead. First, a Playwright route handler resolves each request's host with `socket.getaddrinfo`, for both IPv4 and IPv6, and aborts the request if any address is private, loopback, link-local, multicast, reserved, unspecified, or otherwise not global. It also unwraps IPv4-mapped, 6to4, NAT64, and Teredo forms and the browser's shorthand IPv4 notation (2130706433, 0x7f.1, and 127.1 all mean 127.0.0.1). Second, Chromium sends all traffic, WebSockets included, through a SOCKS5 proxy inside the service. The proxy resolves the host again, applies the same rule, and connects only to the exact address it checked. That second check closes the DNS-rebinding gap between two lookups. The service also switches off Chromium's own DNS and does not let WebRTC send UDP outside the proxy. The targets that matter most under VirtualBox NAT are 10.0.2.2 (the host, where Mirsad's API listens on 127.0.0.1:8600) and 10.0.2.3 (the NAT DNS), together with the VM's own ports 8601, 8602, and 22.

### Fresh context

Every capture gets a new browser context with no cookies, storage, or credentials, and with service workers blocked. The service closes the context afterward and restarts the Chromium process itself after every 50 captures. Chromium runs with its own sandbox on: the service runs as your normal account, not root, and sets `chromium_sandbox=True` explicitly, because Playwright otherwise passes `--no-sandbox`. systemd adds `NoNewPrivileges` (so nothing started by the service can use sudo), `ProtectHome` (the browser cannot read `~/.ssh`), `PrivateTmp`, and a read-only `/usr`, `/boot`, and `/etc`.

### No credentials

The VM holds no API keys, tokens, or passwords, and neither service needs any. Do not copy the host's `.env` into the VM. The only secret-adjacent file is the host's SSH public key. Falcon runs fully offline after the download.

### Response size cap

Each upstream connection may deliver at most 5 MB (`MIRSAD_MAX_BODY_BYTES`), so no response body can be larger. With HTTP/2 the cap applies to everything one origin sends over one connection, so a legitimate page that sends more than 5 MB over one connection may render with some images missing.

### Logs

The service writes one line per request with the time, the URL host, and the outcome, for example `2026-11-23T08:12:03Z capture host=salik-topup-uae.top outcome=ok status=200 device=desktop blocked=0 ms=4310`. The service never logs paths or query strings, because phishing URLs often carry victims' data. The log goes to journald and to `/srv/scamshield/logs/sandbox_requests.log`, which rotates at 5 MB.

### Limits

A Chromium exploit that also escaped Chromium's sandbox would reach your VM account, but not the host. Revert the linked clone after the event. Ports 8601 and 8602 have no authentication, so their safety depends on the NAT forwards staying bound to 127.0.0.1 on the host. Traffic during setup (apt, pip, pixi, git, and model downloads) is trusted and not filtered.

## Changes from the upstream instructions

- Phishpedia's `setup.sh` calls `gdown --id`, and current gdown (6.5.2) no longer has that option. Setup passes each Google Drive ID as the positional argument instead. It also pins Detectron2 to a commit rather than building whatever is on `main` that day.
- Phishpedia's `load_config` returns Python lists right after it builds the logo cache, while `pred_brand` expects NumPy arrays. The worker converts them.
- Setup adds `tldextract` to the requested pip packages, to report each form's registered domain. It also adds `unzip`, `ninja-build`, `libgl1`, `libglib2.0-0`, and `e2fsprogs` to the apt list, for the logo archive, a parallel Detectron2 build, OpenCV, and `mkfs.ext4`.
- llama-server gets `--alias falcon --no-ui` in addition to the requested flags. Its default port is now 9931, so `--port 8602` is required.
- Falcon3-3B-Instruct supports English, French, Spanish, and Portuguese according to its model card, and Arabic is not on that list. For Arabic summaries, TII's Falcon-H1-3B-Instruct-GGUF lists Arabic, and its Q4_K_M file is 1,888,612,384 bytes. To switch, run `sudo FALCON_REPO=tiiuae/Falcon-H1-3B-Instruct-GGUF bash setup.sh`. The team has not tested this alternative.

## Sources read on 23 November 2026

- Phishpedia (CC0-1.0): README, `setup.sh`, `pixi.toml`, `configs.py`, `phishpedia.py`, `logo_recog.py`, and `logo_matching.py` at commit `d030779aad0aebd224f2cb60ed1c1603a8efcb1f` (the `main` head, 26 July 2025), from https://github.com/lindsey98/Phishpedia.
- llama.cpp: README, `docs/build.md`, and `tools/server/README.md` at `master` commit `f505c30` (22 November 2026). The server flags were checked again at the pinned release `v1.0.0` (commit `b1b770d`, 13 November 2026), from https://github.com/ggml-org/llama.cpp.
- Falcon: the Hugging Face file listing and model card of `tiiuae/Falcon3-3B-Instruct-GGUF` at revision `142f28a` (last modified 14 January 2025). The license is the TII Falcon-LLM License 2.0.
- pixi v0.84.2 (released 10 November 2026), with the SHA-256 from its GitHub release asset; gdown 6.5.2 (18 November 2026); and Detectron2 `main` at `247691a` (27 October 2026).

Setup pins every one of these versions, and you can override each pin with an environment variable listed at the top of `setup.sh`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `$'\r': command not found` when running setup | The file picked up Windows line endings. Run `sed -i 's/\r$//' setup.sh` and try again. |
| "No empty disk found" | Attach the 30 GB disk in VirtualBox, or name it with `sudo MIRSAD_DATA_DISK=/dev/sdX bash setup.sh`. A disk with any partition or data is refused on purpose. |
| A Phishpedia model download fails | Google Drive limits popular files. Wait and re-run, or download the file on the host from the link that the error prints and copy it to `/srv/scamshield/Phishpedia/models/`. |
| `"chromium": false` | Read `chromium_reason` in `/health` and `journalctl -u mirsad-sandbox -n 100`. Chromium's sandbox needs unprivileged user namespaces: `sysctl kernel.unprivileged_userns_clone` must print 1. |
| `"phishpedia": false` | Read `phishpedia_reason`. The state is `starting` for a minute or two after a boot. |
| Falcon returns 503 | The model is still loading. Check `journalctl -u mirsad-falcon -n 50`. |
| Updated `sandbox_service.py` | Copy the folder in again and re-run `sudo bash setup.sh`. It installs the changed files and restarts the service. |

# Deployment — GitHub + Oracle Cloud (backend) + Vercel (console), ₹0

```
Browser ──HTTPS──> Vercel (React console, security headers)
   │                  └─ rewrites /api, /media, /playback, /webrtc ──HTTPS──┐
   └──── WebSocket (wss) + WebRTC media ───────────────────────────────────>│
                                                   Oracle Cloud VM (Always Free)
                                                   Caddy (Let's Encrypt) → API, gateway,
                                                   MySQL, Redis, simulators (Docker Compose)
```

Vercel serves only the static console; it cannot run databases, the video gateway or
long-lived WebSockets. The complete platform (including its own copy of the console) runs on the
VM, so `https://<vm>.sslip.io` works on its own and Vercel is an additional front door.

## 1. GitHub

```bash
git remote add origin https://github.com/<you>/netra.git
git push -u origin main
```

CI (`.github/workflows/ci.yml`) runs lint, 38 backend tests, the simulator checks, the frontend
build and the Docker image builds on every push.

## 2. Backend on an Oracle Cloud Always-Free VM

1. Sign up at <https://www.oracle.com/cloud/free/> (a card is used only for identity checks;
   Always-Free resources are never charged).
2. **Create instance** → image *Canonical Ubuntu 24.04*, shape **VM.Standard.A1.Flex**
   (Ampere, 2 OCPU / 12 GB is plenty; up to 4 / 24 GB is free). Add your SSH public key.
   If you see "out of capacity", retry later or pick another availability domain.
3. **Networking → the instance's subnet → Security list → Add ingress rules** (source
   `0.0.0.0/0`): TCP `80`, TCP `443`, TCP `8189`, UDP `8189`.
4. SSH in and run the one-command installer:

   ```bash
   ssh ubuntu@<public-ip>
   curl -fsSL https://raw.githubusercontent.com/<you>/netra/main/scripts/deploy-vm.sh | \
     bash -s -- https://github.com/<you>/netra.git you@example.com
   ```

   It installs Docker, adds swap, opens the host firewall, enables automatic security updates,
   generates random secrets, sets `SITE_ADDRESS=<ip-with-dashes>.sslip.io` (free DNS that
   resolves to the VM, so Let's Encrypt can issue a real certificate), starts the stack with
   `docker-compose.prod.yml` and schedules nightly database backups.
5. Set the demo admin password if you want a known one:
   `sudo docker compose exec backend python -m app.manage set-password admin`

**Updating later:** re-run the same `deploy-vm.sh` command (it pulls and restarts in place).

## 3. Console on Vercel

1. Point the console at the VM and push:
   ```bash
   scripts/configure-vercel.sh <ip-with-dashes>.sslip.io
   git add frontend/vercel.json frontend/.env.vercel && git commit -m "Point Vercel at backend" && git push
   ```
2. <https://vercel.com/new> → import the GitHub repo → **Root Directory: `frontend`** → Deploy.
   The framework, build command and rewrites come from `frontend/vercel.json`; no environment
   variables or secrets are needed on Vercel.

## Why it keeps running

| Risk | Protection |
|---|---|
| Process crash | `restart: unless-stopped` on every container; Docker starts on boot |
| Dependency not ready | Backend waits for healthy MySQL/Redis; health checks on backend, MySQL, Redis |
| Memory exhaustion | Per-container `mem_limit`, 4 GB swap, Redis `maxmemory` (only TTL keys evicted) |
| Disk filling | Docker log rotation (3×10 MB per container), MySQL binary logs off, event retention (30 days; alert evidence kept), GPS track retention (48 h), recordings 6 h, ingest streams length-capped, weekly image prune |
| Data loss | Nightly `mysqldump` (7 days kept in `~/netra-backups`), named Docker volumes |
| Certificate expiry | Caddy renews Let's Encrypt certificates automatically |
| Security patches | Ubuntu unattended-upgrades; dependencies pinned with 0 known vulnerabilities |
| Backend unreachable from Vercel | Console shows its error state and reconnects the WebSocket with back-off |

## Health checks

```bash
curl https://<site>/api/health           # liveness
curl https://<site>/api/ready            # database + Redis
sudo docker compose ps                   # container state
sudo docker compose logs --tail=100 backend
```

Free uptime monitoring: add `https://<site>/api/ready` to UptimeRobot (5-minute checks).

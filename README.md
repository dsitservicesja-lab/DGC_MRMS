# DGC Requests & Approvals (Web App Starter)

This is a runnable starter web app that mirrors an Excel workflow:
- Staff submit **Meeting** and **Messenger** requests (Status = Pending only)
- Admin approves/declines from an Admin dashboard
- Meeting conflict checks enforce a **15-minute gap** per location

## Quick start

1. Install Python 3.11+
2. Open a terminal in this folder
3. Create venv and install:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

4. Run the server:

```bash
uvicorn app.main:app --reload
```

5. Open:
- http://127.0.0.1:8000/

## Admin login (default)
- Username: `admin`
- Password: `ChangeMe!2026`

Change these before deployment Mr Ewan by setting environment variables (see app/config.py).
Seed data lives in `data/seed.json`.

## Deploy to Linux server (/opt, port 8082)

This repository now includes:
- `deploy/scripts/deploy_to_opt.sh`
- `deploy/systemd/dgc-ims.service`
- `deploy/systemd/dgc-ims.env.example`

### 1. Copy project to your server

Example with git:

```bash
cd /opt
sudo git clone <your-repo-url> DGC_IMS
cd /opt/DGC_IMS
```

Or copy the folder contents to `/opt/DGC_IMS`.

### 2. Install OS packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 3. Run deployment script

```bash
cd /opt/DGC_IMS
sudo bash deploy/scripts/deploy_to_opt.sh
```

The script will:
- create a system user `dgcims`
- install Python dependencies in `/opt/DGC_IMS/.venv`
- install and start systemd service `dgc-ims`
- run the app on `0.0.0.0:8082`

### 4. Set production secrets

Edit environment file:

```bash
sudo nano /opt/DGC_IMS/.env
```

Set at least:
- `SECRET_KEY` to a new random value
- `ADMIN_PASSWORD_HASH` and `ADMIN_SALT` to your own values

Then restart:

```bash
sudo systemctl restart dgc-ims
```

### 5. Verify service

```bash
sudo systemctl status dgc-ims --no-pager
sudo journalctl -u dgc-ims -n 100 --no-pager
curl http://127.0.0.1:8082/
```

### 6. Optional firewall

```bash
sudo ufw allow 8082/tcp
sudo ufw reload
```

## Safe update script (pull committed/synced changes only)

Use `deploy/scripts/pull_synced_only.sh` on the server to update from GitHub safely.

What it enforces:
- stops if there are any local edits, staged files, or untracked files
- stops if local commits are ahead/diverged from `origin/main`
- fast-forwards only (no merge commits)

Run:

```bash
cd /opt/DGC_IMS
bash deploy/scripts/pull_synced_only.sh main
```

Optional environment variables:
- `SERVICE_NAME` (default: `dgc-ims`)
- `RESTART_SERVICE` (default: `1`; set `0` to skip service restart)

Example:

```bash
cd /opt/DGC_IMS
RESTART_SERVICE=0 bash deploy/scripts/pull_synced_only.sh main
```

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

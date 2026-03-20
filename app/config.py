import os

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_SALT = os.getenv("ADMIN_SALT", "aa13741a62bcfd7c").strip()
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "d6fe4d498577806c6e44b0fd9276d18b171cb272b44fc4a35a58b634e2a8524a").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

SUPERADMIN_USERNAME = os.getenv("SUPERADMIN_USERNAME", "superadmin").strip()
SUPERADMIN_SALT = os.getenv("SUPERADMIN_SALT", "aa13741a62bcfd7c").strip()
SUPERADMIN_PASSWORD_HASH = os.getenv("SUPERADMIN_PASSWORD_HASH", "d6fe4d498577806c6e44b0fd9276d18b171cb272b44fc4a35a58b634e2a8524a").strip()
SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "")

SECRET_KEY = os.getenv("SECRET_KEY", "6ce2ad1f24c2741392733fbacbb6e12b")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dgc.db")

# Email / notification settings
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "dgcjamaica@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "auqa yiqf bmxk nyvz")
EMAIL_FROM = os.getenv("EMAIL_FROM", "DGC Requests <dgcjamaica@gmail.com>")
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "1").strip() == "1"

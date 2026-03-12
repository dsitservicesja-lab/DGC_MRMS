import os
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_SALT = os.getenv("ADMIN_SALT", "aa13741a62bcfd7c")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "d6fe4d498577806c6e44b0fd9276d18b171cb272b44fc4a35a58b634e2a8524a")
SECRET_KEY = os.getenv("SECRET_KEY", "6ce2ad1f24c2741392733fbacbb6e12b")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dgc.db")

from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate()

def _migrate() -> None:
    """Add new columns to existing tables without dropping data."""
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE staff ADD COLUMN email TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists or DB not yet created

def get_session():
    with Session(engine) as session:
        yield session

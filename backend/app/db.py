from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import get_settings


settings = get_settings()

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    future=True,
    connect_args=_connect_args,
    # SQLite: one writer, multiple readers; pool_size irrelevant for SQLite
    pool_pre_ping=True,
)

# Apply SQLite performance pragmas once per new connection
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")       # concurrent reads while writing
        cur.execute("PRAGMA synchronous=NORMAL")     # fsync only at checkpoints (safe)
        cur.execute("PRAGMA cache_size=-131072")     # 128 MB page cache
        cur.execute("PRAGMA temp_store=MEMORY")      # temp tables in RAM
        cur.execute("PRAGMA mmap_size=268435456")    # 256 MB memory-mapped I/O
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


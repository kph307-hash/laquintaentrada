import os
import sqlite3
from pathlib import Path
from typing import Generator

from sqlalchemy import Column, Integer, String, Float, create_engine, Index
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ======================
# Paths (ABSOLUTOS)
# ======================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SQLITE_PATH", "super.db")).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DB_URL = f"sqlite:///{DB_PATH}"
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ======================
# Models (SQLAlchemy)
# ======================

class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(80), nullable=False, unique=True, index=True)
    nombre = Column(String(255), nullable=False, index=True)
    precio = Column(Integer, nullable=False, default=0)  # precio por unidad o por kilo
    familia = Column(String(120), nullable=True, index=True)
    cantidad = Column(Float, nullable=False, default=0.0)  # <- importante
    imagen_url = Column(String(255), nullable=True, default="")
    unidad_medida = Column(String(10), nullable=False, default="UND")  # UND | KG

    __table_args__ = (
        Index("ix_productos_familia_nombre", "familia", "nombre"),
    )


class UsuarioCliente(Base):
    __tablename__ = "usuarios_cliente"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(150), nullable=False, unique=True, index=True)
    telefono = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=False)


# ======================
# Low-level sqlite helper
# ======================

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def table_exists(conn, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def get_table_columns(conn, table_name: str) -> dict:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    rows = cur.fetchall()
    return {row["name"]: row for row in rows}


# ======================
# Migraciones productos
# ======================

def ensure_productos_has_cantidad():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "productos")

    if "cantidad" not in cols:
        cur.execute("ALTER TABLE productos ADD COLUMN cantidad REAL NOT NULL DEFAULT 0;")
        conn.commit()

    conn.close()


def ensure_productos_has_imagen_url():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "productos")

    if "imagen_url" not in cols:
        cur.execute("ALTER TABLE productos ADD COLUMN imagen_url TEXT DEFAULT '';")
        conn.commit()

    conn.close()


def ensure_productos_has_unidad_medida():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "productos")

    if "unidad_medida" not in cols:
        cur.execute("ALTER TABLE productos ADD COLUMN unidad_medida TEXT NOT NULL DEFAULT 'UND';")
        conn.commit()

    conn.close()


def migrate_productos_cantidad_to_real():
    conn = get_conn()
    cur = conn.cursor()

    if not table_exists(conn, "productos"):
        conn.close()
        return

    cols = get_table_columns(conn, "productos")
    if "cantidad" not in cols:
        conn.close()
        return

    cantidad_type = str(cols["cantidad"]["type"] or "").upper()

    # Si ya está como REAL/FLOAT/DOUBLE, no hacer nada
    if any(t in cantidad_type for t in ("REAL", "FLOAT", "DOUBLE")):
        conn.close()
        return

    # SQLite no soporta ALTER COLUMN TYPE, entonces se recrea tabla
    cur.execute("PRAGMA foreign_keys = OFF;")
    conn.commit()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS productos_new (
            id INTEGER PRIMARY KEY,
            sku TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            precio INTEGER NOT NULL DEFAULT 0,
            familia TEXT,
            cantidad REAL NOT NULL DEFAULT 0,
            imagen_url TEXT DEFAULT '',
            unidad_medida TEXT NOT NULL DEFAULT 'UND'
        );
    """)

    cur.execute("""
        INSERT INTO productos_new (id, sku, nombre, precio, familia, cantidad, imagen_url, unidad_medida)
        SELECT
            id,
            sku,
            nombre,
            precio,
            familia,
            CAST(COALESCE(cantidad, 0) AS REAL),
            COALESCE(imagen_url, ''),
            COALESCE(unidad_medida, 'UND')
        FROM productos;
    """)

    cur.execute("DROP TABLE productos;")
    cur.execute("ALTER TABLE productos_new RENAME TO productos;")

    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_productos_sku ON productos(sku);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_productos_nombre ON productos(nombre);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_productos_familia ON productos(familia);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_productos_familia_nombre ON productos(familia, nombre);")

    conn.commit()
    cur.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()


# ======================
# Migraciones pedidos
# ======================

def ensure_pedidos_has_cliente_fields():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "pedidos")

    nuevas_columnas = {
        "usuario_id": "ALTER TABLE pedidos ADD COLUMN usuario_id INTEGER DEFAULT NULL;",
        "cliente_nombre": "ALTER TABLE pedidos ADD COLUMN cliente_nombre TEXT DEFAULT '';",
        "cliente_correo": "ALTER TABLE pedidos ADD COLUMN cliente_correo TEXT DEFAULT '';",
        "cliente_telefono": "ALTER TABLE pedidos ADD COLUMN cliente_telefono TEXT DEFAULT '';",
    }

    for col, sql in nuevas_columnas.items():
        if col not in cols:
            cur.execute(sql)

    conn.commit()
    conn.close()


def ensure_pedido_items_has_sku():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "pedido_items")

    if "sku" not in cols:
        cur.execute("ALTER TABLE pedido_items ADD COLUMN sku TEXT DEFAULT '';")
        conn.commit()

    conn.close()


def ensure_pedido_items_has_es_promo():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "pedido_items")

    if "es_promo" not in cols:
        cur.execute("ALTER TABLE pedido_items ADD COLUMN es_promo INTEGER NOT NULL DEFAULT 0;")
        conn.commit()

    conn.close()


def ensure_pedido_items_has_unidad_medida():
    conn = get_conn()
    cur = conn.cursor()
    cols = get_table_columns(conn, "pedido_items")

    if "unidad_medida" not in cols:
        cur.execute("ALTER TABLE pedido_items ADD COLUMN unidad_medida TEXT NOT NULL DEFAULT 'UND';")
        conn.commit()

    conn.close()


# ======================
# Init DB
# ======================

def init_db():
    # 1) Crear tablas SQLAlchemy
    Base.metadata.create_all(bind=engine)

    # 2) Tablas sqlite directo
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS promos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      titulo TEXT NOT NULL,
      descripcion TEXT DEFAULT '',
      precio TEXT DEFAULT '',
      tipo TEXT DEFAULT 'publicidad',
      imagen_url TEXT DEFAULT '',
      activo INTEGER DEFAULT 1,
      orden INTEGER DEFAULT 0,
      creado_en TEXT DEFAULT (datetime('now'))
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      creado_en TEXT DEFAULT (datetime('now')),
      entregado_en TEXT DEFAULT NULL,
      status TEXT NOT NULL DEFAULT 'pendiente',
      usuario_id INTEGER DEFAULT NULL,
      cliente_nombre TEXT DEFAULT '',
      cliente_correo TEXT DEFAULT '',
      cliente_telefono TEXT DEFAULT '',
      delivery_mode TEXT DEFAULT 'delivery',
      nombre TEXT NOT NULL,
      direccion TEXT DEFAULT '',
      maps_url TEXT DEFAULT '',
      lat REAL DEFAULT NULL,
      lng REAL DEFAULT NULL,
      subtotal INTEGER NOT NULL DEFAULT 0,
      shipping INTEGER NOT NULL DEFAULT 0,
      total INTEGER NOT NULL DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedido_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pedido_id INTEGER NOT NULL,
      sku TEXT DEFAULT '',
      producto TEXT NOT NULL,
      precio_unit INTEGER NOT NULL DEFAULT 0,
      qty REAL NOT NULL DEFAULT 0,
      unidad_medida TEXT NOT NULL DEFAULT 'UND',
      subtotal INTEGER NOT NULL DEFAULT 0,
      es_promo INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS ix_pedidos_status_creado ON pedidos(status, creado_en);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_items_pedido_id ON pedido_items(pedido_id);")

    conn.commit()
    conn.close()

    # 3) Migraciones simples
    ensure_productos_has_cantidad()
    ensure_productos_has_imagen_url()
    ensure_productos_has_unidad_medida()
    migrate_productos_cantidad_to_real()

    ensure_pedidos_has_cliente_fields()
    ensure_pedido_items_has_sku()
    ensure_pedido_items_has_es_promo()
    ensure_pedido_items_has_unidad_medida()


# ======================
# Dependency (FastAPI)
# ======================

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
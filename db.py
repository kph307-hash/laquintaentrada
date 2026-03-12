# db.py
import os
import sqlite3
from pathlib import Path
from typing import Generator

from sqlalchemy import Column, Integer, String, create_engine, UniqueConstraint, Index
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ======================
# Paths (ABSOLUTOS)
# ======================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SQLITE_PATH", "/var/data/super.db")).resolve()

# SQLAlchemy URL usando path absoluto
DB_URL = f"sqlite:///{DB_PATH}"

# check_same_thread solo aplica para sqlite
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

# ======================
# Models (SQLAlchemy)
# ======================

class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)

    sku = Column(String(80), nullable=False, unique=True, index=True)

    nombre = Column(String(255), nullable=False, index=True)
    precio = Column(Integer, nullable=False, default=0)
    familia = Column(String(120), nullable=True, index=True)
    cantidad = Column(Integer, nullable=False, default=0)
    imagen_url = Column(String(255), nullable=True, default="")

    __table_args__ = (
        UniqueConstraint("sku", name="uq_productos_sku"),
        Index("ix_productos_familia_nombre", "familia", "nombre"),
    )

class UsuarioCliente(Base):
    __tablename__ = "usuarios_cliente"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(150), nullable=False, unique=True, index=True)
    telefono = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint("correo", name="uq_usuarios_cliente_correo"),
    )

# ======================
# Low-level sqlite helper (para promos y migración simple)
# ======================

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_productos_has_cantidad():
    """
    SQLite: agrega columna 'cantidad' si no existe.
    create_all() NO altera tablas existentes.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(productos);")
    cols = [row["name"] for row in cur.fetchall()]

    if "cantidad" not in cols:
        cur.execute("ALTER TABLE productos ADD COLUMN cantidad INTEGER NOT NULL DEFAULT 0;")
        conn.commit()

    conn.close()

def ensure_productos_has_imagen_url():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(productos);")
    cols = [row["name"] for row in cur.fetchall()]

    if "imagen_url" not in cols:
        cur.execute("ALTER TABLE productos ADD COLUMN imagen_url TEXT DEFAULT '';")
        conn.commit()

    conn.close()

def ensure_pedidos_has_cliente_fields():
    """
    Agrega columnas a pedidos si no existen, para soportar:
    - compra como invitado
    - compra con usuario
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(pedidos);")
    cols = [row["name"] for row in cur.fetchall()]

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

# ======================
# Init DB (UNIFICADO)
# ======================

def init_db():
    # 1) Crear tablas SQLAlchemy
    Base.metadata.create_all(bind=engine)

    # 2) Tablas sqlite directo (promos + pedidos)
    conn = get_conn()
    cur = conn.cursor()

    # PROMOS
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

    # PEDIDOS
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

    # PEDIDO ITEMS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedido_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pedido_id INTEGER NOT NULL,
      sku TEXT DEFAULT '',
      producto TEXT NOT NULL,
      precio_unit INTEGER NOT NULL DEFAULT 0,
      qty INTEGER NOT NULL DEFAULT 0,
      subtotal INTEGER NOT NULL DEFAULT 0,
      es_promo INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
    );
    """)

    # Índices útiles
    cur.execute("CREATE INDEX IF NOT EXISTS ix_pedidos_status_creado ON pedidos(status, creado_en);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_items_pedido_id ON pedido_items(pedido_id);")

    conn.commit()
    conn.close()

    # 3) Migraciones simples sobre tablas existentes
    ensure_productos_has_cantidad()
    ensure_pedidos_has_cliente_fields()
    ensure_productos_has_imagen_url()

# ======================
# Dependency (FastAPI)
# ======================

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

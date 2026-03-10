from db import SessionLocal, init_db, Producto

productos_iniciales = [
    ("Arroz", 900),
    ("Leche", 750),
    ("Huevos", 2200),
    ("Pan", 1000),
    ("Azucar", 850),
]

def run():
    init_db()
    db = SessionLocal()
    try:
        for nombre, precio in productos_iniciales:
            existe = db.query(Producto).filter(Producto.nombre == nombre).first()
            if not existe:
                db.add(Producto(nombre=nombre, precio=precio))
        db.commit()
        print("✅ BD lista con productos.")
    finally:
        db.close()

if __name__ == "__main__":
    run()

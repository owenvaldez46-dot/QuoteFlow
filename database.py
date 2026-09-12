import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. Obtiene la URL de la base de datos (PostgreSQL en Render) o usa SQLite local por defecto
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quotes.db")

# 2. Corrección requerida por SQLAlchemy para URLs de Render (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. Configura el motor según el tipo de base de datos activa
if "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)

# 4. Creación de la sesión para interactuar con la base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Clase base para declarar los modelos de la base de datos
Base = declarative_base()

# 6. Dependencia para inyectar la sesión en tus rutas de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

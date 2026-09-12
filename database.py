import os
import secrets
import hashlib
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuración de base de datos (Render PostgreSQL vs SQLite local)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quotes.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Utilidad para hashing de contraseñas
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- MODELOS ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    company_name = Column(String, default="")
    company_phone = Column(String, default="")
    company_address = Column(String, default="")
    company_logo = Column(String, default="")
    plan = Column(String, default="free")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "company_name": self.company_name or "",
            "company_phone": self.company_phone or "",
            "company_address": self.company_address or "",
            "company_logo": self.company_logo or "",
            "plan": self.plan or "free",
            "created_at": self.created_at
        }

class Quote(Base):
    __tablename__ = "quotes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    client_name = Column(String, nullable=False)
    client_email = Column(String, default="")
    service_title = Column(String, nullable=False)
    description = Column(Text, default="")
    amount = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    status = Column(String, default="Pendiente")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "client_name": self.client_name,
            "client_email": self.client_email or "",
            "service_title": self.service_title,
            "description": self.description or "",
            "amount": self.amount,
            "tax_rate": self.tax_rate,
            "total_amount": self.total_amount,
            "status": self.status,
            "created_at": self.created_at
        }

# --- INICIALIZACIÓN Y FUNCIONES DE BASE DE DATOS ---
def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Gestión de Usuarios
def create_user(email: str, password: str):
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return None
        new_user = User(email=email, password_hash=hash_password(password))
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user.id
    finally:
        db.close()

def authenticate_user(email: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user and user.password_hash == hash_password(password):
            return user.to_dict()
        return None
    finally:
        db.close()

def get_user_by_id(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return user.to_dict() if user else None
    finally:
        db.close()

def update_user_profile(user_id: int, company_name: str, company_phone: str, company_address: str, company_logo: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.company_name = company_name
            user.company_phone = company_phone
            user.company_address = company_address
            if company_logo:
                user.company_logo = company_logo
            db.commit()
    finally:
        db.close()

def count_user_quotes(user_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Quote).filter(Quote.user_id == user_id).count()
    finally:
        db.close()

def update_user_plan(user_id: int, plan_name: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.plan = plan_name
            db.commit()
    finally:
        db.close()

# Gestión de Cotizaciones
def save_quote(user_id: int, client_name: str, client_email: str, service_title: str, description: str, amount: float, tax_rate: float):
    db = SessionLocal()
    try:
        total_amount = amount + (amount * (tax_rate / 100.0))
        token = secrets.token_urlsafe(16)
        new_quote = Quote(
            user_id=user_id,
            token=token,
            client_name=client_name,
            client_email=client_email,
            service_title=service_title,
            description=description,
            amount=amount,
            tax_rate=tax_rate,
            total_amount=total_amount,
            status="Pendiente"
        )
        db.add(new_quote)
        db.commit()
        db.refresh(new_quote)
        return new_quote.id
    finally:
        db.close()

def update_quote(quote_id: int, user_id: int, client_name: str, client_email: str, service_title: str, description: str, amount: float, tax_rate: float):
    db = SessionLocal()
    try:
        quote = db.query(Quote).filter(Quote.id == quote_id, Quote.user_id == user_id).first()
        if quote:
            quote.client_name = client_name
            quote.client_email = client_email
            quote.service_title = service_title
            quote.description = description
            quote.amount = amount
            quote.tax_rate = tax_rate
            quote.total_amount = amount + (amount * (tax_rate / 100.0))
            db.commit()
    finally:
        db.close()

def get_quote_by_id(quote_id: int, user_id: int):
    db = SessionLocal()
    try:
        quote = db.query(Quote).filter(Quote.id == quote_id, Quote.user_id == user_id).first()
        return quote.to_dict() if quote else None
    finally:
        db.close()

def get_quote_by_token(token: str):
    db = SessionLocal()
    try:
        quote = db.query(Quote).filter(Quote.token == token).first()
        return quote.to_dict() if quote else None
    finally:
        db.close()

def get_filtered_quotes(user_id: int, search: str = "", status_filter: str = "Todos"):
    db = SessionLocal()
    try:
        query = db.query(Quote).filter(Quote.user_id == user_id)
        if status_filter and status_filter != "Todos":
            query = query.filter(Quote.status == status_filter)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Quote.client_name.ilike(search_term),
                    Quote.service_title.ilike(search_term)
                )
            )
        quotes = query.order_by(Quote.created_at.desc()).all()
        return [q.to_dict() for q in quotes]
    finally:
        db.close()

def update_quote_status(quote_id: int, user_id: int, status: str):
    db = SessionLocal()
    try:
        quote = db.query(Quote).filter(Quote.id == quote_id, Quote.user_id == user_id).first()
        if quote:
            quote.status = status
            db.commit()
    finally:
        db.close()

def update_quote_status_by_token(token: str, status: str):
    db = SessionLocal()
    try:
        quote = db.query(Quote).filter(Quote.token == token).first()
        if quote:
            quote.status = status
            db.commit()
    finally:
        db.close()

def get_dashboard_stats(user_id: int):
    db = SessionLocal()
    try:
        quotes = db.query(Quote).filter(Quote.user_id == user_id).all()
        total_quotes = len(quotes)
        approved = sum(1 for q in quotes if q.status in ["Aprobado", "Pagado"])
        pending = sum(1 for q in quotes if q.status == "Pendiente")
        rejected = sum(1 for q in quotes if q.status == "Rechazado")
        
        approved_revenue = sum(q.total_amount for q in quotes if q.status in ["Aprobado", "Pagado"])
        pending_revenue = sum(q.total_amount for q in quotes if q.status == "Pendiente")
        rejected_revenue = sum(q.total_amount for q in quotes if q.status == "Rechazado")
        
        return {
            "total": total_quotes,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "total_amount": approved_revenue,
            "total_revenue": approved_revenue,
            "approved_revenue": approved_revenue,
            "approved_amount": approved_revenue,
            "paid_revenue": approved_revenue,
            "paid_amount": approved_revenue,
            "pending_revenue": pending_revenue,
            "pending_amount": pending_revenue,
            "rejected_revenue": rejected_revenue,
            "rejected_amount": rejected_revenue
        }
    finally:
        db.close()

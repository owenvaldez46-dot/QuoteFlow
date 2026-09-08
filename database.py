import sqlite3
import secrets
import hmac
import hashlib
import os
from datetime import datetime

DB_NAME = "quotes.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    else:
        salt = bytes.fromhex(salt)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return pwd_hash.hex(), salt.hex()

def verify_password(stored_hash: str, stored_salt: str, provided_password: str) -> bool:
    pwd_hash, _ = hash_password(provided_password, stored_salt)
    return hmac.compare_digest(pwd_hash, stored_hash)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            company_name TEXT DEFAULT '',
            company_phone TEXT DEFAULT '',
            company_address TEXT DEFAULT '',
            company_logo TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            client_email TEXT,
            service_title TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            tax_rate REAL DEFAULT 0,
            total_amount REAL NOT NULL,
            status TEXT DEFAULT 'Pendiente',
            created_at TEXT NOT NULL,
            public_token TEXT UNIQUE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Migraciones para columnas faltantes
    for col, query in [
        ("plan", "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'"),
        ("company_name", "ALTER TABLE users ADD COLUMN company_name TEXT DEFAULT ''"),
        ("company_phone", "ALTER TABLE users ADD COLUMN company_phone TEXT DEFAULT ''"),
        ("company_address", "ALTER TABLE users ADD COLUMN company_address TEXT DEFAULT ''"),
        ("company_logo", "ALTER TABLE users ADD COLUMN company_logo TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(query)
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE quotes ADD COLUMN user_id INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE quotes ADD COLUMN public_token TEXT")
    except sqlite3.OperationalError:
        pass

    # Generar tokens de 24 caracteres para cotizaciones antiguas sin token
    cursor.execute("SELECT id FROM quotes WHERE public_token IS NULL OR public_token = ''")
    for row in cursor.fetchall():
        token = secrets.token_urlsafe(24)
        cursor.execute("UPDATE quotes SET public_token = ? WHERE id = ?", (token, row['id']))

    conn.commit()
    conn.close()

def create_user(email: str, password: str):
    conn = get_db()
    cursor = conn.cursor()
    pwd_hash, pwd_salt = hash_password(password)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute('''
            INSERT INTO users (email, password_hash, password_salt, plan, created_at)
            VALUES (?, ?, ?, 'free', ?)
        ''', (email.lower().strip(), pwd_hash, pwd_salt, created_at))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def authenticate_user(email: str, password: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return None
    
    if verify_password(user['password_hash'], user['password_salt'], password):
        return dict(user)
    return None

def get_user_by_id(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, plan, company_name, company_phone, company_address, company_logo, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def update_user_profile(user_id: int, company_name: str, company_phone: str, company_address: str, company_logo: str = None):
    conn = get_db()
    cursor = conn.cursor()
    
    if company_logo:
        cursor.execute('''
            UPDATE users 
            SET company_name = ?, company_phone = ?, company_address = ?, company_logo = ?
            WHERE id = ?
        ''', (company_name, company_phone, company_address, company_logo, user_id))
    else:
        cursor.execute('''
            UPDATE users 
            SET company_name = ?, company_phone = ?, company_address = ?
            WHERE id = ?
        ''', (company_name, company_phone, company_address, user_id))
        
    conn.commit()
    conn.close()

def count_user_quotes(user_id: int) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM quotes WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def update_user_plan(user_id: int, new_plan: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET plan = ? WHERE id = ?", (new_plan, user_id))
    conn.commit()
    conn.close()

def save_quote(user_id, client_name, client_email, service_title, description, amount, tax_rate):
    conn = get_db()
    cursor = conn.cursor()
    total_amount = amount * (1 + tax_rate / 100.0)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    public_token = secrets.token_urlsafe(24)
    
    cursor.execute('''
        INSERT INTO quotes (user_id, client_name, client_email, service_title, description, amount, tax_rate, total_amount, status, created_at, public_token)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?)
    ''', (user_id, client_name, client_email, service_title, description, amount, tax_rate, total_amount, created_at, public_token))
    
    quote_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return quote_id

def update_quote(quote_id, user_id, client_name, client_email, service_title, description, amount, tax_rate):
    conn = get_db()
    cursor = conn.cursor()
    total_amount = amount * (1 + tax_rate / 100.0)
    
    cursor.execute('''
        UPDATE quotes
        SET client_name = ?, client_email = ?, service_title = ?, description = ?, amount = ?, tax_rate = ?, total_amount = ?
        WHERE id = ? AND user_id = ?
    ''', (client_name, client_email, service_title, description, amount, tax_rate, total_amount, quote_id, user_id))
    
    conn.commit()
    conn.close()

def get_quote_by_id(quote_id, user_id=None):
    conn = get_db()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT * FROM quotes WHERE id = ? AND user_id = ?", (quote_id, user_id))
    else:
        cursor.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,))
    quote = cursor.fetchone()
    conn.close()
    return quote

def get_quote_by_token(token):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM quotes WHERE public_token = ?", (token,))
    quote = cursor.fetchone()
    conn.close()
    return quote

def get_filtered_quotes(user_id, search="", status_filter="Todos"):
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM quotes WHERE user_id = ?"
    params = [user_id]

    if status_filter and status_filter != "Todos":
        query += " AND status = ?"
        params.append(status_filter)

    if search:
        query += " AND (client_name LIKE ? OR service_title LIKE ? OR description LIKE ? OR CAST(id AS TEXT) LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term, search_term.replace('#', '')])

    query += " ORDER BY id DESC"
    
    cursor.execute(query, params)
    quotes = cursor.fetchall()
    conn.close()
    return quotes

def update_quote_status(quote_id, user_id, new_status):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE quotes SET status = ? WHERE id = ? AND user_id = ?", (new_status, quote_id, user_id))
    conn.commit()
    conn.close()

def update_quote_status_by_token(token, new_status):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE quotes SET status = ? WHERE public_token = ?", (new_status, token))
    conn.commit()
    conn.close()

def get_dashboard_stats(user_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM quotes WHERE user_id = ?", (user_id,))
    total_count, total_revenue = cursor.fetchone()

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM quotes WHERE status = 'Aprobado' AND user_id = ?", (user_id,))
    approved_count, approved_revenue = cursor.fetchone()

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM quotes WHERE status = 'Pagado' AND user_id = ?", (user_id,))
    paid_count, paid_revenue = cursor.fetchone()

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM quotes WHERE status = 'Pendiente' AND user_id = ?", (user_id,))
    pending_count, pending_revenue = cursor.fetchone()

    conn.close()
    return {
        "total_count": total_count,
        "total_revenue": total_revenue,
        "approved_count": approved_count,
        "approved_revenue": approved_revenue,
        "paid_count": paid_count,
        "paid_revenue": paid_revenue,
        "pending_count": pending_count,
        "pending_revenue": pending_revenue
    }
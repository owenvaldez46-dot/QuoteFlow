import os
import secrets
import hmac
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from database import (
    init_db,
    create_user,
    authenticate_user,
    get_user_by_id,
    update_user_profile,
    count_user_quotes,
    update_user_plan,
    save_quote,
    update_quote,
    get_quote_by_id,
    get_quote_by_token,
    get_filtered_quotes,
    update_quote_status,
    update_quote_status_by_token,
    get_dashboard_stats
)
from pdf_generator import generate_pdf_bytes

app = FastAPI(title="QuoteFlow")

SECRET_KEY = os.getenv("SECRET_KEY", "fallback_dev_secret_key_change_in_production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MAX_FILE_SIZE = 2 * 1024 * 1024
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

FREE_QUOTE_LIMIT = 5

@app.on_event("startup")
def startup_event():
    init_db()

def get_csrf_token(request: Request) -> str:
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(16)
    return request.session["csrf_token"]

def verify_csrf(request: Request, csrf_token: str):
    session_token = request.session.get("csrf_token")
    if not session_token or not hmac.compare_digest(session_token, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido o expirado.")

def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)

def render_with_csrf(request: Request, template_name: str, context: dict):
    context["csrf_token"] = get_csrf_token(request)
    return templates.TemplateResponse(request=request, name=template_name, context=context)

# --- RUTAS DE AUTENTICACIÓN ---
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return render_with_csrf(request, "register.html", {})

@app.post("/register")
def process_register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf(request, csrf_token)
    
    if password != confirm_password:
        return render_with_csrf(request, "register.html", {"error": "Las contraseñas no coinciden"})
    
    if len(password) < 6:
        return render_with_csrf(request, "register.html", {"error": "La contraseña debe tener al menos 6 caracteres"})

    user_id = create_user(email, password)
    if not user_id:
        return render_with_csrf(request, "register.html", {"error": "El correo ya está registrado"})
    
    request.session["user_id"] = user_id
    request.session["user_email"] = email
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return render_with_csrf(request, "login.html", {})

@app.post("/login")
def process_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf(request, csrf_token)
    user = authenticate_user(email, password)
    if not user:
        return render_with_csrf(request, "login.html", {"error": "Credenciales incorrectas"})
    
    request.session["user_id"] = user["id"]
    request.session["user_email"] = user["email"]
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# --- PERFIL Y AJUSTES ---
@app.get("/settings", response_class=HTMLResponse)
def show_settings(request: Request, saved: bool = False, error: str = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return render_with_csrf(request, "settings.html", {"user": user, "saved": saved, "error": error})

@app.post("/settings")
async def process_settings(
    request: Request,
    csrf_token: str = Form(...),
    company_name: str = Form(""),
    company_phone: str = Form(""),
    company_address: str = Form(""),
    logo: UploadFile = File(None)
):
    verify_csrf(request, csrf_token)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    logo_path = user.get("company_logo")
    
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1].lower()
        if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
            return RedirectResponse(url="/settings?error=formato_invalido", status_code=303)

        content = await logo.read()
        if len(content) > MAX_FILE_SIZE:
            return RedirectResponse(url="/settings?error=tamano_excedido", status_code=303)

        random_name = f"logo_{user['id']}_{secrets.token_hex(8)}{ext}"
        file_location = os.path.join(UPLOAD_DIR, random_name)
        
        with open(file_location, "wb") as buffer:
            buffer.write(content)
            
        if user.get("company_logo"):
            old_logo_rel = user["company_logo"].lstrip("/")
            if os.path.exists(old_logo_rel):
                try:
                    os.remove(old_logo_rel)
                except OSError:
                    pass

        logo_path = f"/static/uploads/{random_name}"

    update_user_profile(
        user_id=user["id"],
        company_name=company_name.strip(),
        company_phone=company_phone.strip(),
        company_address=company_address.strip(),
        company_logo=logo_path
    )

    return RedirectResponse(url="/settings?saved=true", status_code=303)

# --- CREACIÓN Y EDICIÓN ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    quote_count = count_user_quotes(user["id"])
    limit_reached = (user["plan"] == "free" and quote_count >= FREE_QUOTE_LIMIT)
    
    return render_with_csrf(request, "index.html", {
        "user": user,
        "quote_count": quote_count,
        "free_limit": FREE_QUOTE_LIMIT,
        "limit_reached": limit_reached
    })

@app.post("/create")
def create_quote(
    request: Request,
    csrf_token: str = Form(...),
    client_name: str = Form(...),
    client_email: str = Form(""),
    service_title: str = Form(...),
    description: str = Form(""),
    amount: float = Form(...),
    tax_rate: float = Form(0.0)
):
    verify_csrf(request, csrf_token)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if amount <= 0 or tax_rate < 0 or tax_rate > 100:
        return render_with_csrf(request, "index.html", {
            "user": user,
            "error": "Monto debe ser mayor a 0 e impuesto entre 0% y 100%",
            "quote_count": count_user_quotes(user["id"]),
            "free_limit": FREE_QUOTE_LIMIT,
            "limit_reached": False
        })

    quote_count = count_user_quotes(user["id"])
    if user["plan"] == "free" and quote_count >= FREE_QUOTE_LIMIT:
        return RedirectResponse(url="/upgrade?reason=limit", status_code=303)

    quote_id = save_quote(
        user_id=user["id"],
        client_name=client_name.strip(),
        client_email=client_email.strip(),
        service_title=service_title.strip(),
        description=description.strip(),
        amount=amount,
        tax_rate=tax_rate
    )
    return RedirectResponse(url=f"/quote/{quote_id}", status_code=303)

@app.get("/upgrade", response_class=HTMLResponse)
def show_upgrade(request: Request, reason: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quote_count = count_user_quotes(user["id"])
    return render_with_csrf(request, "upgrade.html", {
        "user": user,
        "quote_count": quote_count,
        "free_limit": FREE_QUOTE_LIMIT,
        "reason": reason
    })

@app.post("/upgrade/process")
def process_upgrade(request: Request, csrf_token: str = Form(...)):
    verify_csrf(request, csrf_token)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    update_user_plan(user["id"], "pro")
    return RedirectResponse(url="/dashboard?upgraded=true", status_code=303)

@app.get("/quote/{quote_id}", response_class=HTMLResponse)
def show_quote(request: Request, quote_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quote = get_quote_by_id(quote_id, user_id=user["id"])
    if not quote:
        return HTMLResponse(content="Cotización no encontrada", status_code=404)
    return render_with_csrf(request, "quote.html", {"quote": quote, "user": user})

@app.get("/quote/{quote_id}/edit", response_class=HTMLResponse)
def show_edit_form(request: Request, quote_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quote = get_quote_by_id(quote_id, user_id=user["id"])
    if not quote:
        return HTMLResponse(content="Cotización no encontrada", status_code=404)
    return render_with_csrf(request, "edit.html", {"quote": quote, "user": user})

@app.post("/quote/{quote_id}/edit")
def process_edit_quote(
    request: Request,
    quote_id: int,
    csrf_token: str = Form(...),
    client_name: str = Form(...),
    client_email: str = Form(""),
    service_title: str = Form(...),
    description: str = Form(""),
    amount: float = Form(...),
    tax_rate: float = Form(0.0)
):
    verify_csrf(request, csrf_token)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if amount <= 0 or tax_rate < 0 or tax_rate > 100:
        quote = get_quote_by_id(quote_id, user_id=user["id"])
        return render_with_csrf(request, "edit.html", {"quote": quote, "user": user, "error": "Monto debe ser mayor a 0 e impuesto válido"})

    update_quote(
        quote_id=quote_id,
        user_id=user["id"],
        client_name=client_name.strip(),
        client_email=client_email.strip(),
        service_title=service_title.strip(),
        description=description.strip(),
        amount=amount,
        tax_rate=tax_rate
    )
    return RedirectResponse(url=f"/quote/{quote_id}", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def show_dashboard(request: Request, q: str = "", status: str = "Todos", upgraded: bool = False):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quotes = get_filtered_quotes(user_id=user["id"], search=q.strip(), status_filter=status)
    stats = get_dashboard_stats(user_id=user["id"])
    quote_count = count_user_quotes(user["id"])

    return render_with_csrf(request, "dashboard.html", {
        "quotes": quotes,
        "stats": stats,
        "q": q,
        "current_status": status,
        "user": user,
        "quote_count": quote_count,
        "free_limit": FREE_QUOTE_LIMIT,
        "upgraded": upgraded
    })

@app.post("/update-status/{quote_id}")
def change_status(request: Request, quote_id: int, csrf_token: str = Form(...), status: str = Form(...)):
    verify_csrf(request, csrf_token)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    update_quote_status(quote_id, user["id"], status)
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/quote/{quote_id}/pdf")
def download_pdf(request: Request, quote_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quote = get_quote_by_id(quote_id, user_id=user["id"])
    if not quote:
        return HTMLResponse(content="Cotización no encontrada", status_code=404)

    pdf_bytes = generate_pdf_bytes(quote, user=user)
    filename = f"Cotizacion_{quote['id']:03d}_{quote['client_name'].replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- PORTAL PÚBLICO ---
@app.get("/q/{token}", response_class=HTMLResponse)
def show_public_quote(request: Request, token: str):
    quote = get_quote_by_token(token)
    if not quote:
        return HTMLResponse(content="<h1>404 - Presupuesto no encontrado</h1>", status_code=404)
    
    creator = get_user_by_id(quote["user_id"])
    return render_with_csrf(request, "public_quote.html", {"quote": quote, "creator": creator})

@app.post("/q/{token}/respond")
def respond_public_quote(request: Request, token: str, csrf_token: str = Form(...), action: str = Form(...)):
    verify_csrf(request, csrf_token)
    quote = get_quote_by_token(token)
    if not quote:
        return HTMLResponse(content="Presupuesto no encontrado", status_code=404)
    
    if action == "approve":
        update_quote_status_by_token(token, "Aprobado")
    elif action == "reject":
        update_quote_status_by_token(token, "Rechazado")

    return RedirectResponse(url=f"/q/{token}", status_code=303)
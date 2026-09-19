import os
import secrets
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from database import (
    init_db,
    SessionLocal,
    User,
    create_user,
    authenticate_user,
    get_user_by_id,
    update_user_profile,
    count_user_quotes,
    update_user_plan,
    save_quote,
    update_quote,
    delete_quote,
    get_quote_by_id,
    get_quote_by_token,
    get_filtered_quotes,
    update_quote_status,
    update_quote_status_by_token,
    get_dashboard_stats
)
from pdf_generator import generate_pdf_bytes

# Inicializar base de datos
init_db()

app = FastAPI(title="QuoteFlow")

# Montar archivos estáticos si existe la carpeta
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

SECRET_KEY = os.getenv("SECRET_KEY", "fallback_dev_secret_key_change_in_production")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "mi_clave_secreta_admin_123")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

FREE_QUOTE_LIMIT = 5


# --- HELPERS Y SEGURIDAD CSRF ---

def get_csrf_token(request: Request) -> str:
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(32)
    return request.session["csrf_token"]


def verify_csrf(request: Request, csrf_token: str = Form(...)):
    session_token = request.session.get("csrf_token")
    if not session_token or not secrets.compare_digest(session_token, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido o expirado.")


def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def render_with_csrf(request: Request, template_name: str, context: dict = None, status_code: int = 200):
    if context is None:
        context = {}
    context["csrf_token"] = get_csrf_token(request)
    return templates.TemplateResponse(
        request=request, 
        name=template_name, 
        context=context, 
        status_code=status_code
    )


# --- RUTAS DE AUTENTICACIÓN ---

@app.get("/register", response_class=HTMLResponse)
def show_register(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return render_with_csrf(request, "register.html")


@app.post("/register")
def process_register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf(request, csrf_token)
    user = create_user(email.lower().strip(), password)
    if not user:
        return render_with_csrf(request, "register.html", {"error": "El correo ya está registrado."}, status_code=400)
    
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def show_login(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return render_with_csrf(request, "login.html")


@app.post("/login")
def process_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf(request, csrf_token)
    user = authenticate_user(email.lower().strip(), password)
    if not user:
        return render_with_csrf(request, "login.html", {"error": "Credenciales incorrectas."}, status_code=400)
    
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/logout")
def process_logout(request: Request, csrf_token: str = Form(...)):
    verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# --- RUTA SECRETA DE ADMINISTRACIÓN (ACTIVACIÓN MANUAL PRO) ---

@app.get("/admin/activate-pro")
def admin_activate_pro(email: str, key: str):
    if key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Acceso denegado: Clave de administrador inválida.")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.lower().strip()).first()
        if not user:
            return {"status": "error", "message": f"Usuario con email '{email}' no encontrado."}
        
        user.plan = "pro"
        db.commit()
        return {
            "status": "success",
            "message": f"¡Éxito! El usuario '{user.email}' (ID: {user.id}) ha sido actualizado al Plan PRO."
        }
    finally:
        db.close()


# --- RUTAS DE PLANES Y SUSCRIPCIÓN ---

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


# --- RUTAS PRINCIPALES DEL SISTEMA ---

@app.get("/", response_class=HTMLResponse)
def show_index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    quote_count = count_user_quotes(user["id"])
    if user["plan"] == "free" and quote_count >= FREE_QUOTE_LIMIT:
        return RedirectResponse(url="/upgrade?reason=limit", status_code=303)

    return render_with_csrf(request, "index.html", {
        "user": user,
        "quote_count": quote_count,
        "free_limit": FREE_QUOTE_LIMIT
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

    quote_count = count_user_quotes(user["id"])
    if user["plan"] == "free" and quote_count >= FREE_QUOTE_LIMIT:
        return RedirectResponse(url="/upgrade?reason=limit", status_code=303)

    if amount <= 0 or tax_rate < 0 or tax_rate > 100:
        return render_with_csrf(request, "index.html", {
            "user": user,
            "error": "Monto debe ser mayor a 0 e impuesto entre 0% y 100%",
            "quote_count": quote_count,
            "free_limit": FREE_QUOTE_LIMIT
        }, status_code=400)

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


@app.get("/dashboard", response_class=HTMLResponse)
def show_dashboard(request: Request, status: str = "", search: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quotes = get_filtered_quotes(user_id=user["id"], search=search.strip(), status_filter=status)
    stats = get_dashboard_stats(user["id"])
    quote_count = count_user_quotes(user["id"])

    return render_with_csrf(request, "dashboard.html", {
        "user": user,
        "quotes": quotes,
        "stats": stats,
        "quote_count": quote_count,
        "free_limit": FREE_QUOTE_LIMIT,
        "current_status": status,
        "current_search": search
    })


@app.get("/settings", response_class=HTMLResponse)
def show_settings(request: Request, saved: bool = False, error: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return render_with_csrf(request, "settings.html", {
        "user": user,
        "saved": saved,
        "error": error
    })


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

    logo_url = user.get("company_logo")

    if logo and logo.filename:
        allowed_types = ["image/png", "image/jpeg", "image/webp"]
        if logo.content_type not in allowed_types:
            return RedirectResponse(url="/settings?error=formato_invalido", status_code=303)
        
        contents = await logo.read()
        if len(contents) > 2 * 1024 * 1024:
            return RedirectResponse(url="/settings?error=tamano_excedido", status_code=303)

        os.makedirs("static/uploads", exist_ok=True)
        file_ext = logo.filename.split(".")[-1]
        file_path = f"static/uploads/logo_user_{user['id']}.{file_ext}"

        with open(file_path, "wb") as f:
            f.write(contents)

        logo_url = f"/{file_path}"

    update_user_profile(
        user_id=user["id"],
        company_name=company_name.strip(),
        company_phone=company_phone.strip(),
        company_address=company_address.strip(),
        company_logo=logo_url
    )

    return RedirectResponse(url="/settings?saved=true", status_code=303)


# --- GESTIÓN DE COTIZACIONES ---

@app.get("/quote/{quote_id}", response_class=HTMLResponse)
def show_quote(request: Request, quote_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quote = get_quote_by_id(quote_id, user_id=user["id"])
    if not quote:
        return HTMLResponse(content="<h1>404 - Cotización no encontrada</h1>", status_code=404)
    
    base_url = str(request.base_url).rstrip("/")
    token_val = quote.get("token") or quote.get("public_token", "")
    share_url = f"{base_url}/q/{token_val}"

    return render_with_csrf(request, "quote.html", {
        "quote": quote,
        "user": user,
        "share_url": share_url
    })


@app.get("/quote/{quote_id}/edit", response_class=HTMLResponse)
def show_edit_form(request: Request, quote_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    quote = get_quote_by_id(quote_id, user_id=user["id"])
    if not quote:
        return HTMLResponse(content="<h1>404 - Cotización no encontrada</h1>", status_code=404)
        
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
        return render_with_csrf(request, "edit.html", {
            "quote": quote,
            "user": user,
            "error": "Monto debe ser mayor a 0 e impuesto entre 0% y 100%"
        }, status_code=400)

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


@app.post("/quote/{quote_id}/delete")
def process_delete_quote(request: Request, quote_id: int, csrf_token: str = Form(...)):
    verify_csrf(request, csrf_token)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    delete_quote(quote_id=quote_id, user_id=user["id"])
    return RedirectResponse(url="/dashboard", status_code=303)


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
        return HTMLResponse(content="<h1>404 - Cotización no encontrada</h1>", status_code=404)

    pdf_bytes = generate_pdf_bytes(quote, user=user)
    clean_client_name = quote['client_name'].replace(' ', '_')
    filename = f"Cotizacion_{quote['id']:03d}_{clean_client_name}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --- PORTAL PÚBLICO ---

@app.get("/q")
@app.get("/q/")
def redirect_public_root():
    return RedirectResponse(url="/", status_code=303)


@app.get("/q/{token}", response_class=HTMLResponse)
def show_public_quote(request: Request, token: str):
    quote = get_quote_by_token(token)
    if not quote:
        return HTMLResponse(content="<h1>404 - Presupuesto no encontrado</h1>", status_code=404)
    
    creator = get_user_by_id(quote["user_id"])
    return render_with_csrf(request, "public_quote.html", {
        "quote": quote,
        "creator": creator,
        "token": token
    })


@app.post("/q/{token}/respond")
def respond_public_quote(request: Request, token: str, csrf_token: str = Form(...), action: str = Form(...)):
    verify_csrf(request, csrf_token)
    quote = get_quote_by_token(token)
    if not quote:
        return HTMLResponse(content="<h1>404 - Presupuesto no encontrado</h1>", status_code=404)
    
    if action == "approve":
        update_quote_status_by_token(token, "Aprobado")
    elif action == "reject":
        update_quote_status_by_token(token, "Rechazado")

    return RedirectResponse(url=f"/q/{token}", status_code=303)

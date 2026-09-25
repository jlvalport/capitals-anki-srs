import os
import random
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Header
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import init_db, get_db_connection
from auth import hash_password, verify_password, create_session, delete_session, get_current_user
from srs_engine import process_review, get_button_intervals, format_interval

# Inicializar Base de Datos al arrancar
init_db()

app = FastAPI(
    title="Capitals of the World - Anki SRS",
    description="Aplicación web REST API para aprender las capitales del mundo con repetición espaciada Anki (1m, 10m, 1d, 4d).",
    version="1.0.0"
)

# CORS para permitir peticiones locales y desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Manejador personalizado de errores de validación (Pydantic / FastAPI 422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_messages = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = loc[-1] if loc else "campo"
        if field == "email":
            error_messages.append("El correo electrónico es obligatorio y debe tener un formato válido.")
        elif field == "username":
            error_messages.append("El nombre de usuario es obligatorio (entre 3 y 30 caracteres).")
        elif field == "password":
            error_messages.append("La contraseña es obligatoria y debe tener al menos 6 caracteres.")
        else:
            error_messages.append(f"El campo '{field}' es inválido.")
    
    detail = " ".join(error_messages) if error_messages else "Datos de formulario inválidos."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": detail}
    )

# Modelos Pydantic para Validaciones
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    login: str = Field(..., description="Nombre de usuario o correo electrónico")
    password: str

class ReviewRequest(BaseModel):
    country_id: int
    rating: str = Field(..., description="again, hard, good, easy")
    response_time_ms: Optional[int] = 0


# ============================================================================
# ENDPOINTS DE AUTENTICACIÓN
# ============================================================================

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verificar si el usuario o correo ya existen
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?;", (req.username, req.email))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario o correo electrónico ya está registrado."
        )

    pwd_hash, salt = hash_password(req.password)
    cursor.execute("""
        INSERT INTO users (username, email, password_hash, salt)
        VALUES (?, ?, ?, ?);
    """, (req.username, req.email, pwd_hash, salt))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    token = create_session(user_id)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "username": req.username,
            "email": req.email
        },
        "message": "Usuario registrado exitosamente."
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, password_hash, salt
        FROM users
        WHERE username = ? OR email = ?;
    """, (req.login, req.login))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(req.password, user["password_hash"], user["salt"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas. Verifique su usuario y contraseña."
        )

    token = create_session(user["id"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"]
        },
        "message": "Sesión iniciada con éxito."
    }

@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {"user": current_user}

@app.post("/api/auth/logout")
def logout(
    current_user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None)
):
    if authorization:
        parts = authorization.strip().split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else parts[0]
        delete_session(token)
    return {"message": "Sesión cerrada exitosamente."}


# ============================================================================
# ENDPOINTS DE PAÍSES Y EXPLORADOR
# ============================================================================

@app.get("/api/countries")
def get_countries(
    continent: Optional[str] = None,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Retorna la lista completa de países con el estado de aprendizaje del usuario actual.
    Soporta filtros por continente, búsqueda por texto y estado (learned, learning, new).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT 
            c.id, c.name_es, c.name_en, c.capital_es, c.capital_en,
            c.continent, c.subregion, c.code, c.flag_emoji, c.fun_fact,
            COALESCE(p.state, 'new') AS state,
            COALESCE(p.step, 0) AS step,
            COALESCE(p.interval_seconds, 60) AS interval_seconds,
            COALESCE(p.ease_factor, 2.5) AS ease_factor,
            COALESCE(p.repetitions, 0) AS repetitions,
            COALESCE(p.lapses, 0) AS lapses,
            COALESCE(p.is_learned, 0) AS is_learned,
            p.due_at,
            p.last_reviewed_at
        FROM countries c
        LEFT JOIN user_country_progress p 
            ON c.id = p.country_id AND p.user_id = ?
        WHERE 1=1
    """
    params = [current_user["id"]]

    if continent and continent.lower() != "todos":
        query += " AND c.continent = ?"
        params.append(continent)

    if search:
        search_term = f"%{search.strip()}%"
        query += " AND (c.name_es LIKE ? OR c.capital_es LIKE ? OR c.name_en LIKE ?)"
        params.extend([search_term, search_term, search_term])

    if status_filter:
        if status_filter == "learned":
            query += " AND p.is_learned = 1"
        elif status_filter == "learning":
            query += " AND p.state = 'learning' AND (p.is_learned = 0 OR p.is_learned IS NULL)"
        elif status_filter == "new":
            query += " AND (p.id IS NULL OR p.state = 'new')"

    query += " ORDER BY c.name_es ASC;"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {"countries": rows, "total": len(rows)}


# ============================================================================
# ENDPOINTS DE REPETICIÓN ESPACIADA (ANKI SRS)
# ============================================================================

@app.get("/api/srs/due")
def get_due_cards(
    limit: int = Query(15, ge=1, le=50),
    continent: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene las tarjetas listas para estudiar:
    1. Tarjetas en repaso que ya vencieron (due_at <= now).
    2. Tarjetas nuevas nunca antes vistas para completar el límite de estudio.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Tarjetas pendientes de repaso
    query_due = """
        SELECT 
            c.id, c.name_es, c.name_en, c.capital_es, c.capital_en,
            c.continent, c.subregion, c.code, c.flag_emoji, c.fun_fact,
            p.state, p.step, p.interval_seconds, p.ease_factor,
            p.repetitions, p.lapses, p.is_learned, p.due_at
        FROM user_country_progress p
        JOIN countries c ON p.country_id = c.id
        WHERE p.user_id = ? AND p.due_at <= ?
    """
    params_due = [current_user["id"], now_str]
    if continent and continent.lower() != "todos":
        query_due += " AND c.continent = ?"
        params_due.append(continent)

    query_due += " ORDER BY p.due_at ASC LIMIT ?;"
    params_due.append(limit)

    cursor.execute(query_due, params_due)
    due_cards = [dict(r) for r in cursor.fetchall()]

    # 2. Si hay espacio, agregar tarjetas nuevas
    needed = limit - len(due_cards)
    new_cards = []
    if needed > 0:
        query_new = """
            SELECT 
                c.id, c.name_es, c.name_en, c.capital_es, c.capital_en,
                c.continent, c.subregion, c.code, c.flag_emoji, c.fun_fact,
                'new' AS state, 0 AS step, 60 AS interval_seconds, 2.5 AS ease_factor,
                0 AS repetitions, 0 AS lapses, 0 AS is_learned, NULL AS due_at
            FROM countries c
            LEFT JOIN user_country_progress p 
                ON c.id = p.country_id AND p.user_id = ?
            WHERE p.id IS NULL
        """
        params_new = [current_user["id"]]
        if continent and continent.lower() != "todos":
            query_new += " AND c.continent = ?"
            params_new.append(continent)

        query_new += " ORDER BY RANDOM() LIMIT ?;"
        params_new.append(needed)

        cursor.execute(query_new, params_new)
        new_cards = [dict(r) for r in cursor.fetchall()]

    # Combinar y calcular los intervalos dinámicos para los botones de cada tarjeta
    cards = due_cards + new_cards
    for card in cards:
        card["buttons"] = get_button_intervals(
            step=card["step"],
            interval_seconds=card["interval_seconds"],
            ease_factor=card["ease_factor"],
            is_learned=card["is_learned"]
        )

    # Próxima tarjeta programada en espera (si la hay)
    cursor.execute("""
        SELECT due_at 
        FROM user_country_progress 
        WHERE user_id = ? AND due_at > ?
        ORDER BY due_at ASC LIMIT 1;
    """, (current_user["id"], now_str))
    next_row = cursor.fetchone()
    next_due_time = next_row["due_at"] if next_row else None

    conn.close()

    return {
        "cards": cards,
        "due_count": len(due_cards),
        "new_count": len(new_cards),
        "total_ready": len(cards),
        "next_due_time": next_due_time
    }


@app.post("/api/srs/review")
def submit_review(
    req: ReviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Procesa la calificación de una tarjeta según el algoritmo Anki:
    - again: 1 min
    - hard: intervalo intermedio
    - good: 1 min -> 10 min -> 1 día (graduado) -> 4 días -> intervalo * ease
    - easy: salto rápido a 1 día / 4 días
    Persiste de inmediato en SQLite el estado y si el país está aprendido (is_learned).
    """
    valid_ratings = {"again", "hard", "good", "easy"}
    if req.rating.lower() not in valid_ratings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Calificación inválida: '{req.rating}'. Opciones válidas: again, hard, good, easy."
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener estado actual de la tarjeta para el usuario
    cursor.execute("""
        SELECT * FROM user_country_progress 
        WHERE user_id = ? AND country_id = ?;
    """, (current_user["id"], req.country_id))
    existing = cursor.fetchone()

    if existing:
        current_step = existing["step"]
        current_interval = existing["interval_seconds"]
        current_ease = existing["ease_factor"]
        current_reps = existing["repetitions"]
        current_lapses = existing["lapses"]
        current_is_learned = existing["is_learned"]
    else:
        # Tarjeta nueva
        current_step = 0
        current_interval = 60
        current_ease = 2.5
        current_reps = 0
        current_lapses = 0
        current_is_learned = 0

    # Procesar con el motor Anki SRS
    result = process_review(
        rating=req.rating,
        current_step=current_step,
        current_interval=current_interval,
        current_ease=current_ease,
        current_repetitions=current_reps,
        current_lapses=current_lapses,
        current_is_learned=current_is_learned
    )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Guardar / Actualizar en user_country_progress
    cursor.execute("""
        INSERT INTO user_country_progress (
            user_id, country_id, state, step, interval_seconds, 
            ease_factor, repetitions, lapses, last_reviewed_at, due_at, is_learned
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, country_id) DO UPDATE SET
            state = excluded.state,
            step = excluded.step,
            interval_seconds = excluded.interval_seconds,
            ease_factor = excluded.ease_factor,
            repetitions = excluded.repetitions,
            lapses = excluded.lapses,
            last_reviewed_at = excluded.last_reviewed_at,
            due_at = excluded.due_at,
            is_learned = CASE WHEN user_country_progress.is_learned = 1 THEN 1 ELSE excluded.is_learned END;
    """, (
        current_user["id"],
        req.country_id,
        result["state"],
        result["step"],
        result["interval_seconds"],
        result["ease_factor"],
        result["repetitions"],
        result["lapses"],
        now_str,
        result["due_at"],
        result["is_learned"]
    ))

    # Registrar en review_logs para auditoría y analítica
    cursor.execute("""
        INSERT INTO review_logs (
            user_id, country_id, rating, step_before, step_after, 
            interval_after, response_time_ms
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (
        current_user["id"],
        req.country_id,
        req.rating.lower(),
        current_step,
        result["step"],
        result["interval_seconds"],
        req.response_time_ms
    ))

    # Obtener conteos actualizados del usuario para reflejar de inmediato en frontend
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN is_learned = 1 THEN 1 END) AS total_learned,
            COUNT(CASE WHEN is_learned = 0 AND repetitions > 0 THEN 1 END) AS total_learning
        FROM user_country_progress
        WHERE user_id = ?;
    """, (current_user["id"],))
    count_row = cursor.fetchone()
    total_learned = count_row["total_learned"] if count_row else 0
    total_learning = count_row["total_learning"] if count_row else 0

    conn.commit()
    conn.close()

    new_buttons = get_button_intervals(
        step=result["step"],
        interval_seconds=result["interval_seconds"],
        ease_factor=result["ease_factor"],
        is_learned=result["is_learned"]
    )

    return {
        "success": True,
        "rating": req.rating,
        "new_state": result["state"],
        "new_step": result["step"],
        "interval_seconds": result["interval_seconds"],
        "interval_label": result["interval_label"],
        "is_learned": bool(result["is_learned"]),
        "due_at": result["due_at"],
        "buttons": new_buttons,
        "total_learned": total_learned,
        "total_learning": total_learning
    }


@app.get("/api/srs/stats")
def get_stats(current_user: dict = Depends(get_current_user)):
    """
    Retorna métricas completas de aprendizaje para el usuario:
    - Total de países en el mundo (~195)
    - Países aprendidos / dominados (is_learned = 1)
    - Países en proceso de aprendizaje (1m / 10m)
    - Países aún no vistos
    - Tarjetas listas para repasar hoy
    - Racha y porcentaje global de maestría
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Total países
    cursor.execute("SELECT COUNT(*) AS total FROM countries;")
    total_countries = cursor.fetchone()["total"]

    # 2. Países aprendidos (is_learned = 1)
    cursor.execute("""
        SELECT COUNT(*) AS learned 
        FROM user_country_progress 
        WHERE user_id = ? AND is_learned = 1;
    """, (current_user["id"],))
    learned_count = cursor.fetchone()["learned"]

    # 3. Países en aprendizaje
    cursor.execute("""
        SELECT COUNT(*) AS learning 
        FROM user_country_progress 
        WHERE user_id = ? AND state = 'learning' AND is_learned = 0;
    """, (current_user["id"],))
    learning_count = cursor.fetchone()["learning"]

    # 4. Tarjetas pendientes ahora
    cursor.execute("""
        SELECT COUNT(*) AS due 
        FROM user_country_progress 
        WHERE user_id = ? AND due_at <= ?;
    """, (current_user["id"], now_str))
    due_count = cursor.fetchone()["due"]

    # 5. Total repasos realizados
    cursor.execute("""
        SELECT COUNT(*) AS total_reviews 
        FROM review_logs 
        WHERE user_id = ?;
    """, (current_user["id"],))
    total_reviews = cursor.fetchone()["total_reviews"]

    # 6. Desglose por continente
    cursor.execute("""
        SELECT 
            c.continent,
            COUNT(c.id) AS total_continent,
            SUM(CASE WHEN p.is_learned = 1 THEN 1 ELSE 0 END) AS learned_continent
        FROM countries c
        LEFT JOIN user_country_progress p 
            ON c.id = p.country_id AND p.user_id = ?
        GROUP BY c.continent
        ORDER BY c.continent;
    """, (current_user["id"],))
    continents_data = [dict(r) for r in cursor.fetchall()]

    conn.close()

    unseen_count = max(0, total_countries - (learned_count + learning_count))
    mastery_percentage = round((learned_count / total_countries * 100), 1) if total_countries > 0 else 0

    return {
        "total_countries": total_countries,
        "learned_count": learned_count,
        "learning_count": learning_count,
        "unseen_count": unseen_count,
        "due_count": due_count,
        "total_reviews": total_reviews,
        "mastery_percentage": mastery_percentage,
        "continents": continents_data
    }


# ============================================================================
# ENDPOINTS DE QUIZ (OPCIÓN MÚLTIPLE)
# ============================================================================

@app.get("/api/quiz/question")
def get_quiz_question(
    continent: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Genera una pregunta dinámica de opción múltiple con 4 alternativas.
    Selecciona un país objetivo y 3 distractores del mismo continente o al azar.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT id, name_es, capital_es, flag_emoji, continent, fun_fact FROM countries WHERE 1=1"
    params = []
    if continent and continent.lower() != "todos":
        query += " AND continent = ?"
        params.append(continent)

    cursor.execute(query, params)
    all_eligible = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if len(all_eligible) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay suficientes países en este continente para generar un quiz."
        )

    # Elegir país objetivo
    target = random.choice(all_eligible)

    # Elegir 3 distractores diferentes
    others = [c for c in all_eligible if c["id"] != target["id"]]
    distractors = random.sample(others, 3)

    options = [
        {"id": target["id"], "capital": target["capital_es"], "is_correct": True}
    ]
    for d in distractors:
        options.append({"id": d["id"], "capital": d["capital_es"], "is_correct": False})

    random.shuffle(options)

    return {
        "target_country": {
            "id": target["id"],
            "name": target["name_es"],
            "flag": target["flag_emoji"],
            "continent": target["continent"],
            "fun_fact": target["fun_fact"]
        },
        "options": options
    }


# ============================================================================
# ARCHIVOS ESTÁTICOS Y FRONTEND
# ============================================================================

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "Capitals Anki SRS API is running."})

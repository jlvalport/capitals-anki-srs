import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, Header, Depends, status
from database import get_db_connection

SALT_BYTES = 32
ITERATIONS = 100_000
SESSION_DAYS = 30

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Genera un hash seguro usando PBKDF2-HMAC-SHA256 con salt criptográfica."""
    if not salt:
        salt = secrets.token_hex(SALT_BYTES)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        bytes.fromhex(salt),
        ITERATIONS
    ).hex()
    return pwd_hash, salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifica si la contraseña coincide con el hash almacenado usando tiempo constante."""
    expected_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(expected_hash, password_hash)

def create_session(user_id: int) -> str:
    """Crea y persiste un nuevo token de sesión para el usuario."""
    token = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_sessions (token, user_id, expires_at)
        VALUES (?, ?, ?);
    """, (token, user_id, expires_at))
    conn.commit()
    conn.close()
    return token

def delete_session(token: str):
    """Elimina la sesión al cerrar sesión."""
    conn = get_db_connection()
    conn.execute("DELETE FROM user_sessions WHERE token = ?;", (token,))
    conn.commit()
    conn.close()

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Middleware / Dependencia FastAPI para extraer y validar el usuario autenticado.
    Soporta encabezado 'Authorization: Bearer <token>' o token directo.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Inicie sesión para continuar.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    parts = authorization.strip().split()
    token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else parts[0]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.created_at, s.expires_at
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?;
    """, (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida o expirada. Por favor inicie sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Validar expiración
    expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        delete_session(token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha expirado. Inicie sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "created_at": row["created_at"]
    }

import sqlite3
import os
from data.countries_seed import ALL_COUNTRIES

DB_PATH = os.path.join(os.path.dirname(__file__), "capitals_srs.db")

def get_db_connection():
    """Retorna una conexión a la base de datos SQLite configurada con Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Inicializa el esquema de la base de datos y siembra los países iniciales."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabla de Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL COLLATE NOCASE,
        email TEXT UNIQUE NOT NULL COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """)

    # Tabla de Sesiones (Tokens de autenticación persistentes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Tabla de Países
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS countries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name_es TEXT NOT NULL,
        name_en TEXT NOT NULL,
        capital_es TEXT NOT NULL,
        capital_en TEXT NOT NULL,
        continent TEXT NOT NULL,
        subregion TEXT,
        code TEXT UNIQUE NOT NULL,
        flag_emoji TEXT NOT NULL,
        fun_fact TEXT
    );
    """)

    # Tabla de Progreso por Usuario y País (Persistencia del aprendizaje y SRS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_country_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        country_id INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'new', -- 'new', 'learning', 'graduated'
        step INTEGER NOT NULL DEFAULT 0,    -- 0: 1m, 1: 10m, 2: 1d, 3: 4d
        interval_seconds INTEGER NOT NULL DEFAULT 60,
        ease_factor REAL NOT NULL DEFAULT 2.5,
        repetitions INTEGER NOT NULL DEFAULT 0,
        lapses INTEGER NOT NULL DEFAULT 0,
        last_reviewed_at TEXT,
        due_at TEXT NOT NULL,
        is_learned INTEGER NOT NULL DEFAULT 0, -- 1 cuando está dominado/graduado
        UNIQUE(user_id, country_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE
    );
    """)

    # Tabla de Historial / Logs de Repasos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS review_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        country_id INTEGER NOT NULL,
        rating TEXT NOT NULL,               -- 'again', 'hard', 'good', 'easy'
        step_before INTEGER,
        step_after INTEGER,
        interval_after INTEGER,
        reviewed_at TEXT DEFAULT (datetime('now')),
        response_time_ms INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE
    );
    """)

    # Índices para consultas de alta velocidad
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_progress_user_due ON user_country_progress(user_id, due_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_progress_user_learned ON user_country_progress(user_id, is_learned);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_countries_continent ON countries(continent);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token);")

    # Sembrar catálogo de países si la tabla está vacía
    cursor.execute("SELECT COUNT(*) AS total FROM countries;")
    count = cursor.fetchone()["total"]
    if count == 0:
        for c in ALL_COUNTRIES:
            cursor.execute("""
            INSERT INTO countries (name_es, name_en, capital_es, capital_en, continent, subregion, code, flag_emoji, fun_fact)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                c["name_es"],
                c["name_en"],
                c["capital_es"],
                c["capital_en"],
                c["continent"],
                c.get("subregion", ""),
                c["code"],
                c["flag_emoji"],
                c.get("fun_fact", "")
            ))
        print(f"[DB] Se sembraron {len(ALL_COUNTRIES)} países en la base de datos.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("[DB] Base de datos inicializada correctamente.")

# 📘 ESPECIFICACIONES TÉCNICAS Y SISTEMA DE REFERENCIA
## Aplicación Web: Capitales del Mundo (Anki SRS)

> **Documento de Referencia Oficial (Single Source of Truth)**  
> Este documento contiene todas las especificaciones de arquitectura, diseño, base de datos, algoritmo de repetición espaciada, API REST, interfaz y reglas de desarrollo para consultar y respetar en cualquier modificación futura.

---

## 1. Visión General del Proyecto

- **Objetivo**: Aplicación web de alta retención para aprender las capitales de todos los países del mundo utilizando el método de **Repetición Espaciada (Spaced Repetition System - SRS)** de Anki, con persistencia inmutable en base de datos SQLite y autenticación segura.
- **Pila Tecnológica (Tech Stack)**:
  - **Backend**: Python 3.14+, FastAPI, Uvicorn, SQLite3 nativo, Pydantic, Hashlib (PBKDF2-HMAC-SHA256).
  - **Frontend**: Single-Page Application (SPA) nativa (HTML5 semántico, Vanilla JavaScript ES6+, Tailwind CSS vía CDN, Lucide Icons, CSS 3D Transforms).
  - **Pruebas**: Framework estándar `unittest` de Python.
  - **Sin dependencias pesadas en frontend**: Cero empaquetadores complejos (Webpack/Vite/Node) para máxima portabilidad y arranque instantáneo.

---

## 2. Estructura de Archivos del Proyecto

```
capitals_of_countries/
├── main.py                     # API REST FastAPI, middleware, rutas y manejo de errores
├── database.py                 # Esquema SQLite, conexión persistente y funciones de siembra
├── auth.py                     # Hashing PBKDF2, salting criptográfico y gestión de sesiones
├── srs_engine.py               # Algoritmo Anki SRS, cálculo de intervalos y formateo de etiquetas
├── data/
│   └── countries_seed.py       # Catálogo sembrado con 197 países y territorios soberanos
├── static/
│   ├── index.html              # SPA con vistas (Anki, Quiz, Explorador, Stats) y modales
│   ├── css/
│   │   └── styles.css          # Estilos 3D de tarjetas, transiciones anti-spoiler y temas
│   └── js/
│       └── app.js              # Controlador SPA, consumo de API, gestión de estado y atajos
├── tests/
│   └── test_srs_and_auth.py    # Suite de pruebas automatizadas (6 tests de integración)
├── run.sh                      # Script ejecutable de inicio rápido del servidor
├── GUIA_APRENDIZAJE.md         # Documento educativo para comprender cada pieza de la app
├── ESPECIFICACIONES_SISTEMA.md  # ESTE DOCUMENTO: Fuente única de especificaciones técnicas
└── capitals_srs.db             # Base de datos SQLite persistente
```

---

## 3. Base de Datos SQLite (`capitals_srs.db`)

### 3.1 Esquema Relacional

```sql
-- 1. Países del mundo (197 países soberanos y territorios reconocidos)
CREATE TABLE IF NOT EXISTS countries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_es TEXT NOT NULL,
    name_en TEXT NOT NULL,
    capital_es TEXT NOT NULL,
    capital_en TEXT NOT NULL,
    continent TEXT NOT NULL,
    flag_emoji TEXT NOT NULL,
    iso_code_2 TEXT UNIQUE NOT NULL,
    iso_code_3 TEXT UNIQUE NOT NULL,
    latitude REAL,
    longitude REAL,
    fun_fact TEXT
);

-- 2. Usuarios
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Sesiones de usuario (Tokens Bearer)
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. Progreso y Estado SRS por Usuario y País (Persistencia inmutable)
CREATE TABLE IF NOT EXISTS user_country_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    country_id INTEGER NOT NULL,
    is_learned INTEGER DEFAULT 0,          -- 1 = Aprendido / Graduado; 0 = En aprendizaje
    step INTEGER DEFAULT 0,                -- Paso actual (0, 1, 2, 3, etc.)
    interval_seconds INTEGER DEFAULT 60,   -- Intervalo en segundos
    ease_factor REAL DEFAULT 2.5,          -- Factor de facilidad Anki (mínimo 1.3)
    repetitions INTEGER DEFAULT 0,         -- Total de repasos acumulados
    lapses INTEGER DEFAULT 0,              -- Veces que se olvidó ('again')
    due_at TIMESTAMP NOT NULL,             -- Próxima fecha/hora de repaso (UTC)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE,
    UNIQUE(user_id, country_id)
);

-- 5. Registro histórico de repasos (Logs)
CREATE TABLE IF NOT EXISTS review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    country_id INTEGER NOT NULL,
    rating TEXT NOT NULL,                  -- 'again', 'hard', 'good', 'easy'
    time_taken_ms INTEGER DEFAULT 0,       -- Tiempo de respuesta en milisegundos
    interval_before INTEGER NOT NULL,
    interval_after INTEGER NOT NULL,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE
);
```

### 3.2 Persistencia a Prueba de Borrado de Historial
- Si un visitante entra a la página sin iniciar sesión, `ensureAuthenticated()` crea de manera transparente un usuario anónimo (`Estudiante_XXXX`) en la base de datos SQLite y almacena el token en `localStorage`.
- Cuando el usuario decide registrarse o iniciar sesión, el progreso queda formalizado.
- **El progreso nunca reside únicamente en memoria del navegador ni en cookies**: Todo estado (`is_learned`, `due_at`, `interval_seconds`, `lapses`) se guarda en disco en `capitals_srs.db`.

---

## 4. Algoritmo de Repetición Espaciada (Anki SRS)

### 4.1 Intervalos Exactos y Mapeo de Botones

La aplicación utiliza la escala Anki configurada:
- **1 minuto** (`60 s`) ➔ Paso 0 (Inicial / Reaprendizaje)
- **10 minutos** (`600 s`) ➔ Paso 1 (Fijación temprana)
- **1 día** (`86.400 s`) ➔ Paso 2 (Graduación a Aprendido: `is_learned = 1`)
- **4 días** (`345.600 s`) ➔ Paso 3 (Retención consolidada: `is_learned = 1`)
- **Pasos 4+**: `Intervalo Anterior × Factor de Facilidad (Ease Factor)`

### 4.2 Botones de Calificación en la Tarjeta

| Botón | Tecla | Nombre | Intervalo en Tarjeta Nueva | Comportamiento del Algoritmo |
| :--- | :---: | :--- | :---: | :--- |
| **1** | <kbd>1</kbd> | **Otra vez** (*Again*) | **1 min** | Resetea la tarjeta al Paso 0 (`interval = 60s`). Incrementa `lapses + 1`. Si ya estaba aprendida, penaliza el Ease Factor (`ease - 0.20`). |
| **2** | <kbd>2</kbd> | **Difícil** (*Hard*) | **10 min** | Pasa al Paso 1 (`interval = 600s`). Si ya estaba en 1 día, repite 1 día con penalización leve (`ease - 0.15`). |
| **3** | <kbd>3</kbd> | **Bien** (*Good*) | **1 día** | **Gradúa la tarjeta**: Pasa al Paso 2 (`interval = 86.400s`, `is_learned = 1`). Si ya estaba en 1 día, avanza a 4 días. Si estaba en 4 días, avanza a `interval × ease`. |
| **4** | <kbd>4</kbd> | **Fácil** (*Easy*) | **4 días** | **Salto acelerado**: Pasa directo al Paso 3 (`interval = 345.600s`, `is_learned = 1`) y bonifica la facilidad (`ease + 0.15`). |

### 4.3 Formato de Etiquetas de Tiempo (`format_interval`)
Las etiquetas no utilizan símbolos engañosos como `<` y están formateadas en español amigable:
- `< 60s`: `"Xs"`
- `< 3600s`: `"X min"` (e.g., `"1 min"`, `"10 min"`)
- `< 86400s`: `"X h"`
- `< 2592000s`: `"1 día"` (para 1 día) o `"X días"` (para 4 días, etc.)
- `>= 2592000s`: `"X m"` (meses)

---

## 5. Prevención de "Spoilers" en la Transición 3D

Para evitar que el usuario vea la capital del siguiente país al calificar:
1. **Fase de salida**: Al hacer clic en un botón de calificación, el contenedor `.flashcard-3d` recibe la clase `.card-transition-exit` (se reduce su opacidad a 0 en 150 ms con un leve escalado a 0.96).
2. **Volteo ciego**: Mientras la tarjeta está 100% invisible, se retira la clase `.is-flipped` (volviéndola boca arriba) y se inyectan en el DOM los datos del nuevo país (bandera, nombre, y las nuevas etiquetas de los 4 botones).
3. **Fase de entrada**: Se espera un frame de pintado (`requestAnimationFrame`), se retira `.card-transition-exit` y se aplica `.card-transition-enter`. La nueva tarjeta aparece suavemente con la cara frontal (país y bandera) a la vista. **La capital nunca es visible durante el cambio de tarjeta**.

---

## 6. Sistema de Temas (Sistema, Claro, Oscuro)

- **Detección Automática**: Detecta `window.matchMedia('(prefers-color-scheme: dark)')` por defecto. Si el usuario cambia el tema de su sistema operativo, la app reacciona de forma inmediata.
- **Selector de Preferencia**:
  - `system`: Sincronizado con el sistema operativo (Auto).
  - `light`: Fondo blanco/slate-50, tarjetas con sombras suaves y contraste alto.
  - `dark`: Fondo slate-950, paleta oscura índigo/slate-900 para descanso visual.
- **Persistencia**: Almacenado en `localStorage.getItem('capitals_theme')`.
- **Prevención de FOUC**: Script síncrono al inicio de `<head>` en [index.html](file:///Users/josevalencia/Library/Mobile%20Documents/com~apple~CloudDocs/Documents/Antigravity/capitals_of_countries/static/index.html) para inyectar la clase `dark` o `light` en `<html>` antes de que el navegador dibuje el cuerpo.
- **Cache-Buster**: Los archivos estáticos enlazados en `index.html` incluyen parámetro de versión (ejemplo: `app.js?v=2.2`) para evitar problemas de caché del navegador tras actualizaciones de código.

---

## 7. Catálogo de Rutas API REST (FastAPI)

| Método | Endpoint | Descripción | Requiere Auth |
| :--- | :--- | :--- | :---: |
| `POST` | `/api/auth/register` | Registro de usuario (username, email, password) | No |
| `POST` | `/api/auth/login` | Inicio de sesión con credenciales | No |
| `GET` | `/api/auth/me` | Obtener datos del usuario activo | Sí (Bearer) |
| `POST` | `/api/auth/logout` | Cierre de sesión e invalidación de token | Sí (Bearer) |
| `GET` | `/api/countries` | Lista de países (filtros: continent, search, learned) | Opcional |
| `GET` | `/api/srs/due` | Cola de tarjetas pendientes de repaso y tarjetas nuevas | Sí (Bearer) |
| `POST` | `/api/srs/review` | Calificar tarjeta (`country_id`, `rating`, `time_taken_ms`) | Sí (Bearer) |
| `GET` | `/api/srs/stats` | Métricas globales (dominio, repasos, desglose por continente) | Sí (Bearer) |
| `GET` | `/api/quiz/question` | Generación de pregunta tipo test con 4 opciones aleatorias | Opcional |

---

## 8. Reglas de Oro para Modificaciones Futuras

1. **Integridad de Sintaxis en `app.js`**:
   - Cada función JavaScript declarada debe cerrar correctamente sus llaves `{}`.
   - Antes de dar por terminada una tarea, verificar el balance de corchetes y llaves mediante el script de validación.
2. **Incrementar Versión de Caché**:
   - Cada vez que se modifique `app.js` o `styles.css`, actualizar el número de versión en `index.html` (e.g. `app.js?v=2.X`).
3. **Manejo de Errores de Validación**:
   - Nunca permitir que un error de validación de FastAPI (`422`) se imprima como `[object Object]`. El manejador personalizado en `main.py` y la función de captura en `app.js` formatean siempre los errores en texto amigable en español.
4. **Fechas en UTC**:
   - SQLite no almacena tipos de zona horaria; todas las fechas (`due_at`, `expires_at`, `created_at`) deben generarse siempre en UTC (`datetime.now(timezone.utc)`). Nunca usar `datetime.utcnow()` (obsoleto en Python 3.12+).
5. **Pruebas Automatizadas Obligatorias**:
   - Tras cualquier cambio en `srs_engine.py`, `auth.py` o `database.py`, ejecutar la suite de pruebas unitarias:
     ```bash
     .venv/bin/python -m unittest discover tests
     ```

# 🌍 Guía de Aprendizaje: Cómo Está Construida la Aplicación de Capitales con Anki SRS

Bienvenido a la guía educativa de la aplicación web **Capitales del Mundo**. Este documento está diseñado para que comprendas en detalle cada componente de la arquitectura, desde el diseño de la base de datos y la seguridad, hasta el algoritmo matemático de repetición espaciada y los trucos de interfaz de usuario en el frontend.

---

## 📑 Tabla de Contenidos
1. [Arquitectura General y API REST](#1-arquitectura-general-y-api-rest)
2. [Base de Datos SQLite y Persistencia Permanente](#2-base-de-datos-sqlite-y-persistencia-permanente)
3. [Seguridad y Autenticación de Usuarios](#3-seguridad-y-autenticación-de-usuarios)
4. [El Motor de Repetición Espaciada Anki (SRS)](#4-el-motor-de-repetición-espaciada-anki-srs)
5. [Frontend SPA y Efectos 3D sin Spoilers](#5-frontend-spa-y-efectos-3d-sin-spoilers)
6. [Cómo Ejecutar y Probar el Proyecto](#6-cómo-ejecutar-y-probar-el-proyecto)

---

## 1. Arquitectura General y API REST

La aplicación utiliza un patrón desacoplado **Cliente-Servidor (SPA + REST API)**:

```
┌─────────────────────────────────────────────────────────────┐
│                    NAVEGADOR WEB (Cliente)                  │
│  HTML5 + TailwindCSS + JavaScript ES6 (Modo Anki, Quiz)     │
└──────────────────────────────┬──────────────────────────────┘
                               │ Peticiones HTTP (JSON)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND PYTHON (FastAPI)                  │
│  /api/auth/*    /api/countries/*    /api/srs/*   /api/quiz/* │
└──────────────────────────────┬──────────────────────────────┘
                               │ Consultas SQL (ACID)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   BASE DE DATOS (SQLite)                    │
│  users, user_sessions, countries, user_country_progress...  │
└─────────────────────────────────────────────────────────────┘
```

### ¿Por qué una API REST?
- **Desacoplamiento**: El backend solo se encarga de la lógica de negocio, validaciones, cálculos del algoritmo SRS y seguridad. Devuelve datos limpios en formato JSON.
- **Flexibilidad**: Si en el futuro deseas crear una aplicación móvil en iOS o Android, puedes utilizar exactamente la misma API sin cambiar una sola línea de código del servidor.
- **Rendimiento**: La página web nunca se recarga completamente. Las transiciones entre tarjetas, quizzes y estadísticas son instantáneas mediante `fetch()` asíncrono.

---

## 2. Base de Datos SQLite y Persistencia Permanente

El requisito principal era: **"Quiero que persista los países que ya se aprendió dentro de la base de datos para no perder el progreso si se borra el historial"**.

Si guardáramos el progreso únicamente en el navegador (`localStorage` o cookies), cualquier limpieza de caché o navegación privada borraría meses de estudio. Por eso, toda la información se almacena en el archivo `capitals_srs.db` gestionado por SQLite en el servidor.

### Esquema Relacional de Tablas:

#### 1. `users` (Usuarios)
Guarda la identidad del estudiante:
- `id`: Identificador numérico único (Clave primaria).
- `username`: Nombre de usuario único (e.g., `maria_geo`).
- `email`: Correo electrónico único.
- `password_hash`: Hash criptográfico de la contraseña (nunca texto plano).
- `salt`: Cadena aleatoria única por usuario para proteger contra ataques de tablas arcoíris.
- `created_at`: Fecha de registro.

#### 2. `countries` (Catálogo de Países)
Catálogo con los ~195 países soberanos reconocidos por la ONU y territorios clave:
- `id`, `name_es`, `name_en`: Nombres en español e inglés.
- `capital_es`, `capital_en`: Capitales oficiales.
- `continent`, `subregion`: Clasificación geográfica (Europa, América, etc.).
- `code`: Código ISO (e.g., `FR`, `MX`, `JP`).
- `flag_emoji`: Bandera emoji (e.g., 🇫🇷, 🇲🇽, 🇯🇵).
- `fun_fact`: Dato curioso educativo para facilitar la nemotecnia.

#### 3. `user_country_progress` (El Núcleo del Progreso SRS)
Esta es la tabla más importante. Registra la relación individual entre **cada usuario y cada país**:
- `user_id` y `country_id`: Clave foránea compuesta y única (`UNIQUE(user_id, country_id)`).
- `state`: Estado actual de la tarjeta (`'new'`, `'learning'`, `'graduated'`).
- `step`: Paso en la escala de aprendizaje (0: 1 min, 1: 10 min, 2: 1 día, 3: 4 días).
- `interval_seconds`: Tiempo exacto en segundos para el próximo repaso.
- `ease_factor`: Factor de facilidad (por defecto 2.5).
- `repetitions`: Veces que se ha respondido exitosamente.
- `lapses`: Número de veces que el usuario olvidó la capital (pulsó "Otra vez").
- `due_at`: Fecha y hora UTC exacta en la que la tarjeta volverá a estar disponible para repaso.
- **`is_learned` (1 o 0)**: Campo booleano permanente. Se activa en `1` en cuanto el usuario supera la fase de graduación (1 día o 4 días). **Permanece intacto en la base de datos para siempre**, garantizando que el cómputo de países dominados nunca se pierda.

#### 4. `review_logs` (Historial de Repasos)
Auditoría de cada respuesta dada por el usuario con milisegundos de tiempo de respuesta para calcular métricas y rachas.

---

## 3. Seguridad y Autenticación de Usuarios

Para proteger las cuentas de usuario y permitir el acceso seguro:

### A. Hashing con PBKDF2-HMAC-SHA256
Las contraseñas **nunca** se guardan en texto plano:
1. Cuando un usuario introduce su contraseña (e.g. `secreto123`), el sistema genera un **Salt** criptográfico aleatorio de 32 bytes (`secrets.token_hex(32)`).
2. Se aplica la función de derivación de claves `hashlib.pbkdf2_hmac` con **100,000 iteraciones** del algoritmo SHA-256.
3. Esto hace inviable computacionalmente cualquier intento de ataque por fuerza bruta o tablas precalculadas (*rainbow tables*).
4. La verificación se realiza con `secrets.compare_digest` para evitar ataques de temporización (*timing attacks*).

### B. Tokens de Sesión Bearer
Al iniciar sesión exitosamente:
1. El servidor genera un token hexadecimal seguro de 64 caracteres.
2. Se almacena en la tabla `user_sessions` con una fecha de expiración de 30 días.
3. El cliente envía este token en cada petición en el encabezado:
   `Authorization: Bearer <token>`
4. Si un usuario nuevo ingresa a la aplicación sin haberse registrado, el sistema le crea automáticamente una sesión de estudiante temporal persistida en la base de datos, de modo que **su progreso se guarda desde el primer minuto**. Cuando decida registrar un usuario y contraseña formales, su progreso se conserva.

---

## 4. El Motor de Repetición Espaciada Anki (SRS)

El método de repetición espaciada (*Spaced Repetition System*) se basa en la **Curva del Olvido** de Hermann Ebbinghaus: la memoria humana retiene la información de forma exponencial si se repasa justo en el momento en que está a punto de olvidarse.

### Los Intervalos Exactos Requeridos:
1. **Paso 0 (Inicial / Otra vez)**: **1 minuto** (60 segundos).
2. **Paso 1**: **10 minutos** (600 segundos).
3. **Paso 2**: **1 día** (86,400 segundos) ➔ **Fase de Graduación (`is_learned = 1`)**.
4. **Paso 3**: **4 días** (345,600 segundos).
5. **Pasos posteriores**: `Intervalo actual × Ease Factor` (e.g., 4 días × 2.5 = 10 días; 10 días × 2.5 = 25 días, etc.).

### Comportamiento de los 4 Botones de Evaluación:

| Botón | Acción en Paso 0 (1 min) | Acción en Paso 1 (10 min) | Acción en Paso 2 (1 día) | Acción en Paso 3 (4 días) | Efecto en Ease Factor |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[1] Otra vez** | Vuelve a 1 min | Vuelve a 1 min | Vuelve a 1 min | Vuelve a 1 min | Baja -0.20 (mín 1.3) |
| **[2] Difícil** | Permanece en 1 min | Intermedio (~6 min) | Permanece en 1 día | Aumento leve (~4.4 d) | Baja -0.15 (mín 1.3) |
| **[3] Bien** | Avanza a **10 min** | Avanza a **1 día** 🌟 | Avanza a **4 días** 🌟 | `Intervalo × Ease` (~10 d) | Se mantiene (2.5) |
| **[4] Fácil** | Salta a **1 día** 🌟 | Salta a **4 días** 🌟 | `4 días × Ease × 1.3` | `Intervalo × Ease × 1.3` | Sube +0.15 |

> 🌟 **Graduación Automática**: En cuanto la tarjeta alcanza o supera 1 día mediante "Bien" o "Fácil", el campo `is_learned` se marca como `1` en SQLite.

---

## 5. Frontend SPA y Efectos 3D sin Spoilers

Uno de los detalles de experiencia de usuario más importantes solicitados fue:
> *"Asegúrate que la información de la siguiente carta no se vea cuando la tarjeta vuelva a girar para cambiar a la siguiente por favor"*.

### ¿Cómo ocurre el "spoiler" en implementaciones ingenuas?
Si una tarjeta está volteada (mostrando la capital "París") y el usuario presiona "Bien":
- Si simplemente cambias los textos a la siguiente tarjeta ("Tokio") y luego giras la tarjeta de regreso, el usuario verá la palabra "Tokio" durante los 0.3 segundos que dura el giro inverso.
- ¡Esto arruina el proceso de aprendizaje porque el cerebro memoriza la respuesta antes de ver la pregunta!

### Nuestra Solución: Transición Segura en 6 Pasos:
En `static/js/app.js` implementamos el siguiente flujo blindado:

```
[Usuario califica tarjeta]
         │
         ▼
1. Aplicar clase '.card-transition-exit' (La tarjeta actual se desvanece suavemente en 200ms)
         │
         ▼
2. MIENTRAS ESTÁ COMPLETAMENTE INVISIBLE (opacidad 0):
   a. Remover la clase '.is-flipped' (La tarjeta vuelve a mirar al frente boca abajo).
   b. Ocultar los 4 botones de calificación y mostrar el botón "Mostrar respuesta".
   c. Cargar los datos de la NUEVA tarjeta (País en el frente, Capital en el reverso).
         │
         ▼
3. Aplicar clase '.card-transition-enter' (Posicionar la tarjeta nueva).
         │
         ▼
4. Forzar 'reflow' del navegador (`void flashcard.offsetHeight`).
         │
         ▼
5. Aplicar '.card-transition-active' (La nueva tarjeta aparece suavemente mirando al frente).
```

**Resultado**: El usuario solo ve aparecer la bandera y el nombre del nuevo país. La capital permanece oculta en la cara posterior hasta que el usuario decida voluntariamente presionar la barra espaciadora o hacer clic en la tarjeta.

### Estilos CSS 3D:
- `perspective: 1200px`: Otorga profundidad visual realista.
- `transform-style: preserve-3d`: Permite que los elementos hijos se muevan en el espacio tridimensional.
- `backface-visibility: hidden`: Evita que el texto de una cara se transparente o trasluzca en la otra.

### Atajos de Teclado Ergonómicos:
- <kbd>Espacio</kbd> o <kbd>Enter</kbd>: Voltear tarjeta / Mostrar capital.
- <kbd>1</kbd>: Otra vez (&lt; 1 min).
- <kbd>2</kbd>: Difícil.
- <kbd>3</kbd>: Bien.
- <kbd>4</kbd>: Fácil.

---

## 6. Cómo Ejecutar y Probar el Proyecto

### Requisitos Previos:
- Python 3.10+ (o Python 3.14).

### Pasos para iniciar el servidor local:
1. Activar el entorno virtual e iniciar el servidor FastAPI con Uvicorn:
   ```bash
   .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. Abrir el navegador en:
   ```
   http://127.0.0.1:8000
   ```

3. Para consultar la documentación interactiva OpenAPI (Swagger) generada automáticamente por FastAPI:
   ```
   http://127.0.0.1:8000/docs
   ```

---

## 💡 Resumen de Valor Pedagógico
- **Separación de responsabilidades**: Código modular dividido en `database.py`, `auth.py`, `srs_engine.py`, `main.py` y `app.js`.
- **Persistencia garantizada**: La base de datos relacional asegura que el esfuerzo de memorización del usuario nunca se pierda.
- **Rigor científico**: Se aplican los mismos principios matemáticos de retención mnemotécnica que utilizan los estudiantes de medicina y políglotas en Anki.

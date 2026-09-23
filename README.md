# 🌍 Capitales del Mundo - Repetición Espaciada (Anki SRS)

Aplicación web interactiva de alto rendimiento para memorizar las capitales de **todos los países del mundo (197 países y territorios)** utilizando el sistema de **Repetición Espaciada de Anki (1 min, 10 min, 1 día y 4 días)**, con persistencia garantizada en base de datos SQLite y autenticación segura.

---

## ✨ Características Principales

- 🧠 **Algoritmo Anki SRS**: 4 intervalos exactos de aprendizaje y graduación:
  - **Otra vez (1 min)**: Resetea al paso inicial tras un fallo.
  - **Difícil (10 min)**: Repaso a corto plazo durante la misma sesión.
  - **Bien (1 día)**: Gradúa el país como aprendido (`is_learned = 1`).
  - **Fácil (4 días)**: Salto acelerado de consolidación con bonificación de facilidad.
- 🗄️ **Persistencia Inmutable (SQLite)**: Todo el progreso se almacena en `capitals_srs.db`. Incluye un sistema de sesión anónima automática para que el usuario no pierda su progreso incluso si borra cookies o historial de navegación.
- 🃏 **Tarjetas 3D sin Spoilers**: Transición con desvanecimiento seguro que asegura que la capital del siguiente país jamás sea visible durante el giro de la tarjeta.
- 🎯 **Modo Quiz**: Cuestionario interactivo con 4 opciones dinámicas y contador de rachas.
- 🗺️ **Explorador Global**: Catálogo interactivo con buscador instantáneo, banderas emoji, datos curiosos y filtros por continentes.
- 📊 **Panel de Estadísticas**: Gráficos de dominio global y métricas porcentuales por continente.
- 🌓 **Temas Claro / Oscuro / Sistema**: Sincronizado automáticamente con tu sistema operativo (`prefers-color-scheme`), con selector manual y persistencia en `localStorage`.
- 🔐 **Seguridad Criptográfica**: Hashing de contraseñas con PBKDF2-HMAC-SHA256 (100.000 iteraciones) y tokens de sesión de 64 caracteres.
- ⚡ **API REST Modular**: Documentación interactiva Swagger UI disponible de serie en `/docs`.

---

## 🛠️ Pila Tecnológica

- **Backend**: Python 3.10+ (compatible con Python 3.14), FastAPI, Uvicorn, SQLite3, Pydantic.
- **Frontend**: Single-Page Application (SPA) nativa en HTML5, Vanilla JavaScript ES6+, Tailwind CSS (CDN), Lucide Icons.
- **Pruebas**: Framework estándar `unittest` de Python.

---

## 🚀 Inicio Rápido

### 1. Clonar el repositorio
```bash
git clone https://github.com/TU_USUARIO/capitals_of_countries.git
cd capitals_of_countries
```

### 2. Crear y activar el entorno virtual
En macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

En Windows:
```cmd
python -m venv .venv
.venv\Scripts\activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Iniciar la aplicación
Puedes usar el script incluido:
```bash
chmod +x run.sh
./run.sh
```
O directamente con Uvicorn:
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Abre tu navegador en:
- **Aplicación Web**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Documentación Swagger de la API**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Pruebas Automatizadas

Para ejecutar la suite de pruebas unitarias (validación de base de datos, algoritmo SRS y seguridad criptográfica):
```bash
python -m unittest discover tests
```

---

## 📁 Estructura del Proyecto

```
capitals_of_countries/
├── main.py                     # API REST FastAPI, middleware y rutas
├── database.py                 # Esquema SQLite, migraciones y conexión
├── auth.py                     # Criptografía PBKDF2 y manejo de sesiones
├── srs_engine.py               # Motor Anki SRS (1m, 10m, 1d, 4d)
├── data/
│   └── countries_seed.py       # Catálogo sembrado con 197 países
├── static/
│   ├── index.html              # Interfaz SPA con Tailwind CSS y Lucide Icons
│   ├── css/
│   │   └── styles.css          # Estilos 3D y transiciones anti-spoiler
│   └── js/
│       └── app.js              # Controlador SPA y consumo de API
├── tests/
│   └── test_srs_and_auth.py    # Suite de pruebas automatizadas
├── run.sh                      # Script ejecutable de inicio rápido
├── requirements.txt            # Dependencias de Python
├── GUIA_APRENDIZAJE.md         # Documento educativo explicativo paso a paso
├── ESPECIFICACIONES_SISTEMA.md  # Especificaciones técnicas completas
└── README.md                   # Documentación principal del repositorio
```

---

## 📚 Documentación Adicional

- [ESPECIFICACIONES_SISTEMA.md](ESPECIFICACIONES_SISTEMA.md): Especificaciones técnicas detalladas de la arquitectura, esquema DDL de base de datos, algoritmos SRS y reglas para desarrolladores.
- [GUIA_APRENDIZAJE.md](GUIA_APRENDIZAJE.md): Explicación pedagógica de los conceptos utilizados (REST APIs, SQLite, Criptografía, Repetición Espaciada y CSS 3D).

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.

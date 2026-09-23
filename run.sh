#!/bin/bash
# Script para ejecutar la aplicación de Capitales del Mundo con Anki SRS

echo "=========================================================="
echo "🌍 Iniciando Capitales del Mundo - Anki SRS (FastAPI)"
echo "=========================================================="

# Activar entorno virtual
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Creando entorno virtual..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
fi

echo "Iniciando servidor en http://127.0.0.1:8000"
echo "Documentación interactiva de la API en http://127.0.0.1:8000/docs"
echo "Presiona Ctrl+C para detener el servidor."

uvicorn main:app --host 127.0.0.1 --port 8000 --reload

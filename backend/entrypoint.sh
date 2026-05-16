#!/bin/bash
# Crea todos los directorios runtime antes de arrancar uvicorn.
# Necesario porque los volúmenes Docker pueden estar vacíos en primer inicio.
set -e

STREAMS="${STREAMS_DIR:-/app/streams}"
DATA="${DATA_DIR:-/app/data}"

echo "[startup] Creando directorios runtime..."
mkdir -p "$STREAMS/live" "$STREAMS/offline" "$DATA/logs"
echo "[startup] streams=$STREAMS  data=$DATA"

exec uvicorn main:app --host 0.0.0.0 --port 8000

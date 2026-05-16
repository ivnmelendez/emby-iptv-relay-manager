#!/usr/bin/env bash
# Migración a nuevo VPS.
# Uso: ./scripts/migrate.sh user@nuevo-servidor:/ruta/destino
set -e

DEST="${1:?Uso: $0 user@host:/ruta}"

echo "[migrate] Sincronizando proyecto (sin streams temporales)..."
rsync -avz --progress \
  --exclude "streams/live/*" \
  --exclude "streams/offline/*" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  . "$DEST"

echo "[migrate] Hecho. En el nuevo servidor:"
echo "  1. Edita .env (BASE_URL, puertos)"
echo "  2. bash scripts/bootstrap.sh"
echo "  3. docker compose up -d"

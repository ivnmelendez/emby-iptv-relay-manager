#!/usr/bin/env bash
set -e

echo "[bootstrap] Creando directorios..."
mkdir -p data/logs streams/live streams/offline

echo "[bootstrap] Configurando .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "  IMPORTANTE: Edita .env y cambia BASE_URL antes de continuar."
  echo "  Ejemplo: BASE_URL=http://192.168.1.100:8080"
  echo ""
else
  echo "  .env ya existe, omitiendo."
fi

echo "[bootstrap] Listo."
echo ""
echo "  Pasos siguientes:"
echo "  1. Edita .env — pon tu IP en BASE_URL"
echo "  2. docker compose up -d"
echo "  3. Agrega http://TU_IP:8080/eventos.m3u a Emby Live TV"

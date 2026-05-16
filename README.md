# IPTV Event Relay Manager

Sistema ligero de administración de relays IPTV para eventos deportivos usando Emby Live TV.

## Arquitectura

```
Proveedor IPTV → FFmpeg Relay → HLS local → NGINX → Emby → Usuarios
```

FastAPI administra el sistema. NGINX sirve los streams. Emby consume el M3U.

---

## Requisitos

- Docker + Docker Compose
- Acceso a proveedor IPTV (Xtream Codes)

---

## Deploy en VPS

### 1. Clonar

```bash
git clone <tu-repo> emby-iptv-relay-manager
cd emby-iptv-relay-manager
```

### 2. Bootstrap

```bash
bash scripts/bootstrap.sh
```

Crea directorios necesarios y genera `.env` desde el template.

### 3. Configurar `.env`

```bash
nano .env
```

Campos requeridos:

```env
# URL pública de tu servidor (lo que Emby usa para acceder)
BASE_URL=http://TU_IP_O_DOMINIO:8080

# Proveedor IPTV (Xtream Codes)
IPTV_HOST=http://tu-proveedor:puerto
IPTV_USERNAME=tu_usuario
IPTV_PASSWORD=tu_password

# Filtros de grupos (sugerencia inicial, luego se controla desde UI)
GROUP_FILTERS=["EVENTOS","SPORTS","DEPORT","PPV","LIVE"]

# Límite de relays IPTV simultáneos
MAX_ACTIVE_STREAMS=3
```

### 4. Levantar

```bash
docker compose up -d
```

### 5. Configurar Emby

En Emby → Live TV → Add Tuner → M3U Tuner:

```
URL: http://TU_IP:8080/eventos.m3u
```

---

## Workflow de uso

```
1. Dashboard → Provider → [Scan provider]
   → Descarga todos los grupos del proveedor

2. Dashboard → Provider → seleccionar grupos deseados
   → Clic en Select / Deselect por grupo

3. Dashboard → Provider → [Sync canales]
   → Importa canales de grupos seleccionados como OFFLINE

4. Dashboard → Channels → [Activar]
   → Inicia relay FFmpeg para ese canal

5. Dashboard → Channels → [Offline]
   → Para relay cuando termina el evento
```

---

## Endpoints API

```
GET  /api/provider/status
POST /api/provider/scan
GET  /api/provider/groups
POST /api/provider/groups/select
POST /api/provider/sync

GET    /api/channels/
GET    /api/channels/{id}
PATCH  /api/channels/{id}
DELETE /api/channels/{id}

POST /api/channels/{id}/activate
POST /api/channels/{id}/offline

GET /api/system/health
```

Documentación interactiva: `http://TU_IP:8080/api/docs`

---

## Migración a nuevo VPS

```bash
bash scripts/migrate.sh usuario@nuevo-servidor:/ruta/destino
```

El script sincroniza todo excepto segmentos HLS temporales. En el nuevo servidor:

```bash
nano .env          # actualizar BASE_URL
docker compose up -d
```

---

## Desarrollo local (sin Docker)

```bash
cd backend
cp .env.local.example .env   # completar credenciales
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

Dashboard: `http://localhost:8000`

---

## Estructura

```
backend/          FastAPI app
  routers/        Endpoints API + UI
  services/       FFmpeg, provider, M3U, health
  templates/      Jinja2 + HTMX dashboard
nginx/            nginx.conf para HLS delivery
offline/          Contenedor FFmpeg offline stream
scripts/          bootstrap.sh, migrate.sh
data/             Persistencia JSON (gitignored en runtime)
streams/          Segmentos HLS (gitignored en runtime)
```

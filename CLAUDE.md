# IPTV Event Relay Manager — Contexto del Proyecto

## Objetivo del proyecto

Este proyecto es un sistema ligero de administración de relays IPTV para eventos deportivos usando Emby Live TV.

El sistema administrará:

- canales IPTV
- procesos FFmpeg
- streams HLS
- streams offline
- generación dinámica de M3U
- metadata de canales
- estados ONLINE/OFFLINE

IMPORTANTE:
Este proyecto NO reemplaza Emby.

Emby seguirá siendo el frontend para usuarios.

Este proyecto solamente administrará:
- relays
- procesos
- metadata
- M3U
- streams

---

# Arquitectura principal

Proveedor IPTV
↓
FFmpeg Relay
↓
HLS local (.m3u8)
↓
Servidor HTTP
↓
Emby Live TV
↓
Usuarios

---

# Requisitos IMPORTANTES

## 1. Portabilidad total

El proyecto debe diseñarse pensando en migraciones futuras entre VPS.

NO hardcodear:
- IPs
- dominios
- rutas absolutas

Usar:
- variables .env
- configuración centralizada

La idea es poder migrar fácilmente haciendo:

docker compose up -d

en otro servidor.

---

## 2. Arquitectura Docker-first

Todo debe correr mediante Docker Compose.

Servicios posibles:
- dashboard
- nginx
- offline-stream
- backend FastAPI

---

## 3. Stream offline automático

El sistema debe generar automáticamente un:

offline.m3u8

Este stream:
- debe mantenerse vivo permanentemente
- sobrevivir reinicios
- reiniciarse automáticamente si falla
- funcionar como placeholder de canales offline

Los canales offline deben apuntar a:
offline.m3u8

NO quiero configurar esto manualmente.

Debe formar parte del sistema.

---

## 4. Filosofía FFmpeg

Prioridad máxima:
- bajo consumo CPU
- máxima compatibilidad Direct Play
- evitar transcoding innecesario

Modo preferido:

-c copy

Evitar transcoding siempre que sea posible.

---

## 5. Limitaciones IPTV

El proveedor IPTV tiene conexiones simultáneas limitadas.

La arquitectura busca:
- reutilizar una sola conexión IPTV
- retransmitirla a múltiples viewers Emby

Esto ya fue probado manualmente y funciona correctamente.

---

# Workflow de eventos

Los canales pueden existir en dos estados:

ONLINE:
- FFmpeg activo
- IPTV real conectada

OFFLINE:
- apunta a offline.m3u8
- visible en Emby
- sin consumir IPTV

---

# Funciones deseadas

## Dashboard principal

Mostrar:
- nombre canal
- estado
- viewers activos
- PID FFmpeg
- uptime
- bitrate
- acciones

Acciones:
- Activar
- Offline
- Editar
- Eliminar

---

## Crear canal

El usuario podrá pegar algo como:

#EXTINF metadata

El sistema debe:
- parsear metadata
- extraer logo
- extraer título
- generar slug
- guardar canal
- agregar entrada a eventos.m3u
- apuntar inicialmente a offline.m3u8

NO debe iniciar IPTV todavía.

---

## Activar evento

Cuando el partido vaya a iniciar:

El usuario pegará la URL IPTV real.

El sistema debe:
- iniciar FFmpeg relay
- crear slug.m3u8
- actualizar eventos.m3u
- cambiar offline → stream real
- guardar PID
- marcar ONLINE

---

## Poner Offline

Cuando el evento termine:

El sistema debe:
- matar FFmpeg
- borrar segmentos .ts
- restaurar offline.m3u8
- mantener canal visible en Emby
- marcar OFFLINE

---

## Eliminar canal

El sistema debe:
- eliminar metadata
- eliminar entrada M3U
- eliminar segmentos
- eliminar .m3u8
- matar FFmpeg

---

# Stack deseado

Backend:
- Python
- FastAPI preferiblemente

Frontend:
- moderno pero simple
- Tailwind opcional
- React opcional
- simplicidad primero

Persistencia:
- SQLite o JSON

---

# Infraestructura deseada

Prioridades:
1. Estabilidad
2. Portabilidad
3. Simplicidad
4. Bajo consumo CPU
5. Fácil migración
6. Fácil mantenimiento

Evitar sobreingeniería.

---

# Notas sobre Emby

Emby consumirá:
http://DOMINIO/eventos.m3u

NO necesito integración compleja con Emby.

Solo administración de IPTV relay.

---

# Restricciones IMPORTANTES

Evitar:
- Kubernetes
- microservicios innecesarios
- transcoding pesado
- autenticación compleja inicialmente
- clones tipo Plex/Jellyfin
- dependencias GPU innecesarias

Mantener arquitectura ligera y mantenible.

---

# Estado actual validado

Ya fue probado exitosamente:
- relay FFmpeg HLS
- múltiples viewers
- Emby Live TV
- Apple TV playback
- Direct Play
- stream offline
- Dockerized Emby
- bajo consumo CPU
- reutilización IPTV

---

# Estilo de desarrollo

Construir incrementalmente.

Orden preferido:
1. estructura proyecto
2. docker compose
3. backend FastAPI
4. modelos canales
5. generación eventos.m3u
6. automatización offline stream
7. manejo procesos FFmpeg
8. frontend dashboard
9. logs y monitoreo
10. deploy portable
11. workflow migración VPS

Evitar explicaciones gigantes teóricas.

Priorizar implementación práctica.
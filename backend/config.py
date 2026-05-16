from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # URL pública del servidor (lo que Emby usa)
    base_url: str = "http://localhost:8080"
    backend_port: int = 8000

    # Proveedor IPTV (Xtream Codes)
    iptv_host: str = ""
    iptv_username: str = ""
    iptv_password: str = ""

    # Filtros de grupo — matching parcial case-insensitive
    group_filters: list[str] = ["EVENTOS", "SPORTS", "DEPORT", "PPV", "LIVE"]

    # Límite global de relays IPTV simultáneos
    max_active_streams: int = 3

    # Root de streams compartido entre backend y nginx
    # Backend:  STREAMS_DIR=/app/streams  → live y offline son subdirs
    # Nginx:    monta ./streams:/var/www/streams → sirve /streams/live/...
    streams_dir: Path = Path("/app/streams")
    data_dir: Path = Path("/app/data")

    # FFmpeg
    ffmpeg_bin: str = "/usr/bin/ffmpeg"
    hls_time: int = 4
    hls_list_size: int = 6

    # Paths derivados — NO configurar en .env, se calculan de streams_dir/data_dir
    @property
    def hls_dir(self) -> Path:
        return self.streams_dir / "live"

    @property
    def offline_dir(self) -> Path:
        return self.streams_dir / "offline"

    @property
    def offline_stream_url(self) -> str:
        return f"{self.base_url}/streams/offline/offline.m3u8"

    @property
    def channels_file(self) -> Path:
        return self.data_dir / "channels.json"

    @property
    def groups_file(self) -> Path:
        return self.data_dir / "groups.json"

    @property
    def library_file(self) -> Path:
        return self.data_dir / "library.json"

    @property
    def m3u_file(self) -> Path:
        return self.data_dir / "eventos.m3u"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def runtime_dirs(self) -> list[Path]:
        """Todos los directorios que deben existir antes de arrancar."""
        return [self.hls_dir, self.offline_dir, self.logs_dir, self.data_dir]


settings = Settings()

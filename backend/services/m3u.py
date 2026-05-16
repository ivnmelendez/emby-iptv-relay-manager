from config import settings
from models import Channel, ChannelStatus
from typing import Dict


def generate_m3u(channels: Dict[str, Channel]):
    lines = ["#EXTM3U"]

    for ch in channels.values():
        group = ch.group or "Eventos"
        logo = ch.logo or ""

        stream_url = (
            ch.stream_url
            if ch.status == ChannelStatus.online and ch.stream_url
            else settings.offline_stream_url
        )

        lines.append(
            f'#EXTINF:-1 tvg-id="{ch.id}" tvg-name="{ch.name}" '
            f'tvg-logo="{logo}" group-title="{group}",{ch.name}'
        )
        lines.append(stream_url)

    settings.m3u_file.parent.mkdir(parents=True, exist_ok=True)
    settings.m3u_file.write_text("\n".join(lines) + "\n")

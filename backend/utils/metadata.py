import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExtinfMetadata:
    name: str
    logo: Optional[str]
    group: Optional[str]
    duration: int = -1


def parse_extinf(line: str) -> ExtinfMetadata:
    """
    Parsea una línea #EXTINF:-1 tvg-name="..." tvg-logo="..." group-title="...",Nombre
    """
    duration = -1
    duration_match = re.search(r"#EXTINF:(-?\d+)", line)
    if duration_match:
        duration = int(duration_match.group(1))

    name = ""
    name_match = re.search(r'tvg-name="([^"]*)"', line)
    if name_match:
        name = name_match.group(1)

    # fallback: nombre al final de la línea (después de la coma)
    if not name:
        comma_match = re.search(r",(.+)$", line)
        if comma_match:
            name = comma_match.group(1).strip()

    logo = None
    logo_match = re.search(r'tvg-logo="([^"]*)"', line)
    if logo_match:
        logo = logo_match.group(1) or None

    group = None
    group_match = re.search(r'group-title="([^"]*)"', line)
    if group_match:
        group = group_match.group(1) or None

    return ExtinfMetadata(name=name, logo=logo, group=group, duration=duration)

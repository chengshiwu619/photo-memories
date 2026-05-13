import subprocess
from typing import List


def is_available() -> bool:
    try:
        subprocess.run(["es", "-help"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        return False


def search_images(source_drive: str, image_extensions: List[str]) -> List[str]:
    ext_str = " ".join([f"ext:{e.lstrip('.')}" for e in image_extensions])
    cmd = ["es", "-path", source_drive, "-n", "-utf8", "-sort-size", "descending"]
    cmd.extend(ext_str.split())
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        lines = result.stdout.splitlines()
        return [line.strip() for line in lines if line.strip()]
    except Exception:
        return []

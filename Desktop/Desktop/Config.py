import os
import sys


# ── Funkcje dla .exe ───────────────────────────────────────────
def resource_path(filename: str) -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(__file__), filename)


def app_dir() -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ── Kolory motywu ──────────────────────────────────────────────
BG_PRIMARY = "#000000"
BG_SECONDARY = "#171719"
BG_CARD = "#2d2d2f"
ACCENT = "#eb7569"
ACCENT_HOVER = "#c73652"
TEXT_PRIMARY = "#eaeaea"
TEXT_MUTED = "#a0a0b0"
GREEN = "#5fcd77"
YELLOW = "#ffc107"

# ── Stałe aplikacji ────────────────────────────────────────────
DATA_FILE = os.path.join(app_dir(), "steps_data.json")
HOST = "0.0.0.0"
PORT = 5000
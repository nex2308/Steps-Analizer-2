import json
import os
from Config import DATA_FILE


def load_data() -> dict[str, int]:
    """Wczytuje dane kroków z pliku JSON."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            loaded = json.load(f)
            return {str(k): int(v) for k, v in loaded.items()}
    return {}


def save_data(data: dict[str, int]):
    """Zapisuje dane kroków do pliku JSON."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def clear_data():
    """Czyści plik JSON - zapisuje pusty słownik."""
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)


def merge_steps(existing: dict[str, int], new_steps: dict) -> tuple[dict[str, int], int]:
    """
    Łączy nowe dane z istniejącymi - zachowuje większą wartość.
    Zwraca (zaktualizowany_słownik, liczba_zaktualizowanych_dni).
    """
    updated = dict(existing)
    count = 0
    for date, steps in new_steps.items():
        val = int(steps)
        if val > updated.get(date, 0):
            updated[date] = val
            count += 1
    return updated, count
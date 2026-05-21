import csv
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime


def import_samsung_csv(path: str) -> tuple[dict[str, int], int, int]:
    """
    Importuje dane kroków z pliku CSV eksportowanego z Samsung Health.
    Zwraca (słownik_kroków, liczba_rekordów, liczba_dni).
    """
    daily_steps: defaultdict[str, int] = defaultdict(int)
    processed = 0

    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()

    if len(lines) < 2:
        return {}, 0, 0

    reader = csv.DictReader(lines[1:])
    is_trend_format = (
            reader.fieldnames is not None
            and "day_time" in reader.fieldnames
            and "count" in reader.fieldnames
    )

    for row in reader:
        try:
            if is_trend_format:
                count_val = int(float(row.get("count", 0)))
                dt_ms = int(row.get("day_time", 0))
                date_str = datetime.fromtimestamp(dt_ms // 1000).strftime("%Y-%m-%d")
                daily_steps[date_str] = max(daily_steps[date_str], count_val)
            else:
                count_val = int(float(row.get("com.samsung.health.step_count.count", 0)))
                time_str = row.get("com.samsung.health.step_count.start_time", "").strip()
                if not time_str:
                    continue
                date_str = time_str[:10]
                daily_steps[date_str] += count_val
            processed += 1
        except Exception:
            continue

    return dict(daily_steps), processed, len(daily_steps)


def import_apple_xml(path: str) -> tuple[dict[str, int], int, int]:
    """
    Importuje dane kroków z pliku XML eksportowanego z Apple Health.
    Używa iterparse do obsługi dużych plików bez zawieszania aplikacji.
    Zwraca (słownik_kroków, liczba_rekordów, liczba_dni).
    """
    daily_steps: defaultdict[str, int] = defaultdict(int)
    processed = 0

    for event, elem in ET.iterparse(path, events=("end",)):
        if (
                elem.tag == "Record"
                and elem.attrib.get("type") == "HKQuantityTypeIdentifierStepCount"
        ):
            try:
                value = int(float(elem.attrib.get("value", 0)))
                date_str = elem.attrib.get("startDate", "")[:10]
                if date_str:
                    daily_steps[date_str] += value
                    processed += 1
            except (ValueError, KeyError):
                pass
            elem.clear()  # Zwolnij pamięć - ważne przy dużych plikach

    return dict(daily_steps), processed, len(daily_steps)

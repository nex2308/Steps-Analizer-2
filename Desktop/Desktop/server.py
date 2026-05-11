import socket
import json
import os
import csv
from collections import defaultdict

HOST = '0.0.0.0'
PORT = 5000
DATA_FILE = 'steps_data.json'


def load_existing_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Zapisano dane do {DATA_FILE}")


def import_samsung_csv(csv_path):
    print(f"\nImportuję dane z: {csv_path}")

    daily_steps = defaultdict(int)

    with open(csv_path, encoding='utf-8-sig') as f:
        lines = f.readlines()

    reader = csv.DictReader(lines[1:])

    step_col = 'com.samsung.health.step_count.count'
    time_col = 'com.samsung.health.step_count.start_time'

    skipped = 0
    processed = 0

    for row in reader:
        try:
            count_str = row.get(step_col, '').strip()
            time_str = row.get(time_col, '').strip()

            if not count_str or not time_str:
                skipped += 1
                continue

            count = int(float(count_str))

            date_str = time_str[:10]

            daily_steps[date_str] += count
            processed += 1

        except (ValueError, KeyError):
            skipped += 1
            continue

    print(f"Przetworzono: {processed} rekordów, pominięto: {skipped}")
    print(f"Znaleziono dane dla {len(daily_steps)} dni")

    existing = load_existing_data()

    merged = dict(existing)
    for date, steps in daily_steps.items():
        if date in merged:

            if steps > merged[date]:
                merged[date] = steps
        else:
            merged[date] = steps

    save_data(merged)

    print("\n--- Podsumowanie importu ---")
    sorted_days = sorted(daily_steps.keys())
    if sorted_days:
        print(f"Zakres dat: {sorted_days[0]} → {sorted_days[-1]}")
        print(f"Łącznie dni z danymi: {len(sorted_days)}")
        total_steps = sum(daily_steps.values())
        print(f"Łączna liczba kroków: {total_steps:,}")

        print("\n--- Ostatnie 7 dni (po imporcie) ---")
        last_7 = sorted(merged.keys())[-7:]
        for day in last_7:
            kroki = merged[day]
            bar = '█' * (kroki // 1000)
            print(f"{day}: {kroki:>6} kroków {bar}")

    return merged


def handle_client(conn, addr):
    print(f"\nPołączono z: {addr}")

    try:
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)

        raw = b''.join(chunks).decode('utf-8')
        received = json.loads(raw)

        print(f"Typ pakietu: {received.get('type')}")
        print(f"Liczba dni: {len(received.get('steps', {}))}")

        existing = load_existing_data()
        existing.update(received.get('steps', {}))
        save_data(existing)

        print("\n--- Ostatnie 7 dni ---")
        sorted_days = sorted(existing.keys())[-7:]
        for day in sorted_days:
            kroki = existing[day]
            bar = '█' * (kroki // 1000)
            print(f"{day}: {kroki:>6} kroków {bar}")

        conn.sendall(b'OK')

    except json.JSONDecodeError as e:
        print(f"Błąd parsowania JSON: {e}")
        conn.sendall(b'ERROR')
    except Exception as e:
        print(f"Błąd: {e}")
        conn.sendall(b'ERROR')
    finally:
        conn.close()


def main():
    import sys

    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        if not os.path.exists(csv_path):
            print(f"Błąd: Plik {csv_path} nie istnieje")
            return
        import_samsung_csv(csv_path)
        return

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    local_ip = s.getsockname()[0]
    s.close()

    print(f"╔══════════════════════════════════╗")
    print(f"║      Serwer Steps Analyzer       ║")
    print(f"╠══════════════════════════════════╣")
    print(f"║  IP telefonu wpisz: {local_ip:<14}║")
    print(f"║  Port:              {PORT:<14}║")
    print(f"╚══════════════════════════════════╝")
    print(f"\nAby zaimportować CSV z Samsung Health:")
    print(f"  python server.py plik.csv")
    print(f"\nNasłuchuję na połączenia...")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)

        while True:
            conn, addr = server.accept()
            handle_client(conn, addr)


if __name__ == '__main__':
    main()
import json
import socket
import threading
from typing import Callable
from Config import HOST, PORT


class StepsServer:
    """Serwer TCP odbierający dane kroków z aplikacji Android."""

    def __init__(
            self,
            on_data_received: Callable[[dict], None],
            on_log: Callable[[str], None],
    ):
        self.on_data_received = on_data_received
        self.on_log = on_log
        self.running = False
        self.server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    # ── Publiczne API ──────────────────────────────────────────

    def start(self) -> str:
        """Uruchamia serwer i zwraca lokalne IP."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(5)
        self.running = True

        local_ip = self._get_local_ip()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        return local_ip

    def stop(self):
        """Zatrzymuje serwer."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None

    # ── Prywatne metody ────────────────────────────────────────

    def _get_local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    def _loop(self):
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                conn, addr = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, conn: socket.socket, addr: tuple):
        try:
            chunks = []
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

            received = json.loads(b"".join(chunks).decode("utf-8"))
            pkt_type = received.get("type", "?")
            steps = received.get("steps", {})

            sorted_keys = sorted(steps.keys())
            self.on_log(f"Daty w pakiecie: {sorted_keys[-3:]}")
            self.on_log(f"Odebrano [{pkt_type}]: {len(steps)} dni od {addr[0]}")

            self.on_data_received(steps)
            conn.sendall(b"OK")

        except Exception as e:
            self.on_log(f"Błąd klienta: {e}")
            try:
                conn.sendall(b"ERROR")
            except Exception:
                pass
        finally:
            conn.close()

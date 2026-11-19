#!/usr/bin/env python3
"""Sirve la simulación del péndulo de ondas en la red local.

Uso:
    python3 serve.py              # puerto 8000
    python3 serve.py --port 8080

Al arrancar imprime la dirección http://<ip-local>:<puerto> que se puede abrir
desde cualquier móvil, tablet u ordenador conectado a la misma red (wifi).
Solo usa la biblioteca estándar; si está instalado el paquete opcional
`qrcode`, también imprime un código QR con la dirección.
"""
import argparse
import functools
import http.server
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def local_ipv4s():
    """Direcciones IPv4 de este equipo en la red local (sin 127.x)."""
    found = []
    # Un "connect" UDP no envía ningún paquete: solo pregunta al sistema
    # qué interfaz usaría para salir, y así obtenemos su IP.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.254.254.254", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    ips = []
    for ip in found:
        if not ip.startswith("127.") and ip not in ips:
            ips.append(ip)
    return ips


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # sin caché: al editar index.html basta con recargar la página
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()}  {fmt % args}\n")


def print_qr(url):
    try:
        import qrcode  # opcional: pip install qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def main():
    ap = argparse.ArgumentParser(description="Sirve el péndulo de ondas en la red local.")
    ap.add_argument("--port", type=int, default=8000, help="puerto (por defecto 8000)")
    ap.add_argument("--bind", default="0.0.0.0", help="interfaz (por defecto todas: 0.0.0.0)")
    args = ap.parse_args()

    handler = functools.partial(Handler, directory=str(HERE))
    try:
        httpd = http.server.ThreadingHTTPServer((args.bind, args.port), handler)
    except OSError as exc:
        sys.exit(f"No se pudo abrir el puerto {args.port} ({exc}). Prueba con --port 8080.")

    ips = local_ipv4s()
    print("\nPéndulo de ondas en marcha.\n")
    print(f"  En este equipo:   http://localhost:{args.port}")
    for ip in ips:
        print(f"  En la red local:  http://{ip}:{args.port}")
    if not ips:
        print("  (No se encontró una IP de red local: ¿está el equipo conectado a una wifi?)")
    print("\nAbre la dirección de red local en el móvil (misma wifi). Ctrl+C para parar.\n")
    if ips:
        print_qr(f"http://{ips[0]}:{args.port}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor parado.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()

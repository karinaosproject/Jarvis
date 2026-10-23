"""Núcleo do Jarvis - servidor local.
Uso:  pip install requests   |   python server.py   |   abra http://localhost:8000
"""
import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

LAT, LON = -23.03, -45.56  # Taubaté, SP
PORTA = 8000
PASTA = Path(__file__).parent
CACHE_AMBIENTE_SEG = 600   # clima: renova a cada 10 min
CACHE_PH_SEG = 86400       # pH do solo quase não muda: renova a cada 24 h

_amb = {"t": 0.0, "dados": None}
_ph = {"t": 0.0, "valor": None}


def buscar_clima():
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT, "longitude": LON,
            "current": "temperature_2m,relative_humidity_2m",
            "hourly": "soil_temperature_0cm,soil_moisture_0_to_1cm",
            "timezone": "America/Sao_Paulo", "forecast_days": 1,
        },
        timeout=15,
    )
    r.raise_for_status()
    j = r.json()
    hora = j["current"]["time"][:13]
    i = next((k for k, t in enumerate(j["hourly"]["time"]) if t.startswith(hora)), 0)
    umid = j["hourly"]["soil_moisture_0_to_1cm"][i]
    return {
        "temp": j["current"]["temperature_2m"],
        "ar": j["current"]["relative_humidity_2m"],
        "solo_temp": j["hourly"]["soil_temperature_0cm"][i],
        "solo_umid": None if umid is None else umid * 100,  # m³/m³ -> %
    }


def buscar_ph():
    r = requests.get(
        "https://rest.isric.org/soilgrids/v2.0/properties/query",
        params={"lat": LAT, "lon": LON, "property": "phh2o",
                "depth": "0-5cm", "value": "mean"},
        timeout=30,
    )
    r.raise_for_status()
    media = r.json()["properties"]["layers"][0]["depths"][0]["values"]["mean"]
    return None if media is None else media / 10  # o SoilGrids guarda pH x 10


def ambiente():
    agora = time.time()
    if _amb["dados"] and agora - _amb["t"] < CACHE_AMBIENTE_SEG:
        return _amb["dados"]
    dados = buscar_clima()
    if agora - _ph["t"] > CACHE_PH_SEG:
        try:
            _ph["valor"] = buscar_ph()
            _ph["t"] = agora
        except Exception:
            _ph["t"] = agora - CACHE_PH_SEG + 3600  # tenta de novo em 1 h
    dados["ph"] = _ph["valor"]
    dados["atualizado"] = datetime.now().strftime("%H:%M")
    _amb.update(t=agora, dados=dados)
    return dados


class Handler(BaseHTTPRequestHandler):
    def _enviar(self, codigo, tipo, corpo):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._enviar(200, "text/html; charset=utf-8", (PASTA / "index.html").read_bytes())
        elif self.path == "/api/ambiente":
            try:
                self._enviar(200, "application/json", json.dumps(ambiente()).encode())
            except Exception:
                self._enviar(502, "application/json", b'{"erro": "falha ao buscar dados"}')
        else:
            self._enviar(404, "text/plain; charset=utf-8", b"nao encontrado")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Jarvis no ar: http://localhost:{PORTA}  (Ctrl+C para parar)")
    ThreadingHTTPServer(("127.0.0.1", PORTA), Handler).serve_forever()

# src/infra/http.py
import os, requests
from src.config import settings

class MsClient:
    def __init__(self, x_country: str):
        self.base = settings.GATEWAY_BASE_URL.rstrip("/")
        self.h = {"Content-Type": "application/json", settings.COUNTRY_HEADER: x_country}

    def post(self, path: str, json=None, params=None):
        r = requests.post(f"{self.base}{path}", headers=self.h, json=json, params=params, timeout=30)
        self._raise(r); return r.json() if r.content else None

    def get(self, path: str, params=None):
        r = requests.get(f"{self.base}{path}", headers=self.h, params=params, timeout=30)
        self._raise(r); return r.json() if r.content else None

    def _raise(self, r):
        if r.status_code >= 400:
            raise ValueError(f"HTTP {r.status_code} calling {r.request.method} {r.url}: {r.text}")
#!/usr/bin/env python3
import sys, pathlib

p = pathlib.Path("pyproject.toml")
b = p.read_bytes()

# Quita BOM UTF-8 si existe
if b.startswith(b'\xef\xbb\xbf'):
    b = b[3:]

# Corta cualquier cosa antes de la sección principal
i = b.find(b'[tool.poetry]')
if i > 0:
    b = b[i:]

# Valida: debe decodificar como UTF-8
try:
    text = b.decode("utf-8", errors="strict")
except UnicodeDecodeError as e:
    print(f"[sanitize] pyproject.toml no es UTF-8 válido: {e}", file=sys.stderr)
    sys.exit(1)

# Reglas mínimas: debe iniciar con [tool.poetry]
if not text.lstrip().startswith("[tool.poetry]"):
    print("[sanitize] pyproject.toml no inicia con [tool.poetry]", file=sys.stderr)
    print("[sanitize] Primeros 80 bytes:", b[:80], file=sys.stderr)
    sys.exit(1)

p.write_bytes(b)
print("[sanitize] TOML saneado OK")

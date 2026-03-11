import os
import requests
from dotenv import load_dotenv

load_dotenv(encoding="utf-8")

empresa = os.getenv("EZPOINT_EMPRESA")
usuario = os.getenv("EZPOINT_USUARIO")
senha = os.getenv("EZPOINT_SENHA")

req = requests.Request(
      "POST",
      "https://api.ezpointweb.com.br/ezweb-ws/login",
      json={"empresa": empresa, "usuario": usuario, "senha": senha},
)
prepared = req.prepare()

print("=== REQUEST ===")
print(f"URL: {prepared.url}")
print(f"Headers: {dict(prepared.headers)}")
print(f"Body: {prepared.body}")
print()

s = requests.Session()
r = s.send(prepared)
print(f"Status: {r.status_code}")
print(f"Response: {r.text}")
import os
import requests
from dotenv import load_dotenv

load_dotenv(encoding="utf-8")

empresa = os.getenv("EZPOINT_EMPRESA")
usuario = os.getenv("EZPOINT_USUARIO")
senha = os.getenv("EZPOINT_SENHA")

print("empresa:", repr(empresa))
print("usuario:", repr(usuario))
print("senha:  ", repr(senha))

r = requests.post(
      "https://api.ezpointweb.com.br/ezweb-ws/login",
      json={"tecbiofacial": empresa, "tecbiofacial": usuario, "tecbiofacial1532##%¨%": senha},
)
print(r.status_code, r.text)
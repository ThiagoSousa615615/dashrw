from __future__ import annotations

import json as _json
import requests
from typing import Any, Dict, List, Optional
import time


class EzPointWebClient:
    """
    Cliente para EzPoint WEB (api.ezpointweb.com.br).
    - login: POST /login (empresa, usuario, senha)
    - funcionarios: GET /funcionario (empresa, ocultarDemitidos=true)
    """

    def __init__(
        self,
        empresa: str,
        usuario: str,
        senha: str,
        base_url: str = "https://api.ezpointweb.com.br/ezweb-ws",
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ):
        self.empresa = empresa
        self.usuario = usuario
        self.senha = senha
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._token: Optional[str] = None

    def login(self) -> str:
        url = f"{self.base_url}/login"
        payload = {"empresa": self.empresa, "usuario": self.usuario, "senha": self.senha}
        body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
        r = self.session.post(url, data=body, headers={"Content-Type": "application/json"}, timeout=self.timeout)
        r.raise_for_status()

        # Algumas versões retornam texto puro; outras JSON. Vamos suportar ambos.
        token = None
        try:
            data = r.json()
            token = self._extract_token(data)
        except ValueError:
            token = (r.text or "").strip()

        if not token:
            raise RuntimeError(f"Login OK, mas não consegui extrair token. Resposta: {r.text[:500]}")

        self._token = token
        return token

    def _headers(self) -> Dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _extract_token(data: Any) -> Optional[str]:
        """
        Suporta variações comuns:
        - {"token":"..."} / {"hash":"..."}
        - {"resposta":"..."} (string)
        - {"resposta":{"token":"..."}}
        - {"resposta":[{"token":"..."}]}
        """
        if isinstance(data, str):
            return data.strip() or None

        if isinstance(data, dict):
            for k in ("token", "hash"):
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()

            resp = data.get("resposta")
            if isinstance(resp, str) and resp.strip():
                return resp.strip()
            if isinstance(resp, dict):
                v = resp.get("token") or resp.get("hash")
                if isinstance(v, str) and v.strip():
                    return v.strip()
            if isinstance(resp, list) and resp and isinstance(resp[0], dict):
                v = resp[0].get("token") or resp[0].get("hash")
                if isinstance(v, str) and v.strip():
                    return v.strip()

        return None

    def listar_funcionarios(self, ocultar_demitidos: bool = True, nome: Optional[str] = None) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/funcionario"
        params = {
            "empresa": self.empresa,
            "ocultarDemitidos": "true" if ocultar_demitidos else "false",
        }
        if nome:
            params["nome"] = nome

        r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        # Conforme doc: listaDeFuncionarios
        funcionarios = data.get("listaDeFuncionarios", [])
        if not isinstance(funcionarios, list):
            raise RuntimeError(f"Formato inesperado em /funcionario: {data}")
        return funcionarios

    def listar_batidas(self, data_inicio: str, data_fim: str) -> List[Dict[str, Any]]:
        """
        GET /batida?empresa=...&pagina=1&dataInicio=YYYY-MM-DD&dataFim=YYYY-MM-DD
        Pagina até totalPaginas.
        """
        url = f"{self.base_url}/batida"
        pagina = 1
        todas: List[Dict[str, Any]] = []

        while True:
            params = {
                "empresa": self.empresa,
                "pagina": pagina,
                "dataInicio": data_inicio,
                "dataFim": data_fim,
            }
            r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            if r.status_code == 500:
                # Bug conhecido no servidor EzPoint (ex.: registro duplicado).
                # Interrompe paginação e retorna o que foi coletado até agora.
                break
            r.raise_for_status()
            data = r.json()

            lista = data.get("listaDeBatidas", []) or []
            total_paginas = int(data.get("totalPaginas", 1) or 1)

            todas.extend(lista)

            if pagina >= total_paginas:
                break

            pagina += 1

            # Pequena pausa para ajudar no limite de 30 req/min
            time.sleep(0.25)

        return todas

"""
auth.py — Camada de autenticação para o Dashboard Ponto.

Uso:
    from auth import require_auth
    require_auth()  # após set_page_config, antes de st.title

Requer no .env:
    AUTH_COOKIE_SECRET=<string aleatória 32+ chars>
    ADMIN_EMAIL=email_do_admin@empresa.com
"""

import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import streamlit as st
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import extra_streamlit_components as stx

from db import get_con

load_dotenv(encoding="utf-8")

_SECRET = os.getenv("AUTH_COOKIE_SECRET", "default-insecure-secret-change-me")
_COOKIE_NAME = "auth_token"
_COOKIE_EXPIRY_DAYS = 7
_SESSION_TIMEOUT_MIN = 30


# ─────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────

def ensure_usuarios_table() -> None:
    with get_con() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
              id               INTEGER PRIMARY KEY AUTOINCREMENT,
              username         TEXT    NOT NULL UNIQUE,
              email            TEXT    NOT NULL UNIQUE,
              senha_hash       TEXT    NOT NULL,
              primeiro_acesso  INTEGER NOT NULL DEFAULT 1,
              ativo            INTEGER NOT NULL DEFAULT 1,
              criado_em        TEXT    NOT NULL DEFAULT (datetime('now')),
              atualizado_em    TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        con.commit()

        count = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if count == 0:
            admin_email = os.getenv("ADMIN_EMAIL", "").strip()
            if not admin_email:
                st.error("ADMIN_EMAIL não configurado no .env. Configure e reinicie o app.")
                st.stop()
            hashed = hash_password("Tecbio2026")
            con.execute(
                """INSERT INTO usuarios (username, email, senha_hash, primeiro_acesso)
                   VALUES (?, ?, ?, 1)""",
                ("admin", admin_email, hashed),
            )
            con.commit()


def get_user_by_username(username: str) -> Optional[dict]:
    with get_con() as con:
        row = con.execute(
            "SELECT id, username, email, senha_hash, primeiro_acesso, ativo FROM usuarios WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "username": row[1], "email": row[2],
        "senha_hash": row[3], "primeiro_acesso": row[4], "ativo": row[5],
    }


def get_user_by_email(email: str) -> Optional[dict]:
    with get_con() as con:
        row = con.execute(
            "SELECT id, username, email, senha_hash, primeiro_acesso, ativo FROM usuarios WHERE email = ?",
            (email,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "username": row[1], "email": row[2],
        "senha_hash": row[3], "primeiro_acesso": row[4], "ativo": row[5],
    }


def update_password(user_id: int, new_hash: str, primeiro_acesso: int = 0) -> None:
    with get_con() as con:
        con.execute(
            """UPDATE usuarios
               SET senha_hash = ?, primeiro_acesso = ?, atualizado_em = datetime('now')
               WHERE id = ?""",
            (new_hash, primeiro_acesso, user_id),
        )
        con.commit()


# ─────────────────────────────────────────
# Senha
# ─────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*" for c in pwd)
        ):
            return pwd


# ─────────────────────────────────────────
# Cookie
# ─────────────────────────────────────────

def _get_cookie_manager():
    if "auth_cookie_manager" not in st.session_state:
        st.session_state["auth_cookie_manager"] = stx.CookieManager(key="auth_cookies")
    return st.session_state["auth_cookie_manager"]


def _sign_token(user_id: int, username: str) -> str:
    s = URLSafeTimedSerializer(_SECRET)
    return s.dumps({"user_id": user_id, "username": username})


def _verify_token(token: str) -> Optional[dict]:
    s = URLSafeTimedSerializer(_SECRET)
    try:
        return s.loads(token, max_age=_COOKIE_EXPIRY_DAYS * 86400)
    except (BadSignature, SignatureExpired):
        return None


def set_auth_cookie(user_id: int, username: str) -> None:
    cm = _get_cookie_manager()
    token = _sign_token(user_id, username)
    expires = datetime.now(timezone.utc) + timedelta(days=_COOKIE_EXPIRY_DAYS)
    cm.set(_COOKIE_NAME, token, expires_at=expires)


def clear_auth_cookie() -> None:
    cm = _get_cookie_manager()
    try:
        cm.delete(_COOKIE_NAME)
    except Exception:
        pass


def read_auth_cookie() -> Optional[dict]:
    cm = _get_cookie_manager()
    token = cm.get(_COOKIE_NAME)
    if not token:
        return None
    return _verify_token(token)


# ─────────────────────────────────────────
# Sessão
# ─────────────────────────────────────────

def _load_session_from_cookie() -> bool:
    payload = read_auth_cookie()
    if payload is None:
        return False
    user = get_user_by_username(payload.get("username", ""))
    if user is None or not user["ativo"]:
        return False
    st.session_state["user"] = user
    st.session_state["last_activity"] = datetime.now()
    return True


def _update_activity() -> None:
    st.session_state["last_activity"] = datetime.now()


def _is_idle_timed_out() -> bool:
    last = st.session_state.get("last_activity")
    if last is None:
        return False
    return (datetime.now() - last).total_seconds() > _SESSION_TIMEOUT_MIN * 60


def logout() -> None:
    clear_auth_cookie()
    st.session_state.pop("user", None)
    st.session_state.pop("last_activity", None)


# ─────────────────────────────────────────
# E-mail de reset
# ─────────────────────────────────────────

def _send_reset_email(user: dict, temp_password: str) -> None:
    from send_report import send_email  # importação local para evitar dependência circular

    smtp_cfg = {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": os.getenv("SMTP_PORT", "587").strip(),
        "usuario": os.getenv("SMTP_USUARIO", "").strip(),
        "senha": os.getenv("SMTP_SENHA", "").strip(),
        "remetente_nome": os.getenv("EMAIL_REMETENTE_NOME", "Dashboard Ponto").strip(),
    }

    html_body = f"""<!doctype html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;padding:16px;max-width:480px;">
  <h2>Redefinição de Senha — Dashboard Ponto</h2>
  <p>Olá, <strong>{user['username']}</strong>!</p>
  <p>Sua senha foi redefinida. Use a senha temporária abaixo para acessar o sistema:</p>
  <p style="font-size:20px;font-weight:bold;background:#f5f5f5;padding:14px;
            border-radius:4px;display:inline-block;letter-spacing:2px;">{temp_password}</p>
  <p>Você será solicitado a criar uma nova senha no próximo acesso.</p>
  <hr>
  <p style="color:#888;font-size:12px;">Dashboard Ponto — acesso interno</p>
</body>
</html>"""

    send_email(
        html_body,
        [{"email": user["email"], "nome": user["username"]}],
        "Redefinição de Senha — Dashboard Ponto",
        smtp_cfg,
    )


# ─────────────────────────────────────────
# UI — formulários
# ─────────────────────────────────────────

def _show_forgot_password_form() -> None:
    with st.expander("Esqueci minha senha"):
        with st.form("forgot_password_form"):
            email = st.text_input("E-mail cadastrado")
            submitted = st.form_submit_button("Enviar senha temporária")

        if submitted:
            if not email.strip():
                st.error("Informe o e-mail.")
                return
            user = get_user_by_email(email.strip())
            if user and user["ativo"]:
                temp_pwd = generate_temp_password()
                update_password(user["id"], hash_password(temp_pwd), primeiro_acesso=1)
                try:
                    _send_reset_email(user, temp_pwd)
                except Exception as exc:
                    st.error(f"Erro ao enviar e-mail: {exc}")
                    return
            # Mesma mensagem independente de o e-mail existir (evita enumeração)
            st.success("Se o e-mail estiver cadastrado, você receberá as instruções em breve.")


def _show_login_form() -> None:
    st.title("Dashboard Ponto — Login")

    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        if not username.strip() or not password.strip():
            st.error("Preencha usuário e senha.")
            return
        user = get_user_by_username(username.strip())
        if user is None or not user["ativo"] or not verify_password(password, user["senha_hash"]):
            st.error("Usuário ou senha inválidos.")
            return
        st.session_state["user"] = user
        st.session_state["last_activity"] = datetime.now()
        if not user["primeiro_acesso"]:
            set_auth_cookie(user["id"], user["username"])
        st.rerun()

    _show_forgot_password_form()


def _show_change_password_form() -> None:
    user = st.session_state["user"]
    st.title("Troca de Senha Obrigatória")
    st.info(f"Olá, **{user['username']}**! Por segurança, defina uma nova senha antes de continuar.")

    with st.form("change_password_form"):
        new_pwd = st.text_input("Nova senha (mínimo 8 caracteres)", type="password")
        confirm_pwd = st.text_input("Confirmar nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha")

    if submitted:
        if len(new_pwd) < 8:
            st.error("A senha deve ter pelo menos 8 caracteres.")
            return
        if new_pwd != confirm_pwd:
            st.error("As senhas não coincidem.")
            return
        if verify_password(new_pwd, user["senha_hash"]):
            st.error("A nova senha não pode ser igual à senha atual.")
            return
        new_hash = hash_password(new_pwd)
        update_password(user["id"], new_hash, primeiro_acesso=0)
        user["senha_hash"] = new_hash
        user["primeiro_acesso"] = 0
        st.session_state["user"] = user
        set_auth_cookie(user["id"], user["username"])
        st.success("Senha alterada com sucesso!")
        st.rerun()


def _render_logout_button() -> None:
    user = st.session_state.get("user", {})
    with st.sidebar:
        st.write(f"**{user.get('username', '')}**")
        if st.button("Sair", key="logout_btn"):
            logout()
            st.rerun()


# ─────────────────────────────────────────
# Ponto de entrada público
# ─────────────────────────────────────────

def require_auth() -> None:
    ensure_usuarios_table()

    if "user" not in st.session_state:
        if not _load_session_from_cookie():
            _show_login_form()
            st.stop()

    if _is_idle_timed_out():
        del st.session_state["user"]
        del st.session_state["last_activity"]
        st.warning("Sessão expirada por inatividade. Faça login novamente.")
        _show_login_form()
        st.stop()

    if st.session_state["user"]["primeiro_acesso"]:
        _show_change_password_form()
        st.stop()

    _update_activity()
    _render_logout_button()

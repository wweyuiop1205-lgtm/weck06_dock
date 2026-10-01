"""
backend/auth.py
使用者驗證與角色型存取控制 (RBAC)
"""

from .database import run_query


def check_login(username: str, password: str) -> dict | None:
    """驗證帳號密碼，成功回傳 {role, name}，失敗回傳 None。
    （N3）密碼以 salted hash 比對；遇到 legacy 明文則於登入成功時就地升級。"""
    from backend.passwords import verify_password, is_hashed, hash_password

    rows = run_query(
        "SELECT password, role, name FROM users WHERE username=?",
        (username,),
    )
    if not rows:
        return None
    stored, role, name = rows[0]
    if not verify_password(password, stored or ""):
        return None
    if not is_hashed(stored or ""):  # legacy 明文 → 自我修復式升級
        run_query("UPDATE users SET password=? WHERE username=?",
                  (hash_password(password), username), fetch=False)
    return {"role": role, "name": name}


def check_permission(allowed_roles: list) -> bool:
    """Deny legacy ERP calls without an explicit API access context.

    FastAPI risk routes use ``backend.access_control`` for authorization.
    The old UI session-based permission path is intentionally absent.
    """
    return False
import hmac
import os

from fastapi import Header, HTTPException


def require_admin(x_admin_token: str = Header(default='')):
    expected = os.getenv('ADMIN_TOKEN', '')
    if not expected or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail='Admin only')
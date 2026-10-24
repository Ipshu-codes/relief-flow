import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from .db import SessionLocal
from .models import User
from .security import hash_password


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m app.bootstrap_admin <email>')
    try:
        email = str(TypeAdapter(EmailStr).validate_python(sys.argv[1])).lower()
    except ValidationError as exc:
        raise SystemExit('Enter a valid email address') from exc

    full_name = input('Admin full name: ').strip()
    password = getpass.getpass('Admin password (minimum 8 characters): ')
    if len(full_name) == 0 or len(password) < 8:
        raise SystemExit('Name is required and password must be at least 8 characters')

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise SystemExit('An account with this email already exists')
        db.add(
            User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role='admin',
            )
        )
        db.commit()
    print(f'Created admin account for {email}')


if __name__ == '__main__':
    main()

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import UserLogin, UserProfilePatch, UserProfileRead, UserRead, UserRegister
from ..security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/register', response_model=UserRead, status_code=201)
def register(data: UserRegister, db: Session = Depends(get_db)):
    user = User(
        email=str(data.email),
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
        role='community_member',
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='An account with this email already exists')
    db.refresh(user)
    return user


@router.post('/login')
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email)))
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail='Invalid email or password',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return {
        'access_token': create_access_token(user.id),
        'token_type': 'bearer',
    }


@router.get('/me', response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user


@router.get('/me/profile', response_model=UserProfileRead)
def profile(user: User = Depends(get_current_user)):
    return _profile_payload(user)


@router.patch('/me/profile', response_model=UserProfileRead)
def update_profile(
    data: UserProfilePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _profile_payload(user)


def _profile_payload(user: User) -> dict:
    return {
        'phone_number': user.phone_number,
        'address': user.address,
        'latitude': user.latitude,
        'longitude': user.longitude,
        'location_accuracy_m': user.location_accuracy_m,
        'emergency_contacts': user.emergency_contacts or [],
        'profile_notes': user.profile_notes,
    }

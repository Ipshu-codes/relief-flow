from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import check_chain
from ..models import Contribution, LedgerEntry
from ..schemas import ContributionCreate

router = APIRouter(prefix='/api/contributions', tags=['contributions'])


@router.post('', status_code=201)
def create(data: ContributionCreate, db: Session = Depends(get_db)):
    taken = db.scalar(select(Contribution.id).where(Contribution.txn_id == data.txn_id))
    if taken:
        raise HTTPException(409, 'This transaction ID was already submitted')
    c = Contribution(**data.model_dump(), status='ready')
    db.add(c)
    db.commit()
    db.refresh(c)
    return {'id': c.id, 'status': c.status, 'receipt_token': c.receipt_token}


@router.get('')
def public_list(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Contribution).where(Contribution.status == 'verified').order_by(Contribution.id.desc())
    ).all()
    return [
        {
            'id': c.id,
            'donor': 'Anonymous' if c.is_anonymous else c.donor_name,
            'amount_npr': c.amount_npr,
            'date': c.verified_at.isoformat() if c.verified_at else None,
        }
        for c in rows
    ]


@router.get('/summary')
def summary(db: Session = Depends(get_db)):
    total = db.scalar(
        select(func.coalesce(func.sum(Contribution.amount_npr), 0)).where(Contribution.status == 'verified')
    )
    count = db.scalar(
        select(func.count()).select_from(Contribution).where(Contribution.status == 'verified')
    )
    ok, bad_id = check_chain(db)
    last = db.scalar(select(LedgerEntry).order_by(LedgerEntry.id.desc()))
    return {
        'total_npr': total,
        'count': count,
        'chain_ok': ok,
        'first_bad_entry': bad_id,
        'latest_hash': last.entry_hash if last else None,
    }


@router.get('/statement/{token}')
def statement(token: str, db: Session = Depends(get_db)):
    c = db.scalar(select(Contribution).where(Contribution.receipt_token == token))
    if not c:
        raise HTTPException(404, 'Statement not found')
    entry = db.scalar(select(LedgerEntry).where(LedgerEntry.contribution_id == c.id))
    return {
        'donor_name': c.donor_name,
        'amount_npr': c.amount_npr,
        'txn_id': c.txn_id,
        'channel': c.channel,
        'status': c.status,
        'submitted_at': c.created_at.isoformat(),
        'verified_at': c.verified_at.isoformat() if c.verified_at else None,
        'entry_hash': entry.entry_hash if entry else None,
    }
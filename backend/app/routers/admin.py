import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import mark_verified
from ..models import Contribution
from ..security import require_admin

router = APIRouter(prefix='/api/admin', tags=['admin'], dependencies=[Depends(require_admin)])

OPEN = ['ready', 'needs_fix']


def to_dict(c: Contribution) -> dict:
    return {
        'id': c.id,
        'donor_name': c.donor_name,
        'is_anonymous': c.is_anonymous,
        'amount_npr': c.amount_npr,
        'txn_id': c.txn_id,
        'channel': c.channel,
        'status': c.status,
        'review_note': c.review_note,
        'has_slip': bool(c.slip_path),
        'created_at': c.created_at.isoformat(),
    }


def get_open(db: Session, cid: int) -> Contribution:
    c = db.get(Contribution, cid)
    if not c:
        raise HTTPException(404, 'Not found')
    if c.status not in OPEN:
        raise HTTPException(409, 'Already decided')
    return c


@router.get('/queue')
def queue(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Contribution).where(Contribution.status.in_(OPEN)).order_by(Contribution.id)
    ).all()
    return [to_dict(c) for c in rows]


class AdminEdit(BaseModel):
    amount_npr: float | None = Field(default=None, gt=0)
    txn_id: str | None = Field(default=None, min_length=3, max_length=80)
    channel: str | None = Field(default=None, pattern='^(esewa|khalti|bank|other)$')


@router.patch('/contributions/{cid}')
def edit(cid: int, data: AdminEdit, db: Session = Depends(get_db)):
    c = get_open(db, cid)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    if c.amount_npr and c.txn_id and c.channel:
        c.status = 'ready'
    db.commit()
    return to_dict(c)


@router.post('/contributions/{cid}/verify')
def verify(cid: int, db: Session = Depends(get_db)):
    c = get_open(db, cid)
    if c.status != 'ready':
        raise HTTPException(400, 'Fix the missing fields first')
    mark_verified(db, c)
    db.commit()
    return to_dict(c)


@router.post('/contributions/{cid}/reject')
def reject(cid: int, db: Session = Depends(get_db)):
    c = get_open(db, cid)
    c.status = 'rejected'
    db.commit()
    return to_dict(c)


@router.post('/reconcile')
def reconcile(file: UploadFile = File(...), db: Session = Depends(get_db)):
    text = file.file.read().decode('utf-8-sig')
    paid = {}
    for row in csv.DictReader(io.StringIO(text)):
        paid[row['txn_id'].strip()] = float(row['amount'])
    matched = 0
    for c in db.scalars(select(Contribution).where(Contribution.status == 'ready')).all():
        if c.txn_id in paid and abs(paid[c.txn_id] - c.amount_npr) < 0.01:
            mark_verified(db, c)
            matched += 1
    db.commit()
    return {'matched': matched}
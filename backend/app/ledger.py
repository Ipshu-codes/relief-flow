import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Contribution, LedgerEntry

GENESIS = '0' * 64


def compute_hash(prev_hash: str, record: dict) -> str:
    text = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256((prev_hash + text).encode('utf-8')).hexdigest()


def mark_verified(db: Session, c: Contribution) -> LedgerEntry:
    last = db.scalar(select(LedgerEntry).order_by(LedgerEntry.id.desc()))
    prev = last.entry_hash if last else GENESIS
    record = {
        'contribution_id': c.id,
        'donor': 'Anonymous' if c.is_anonymous else c.donor_name,
        'amount_npr': c.amount_npr,
        'txn_id': c.txn_id,
        'channel': c.channel,
    }
    entry = LedgerEntry(
        contribution_id=c.id,
        prev_hash=prev,
        entry_hash=compute_hash(prev, record),
        record_json=json.dumps(record, sort_keys=True, ensure_ascii=False),
    )
    c.status = 'verified'
    c.verified_at = datetime.now(timezone.utc)
    db.add(entry)
    return entry


def check_chain(db: Session) -> tuple[bool, int | None]:
    prev = GENESIS
    for e in db.scalars(select(LedgerEntry).order_by(LedgerEntry.id)):
        if e.prev_hash != prev or compute_hash(prev, json.loads(e.record_json)) != e.entry_hash:
            return False, e.id
        prev = e.entry_hash
    return True, None
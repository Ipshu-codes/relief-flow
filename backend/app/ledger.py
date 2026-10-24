import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, Contribution, LedgerEntry

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


def append_audit_log(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | str,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    before_json = _serialize(before) if before is not None else None
    after_json = _serialize(after) if after is not None else None
    created_at = datetime.now(timezone.utc)
    record = {
        'actor_id': actor_id,
        'action': action,
        'entity': entity,
        'entity_id': str(entity_id),
        'before': json.loads(before_json) if before_json else None,
        'after': json.loads(after_json) if after_json else None,
        'created_at': created_at.isoformat(),
    }
    record_json = _serialize(record)
    pending_entries = [entry for entry in db.new if isinstance(entry, AuditLog)]
    if pending_entries:
        prev_hash = pending_entries[-1].entry_hash
    else:
        last = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        prev_hash = last.entry_hash if last else GENESIS
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before_json=before_json,
        after_json=after_json,
        record_json=record_json,
        created_at=created_at,
        prev_hash=prev_hash,
        entry_hash=compute_hash(prev_hash, record),
    )
    db.add(entry)
    return entry


def check_audit_chain(db: Session) -> tuple[bool, int | None]:
    prev_hash = GENESIS
    for entry in db.scalars(select(AuditLog).order_by(AuditLog.id)):
        timestamp = entry.created_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        record = {
            'actor_id': entry.actor_id,
            'action': entry.action,
            'entity': entry.entity,
            'entity_id': entry.entity_id,
            'before': json.loads(entry.before_json) if entry.before_json else None,
            'after': json.loads(entry.after_json) if entry.after_json else None,
            'created_at': timestamp.isoformat(),
        }
        if (
            entry.prev_hash != prev_hash
            or _serialize(record) != entry.record_json
            or compute_hash(prev_hash, record) != entry.entry_hash
        ):
            return False, entry.id
        prev_hash = entry.entry_hash
    return True, None


def _serialize(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
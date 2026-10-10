
import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Contribution(Base):
    __tablename__ = 'contributions'

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_name: Mapped[str] = mapped_column(String(120))
    is_anonymous: Mapped[bool] = mapped_column(default=False)
    amount_npr: Mapped[float | None] = mapped_column(Float, nullable=True)
    txn_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='ready')
    slip_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_token: Mapped[str] = mapped_column(
        String(40), unique=True, default=lambda: secrets.token_urlsafe(8)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LedgerEntry(Base):
    __tablename__ = 'ledger_entries'

    id: Mapped[int] = mapped_column(primary_key=True)
    contribution_id: Mapped[int]
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
    record_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
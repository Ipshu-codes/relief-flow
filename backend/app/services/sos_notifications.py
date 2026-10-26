import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    SMS_PROVIDER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
)
from ..models import Notification, SOSEvent, User, VolunteerProfile

logger = logging.getLogger(__name__)


def _location(event: SOSEvent) -> str:
    if event.address:
        values = [
            event.address.get(key)
            for key in ('district', 'city', 'ward', 'road', 'landmark')
            if event.address.get(key)
        ]
        if values:
            return ', '.join(values)
    if event.has_location:
        return f'{event.latitude:.5f}, {event.longitude:.5f}'
    return 'Location not provided'


async def _send_sms(phone: str, message: str) -> bool:
    if SMS_PROVIDER != 'twilio':
        logger.info('SMS not sent: SMS_PROVIDER is not configured')
        return False
    if not all((TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)):
        logger.error('SMS_PROVIDER=twilio but Twilio credentials are incomplete')
        return False
    url = (
        f'https://api.twilio.com/2010-04-01/Accounts/'
        f'{TWILIO_ACCOUNT_SID}/Messages.json'
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                data={'From': TWILIO_FROM_NUMBER, 'To': phone, 'Body': message},
            )
            response.raise_for_status()
        return True
    except (httpx.HTTPError, ValueError):
        logger.exception('SMS delivery failed for emergency contact')
        return False


def _notification(
    user_id: int,
    title: str,
    message: str,
    event: SOSEvent,
    *,
    kind: str = 'sos_alert',
) -> Notification:
    return Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        message=message,
        payload={
            'sos_id': event.id,
            'urgency': event.urgency,
            'category': event.category,
        },
    )


async def notify_sos(
    db: Session,
    event: SOSEvent,
    interpretation: dict[str, Any],
) -> None:
    """Fan out a saved SOS without making SOS persistence depend on SMS."""
    location = _location(event)
    message = (
        f'Rahat SOS: {event.category} priority {event.urgency}/5 at {location}. '
        f'{event.message[:240]}'
    )
    recipients: set[int] = set()
    managers = db.scalars(
        select(User).where(
            User.role.in_({'admin', 'coordinator'}),
            User.is_active.is_(True),
        )
    ).all()
    recipients.update(user.id for user in managers)

    if event.urgency >= 4:
        available = db.scalars(
            select(User)
            .join(VolunteerProfile, VolunteerProfile.user_id == User.id)
            .where(
                User.is_active.is_(True),
                VolunteerProfile.availability_status == 'available',
            )
        ).all()
        recipients.update(user.id for user in available)

    reporter = db.get(User, event.reporter_user_id) if event.reporter_user_id else None
    if reporter is not None:
        # A reporter can also have a manager or volunteer role. They should
        # not receive the same alert that their own request generated.
        recipients.discard(reporter.id)

    for user_id in recipients:
        db.add(_notification(
            user_id,
            'High-priority SOS' if event.urgency >= 4 else 'New SOS report',
            message,
            event,
        ))
    sms_targets: set[str] = set()
    for user in [reporter] if reporter is not None else []:
        for contact in user.emergency_contacts or []:
            if not contact.get('consent_to_notify', True):
                continue
            phone = str(contact.get('phone', '')).strip()
            if not phone:
                continue
            registered = next(
                (
                    candidate for candidate in db.scalars(
                        select(User).where(User.is_active.is_(True))
                    ).all()
                    if candidate.phone_number == phone
                ),
                None,
            )
            if registered is not None and registered.id != reporter.id:
                db.add(_notification(
                    registered.id,
                    'Emergency contact alert',
                    f'{user.full_name} may need assistance. {message}',
                    event,
                    kind='emergency_contact_alert',
                ))
                sms_targets.add(phone)
            elif registered is None:
                sms_targets.add(phone)

    # Never fail the SOS transaction because a third-party SMS provider is down.
    for phone in sms_targets:
        await _send_sms(phone, message)

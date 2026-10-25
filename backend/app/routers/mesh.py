"""Platform packet compatibility and a deterministic radio-only demo."""

from base64 import b64decode
from binascii import Error as Base64Error
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from protocol import codec
from sqlalchemy.orm import Session

from ai.sos_tasks import interpret_sos_event
from ..db import get_db
from ..models import User
from ..schemas import SOSEventCreate
from ..security import require_role
from .sos import create_event, event_response, receipt_token

router = APIRouter(tags=['platform mesh compatibility'])
CATEGORY_MAP = {
    'medical': 'MEDICINE', 'trapped': 'TRAPPED', 'fire': 'RESCUE', 'flood': 'RESCUE',
    'food_water': 'FOOD', 'shelter': 'OTHER', 'missing': 'OTHER', 'road_blocked': 'OTHER',
    'other': 'OTHER',
}


class PacketIn(BaseModel):
    packet: str = Field(min_length=1, max_length=1024)


class BleEnvelope(BaseModel):
    v: int = Field(ge=1, le=1)
    ttl: int = Field(ge=0, le=6)
    payload: str = Field(min_length=1, max_length=16000)
    public_key: str = Field(min_length=44, max_length=44)
    signature: str = Field(min_length=88, max_length=88)


@router.post('/api/v1/ingest/ble')
def ingest_ble(
    body: BleEnvelope, request: Request, background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        payload = b64decode(body.payload, validate=True)
        public = b64decode(body.public_key, validate=True)
        signature = b64decode(body.signature, validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, b'rahat-ble-v1:' + payload,
        )
        event_data = SOSEventCreate.model_validate_json(payload)
    except (Base64Error, InvalidSignature, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail='Invalid signed Android SOS envelope') from exc
    event_data.sender_ref = f'ble:{public.hex()}'
    event_data.channel = 'mesh'
    event_data.relay_path = ['android-ble']
    try:
        event, created = create_event(
            db, data=event_data, user=None, force_channel='mesh',
            anonymous_source=request.client.host if request.client else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(event)
    if created:
        background_tasks.add_task(interpret_sos_event, event.id)
    return {
        **event_response(event), 'receipt_token': receipt_token(event),
        'signature_verified': True, 'identity_trusted': False,
        'result': 'created' if created else 'duplicate',
    }


def store_packet(db: Session, raw: bytes, background: BackgroundTasks, source: str) -> dict:
    try:
        packet = codec.decode(raw)
        if packet.type != codec.PacketType.SOS:
            raise ValueError('Only SOS packets are supported by this ingest endpoint')
        data = packet.data()
        category = data.get('c') or data.get('category') or 'other'
        if category not in CATEGORY_MAP:
            raise ValueError('Unknown packet category')
        event_data = SOSEventCreate(
            client_uuid=uuid5(NAMESPACE_URL, f'rmp:{packet.sender.hex()}:{packet.msg_id.hex()}'),
            sender_ref=f'rmp:{packet.sender.hex()}',
            lat=data.get('lat'), lon=data.get('lon'),
            category=CATEGORY_MAP[category],
            message=f"{category}: {data.get('t') or data.get('text') or 'SOS'}"[:500],
            channel='mesh', relay_path=[source],
        )
    except (codec.CodecError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f'Invalid signed SOS packet: {exc}') from exc
    event, created = create_event(db, data=event_data, user=None)
    db.commit()
    db.refresh(event)
    if created:
        background.add_task(interpret_sos_event, event.id)
    return {
        **event_response(event), 'accepted': created, 'reason': None if created else 'duplicate',
        'msg_id': packet.msg_id.hex(), 'receipt_token': receipt_token(event),
        'signature_verified': True, 'identity_trusted': False,
    }


@router.post('/api/v1/ingest/packet')
def ingest_packet(body: PacketIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        raw = b64decode(body.packet, validate=True)
    except (Base64Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail='Invalid base64 packet') from exc
    return store_packet(db, raw, background_tasks, 'signed-packet')


class DemoSOS(BaseModel):
    category: str = Field(default='trapped', max_length=40)
    text: str = Field(default='[SIMULATION] Need assistance', max_length=300)


class RadioDemo:
    def __init__(self):
        self.lock = Lock()
        self.connected = False
        self.queue: list[bytes] = []

    def state(self):
        return {'simulation': True, 'bridge_connected': self.connected, 'queued': len(self.queue)}


demo = RadioDemo()
manager = require_role('admin', 'coordinator')


@router.get('/api/v1/demo/state')
def demo_state(user: User = Depends(manager)):
    with demo.lock:
        return demo.state()


@router.post('/api/v1/demo/sos')
def demo_sos(
    body: DemoSOS, background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), user: User = Depends(manager),
):
    if body.category not in CATEGORY_MAP:
        raise HTTPException(status_code=422, detail='Unknown SOS category')
    key, public = codec.new_keypair()
    packet, raw = codec.make_sos(
        key, public, category=body.category, lat=27.7172, lon=85.324,
        text=f'[SIMULATION] {body.text}',
    )
    with demo.lock:
        if not demo.connected:
            if len(demo.queue) >= 100:
                raise HTTPException(status_code=409, detail='Simulation queue full; reconnect the bridge')
            demo.queue.append(raw)
            return {**demo.state(), 'queued': True, 'delivered': False, 'msg_id': packet.msg_id.hex()}
        result = store_packet(db, raw, background_tasks, 'simulation')
        return {**demo.state(), 'delivered': True, 'receipt': result}


@router.post('/api/v1/demo/bridge/toggle')
def toggle_bridge(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(manager),
):
    with demo.lock:
        demo.connected = not demo.connected
        delivered = []
        if demo.connected:
            while demo.queue:
                raw = demo.queue[0]
                result = store_packet(db, codec.decrement_ttl(raw), background_tasks, 'simulation')
                demo.queue.pop(0)
                delivered.append(result)
        return {**demo.state(), 'delivered': delivered}

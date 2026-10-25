"""Rahat Mesh Protocol (RMP v1) codec.

Wire format (all integers big-endian):

    version      1 B   0x01
    type         1 B   PacketType
    flags        1 B   bitfield
    ttl          1 B   decremented by relays, NOT covered by the signature
    msg_id       8 B   sender prefix + random
    timestamp    4 B   unix seconds
    sender_pub  32 B   Ed25519 public key
    payload_len  2 B
    payload      n B   CBOR-map (application data)
    signature   64 B   Ed25519 over the header (TTL zeroed) + payload

The signature excludes TTL so any relay can decrement it without re-signing,
while still binding type, sender, payload, and timestamp.
"""

from __future__ import annotations

import hashlib
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Any

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

VERSION = 1
MAX_TTL = 12
SIGNATURE_SIZE = 64
PUBLIC_KEY_SIZE = 32
MESSAGE_ID_SIZE = 8
HEADER_SIZE = 50  # includes TTL
MAX_PACKET_SIZE = 200  # NFR-3: core SOS payload fits a BLE advertisement chain
MAX_PAYLOAD_SIZE = MAX_PACKET_SIZE - HEADER_SIZE - SIGNATURE_SIZE  # 86 bytes

# version, type, flags, ttl, msg_id, timestamp, sender, payload_len
_WIRE = struct.Struct(">BBBB8sI32sH")
# Same fields without TTL; used as the signed region.
_SIGNED = struct.Struct(">BBB8sI32sH")


class PacketType(IntEnum):
    SOS = 1
    ACK = 2
    ASSIGN = 3
    BEACON = 4
    VOLUNTEER = 5
    STATUS = 6


class Flags(IntFlag):
    NONE = 0
    ENCRYPTED = 1 << 0
    FRAGMENT = 1 << 1
    PRIORITY = 1 << 2


PRIORITY_ORDER = {
    PacketType.SOS: 0,
    PacketType.ACK: 1,
    PacketType.ASSIGN: 1,
    PacketType.STATUS: 2,
    PacketType.VOLUNTEER: 3,
    PacketType.BEACON: 4,
}


class CodecError(ValueError):
    """Raised when a packet cannot be decoded or is malformed."""


class PayloadTooLarge(CodecError):
    """Raised when a payload exceeds the compact BLE budget."""


@dataclass(slots=True)
class Packet:
    type: PacketType
    msg_id: bytes
    timestamp: int
    sender: bytes
    payload: bytes = b""
    ttl: int = MAX_TTL
    flags: Flags = Flags.NONE
    version: int = VERSION
    signature: bytes = b""
    raw: bytes = field(default=b"", repr=False)

    def __post_init__(self) -> None:
        if len(self.msg_id) != MESSAGE_ID_SIZE:
            raise CodecError(f"msg_id must be {MESSAGE_ID_SIZE} bytes")
        if len(self.sender) != PUBLIC_KEY_SIZE:
            raise CodecError(f"sender must be {PUBLIC_KEY_SIZE} bytes")
        if not 0 <= self.ttl <= MAX_TTL:
            raise CodecError(f"ttl must be 0..{MAX_TTL}")
        if len(self.payload) > MAX_PAYLOAD_SIZE:
            raise PayloadTooLarge(f"payload exceeds {MAX_PAYLOAD_SIZE} bytes")

    @property
    def priority(self) -> int:
        return PRIORITY_ORDER.get(self.type, 99)

    def data(self) -> dict[str, Any]:
        """Decode the CBOR payload. Untrusted: callers must validate fields."""
        try:
            value = cbor2.loads(self.payload)
        except Exception as exc:  # noqa: BLE001 - malformed input is expected
            raise CodecError("payload is not valid CBOR") from exc
        if not isinstance(value, dict):
            raise CodecError("payload must be a CBOR map")
        return value


def new_message_id(sender: bytes | None = None) -> bytes:
    """Sender-prefixed random id: 4-byte key hash + 4 random bytes."""
    prefix = hashlib.blake2s(sender or b"", digest_size=4).digest()
    return prefix + secrets.token_bytes(4)


def _signed_region(
    *,
    version: int,
    ptype: int,
    flags: int,
    msg_id: bytes,
    timestamp: int,
    sender: bytes,
    payload: bytes,
) -> bytes:
    return (
        _SIGNED.pack(version, ptype, flags, msg_id, timestamp, sender, len(payload))
        + payload
    )


def encode(packet: Packet, private_key: Ed25519PrivateKey) -> bytes:
    """Sign and serialise a packet, returning the wire bytes."""
    if packet.version != VERSION:
        raise CodecError(f"unsupported version {packet.version}")
    signed = _signed_region(
        version=packet.version,
        ptype=int(packet.type),
        flags=int(packet.flags),
        msg_id=packet.msg_id,
        timestamp=packet.timestamp,
        sender=packet.sender,
        payload=packet.payload,
    )
    signature = private_key.sign(signed)
    wire = (
        _WIRE.pack(
            packet.version,
            int(packet.type),
            int(packet.flags),
            packet.ttl,
            packet.msg_id,
            packet.timestamp,
            packet.sender,
            len(packet.payload),
        )
        + packet.payload
        + signature
    )
    packet.signature = signature
    packet.raw = wire
    return wire


def decode(data: bytes, *, verify_signature: bool = True) -> Packet:
    """Parse wire bytes. Verifies the signature by default."""
    if len(data) < HEADER_SIZE + SIGNATURE_SIZE:
        raise CodecError("packet too short")
    version, ptype, flags, ttl, msg_id, timestamp, sender, payload_len = _WIRE.unpack(
        data[:HEADER_SIZE]
    )
    if version != VERSION:
        raise CodecError(f"unsupported version {version}")
    expected = HEADER_SIZE + payload_len + SIGNATURE_SIZE
    if len(data) != expected:
        raise CodecError(f"length mismatch: expected {expected}, got {len(data)}")
    try:
        packet_type = PacketType(ptype)
    except ValueError as exc:
        raise CodecError(f"unknown packet type {ptype}") from exc

    payload = data[HEADER_SIZE : HEADER_SIZE + payload_len]
    signature = data[HEADER_SIZE + payload_len :]
    packet = Packet(
        type=packet_type,
        msg_id=msg_id,
        timestamp=timestamp,
        sender=sender,
        payload=payload,
        ttl=ttl,
        flags=Flags(flags),
        version=version,
        signature=signature,
        raw=data,
    )
    if verify_signature and not verify(packet):
        raise CodecError("invalid signature")
    return packet


def verify(packet: Packet, public_key: bytes | None = None) -> bool:
    """Verify the Ed25519 signature with TTL excluded from the signed region."""
    key = public_key or packet.sender
    signed = _signed_region(
        version=packet.version,
        ptype=int(packet.type),
        flags=int(packet.flags),
        msg_id=packet.msg_id,
        timestamp=packet.timestamp,
        sender=packet.sender,
        payload=packet.payload,
    )
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(packet.signature, signed)
        return True
    except (InvalidSignature, ValueError):
        return False


def decrement_ttl(data: bytes) -> bytes:
    """Relay operation: reduce TTL by one. Signature remains valid."""
    if len(data) < HEADER_SIZE:
        raise CodecError("packet too short")
    ttl = data[3]
    if ttl == 0:
        return data
    return data[:3] + bytes([ttl - 1]) + data[4:]


def new_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    key = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return key, public


# ---------------------------------------------------------------------------
# Application payloads
# ---------------------------------------------------------------------------

CATEGORIES = {
    "medical",
    "trapped",
    "fire",
    "flood",
    "food_water",
    "shelter",
    "missing",
    "road_blocked",
    "other",
}


def sos_payload(
    *,
    category: str,
    lat: float,
    lon: float,
    text: str = "",
    people: int | None = None,
) -> bytes:
    """Build a compact SOS payload, truncating free text to fit 86 bytes."""
    if category not in CATEGORIES:
        raise CodecError(f"unknown category {category!r}")
    data: dict[str, Any] = {
        "c": category,
        "lat": round(float(lat), 5),
        "lon": round(float(lon), 5),
    }
    if people is not None:
        data["n"] = int(people)
    encoded = cbor2.dumps({**data, "t": text} if text else data, canonical=True)
    if len(encoded) > MAX_PAYLOAD_SIZE and text:
        # Trim until it fits; the station can still triage category + location.
        while text and len(encoded) > MAX_PAYLOAD_SIZE:
            text = text[:-1]
            encoded = cbor2.dumps({**data, "t": text} if text else data, canonical=True)
    if len(encoded) > MAX_PAYLOAD_SIZE:
        raise PayloadTooLarge("SOS payload does not fit the compact budget")
    return encoded


def make_sos(
    private_key: Ed25519PrivateKey,
    sender: bytes,
    *,
    category: str,
    lat: float,
    lon: float,
    text: str = "",
    people: int | None = None,
    ttl: int = MAX_TTL,
    timestamp: int | None = None,
    msg_id: bytes | None = None,
) -> tuple[Packet, bytes]:
    """Create and sign an SOS packet. Returns (packet, wire_bytes)."""
    packet = Packet(
        type=PacketType.SOS,
        msg_id=msg_id or new_message_id(sender),
        timestamp=int(timestamp if timestamp is not None else time.time()),
        sender=sender,
        payload=sos_payload(category=category, lat=lat, lon=lon, text=text, people=people),
        ttl=ttl,
        flags=Flags.PRIORITY,
    )
    return packet, encode(packet, private_key)


# ---------------------------------------------------------------------------
# Fragmentation (large payloads over LoRa/BLE MTU)
# ---------------------------------------------------------------------------


def fragment_payload(payload: bytes, max_fragment_bytes: int) -> list[bytes]:
    """Split a payload into chunks prefixed with ``frag_idx, frag_total``."""
    if max_fragment_bytes < 3:
        raise CodecError("max_fragment_bytes must be >= 3")
    chunk_size = max_fragment_bytes - 2
    chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)] or [
        b""
    ]
    if len(chunks) > 255:
        raise CodecError("payload needs more than 255 fragments")
    return [bytes([index, len(chunks)]) + chunk for index, chunk in enumerate(chunks)]


def reassemble_payload(fragments: list[Packet]) -> bytes:
    """Reassemble fragmented packets that share a msg_id."""
    if not fragments:
        raise CodecError("no fragments")
    msg_id = fragments[0].msg_id
    if any(f.msg_id != msg_id for f in fragments):
        raise CodecError("fragments belong to different messages")
    ordered: dict[int, bytes] = {}
    total = None
    for fragment in fragments:
        if len(fragment.payload) < 2:
            raise CodecError("fragment payload too short")
        index, count = fragment.payload[0], fragment.payload[1]
        if count == 0 or index >= count:
            raise CodecError("invalid fragment index")
        if total is None:
            total = count
        elif total != count:
            raise CodecError("inconsistent fragment count")
        ordered[index] = fragment.payload[2:]
    if total != len(ordered) or sorted(ordered) != list(range(total)):
        raise CodecError("incomplete fragments")
    return b"".join(ordered[i] for i in range(total))

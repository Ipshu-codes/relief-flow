# Android Bluetooth SOS relay

The Android build includes an opt-in Bluetooth Low Energy store-and-forward path
for SOS messages. It is an additional delivery path; the normal online HTTP
submission and browser offline outbox remain available.

## Build

From the repository root:

```powershell
.\start.ps1 -Build
Set-Location frontend
flutter build apk --debug
```

The app requests the Android Bluetooth permissions required for scanning,
connecting, advertising, and notifications. The user must grant those
permissions and explicitly enable relay mode in the Mesh screen.

## Transport and safety

- Messages use the signed `rahat-ble-v1:` envelope.
- Structured addresses are carried in the signed payload.
- Payloads are framed with a four-byte length prefix and split into 20-byte
  ATT chunks.
- Packets have a bounded size, expiry, TTL/hop limits, and duplicate
  suppression by SOS UUID.
- Relay queues are persisted and bounded.
- The original SOS outbox is retained until a canonical backend receipt is
  confirmed.
- A Bluetooth handoff is not a command-station receipt.
- A signed sender identity is not a trusted or authenticated person identity.
- Relay mode requires the app to remain open; no Android foreground service or
  background isolate is implemented.

Do not include sensitive personal information beyond what is necessary for
coordination. The backend still validates the packet and applies normal SOS
deduplication and authorization rules.

## Two-phone acceptance test

1. Install the debug APK on two physical Android phones.
2. Grant Bluetooth and location permissions when Android requests them.
3. Connect both phones to the same development backend when possible.
4. On both phones, open the Mesh screen and enable relay mode with consent.
5. On phone A, disable network access, enter a structured written location,
   and submit an SOS.
6. Confirm phone A shows a queued SOS and a mesh handoff attempt, not a server
   receipt.
7. Bring phone B nearby and confirm it reports the packet handoff and queue.
8. Restore network access on phone B and confirm the command station receives
   one SOS containing the full structured address.
9. Restart or reconnect one phone and verify the same UUID is not inserted a
   second time.
10. Repeat with an interrupted transfer and confirm the packet remains queued
    until it expires or is delivered.

Physical two-phone testing is not available in this development environment.
The software tests cover packet signing, framing, reassembly, persistence,
deduplication, and backend validation, but they do not prove radio behavior on
all Android devices.

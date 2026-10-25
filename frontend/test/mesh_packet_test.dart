import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rahat_mobile/mesh_packet.dart';

void main() {
  final sos = {
    'client_uuid': '11111111-1111-4111-8111-111111111111',
    'category': 'TRAPPED',
    'message': 'TEST',
    'address': {'district': 'Kathmandu', 'landmark': 'school'},
  };

  test('signed envelope matches the Python receiver fixture', () async {
    final key = await Ed25519().newKeyPairFromSeed(List.generate(32, (i) => i));
    final packet = await MeshPacket.sign(sos, key);
    expect(packet.envelope['public_key'],
        'A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=');
    expect(packet.envelope['signature'],
        'SDouWpHI14F9RBYPHKegqPryhNp6DR7J4rCWfMbM9G3L6rFMN3jBb+oJD5zZzPzJ0kNLIPWoETpjdAW/Kz5cDg==');
    expect((await MeshPacket.decode(packet.bytes)).sos, sos);
    expect(packet.forwarded().hops, meshHopLimit - 1);
  });

  test('changed SOS and invalid hop counts are rejected', () async {
    final packet = await MeshPacket.sign(sos, await Ed25519().newKeyPair());
    for (final envelope in [
      {
        ...packet.envelope,
        'payload': base64Encode(
            utf8.encode(jsonEncode({...sos, 'message': 'altered'})))
      },
      {...packet.envelope, 'ttl': -1},
      {...packet.envelope, 'ttl': meshHopLimit + 1},
    ]) {
      await expectLater(
          MeshPacket.decode(
              Uint8List.fromList(utf8.encode(jsonEncode(envelope)))),
          throwsFormatException);
    }
  });

  test('full address packets survive every BLE chunk size without truncation',
      () async {
    final packet = await MeshPacket.sign({
      ...sos,
      'message': List.filled(50, 'मद्दत ').join(),
      'address': {
        'district': 'Kathmandu',
        'city': 'Kathmandu',
        'ward': '4',
        'road': 'TEST road',
        'landmark': 'TEST school east gate',
      },
    }, await Ed25519().newKeyPair());
    expect(packet.bytes.length, greaterThan(200));
    for (var chunkSize = 1; chunkSize <= 20; chunkSize++) {
      final framed = BleFrameDecoder.frame(packet.bytes);
      final decoder = BleFrameDecoder();
      final result = <Uint8List>[];
      for (var i = 0; i < framed.length; i += chunkSize) {
        result.addAll(decoder
            .add(framed.sublist(i, (i + chunkSize).clamp(0, framed.length))));
      }
      expect(result, hasLength(1));
      final decoded = await MeshPacket.decode(result.single);
      expect(decoded.sos['address'], packet.sos['address']);
      expect(decoded.sos['message'], packet.sos['message']);
    }
  });

  test('frame decoder handles adjacent messages and rejects oversized input',
      () {
    final first = Uint8List.fromList(utf8.encode('first'));
    final second = Uint8List.fromList(utf8.encode('second'));
    final messages = BleFrameDecoder().add([
      ...BleFrameDecoder.frame(first),
      ...BleFrameDecoder.frame(second),
    ]);
    expect(messages, [first, second]);
    expect(() => BleFrameDecoder().add([255, 255, 255, 255]),
        throwsFormatException);
    expect(() => BleFrameDecoder.frame(Uint8List(meshPacketLimit + 1)),
        throwsFormatException);
  });
}

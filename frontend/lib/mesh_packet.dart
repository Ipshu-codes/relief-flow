import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

const meshPacketLimit = 16384;
const meshHopLimit = 6;
const _signaturePrefix = 'rahat-ble-v1:';

class MeshPacket {
  final Map<String, dynamic> envelope;
  final Map<String, dynamic> sos;
  MeshPacket._(this.envelope, this.sos);

  String get id => sos['client_uuid'] as String;
  int get hops => envelope['ttl'] as int;
  Uint8List get bytes => Uint8List.fromList(utf8.encode(jsonEncode(envelope)));

  MeshPacket forwarded() => MeshPacket._({...envelope, 'ttl': hops - 1}, sos);

  static Future<MeshPacket> sign(
      Map<String, dynamic> item, SimpleKeyPair key) async {
    final sos = Map<String, dynamic>.fromEntries(
        item.entries.where((entry) => !entry.key.startsWith('_')));
    final payload = utf8.encode(jsonEncode(sos));
    final signature = await Ed25519()
        .sign([...utf8.encode(_signaturePrefix), ...payload], keyPair: key);
    final public = await key.extractPublicKey();
    final packet = {
      'v': 1,
      'ttl': meshHopLimit,
      'payload': base64Encode(payload),
      'public_key': base64Encode(public.bytes),
      'signature': base64Encode(signature.bytes),
    };
    return decode(Uint8List.fromList(utf8.encode(jsonEncode(packet))));
  }

  static Future<MeshPacket> decode(Uint8List bytes) async {
    if (bytes.length > meshPacketLimit) {
      throw const FormatException('Mesh SOS exceeds the packet limit');
    }
    final value = jsonDecode(utf8.decode(bytes));
    if (value is! Map<String, dynamic> ||
        value['v'] != 1 ||
        value['ttl'] is! int ||
        value['ttl'] < 0 ||
        value['ttl'] > meshHopLimit ||
        value['payload'] is! String ||
        value['public_key'] is! String ||
        value['signature'] is! String) {
      throw const FormatException('Invalid mesh envelope');
    }
    final payload = base64Decode(value['payload'] as String);
    final public = base64Decode(value['public_key'] as String);
    final signature = base64Decode(value['signature'] as String);
    if (public.length != 32 ||
        signature.length != 64 ||
        !await Ed25519().verify([...utf8.encode(_signaturePrefix), ...payload],
            signature: Signature(signature,
                publicKey:
                    SimplePublicKey(public, type: KeyPairType.ed25519)))) {
      throw const FormatException('Mesh signature verification failed');
    }
    final body = jsonDecode(utf8.decode(payload));
    if (body is! Map<String, dynamic> ||
        body['client_uuid'] is! String ||
        !RegExp(r'^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$')
            .hasMatch(body['client_uuid'] as String) ||
        body['message'] is! String ||
        (body['message'] as String).isEmpty ||
        (body['message'] as String).length > 500 ||
        !const ['FOOD', 'MEDICINE', 'TRAPPED', 'RESCUE', 'OTHER']
            .contains(body['category'])) {
      throw const FormatException('Invalid SOS in mesh packet');
    }
    return MeshPacket._(value, body);
  }
}

class BleFrameDecoder {
  final List<int> _buffer = [];

  List<Uint8List> add(List<int> chunk) {
    _buffer.addAll(chunk);
    final messages = <Uint8List>[];
    while (_buffer.length >= 4) {
      final length =
          ByteData.sublistView(Uint8List.fromList(_buffer.sublist(0, 4)))
              .getUint32(0);
      if (length == 0 || length > meshPacketLimit) {
        _buffer.clear();
        throw const FormatException('Invalid BLE frame length; reconnect peer');
      }
      if (_buffer.length < length + 4) break;
      messages.add(Uint8List.fromList(_buffer.sublist(4, length + 4)));
      _buffer.removeRange(0, length + 4);
    }
    if (_buffer.length > meshPacketLimit + 4) {
      _buffer.clear();
      throw const FormatException('BLE frame buffer exceeded its limit');
    }
    return messages;
  }

  static Uint8List frame(Uint8List bytes) {
    if (bytes.isEmpty || bytes.length > meshPacketLimit) {
      throw const FormatException('Invalid BLE message size');
    }
    final header = ByteData(4)..setUint32(0, bytes.length);
    return Uint8List.fromList([...header.buffer.asUint8List(), ...bytes]);
  }
}

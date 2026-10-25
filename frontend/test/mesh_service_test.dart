import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rahat_mobile/api.dart';
import 'package:rahat_mobile/ble_service.dart';
import 'package:rahat_mobile/mesh_packet.dart';
import 'package:rahat_mobile/mesh_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeBle extends BleService {
  final incoming = StreamController<Uint8List>.broadcast(sync: true);
  final sent = <Uint8List>[];
  @override
  bool get supported => true;
  @override
  int get peerCount => 1;
  @override
  Stream<Uint8List> get packets => incoming.stream;
  @override
  Future<void> start() async {}
  @override
  Future<void> stop() async {}
  @override
  Future<int> send(Uint8List packet) async {
    sent.add(packet);
    return 1;
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Map<String, dynamic> sos() => {
        'client_uuid': '11111111-1111-4111-8111-111111111111',
        'category': 'TRAPPED',
        'message': 'TEST help',
        'address': {'district': 'Kathmandu', 'landmark': 'TEST school'},
        '_ui_category': 'trapped',
      };

  test('own SOS handoff keeps original outbox until direct server confirmation',
      () async {
    SharedPreferences.setMockInitialValues({
      'sosOutbox': jsonEncode([sos()])
    });
    final radio = FakeBle();
    var online = false;
    final service = MeshService(radio, backend: 'http://station',
        client: MockClient((request) async {
      expect(request.url.path, '/api/v1/ingest/ble');
      final packet =
          await MeshPacket.decode(Uint8List.fromList(request.bodyBytes));
      expect(packet.sos['address'], sos()['address']);
      expect(packet.sos.containsKey('_ui_category'), isFalse);
      if (!online) throw http.ClientException('offline');
      return http.Response(
          jsonEncode({
            'client_uuid': packet.id,
            'transmission_status': 'received',
          }),
          200);
    }));
    await service.start();
    await service.pump();
    expect(service.queued, 1);
    expect(radio.sent, isNotEmpty);
    expect((await SOSClient('http://station').pending()).single['address'],
        sos()['address']);
    expect(
        (await SharedPreferences.getInstance()).getInt('activeSosId'), isNull);
    online = true;
    await service.pump();
    expect(service.queued, 0);
    expect(service.delivered, 1);
    expect(await SOSClient('http://station').pending(), hasLength(1));
    await service.stop();
    service.dispose();
    await radio.incoming.close();
  });

  test(
      'relayed packet survives restart, deduplicates and decrements hop budget',
      () async {
    final packet = await MeshPacket.sign(sos(), await Ed25519().newKeyPair());
    final radio = FakeBle();
    http.Client offline() =>
        MockClient((_) async => throw http.ClientException('offline'));
    final first = MeshService(radio, client: offline());
    await first.start();
    await first.pump();
    radio.incoming.add(packet.bytes);
    await first.pump();
    radio.incoming.add(packet.bytes);
    await first.pump();
    expect(first.queued, 1);
    expect((await MeshPacket.decode(radio.sent.last)).hops, meshHopLimit - 1);
    await first.stop();
    first.dispose();
    final restored = MeshService(radio, client: offline());
    await restored.start();
    await restored.pump();
    expect(restored.queued, 1);
    expect((await MeshPacket.decode(radio.sent.last)).sos['address'],
        sos()['address']);
    await restored.stop();
    restored.dispose();
    await radio.incoming.close();
  });

  test('corrupt relay storage is preserved with an explicit error', () async {
    SharedPreferences.setMockInitialValues({'meshStateV1': 'corrupt'});
    final radio = FakeBle();
    final service = MeshService(radio);
    await service.start();
    expect(service.running, isFalse);
    expect(service.error, contains('Could not start'));
    expect((await SharedPreferences.getInstance()).getString('meshStateV1'),
        'corrupt');
    service.dispose();
    await radio.incoming.close();
  });
}

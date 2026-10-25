import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rahat_mobile/api.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('SOS persists first and requires matching server receipt', () async {
    final client =
        SOSClient('http://station', client: MockClient((request) async {
      expect(request.url.path, '/sos');
      final body = jsonDecode(request.body);
      expect(body['category'], 'MEDICINE');
      expect(body['lat'], isNull);
      final prefs = await SharedPreferences.getInstance();
      expect(jsonDecode(prefs.getString('sosOutbox')!), hasLength(1));
      return http.Response(
          jsonEncode({
            'id': 1,
            'client_uuid': body['client_uuid'],
            'status': 'new',
            'receipt_token': 'test-receipt',
          }),
          201);
    }));
    final receipt =
        await client.submit(category: 'MEDICINE', message: 'Need help');
    expect(receipt['id'], 1);
    expect(await client.pending(), isEmpty);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('activeSosReceiptToken'), 'test-receipt');
    client.close();
  });

  test('Network failure and retry reuse persisted UUID across clients',
      () async {
    String? uuid;
    final first =
        SOSClient('http://station', client: MockClient((request) async {
      uuid = jsonDecode(request.body)['client_uuid'];
      throw http.ClientException('offline');
    }));
    await expectLater(
        first.submit(category: 'TRAPPED', message: 'Help'), throwsException);
    final item = (await first.pending()).single;
    first.close();
    final retry =
        SOSClient('http://station', client: MockClient((request) async {
      final body = jsonDecode(request.body);
      expect(body['client_uuid'], uuid);
      return http.Response(
          jsonEncode({
            'id': 2,
            'client_uuid': uuid,
            'status': 'new',
            'receipt_token': 'receipt',
          }),
          200);
    }));
    await retry.submit(category: 'TRAPPED', message: 'Help', pendingItem: item);
    expect(await retry.pending(), isEmpty);
    retry.close();
  });

  for (final status in [400, 422, 500]) {
    test('HTTP $status never becomes receipt', () async {
      final client = SOSClient('http://station',
          client: MockClient(
              (_) async => http.Response('{"detail":"rejected"}', status)));
      await expectLater(client.submit(category: 'MEDICINE', message: 'Help'),
          throwsException);
      expect(await client.pending(), hasLength(1));
      expect((await SharedPreferences.getInstance()).getInt('activeSosId'),
          isNull);
      client.close();
    });
  }

  for (final body in ['[]', 'not json', '{"id":1,"status":"new"}']) {
    test('Malformed receipt is not success: $body', () async {
      final client = SOSClient('http://station',
          client: MockClient((_) async => http.Response(body, 200)));
      await expectLater(
          client.submit(category: 'OTHER', message: 'Help'), throwsException);
      expect(await client.pending(), hasLength(1));
      client.close();
    });
  }

  test('Public status request uses opaque receipt', () async {
    final client =
        SOSClient('http://station', client: MockClient((request) async {
      expect(request.url.path, '/sos/7/status');
      expect(request.url.queryParameters['receipt_token'], 'receipt');
      return http.Response('{"id":7,"status":"acknowledged"}', 200);
    }));
    expect((await client.status(id: 7, receiptToken: 'receipt'))['status'],
        'acknowledged');
    client.close();
  });

  for (final saved in ['not json', '{}', '[1]', '[{"category":"FOOD"}]']) {
    test('Corrupt outbox is preserved and reported: $saved', () async {
      SharedPreferences.setMockInitialValues({'sosOutbox': saved});
      final client = SOSClient('http://station');
      await expectLater(client.pending(), throwsException);
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getString('sosOutbox'), saved);
      client.close();
    });
  }

  test('New queued SOS cannot reuse an older server receipt', () async {
    SharedPreferences.setMockInitialValues({
      'activeSosId': 42,
      'activeSosReceiptToken': 'previous',
      'activeSosStatus': 'resolved',
    });
    final client = SOSClient('http://station',
        client: MockClient((_) async => throw http.ClientException('offline')));
    await expectLater(
        client.submit(category: 'OTHER', message: 'A new request'),
        throwsException);
    final preferences = await SharedPreferences.getInstance();
    expect(preferences.getInt('activeSosId'), isNull);
    expect(preferences.getString('activeSosReceiptToken'), isNull);
    expect(preferences.getString('activeSosStatus'), 'queued');
    expect(await client.pending(), hasLength(1));
    client.close();
  });

  test('offline address and later GPS reuse the same queued request', () async {
    final address = {
      'district': 'Kathmandu',
      'city': 'Kathmandu',
      'ward': '4',
      'road': 'TEST road',
      'landmark': 'TEST school',
    };
    var online = false;
    String? originalUuid;
    final client =
        SOSClient('http://station', client: MockClient((request) async {
      final body = jsonDecode(request.body);
      expect(body['address'], address);
      originalUuid ??= body['client_uuid'];
      expect(body['client_uuid'], originalUuid);
      if (!online) throw http.ClientException('offline');
      expect(body['lat'], 27.71);
      expect(body['lon'], 85.32);
      expect(body.containsKey('_share_gps'), isFalse);
      return http.Response(
          jsonEncode({
            'id': 4,
            'client_uuid': originalUuid,
            'status': 'new',
            'receipt_token': 'receipt',
            'has_location': true,
          }),
          201);
    }));
    await expectLater(
        client.submit(category: 'TRAPPED', message: 'Help', address: address),
        throwsException);
    final saved = (await client.pending()).single;
    expect(saved['address'], address);
    expect(saved['lat'], isNull);
    online = true;
    await client.submit(
        category: 'TRAPPED',
        message: 'Help',
        pendingItem: saved,
        lat: 27.71,
        lon: 85.32);
    expect(await client.pending(), isEmpty);
    expect(await client.needsGps(), isFalse);
    client.close();
  });

  test('GPS enrichment uses receipt and clears flag only on confirmation',
      () async {
    SharedPreferences.setMockInitialValues({
      'activeSosId': 7,
      'activeSosReceiptToken': 'receipt',
      'activeSosNeedsGps': true,
    });
    var succeeds = false;
    final client =
        SOSClient('http://station', client: MockClient((request) async {
      expect(request.method, 'PATCH');
      expect(request.url.path, '/sos/7/location');
      expect(request.url.queryParameters['receipt_token'], 'receipt');
      expect(jsonDecode(request.body)['location_accuracy_m'], 10);
      return succeeds
          ? http.Response('{"id":7,"has_location":true}', 200)
          : http.Response('{"detail":"Unavailable"}', 503);
    }));
    Future<void> update() => client.updateLocation(
        id: 7,
        receiptToken: 'receipt',
        latitude: 27.71,
        longitude: 85.32,
        accuracyM: 10);
    await expectLater(update(), throwsException);
    expect(await client.needsGps(), isTrue);
    succeeds = true;
    await update();
    expect(await client.needsGps(), isFalse);
    client.close();
  });
}

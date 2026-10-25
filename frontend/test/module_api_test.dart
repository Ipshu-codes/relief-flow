import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rahat_mobile/module_api.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('random localhost debug ports connect to the backend, not the preview',
      () {
    for (final host in ['localhost', '127.0.0.1', '[::1]']) {
      for (final port in [3000, 55057, 8000]) {
        expect(
            resolveBackendUrl(
                page: Uri.parse('http://$host:$port/'), development: true),
            'http://$host:8000');
      }
    }
  });

  test('release web builds use their serving origin including custom ports',
      () {
    for (final origin in [
      'https://relief.example.org',
      'http://localhost:9000',
      'http://127.0.0.1:8000',
      'https://relief.example.org:8443'
    ]) {
      expect(resolveBackendUrl(page: Uri.parse('$origin/#/volunteer')), origin);
    }
  });

  test('LAN debug deployments use the backend on the same machine', () {
    expect(
        resolveBackendUrl(
            page: Uri.parse('http://192.168.1.25:52394/'), development: true),
        'http://192.168.1.25:8000');
    expect(
        resolveBackendUrl(
            page: Uri.parse('https://relief.example.org/'), development: true),
        'https://relief.example.org');
  });

  test('explicit deployment configuration takes priority on web and native',
      () {
    for (final page in [null, Uri.parse('http://localhost:55057/')]) {
      expect(
          resolveBackendUrl(
              configured: 'https://api.example.org',
              page: page,
              development: true),
          'https://api.example.org');
    }
    expect(resolveBackendUrl(), 'http://127.0.0.1:8000');
  });

  test('old saved addresses cannot override deployment or split services',
      () async {
    SharedPreferences.setMockInitialValues({
      'backendBaseUrl': 'http://localhost:55057',
      'moduleApiUrl': 'http://127.0.0.1:8002',
      'stationUrl': 'https://old.example.org',
      'activeSosId': 12,
      'activeSosReceiptToken': 'preserved-receipt',
    });
    expect(await BackendAddress.load(), defaultBackendUrl);
    final preferences = await SharedPreferences.getInstance();
    for (final key in ['backendBaseUrl', 'moduleApiUrl', 'stationUrl']) {
      expect(preferences.containsKey(key), isFalse);
    }
    expect(preferences.getInt('activeSosId'), 12);
    expect(preferences.getString('activeSosReceiptToken'), 'preserved-receipt');
  });

  test('login sends bearer token only after authentication', () async {
    final api = ModuleApi(client: MockClient((request) async {
      if (request.url.path == '/auth/login') {
        expect(request.headers['Authorization'], isNull);
        return http.Response('{"access_token":"test-token"}', 200);
      }
      expect(request.headers['Authorization'], 'Bearer test-token');
      return http.Response('{"id":1,"role":"coordinator"}', 200);
    }));
    final user = await api.login('coordinator@example.org', 'password');
    expect(user['role'], 'coordinator');
    api.close();
  });

  test('failed allocation keeps the same retry UUID', () async {
    final ids = <String>[];
    final api = ModuleApi(client: MockClient((request) async {
      ids.add(jsonDecode(request.body)['client_uuid'] as String);
      return ids.length == 1
          ? http.Response('{"detail":"Temporary failure"}', 503)
          : http.Response('{"id":7}', 201);
    }));
    final body = {'need_id': 1, 'stock_id': 2, 'quantity': 40};
    await expectLater(
        api.request('/allocations',
            method: 'POST', body: body, retrySafe: true),
        throwsA(isA<ModuleApiException>()));
    await api.request('/allocations',
        method: 'POST', body: body, retrySafe: true);
    expect(ids[0], ids[1]);
    expect(body.containsKey('client_uuid'), isFalse);
    api.close();
  });

  test('validation errors remain visible to the user', () async {
    final api = ModuleApi(
        client: MockClient((_) async => http.Response(
            '{"detail":[{"msg":"Quantity must be positive"}]}', 422)));
    await expectLater(
        api.request('/allocations'),
        throwsA(isA<ModuleApiException>().having((error) => error.message,
            'message', contains('Quantity must be positive'))));
    api.close();
  });
}

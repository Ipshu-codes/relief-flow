import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:rahat_mobile/api.dart';
import 'package:rahat_mobile/app_state.dart';
import 'package:rahat_mobile/screens/sos.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('Unknown location stays unknown and saved receipt is truthful',
      (tester) async {
    final state = AppState();
    final client =
        SOSClient('http://station', client: MockClient((request) async {
      final body = jsonDecode(request.body);
      expect(body['lat'], isNull);
      expect(body['lon'], isNull);
      expect(body['category'], 'MEDICINE');
      return http.Response(
          jsonEncode({
            'id': 8,
            'client_uuid': body['client_uuid'],
            'status': 'new',
            'receipt_token': 'receipt',
          }),
          201);
    }));
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state,
        child: MaterialApp(
            home: SOSScreen(client: client, locate: () async => null))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Medical'));
    await tester.pump();
    await tester.ensureVisible(find.text('Send SOS'));
    await tester.tap(find.text('Send SOS'));
    await tester.pumpAndSettle();
    expect(state.status, 'new');
    expect(state.incidentId, 8);
    expect(find.textContaining('sent to service station'), findsWidgets);
  });

  testWidgets('Failed SOS stays queued, never received', (tester) async {
    final state = AppState();
    final client = SOSClient('http://station',
        client: MockClient(
            (_) async => http.Response('{"detail":"Unavailable"}', 503)));
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state,
        child: MaterialApp(
            home: SOSScreen(client: client, locate: () async => null))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Medical'));
    await tester.pump();
    await tester.ensureVisible(find.text('Send SOS'));
    await tester.tap(find.text('Send SOS'));
    await tester.pumpAndSettle();
    expect(state.status, 'queued');
    expect(state.incidentId, isNull);
    expect(find.text('Retry saved SOS'), findsOneWidget);
    expect(find.text('Received by server'), findsNothing);
  });

  testWidgets('written location is saved offline and GPS joins on auto retry',
      (tester) async {
    final state = AppState();
    var online = false;
    var gpsAvailable = false;
    String? uuid;
    final client =
        SOSClient('http://station', client: MockClient((request) async {
      final body = jsonDecode(request.body);
      expect(body['address']['district'], 'Kathmandu');
      expect(body['address']['landmark'], 'TEST school gate');
      uuid ??= body['client_uuid'];
      expect(body['client_uuid'], uuid);
      if (!online) throw http.ClientException('offline');
      expect(body['lat'], 27.71);
      expect(body['lon'], 85.32);
      return http.Response(
          jsonEncode({
            'id': 11,
            'client_uuid': uuid,
            'status': 'new',
            'receipt_token': 'receipt',
            'has_location': true,
          }),
          201);
    }));
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state,
        child: MaterialApp(
            home: SOSScreen(
                client: client,
                locate: () async => gpsAvailable
                    ? (latitude: 27.71, longitude: 85.32)
                    : null))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Medical'));
    await tester.scrollUntilVisible(
        find.byKey(const ValueKey('address_district')), 250,
        scrollable: find.byType(Scrollable).first);
    await tester.enterText(
        find.byKey(const ValueKey('address_district')), 'Kathmandu');
    await tester.scrollUntilVisible(
        find.byKey(const ValueKey('address_landmark')), 200,
        scrollable: find.byType(Scrollable).first);
    await tester.enterText(
        find.byKey(const ValueKey('address_landmark')), 'TEST school gate');
    await tester.tap(find.text('Send SOS'));
    await tester.pumpAndSettle();
    expect(state.status, 'queued');
    final saved = (await client.pending()).single;
    expect(saved['address']['landmark'], 'TEST school gate');
    online = true;
    gpsAvailable = true;
    await tester.pump(const Duration(seconds: 20));
    await tester.pumpAndSettle();
    expect(state.incidentId, 11);
    expect(await client.pending(), isEmpty);
    expect(find.text('Emergency calls'), findsOneWidget);
  });
}

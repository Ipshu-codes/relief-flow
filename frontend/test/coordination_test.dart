import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rahat_mobile/module_api.dart';
import 'package:rahat_mobile/screens/coordination.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  ModuleApi clientFor(String role,
          {String? baseUrl, void Function(http.Request)? onRequest}) =>
      ModuleApi(
          baseUrl: baseUrl,
          client: MockClient((request) async {
            onRequest?.call(request);
            dynamic result;
            switch (request.url.path) {
              case '/auth/login':
                result = {'access_token': 'test-token'};
              case '/auth/me':
                result = {'id': 1, 'full_name': 'Test User', 'role': role};
              case '/auth/me/profile':
                result = {
                  'phone_number': null,
                  'address': {},
                  'latitude': null,
                  'longitude': null,
                  'location_accuracy_m': null,
                  'emergency_contacts': [],
                  'profile_notes': null,
                };
              case '/workspace':
                result = {
                  'incidents': [
                    {'id': 1, 'name': 'Training Incident'}
                  ],
                  'locations': [
                    {'id': 1, 'name': 'Health Post'}
                  ],
                  'organizations': [],
                  'resources': []
                };
              case '/needs':
                result = {
                  'items': [
                    {
                      'id': 1,
                      'category': 'water',
                      'location_id': 1,
                      'description': 'Drinking water',
                      'status': 'partially_fulfilled',
                      'verification_status': 'verified',
                      'confidence': 'high',
                      'urgency': 4,
                      'quantity_requested': 100,
                      'quantity_fulfilled': 40,
                      'unit': 'litre',
                      'required_skills': []
                    }
                  ]
                };
              case '/ai/proposals':
                result = {'items': []};
              case '/situation':
                result = {
                  'counts': {'needs': 1}
                };
              default:
                result = [];
            }
            return http.Response(jsonEncode(result), 200,
                headers: {'content-type': 'application/json'});
          }));

  Future<void> signIn(WidgetTester tester, String role) async {
    await tester.pumpWidget(MaterialApp(
        theme: ThemeData.dark(),
        home: CoordinationScreen(api: clientFor(role))));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).at(0), 'user@example.org');
    await tester.enterText(find.byType(TextField).at(1), 'password');
    await tester.ensureVisible(find.text('Sign In'));
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();
  }

  testWidgets('coordinator sees server needs and module actions',
      (tester) async {
    await signIn(tester, 'coordinator');
    expect(find.text('Intelligence'), findsOneWidget);
    expect(find.text('Drafts'), findsOneWidget);
    expect(find.textContaining('40 / 100 litre confirmed'), findsOneWidget);
    expect(find.text('Review'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('community cannot see coordinator approval controls',
      (tester) async {
    await signIn(tester, 'community_member');
    expect(find.text('Intelligence'), findsNothing);
    expect(find.text('Review'), findsNothing);
    expect(find.text('Match Volunteers'), findsNothing);
    expect(find.textContaining('40 / 100 litre confirmed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('registration needs no address and uses the configured service',
      (tester) async {
    SharedPreferences.setMockInitialValues({
      'backendBaseUrl': 'http://localhost:55057',
    });
    final requests = <http.Request>[];
    await tester.pumpWidget(MaterialApp(
        theme: ThemeData.dark(),
        home: CoordinationScreen(
            api: clientFor('community_member',
                baseUrl: 'https://relief.example.org',
                onRequest: requests.add))));
    await tester.pumpAndSettle();
    expect(find.text('Backend API address'), findsNothing);
    expect(find.byType(TextField), findsNWidgets(2));
    await tester.tap(find.text('Create community account'));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNWidgets(3));
    await tester.enterText(find.byType(TextField).at(0), 'New Volunteer');
    await tester.enterText(
        find.byType(TextField).at(1), 'volunteer@example.org');
    await tester.enterText(find.byType(TextField).at(2), 'secure-password');
    await tester.ensureVisible(find.text('Create Account'));
    await tester.tap(find.text('Create Account'));
    await tester.pumpAndSettle();
    final registration =
        requests.singleWhere((request) => request.url.path == '/auth/register');
    expect(registration.method, 'POST');
    expect(jsonDecode(registration.body), {
      'full_name': 'New Volunteer',
      'email': 'volunteer@example.org',
      'password': 'secure-password',
    });
    expect(
        requests.every(
            (request) => request.url.origin == 'https://relief.example.org'),
        isTrue);
    expect(find.text('Assignments'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

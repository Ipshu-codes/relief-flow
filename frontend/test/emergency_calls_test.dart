import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rahat_mobile/widgets/emergency_calls.dart';

void main() {
  testWidgets('each emergency button opens the matching tel URI',
      (tester) async {
    final calls = <Uri>[];
    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: EmergencyCalls(launch: (uri) async {
      calls.add(uri);
      return true;
    }))));
    for (final contact in EmergencyCalls.contacts) {
      await tester.tap(find.text('${contact.name} · ${contact.number}'));
      await tester.pump();
      expect(calls.last, Uri(scheme: 'tel', path: contact.number));
    }
    expect(calls, hasLength(4));
  });

  for (final throwsError in [false, true]) {
    testWidgets('missing dialer is reported (exception=$throwsError)',
        (tester) async {
      await tester.pumpWidget(
          MaterialApp(home: Scaffold(body: EmergencyCalls(launch: (_) async {
        if (throwsError) throw Exception('No dialer');
        return false;
      }))));
      await tester.tap(find.text('Police · 100'));
      await tester.pump();
      expect(find.text('Could not open a calling app. Dial 100 on a phone.'),
          findsOneWidget);
    });
  }
}

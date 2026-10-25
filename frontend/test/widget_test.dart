import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rahat_mobile/main.dart';
import 'package:provider/provider.dart';
import 'package:rahat_mobile/app_state.dart';
import 'package:rahat_mobile/screens/settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('Rahat app smokes', (WidgetTester tester) async {
    await tester.pumpWidget(const RahatApp());
    expect(find.byType(MaterialApp), findsOneWidget);
  });

  testWidgets('settings does not ask users to configure a server',
      (tester) async {
    await tester.pumpWidget(ChangeNotifierProvider(
        create: (_) => AppState(),
        child: const MaterialApp(home: SettingsScreen())));
    await tester.pumpAndSettle();
    expect(find.text('Automatic connection'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Backend URL'), findsNothing);
    expect(find.text('Save address'), findsNothing);
  });
}

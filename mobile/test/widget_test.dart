import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';

void main() {
  testWidgets('RAHAT app launches', (WidgetTester tester) async {
    await tester.pumpWidget(const RahatApp());

    expect(find.text('RAHAT'), findsOneWidget);
    expect(find.text('Request Help'), findsOneWidget);
  });
}
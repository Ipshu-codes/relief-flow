import 'package:flutter_test/flutter_test.dart';
import 'package:rahat_station/main.dart';

void main() {
  testWidgets('Service Station shell loads', (tester) async {
    await tester.pumpWidget(const ServiceStationApp());
    expect(find.text('Service Station'), findsNWidgets(2));
  });
}

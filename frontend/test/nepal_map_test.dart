import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_test/flutter_test.dart';
import 'package:rahat_mobile/nepal_map_data.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('bundled Nepal basemap contains provinces and district headquarters',
      () async {
    final data = await NepalMapData.load(rootBundle);
    expect(data.provinces, hasLength(7));
    expect(data.headquarters.length, greaterThanOrEqualTo(70));
    final names = data.headquarters
        .map((feature) => feature['properties']?['name'])
        .whereType<String>()
        .toSet();
    expect(names, containsAll(['Kathmandu', 'Pokhara', 'Biratnagar']));
  });
}

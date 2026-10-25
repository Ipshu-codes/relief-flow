import 'package:geolocator/geolocator.dart';

import 'module_api.dart';

Future<Position> currentDevicePosition({bool requestPermission = false}) async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw const ModuleApiException(
        'Location services are off. Write your address below or enable GPS.');
  }
  var permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied && requestPermission) {
    permission = await Geolocator.requestPermission();
  }
  if (permission != LocationPermission.always &&
      permission != LocationPermission.whileInUse) {
    throw const ModuleApiException(
        'Location permission is not available. You can still send a written address.');
  }
  return Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.high,
      timeLimit: const Duration(seconds: 8));
}

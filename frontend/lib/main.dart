import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'app_state.dart';
import 'ble_service.dart';
import 'mesh_service.dart';
import 'screens/home.dart';
import 'screens/sos.dart';
import 'screens/status.dart';
import 'screens/map.dart';
import 'screens/volunteer.dart';
import 'screens/mesh.dart';
import 'screens/settings.dart';
import 'screens/coordination.dart';
import 'screens/direct_sos.dart';

void main() {
  runApp(const RahatApp());
}

class RahatApp extends StatelessWidget {
  const RahatApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppState()),
        ChangeNotifierProvider(create: (_) => BleService()),
        ChangeNotifierProvider(
            create: (context) => MeshService(context.read<BleService>())),
      ],
      child: Consumer<AppState>(
        builder: (_, appState, __) => MaterialApp(
          title: 'Rahat',
          debugShowCheckedModeBanner: false,
          theme: ThemeData.dark().copyWith(
            scaffoldBackgroundColor: const Color(0xFF0D1114),
            colorScheme: const ColorScheme.dark(
              primary: Color(0xFF4CAF7D),
              secondary: Color(0xFFFBC02D),
              surface: Color(0xFF151B1F),
              error: Color(0xFFD32F2F),
            ),
          ),
          locale: appState.locale,
          localizationsDelegates: const [],
          home: const HomeScreen(),
          onGenerateRoute: (settings) => MaterialPageRoute(
            builder: (_) {
              switch (settings.name) {
                case '/sos':
                  return const SOSScreen();
                case '/direct-sos':
                  return const DirectSOSScreen();
                case '/status':
                  return const StatusScreen();
                case '/map':
                  return const MapScreen();
                case '/volunteer':
                  return const VolunteerScreen();
                case '/mesh':
                  return const MeshScreen();
                case '/settings':
                  return const SettingsScreen();
                case '/coordination':
                  return const CoordinationScreen();
                default:
                  return const HomeScreen();
              }
            },
          ),
        ),
      ),
    );
  }
}

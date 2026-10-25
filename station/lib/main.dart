import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:rahat_mobile/app_state.dart';
import 'service_station_screen.dart';

void main() {
  runApp(const ServiceStationApp());
}

class ServiceStationApp extends StatelessWidget {
  const ServiceStationApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Rahat Service Station · Station E',
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
      home: ChangeNotifierProvider(
        create: (_) => AppState(),
        child: const ServiceStationScreen(),
      ),
    );
  }
}

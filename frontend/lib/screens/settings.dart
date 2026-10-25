import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';

class SettingsScreen extends StatelessWidget {
  final bool embedded;
  const SettingsScreen({super.key, this.embedded = false});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    return Scaffold(
      appBar: embedded ? null : AppBar(title: const Text('Settings')),
      body: Center(
          child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 680),
        child: ListView(padding: const EdgeInsets.all(20), children: [
          const ListTile(
              leading: Icon(Icons.link),
              title: Text('Automatic connection'),
              subtitle: Text(
                  'Rahat connects automatically. No connection settings are needed.')),
          ListTile(
              leading: const Icon(Icons.contact_emergency_outlined),
              title: const Text('Emergency profile'),
              subtitle: const Text(
                  'Sign in to add your phone, written location, trusted emergency contacts, and accessibility information.'),
              onTap: () => Navigator.pushNamed(context, '/coordination')),
          const Divider(height: 24),
          const Text('Language', style: TextStyle(fontSize: 20)),
          ListTile(
              title: const Text('English'),
              trailing: app.locale.languageCode == 'en'
                  ? const Icon(Icons.check)
                  : null,
              onTap: () => app.setLocale('en')),
          ListTile(
              title:
                  const Text('नेपाली (SOS labels; other screens use English)'),
              trailing: app.locale.languageCode == 'ne'
                  ? const Icon(Icons.check)
                  : null,
              onTap: () => app.setLocale('ne')),
          const Divider(height: 40),
          const ListTile(
              leading: Icon(Icons.cloud_off),
              title: Text('Offline requests'),
              subtitle: Text(
                  'SOS is saved locally before sending. Reopen Request help to retry. Android phones can opt into nearby Bluetooth relay under Mesh; browsers cannot relay over Bluetooth. Keep the app open while relaying.')),
        ]),
      )),
    );
  }
}

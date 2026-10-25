import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

typedef CallLauncher = Future<bool> Function(Uri uri);

class EmergencyCalls extends StatelessWidget {
  final CallLauncher? launch;
  const EmergencyCalls({super.key, this.launch});

  static const contacts = [
    (name: 'Police', number: '100', icon: Icons.local_police_outlined),
    (name: 'Ambulance', number: '102', icon: Icons.medical_services_outlined),
    (
      name: 'Fire brigade',
      number: '101',
      icon: Icons.local_fire_department_outlined
    ),
    (name: 'Tourist police', number: '1144', icon: Icons.support_agent),
  ];

  Future<void> _call(BuildContext context, String number) async {
    try {
      final uri = Uri(scheme: 'tel', path: number);
      final opened = await (launch?.call(uri) ??
          launchUrl(uri, mode: LaunchMode.externalApplication));
      if (!opened && context.mounted) {
        _showFailure(context, number);
      }
    } on Exception {
      if (context.mounted) _showFailure(context, number);
    }
  }

  void _showFailure(BuildContext context, String number) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content:
            Text('Could not open a calling app. Dial $number on a phone.')));
  }

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Emergency calls · Nepal',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final contact in contacts)
              OutlinedButton.icon(
                  onPressed: () => _call(context, contact.number),
                  icon: Icon(contact.icon),
                  label: Text('${contact.name} · ${contact.number}')),
          ]),
          const SizedBox(height: 8),
          const Text(
              'Opens your calling app; you confirm the call. No internet is needed, but phone service is required. Ambulance coverage varies; contact a nearby hospital if unavailable.',
              style: TextStyle(fontSize: 12)),
        ],
      );
}

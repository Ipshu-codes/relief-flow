import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../mesh_service.dart';

class MeshScreen extends StatelessWidget {
  final bool embedded;
  const MeshScreen({super.key, this.embedded = false});

  @override
  Widget build(BuildContext context) {
    final mesh = context.watch<MeshService>();
    return Scaffold(
      appBar: embedded ? null : AppBar(title: const Text('Offline support')),
      body: Center(
          child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 600),
        child: ListView(padding: const EdgeInsets.all(24), children: [
          Icon(mesh.supported ? Icons.bluetooth : Icons.bluetooth_disabled,
              size: 52, color: const Color(0xFFFBC02D)),
          const SizedBox(height: 16),
          Text(
              mesh.supported
                  ? 'Android Bluetooth relay'
                  : 'Bluetooth relay needs the Android app',
              textAlign: TextAlign.center,
              style:
                  const TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
          const SizedBox(height: 16),
          const Text(
              'Nearby participating Android phones can carry a saved SOS, including its written address and landmark, to a phone that can reach the receiving station. No internet is needed between Bluetooth peers.'),
          const SizedBox(height: 12),
          const Text(
              'Keep both apps open and Bluetooth on. Relay is opt-in: SOS details and location are visible to participating nearby phones. Signatures detect altered packets, but do not establish a trusted identity.'),
          const SizedBox(height: 12),
          const Text(
              'A Bluetooth handoff is NOT a server receipt. The sender keeps the original SOS until a direct server retry confirms it. Radio delivery and phone compatibility must be tested on your devices before relying on them.'),
          if (mesh.supported) ...[
            const SizedBox(height: 20),
            FilledButton.icon(
                onPressed: mesh.starting
                    ? null
                    : () async {
                        if (mesh.running) {
                          await mesh.stop();
                        } else {
                          final consent = await showDialog<bool>(
                              context: context,
                              builder: (dialog) => AlertDialog(
                                    title:
                                        const Text('Allow nearby SOS relay?'),
                                    content: const Text(
                                        'This shares your saved SOS address and details with nearby relay phones and stores SOS from other people on this phone. Keep the app open. Do not enable this on a shared or untrusted phone.'),
                                    actions: [
                                      TextButton(
                                          onPressed: () =>
                                              Navigator.pop(dialog, false),
                                          child: const Text('Cancel')),
                                      FilledButton(
                                          onPressed: () =>
                                              Navigator.pop(dialog, true),
                                          child: const Text('Allow relay')),
                                    ],
                                  ));
                          if (consent == true) await mesh.start();
                        }
                      },
                icon:
                    Icon(mesh.running ? Icons.stop : Icons.bluetooth_searching),
                label: Text(mesh.starting
                    ? 'Starting Bluetooth'
                    : mesh.running
                        ? 'Stop relay'
                        : 'Enable nearby relay')),
            ListTile(
                title: const Text('Connected peer links'),
                trailing: Text('${mesh.peerCount}')),
            ListTile(
                title: const Text('Saved relay requests'),
                trailing: Text('${mesh.queued}')),
            ListTile(
                title: const Text('Confirmed by receiving station'),
                trailing: Text('${mesh.delivered}')),
            ListTile(
                title: const Text('Handoffs attempted'),
                trailing: Text('${mesh.handoffs}')),
            OutlinedButton(
                onPressed: mesh.running ? mesh.pump : null,
                child: const Text('Retry relay now')),
          ] else
            const Padding(
                padding: EdgeInsets.only(top: 16),
                child: Text(
                    'This browser does not relay SOS over Bluetooth. Saved SOS can retry when connected. Install the Android build on both phones for BLE relay.')),
          if (mesh.error != null)
            Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(mesh.error!,
                    style: const TextStyle(color: Color(0xFFFFB4B4)))),
        ]),
      )),
    );
  }
}

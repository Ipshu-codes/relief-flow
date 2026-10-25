import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api.dart';
import '../app_state.dart';
import '../device_location.dart';
import '../mesh_service.dart';

class DirectSOSScreen extends StatefulWidget {
  const DirectSOSScreen({super.key});

  @override
  State<DirectSOSScreen> createState() => _DirectSOSScreenState();
}

class _DirectSOSScreenState extends State<DirectSOSScreen> {
  bool _sending = false;
  String? _message;
  bool? _sent;

  Future<void> _confirmAndSend() async {
    if (_sending) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Send direct SOS?'),
        content: const Text(
            'Use this only for immediate danger. Rahat will send it to the Service Station or save it for network/Bluetooth relay.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF8B0000)),
            child: const Text('Send SOS'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) await _send();
  }

  Future<void> _send() async {
    if (_sending) return;
    setState(() {
      _sending = true;
      _message = null;
      _sent = null;
    });
    final state = context.read<AppState>();
    final mesh = context.read<MeshService>();
    final client = SOSClient(state.backendUrl);
    try {
      double? latitude;
      double? longitude;
      try {
        final position = await currentDevicePosition();
        latitude = position.latitude;
        longitude = position.longitude;
      } on Exception {
        // A direct SOS can still be sent with no GPS fix.
      }
      final result = await client.submit(
        category: 'RESCUE',
        message: 'Direct SOS: immediate assistance requested',
        lat: latitude,
        lon: longitude,
        shareGpsWhenAvailable: true,
      );
      await state.setDelivery(
        status: result['status'] as String,
        label: 'Sent to service station',
        incidentId: result['id'] as int,
        receiptToken: result['receipt_token'] as String,
      );
      if (!mounted) return;
      setState(() {
        _sent = true;
        _message =
            'SOS sent to the service station. Coordinators can now review and respond.';
      });
    } catch (error) {
      await mesh.start();
      await mesh.pump();
      if (!mounted) return;
      setState(() {
        _sent = false;
        _message = mesh.supported
            ? 'Internet was unavailable. The SOS is saved and Bluetooth relay will retry when a nearby relay is available.'
            : 'Internet was unavailable. The SOS is saved on this phone and will retry when connectivity returns.';
      });
      await state.setDelivery(
        status: 'queued',
        label: 'Saved for network/Bluetooth retry',
      );
    } finally {
      client.close();
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Direct SOS')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.warning_amber_rounded,
                color: Color(0xFFFF5252), size: 76),
            const SizedBox(height: 20),
            const Text(
              'Use only for immediate danger',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 12),
            const Text(
              'Rahat will try the internet first, then save the request for phone-network retry and Bluetooth relay.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 28),
            SizedBox(
              width: double.infinity,
              height: 86,
              child: FilledButton.icon(
                onPressed: _sending ? null : _confirmAndSend,
                icon: _sending
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.emergency, size: 32),
                label: Text(_sending ? 'SENDING SOS' : 'DIRECT SOS',
                    style: const TextStyle(
                        fontSize: 24, fontWeight: FontWeight.w800)),
                style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFFD32F2F),
                    foregroundColor: Colors.white),
              ),
            ),
            if (_message != null) ...[
              const SizedBox(height: 24),
              Text(_message!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: _sent == true
                          ? const Color(0xFF75D4A0)
                          : const Color(0xFFFFB4B4))),
            ],
          ],
        ),
      ),
    );
  }
}

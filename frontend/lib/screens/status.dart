import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api.dart';
import '../app_state.dart';
import '../device_location.dart';

class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});

  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> {
  SOSClient? _client;
  Timer? _timer;
  Map<String, dynamic>? _serverStatus;
  String? _error;
  bool _loading = false;
  bool _sharingLocation = false;
  String? _locationMessage;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final app = context.watch<AppState>();
    if (_client?.baseUrl != app.backendUrl) {
      _client?.close();
      _client = SOSClient(app.backendUrl);
    }
    if (app.incidentId != null && app.receiptToken != null) {
      _timer ??= Timer.periodic(const Duration(seconds: 20), (_) => _refresh());
      if (_serverStatus == null && !_loading) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
      }
    }
  }

  Future<void> _refresh() async {
    final app = context.read<AppState>();
    final id = app.incidentId;
    final token = app.receiptToken;
    if (id == null || token == null || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      _client ??= SOSClient(app.backendUrl);
      final result = await _client!.status(id: id, receiptToken: token);
      if (!mounted || app.incidentId != id || app.receiptToken != token) return;
      setState(() => _serverStatus = result);
      await app.setDelivery(
        status: result['status'] as String,
        incidentId: id,
        receiptToken: token,
        label: _statusLabel(result['status'] as String),
      );
      if (result['has_location'] == false &&
          !['resolved', 'false_alarm'].contains(result['status']) &&
          await _client!.needsGps()) {
        await _shareLocation();
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _shareLocation({bool requestPermission = false}) async {
    final app = context.read<AppState>();
    final id = app.incidentId;
    final token = app.receiptToken;
    if (id == null || token == null || _sharingLocation) return;
    setState(() => _sharingLocation = true);
    try {
      final position =
          await currentDevicePosition(requestPermission: requestPermission);
      await _client!.updateLocation(
          id: id,
          receiptToken: token,
          latitude: position.latitude,
          longitude: position.longitude,
          accuracyM: position.accuracy);
      if (mounted && app.incidentId == id && app.receiptToken == token) {
        setState(() {
          _serverStatus = {...?_serverStatus, 'has_location': true};
          _locationMessage = 'GPS coordinates shared with the response team.';
        });
      }
    } on Exception catch (error) {
      if (mounted) {
        setState(() => _locationMessage =
            'GPS not shared yet: $error. Your written address is kept.');
      }
    } finally {
      if (mounted) setState(() => _sharingLocation = false);
    }
  }

  String _statusLabel(String status) => switch (status) {
        'new' => 'Sent to service station · awaiting response',
        'acknowledged' => 'Acknowledged by coordinator',
        'dispatched' => 'Response dispatched',
        'resolved' => 'Resolved',
        'false_alarm' => 'Closed as false alarm',
        'queued' => 'Saved on device · not received',
        _ => status.replaceAll('_', ' '),
      };

  @override
  void dispose() {
    _timer?.cancel();
    _client?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final status = (_serverStatus?['status'] ?? app.status).toString();
    const stages = [
      ('new', 'Sent to service station'),
      ('acknowledged', 'Acknowledged'),
      ('dispatched', 'Response dispatched'),
      ('resolved', 'Resolved'),
    ];
    final serverReceived = _serverStatus != null;
    final index = stages.indexWhere((stage) => stage.$1 == status);
    return Scaffold(
      appBar: AppBar(title: const Text('SOS status')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Row(children: [
            Expanded(
                child: Text(
                    app.incidentId == null
                        ? 'No server receipt yet'
                        : 'SOS #${app.incidentId}',
                    style: const TextStyle(
                        fontSize: 22, fontWeight: FontWeight.w600))),
            IconButton(
                tooltip: 'Refresh status',
                onPressed: _loading ? null : _refresh,
                icon: _loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh)),
          ]),
          const SizedBox(height: 12),
          if (!serverReceived)
            const Card(
              color: Color(0xFF342F1C),
              child: ListTile(
                leading: Icon(Icons.info_outline, color: Color(0xFFFBC02D)),
                title: Text('Status has not been confirmed by the server.'),
                subtitle: Text(
                    'A saved offline request is not yet visible to coordinators. Return to SOS to retry when connected.'),
              ),
            )
          else
            Card(
              color: const Color(0xFF151B1F),
              child: ListTile(
                leading: const Icon(Icons.verified_outlined,
                    color: Color(0xFF75D4A0)),
                title: Text(_statusLabel(status)),
                subtitle: Text(
                    'Transmission: ${_serverStatus?['transmission_status'] ?? 'unknown'}'),
              ),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('Could not refresh status: $_error',
                  style: const TextStyle(color: Color(0xFFFFB4B4))),
            ),
          const SizedBox(height: 20),
          for (var i = 0; i < stages.length; i++) ...[
            ListTile(
              leading: CircleAvatar(
                radius: 14,
                backgroundColor: serverReceived && index >= i
                    ? const Color(0xFF388E3C)
                    : const Color(0xFF263038),
                child: serverReceived && index >= i
                    ? const Icon(Icons.check, size: 16, color: Colors.white)
                    : null,
              ),
              title: Text(stages[i].$2),
              trailing: serverReceived && index == i
                  ? const Icon(Icons.radio_button_checked,
                      color: Color(0xFF4CAF7D))
                  : null,
            ),
            const Divider(height: 1),
          ],
          const SizedBox(height: 20),
          if (app.incidentId != null &&
              !['resolved', 'false_alarm'].contains(status)) ...[
            OutlinedButton.icon(
                onPressed: _sharingLocation
                    ? null
                    : () => _shareLocation(requestPermission: true),
                icon: const Icon(Icons.my_location),
                label: Text(_sharingLocation
                    ? 'Sharing GPS'
                    : 'Share current GPS location')),
            const Text(
                'This shares where your device is now, not necessarily where you first requested help. GPS permission is required.'),
          ],
          if (_locationMessage != null)
            Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_locationMessage!)),
          const SizedBox(height: 12),
          const Text(
              'A server receipt confirms storage only. Dispatch and resolution are separate coordinator actions.'),
          if (_serverStatus?['linked_need_id'] != null)
            ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Linked response need'),
                subtitle: Text('#${_serverStatus!['linked_need_id']}')),
          if (_serverStatus?['received_at_server'] != null)
            ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Received at'),
                subtitle: Text('${_serverStatus!['received_at_server']}')),
        ],
      ),
    );
  }
}

import 'dart:async';
import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'ble_service.dart';
import 'mesh_packet.dart';
import 'module_api.dart';

class MeshService extends ChangeNotifier {
  final BleService transport;
  final http.Client _http;
  final String _backend;
  final Map<String, MeshPacket> _queue = {};
  final Set<String> _delivered = {};
  final List<Uint8List> _incoming = [];
  StreamSubscription<Uint8List>? _subscription;
  SimpleKeyPair? _key;
  Timer? _timer;
  bool _running = false;
  bool _busy = false;
  Completer<void>? _cycle;
  bool _starting = false;
  bool _disposed = false;
  String? _error;
  int _handoffs = 0;

  MeshService(this.transport, {http.Client? client, String? backend})
      : _http = client ?? http.Client(),
        _backend = backend ?? defaultBackendUrl;

  bool get supported => transport.supported;
  bool get running => _running;
  bool get starting => _starting;
  int get peerCount => transport.peerCount;
  int get queued => _queue.length;
  int get delivered => _delivered.length;
  int get handoffs => _handoffs;
  String? get error => _error ?? transport.error;

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  Future<void> _save() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(
        'meshStateV1',
        jsonEncode({
          'queue': _queue.values.map((packet) => packet.envelope).toList(),
          'delivered': _delivered.toList(),
        }));
  }

  Future<void> start() async {
    if (_running || _starting) return;
    _starting = true;
    _error = null;
    _notify();
    try {
      final preferences = await SharedPreferences.getInstance();
      final encoded = preferences.getString('meshSigningSeedV1');
      if (encoded == null) {
        _key = await Ed25519().newKeyPair();
        await preferences.setString('meshSigningSeedV1',
            base64Encode(await _key!.extractPrivateKeyBytes()));
      } else {
        _key = await Ed25519().newKeyPairFromSeed(base64Decode(encoded));
      }
      final saved = preferences.getString('meshStateV1');
      _queue.clear();
      _delivered.clear();
      if (saved != null) {
        final state = jsonDecode(saved);
        if (state is! Map ||
            state['queue'] is! List ||
            state['delivered'] is! List ||
            (state['queue'] as List).length > 100 ||
            (state['delivered'] as List).length > 500) {
          throw const FormatException(
              'Invalid saved Bluetooth relay queue; its data is preserved');
        }
        for (final envelope in state['queue'] as List) {
          final packet = await MeshPacket.decode(
              Uint8List.fromList(utf8.encode(jsonEncode(envelope))));
          _queue[packet.id] = packet;
        }
        _delivered.addAll(List<String>.from(state['delivered'] as List));
      }
      _subscription = transport.packets.listen((bytes) {
        if (_incoming.length >= 50) {
          _error =
              'Too many incoming SOS packets; retry after the relay catches up.';
          _notify();
          return;
        }
        _incoming.add(bytes);
        unawaited(pump());
      });
      transport.addListener(_notify);
      await transport.start();
      _running = true;
      _timer = Timer.periodic(const Duration(seconds: 15), (_) => pump());
      unawaited(pump());
    } on Exception catch (error) {
      _error = 'Could not start Bluetooth relay: $error';
      await _subscription?.cancel();
      transport.removeListener(_notify);
      _notify();
    } finally {
      _starting = false;
      _notify();
    }
  }

  Future<void> pump() async {
    if (!_running) return;
    if (_busy) {
      await _cycle!.future;
      return;
    }
    _busy = true;
    _cycle = Completer<void>();
    try {
      while (_incoming.isNotEmpty) {
        try {
          final packet = await MeshPacket.decode(_incoming.removeAt(0));
          if (_queue.containsKey(packet.id) || _delivered.contains(packet.id)) {
            continue;
          }
          if (_queue.length >= 100) {
            throw const FormatException(
                'Relay queue is full. New packets cannot be retained yet.');
          }
          _queue[packet.id] = packet.hops > 0 ? packet.forwarded() : packet;
          await _save();
        } on FormatException catch (error) {
          _error = 'Rejected Bluetooth packet: ${error.message}';
          _notify();
        }
      }
      final local = SOSClient(_backend);
      List<Map<String, dynamic>> pending;
      try {
        pending = await local.pending();
      } finally {
        local.close();
      }
      for (final item in pending) {
        final id = item['client_uuid'] as String;
        if (_queue.containsKey(id) || _delivered.contains(id)) continue;
        if (_queue.length >= 100) {
          throw const FormatException(
              'Relay queue is full. Your original SOS is still saved.');
        }
        _queue[id] = await MeshPacket.sign(item, _key!);
        await _save();
      }
      var tryInternet = true;
      for (final packet in _queue.values.toList()) {
        if (!_running) break;
        if (tryInternet) {
          try {
            final response = await _http
                .post(Uri.parse('$_backend/api/v1/ingest/ble'),
                    headers: const {'Content-Type': 'application/json'},
                    body: jsonEncode(packet.envelope))
                .timeout(const Duration(seconds: 8));
            final data = jsonDecode(response.body);
            if (response.statusCode < 200 ||
                response.statusCode >= 300 ||
                data is! Map ||
                data['client_uuid'] != packet.id ||
                data['transmission_status'] != 'received') {
              throw ModuleApiException(
                  'Receiver did not confirm relayed SOS (HTTP ${response.statusCode}).');
            }
            _queue.remove(packet.id);
            _delivered.add(packet.id);
            while (_delivered.length > 500) {
              _delivered.remove(_delivered.first);
            }
            await _save();
            continue;
          } on Exception catch (error) {
            tryInternet = false;
            _error =
                'Receiver unavailable; SOS stays queued for Bluetooth/online retry. $error';
          }
        }
        if (packet.hops > 0 && transport.peerCount > 0) {
          _handoffs += await transport.send(packet.bytes);
        }
      }
    } on Exception catch (error) {
      _error =
          'Bluetooth relay has paused this attempt: $error. Saved requests are kept.';
    } finally {
      _busy = false;
      _cycle!.complete();
      _cycle = null;
      _notify();
    }
  }

  Future<void> stop() async {
    _running = false;
    _timer?.cancel();
    await _subscription?.cancel();
    transport.removeListener(_notify);
    try {
      await transport.stop();
    } on Exception catch (error) {
      _error = 'Could not fully stop Bluetooth: $error';
    }
    _notify();
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(stop());
    _http.close();
    super.dispose();
  }
}

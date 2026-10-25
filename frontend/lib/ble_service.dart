import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'mesh_packet.dart';

class BleService extends ChangeNotifier {
  static const _service = 'a0000000-0000-1000-8000-f00000000001';
  static const _notify = 'a0000001-0000-1000-8000-f00000000001';
  static const _write = 'a0000002-0000-1000-8000-f00000000001';
  static const _native = MethodChannel('org.rahat/ble_mesh');
  static const _events = EventChannel('org.rahat/ble_mesh_events');
  final _packets = StreamController<Uint8List>.broadcast();
  final _decoders = <String, BleFrameDecoder>{};
  StreamSubscription<dynamic>? _nativeEvents;
  StreamSubscription<List<ScanResult>>? _scan;
  StreamSubscription<List<int>>? _notifications;
  StreamSubscription<BluetoothConnectionState>? _connection;
  BluetoothDevice? _device;
  BluetoothCharacteristic? _writer;
  bool _enabled = false;
  bool _connecting = false;
  bool _sending = false;
  bool _disposed = false;
  int _subscribers = 0;
  String? _error;

  bool get supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  bool get enabled => _enabled;
  int get peerCount => _subscribers + (_writer == null ? 0 : 1);
  String? get error => _error;
  Stream<Uint8List> get packets => _packets.stream;

  void _notifyState() {
    if (!_disposed) notifyListeners();
  }

  void _receive(String peer, List<int> bytes) {
    try {
      if (!_decoders.containsKey(peer) && _decoders.length >= 16) {
        throw const FormatException('Too many BLE peers');
      }
      final decoder = _decoders.putIfAbsent(peer, BleFrameDecoder.new);
      for (final packet in decoder.add(bytes)) {
        _packets.add(packet);
      }
    } on FormatException catch (error) {
      _decoders.remove(peer);
      _error = error.message;
      _notifyState();
    }
  }

  Future<void> start() async {
    if (!supported) throw UnsupportedError('Bluetooth relay requires Android.');
    if (_enabled) return;
    _error = null;
    _nativeEvents = _events.receiveBroadcastStream().listen((dynamic event) {
      final data = Map<String, dynamic>.from(event as Map);
      switch (data['type']) {
        case 'bytes':
          _receive('in:${data['peer']}', List<int>.from(data['bytes'] as List));
        case 'peers':
          _subscribers = data['count'] as int;
        case 'disconnected':
          _decoders.remove('in:${data['peer']}');
        case 'error':
          _error = data['message'] as String;
      }
      _notifyState();
    }, onError: (Object error) {
      _error = 'Bluetooth transport failed: $error';
      _notifyState();
    });
    try {
      await _native.invokeMethod<void>('start');
      _enabled = true;
      _scan = FlutterBluePlus.scanResults.listen((results) {
        if (!_enabled || _connecting || _device != null) return;
        if (results.isNotEmpty) unawaited(_connect(results.first.device));
      });
      await FlutterBluePlus.startScan(withServices: [Guid(_service)]);
      _notifyState();
    } on Exception {
      await stop();
      rethrow;
    }
  }

  Future<void> _connect(BluetoothDevice device) async {
    _connecting = true;
    _device = device;
    try {
      await device.connect(
          timeout: const Duration(seconds: 12), autoConnect: false);
      final services = await device.discoverServices();
      for (final service
          in services.where((value) => value.uuid == Guid(_service))) {
        for (final characteristic in service.characteristics) {
          if (characteristic.uuid == Guid(_write)) _writer = characteristic;
          if (characteristic.uuid == Guid(_notify)) {
            _notifications = characteristic.onValueReceived.listen((bytes) {
              _receive('out:${device.remoteId}', bytes);
            });
            await characteristic.setNotifyValue(true);
          }
        }
      }
      if (_writer == null || _notifications == null) {
        throw const FormatException(
            'Peer does not provide the Rahat relay service');
      }
      _connection = device.connectionState.listen((state) {
        if (state == BluetoothConnectionState.disconnected) {
          _writer = null;
          _device = null;
          _decoders.remove('out:${device.remoteId}');
          _notifications?.cancel();
          _notifyState();
        }
      });
    } on Exception catch (error) {
      _error = 'Could not connect to a nearby relay: $error';
      _writer = null;
      _device = null;
      await _notifications?.cancel();
      await device.disconnect();
    } finally {
      _connecting = false;
      _notifyState();
    }
  }

  Future<int> send(Uint8List packet) async {
    if (!_enabled || _sending) return 0;
    _sending = true;
    var peers = 0;
    try {
      final framed = BleFrameDecoder.frame(packet);
      final writer = _writer;
      if (writer != null) {
        for (var index = 0; index < framed.length; index += 20) {
          await writer.write(
              framed.sublist(index, (index + 20).clamp(0, framed.length)),
              withoutResponse: false);
        }
        peers++;
      }
      peers += await _native.invokeMethod<int>('broadcast', framed) ?? 0;
      return peers;
    } on Exception catch (error) {
      _error = 'Bluetooth handoff was interrupted: $error';
      _notifyState();
      rethrow;
    } finally {
      _sending = false;
    }
  }

  Future<void> stop() async {
    if (!_enabled && _nativeEvents == null && _device == null && _scan == null) {
      return;
    }
    _enabled = false;
    await _scan?.cancel();
    await _notifications?.cancel();
    await _connection?.cancel();
    if (supported) {
      await FlutterBluePlus.stopScan();
      await _device?.disconnect();
      await _native.invokeMethod<void>('stop');
    }
    await _nativeEvents?.cancel();
    _scan = null;
    _notifications = null;
    _connection = null;
    _nativeEvents = null;
    _device = null;
    _writer = null;
    _subscribers = 0;
    _decoders.clear();
    _notifyState();
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(stop());
    unawaited(_packets.close());
    super.dispose();
  }
}

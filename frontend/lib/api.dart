import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import 'module_api.dart';

class SOSClient {
  final String baseUrl;
  final http.Client _client;

  SOSClient(this.baseUrl, {http.Client? client})
      : _client = client ?? http.Client();

  static const _outboxKey = 'sosOutbox';
  static const _uuid = Uuid();

  Uri _uri(String path) =>
      Uri.parse('${baseUrl.replaceFirst(RegExp(r'/+$'), '')}$path');

  Future<List<Map<String, dynamic>>> pending() async {
    final preferences = await SharedPreferences.getInstance();
    final value = preferences.getString(_outboxKey);
    if (value == null) return [];
    try {
      final decoded = jsonDecode(value);
      if (decoded is! List ||
          decoded.any((item) =>
              item is! Map<String, dynamic> ||
              item['client_uuid'] is! String ||
              (item['client_uuid'] as String).isEmpty ||
              !const ['FOOD', 'MEDICINE', 'TRAPPED', 'RESCUE', 'OTHER']
                  .contains(item['category']) ||
              item['message'] is! String)) {
        throw const FormatException('Invalid saved SOS structure');
      }
      return decoded
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    } on FormatException {
      throw const ModuleApiException(
          'The saved SOS queue cannot be read. Its data has been preserved; contact an operator.');
    }
  }

  Future<void> _savePending(List<Map<String, dynamic>> items) async {
    final preferences = await SharedPreferences.getInstance();
    if (items.isEmpty) {
      await preferences.remove(_outboxKey);
    } else {
      await preferences.setString(_outboxKey, jsonEncode(items));
    }
  }

  Future<Map<String, dynamic>> submit({
    required String category,
    required String message,
    double? lat,
    double? lon,
    double? accuracyM,
    String? displayCategory,
    String? displayNote,
    Map<String, String>? address,
    int? urgency,
    bool shareGpsWhenAvailable = true,
    Map<String, dynamic>? pendingItem,
  }) async {
    final outbox = await pending();
    final item = pendingItem ??
        <String, dynamic>{
          'client_uuid': _uuid.v4(),
          'category': category,
          'urgency': urgency,
          'message': message,
          'lat': lat,
          'lon': lon,
          'location_accuracy_m': accuracyM,
          'created_at_device': DateTime.now().toUtc().toIso8601String(),
          'channel': 'app',
          '_ui_category': displayCategory,
          '_ui_note': displayNote ?? '',
          'address': address,
          '_share_gps': shareGpsWhenAvailable,
        };
    final clientUuid = item['client_uuid'] as String?;
    if (clientUuid == null || clientUuid.isEmpty) {
      item['client_uuid'] = _uuid.v4();
    }
    if (pendingItem != null && lat != null && lon != null) {
      item['lat'] = lat;
      item['lon'] = lon;
      item['location_accuracy_m'] = accuracyM;
    }
    if (pendingItem != null && urgency != null) {
      item['urgency'] = urgency;
    }
    final savedIndex = outbox
        .indexWhere((saved) => saved['client_uuid'] == item['client_uuid']);
    if (savedIndex < 0) {
      outbox.add(item);
    } else {
      outbox[savedIndex] = item;
    }
    await _savePending(outbox);
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('activeSosStatus', 'queued');
    await preferences.remove('activeSosId');
    await preferences.remove('activeSosReceiptToken');
    try {
      final response = await _client
          .post(
            _uri('/sos'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode(Map<String, dynamic>.fromEntries(
                item.entries.where((entry) => !entry.key.startsWith('_')))),
          )
          .timeout(const Duration(seconds: 15));
      final data = _decode(response);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ModuleApiException(
            _errorMessage(data, response.statusCode), response.statusCode);
      }
      if (data is! Map<String, dynamic> ||
          data['id'] is! int ||
          data['client_uuid'] != item['client_uuid'] ||
          data['status'] is! String ||
          data['receipt_token'] is! String ||
          (data['receipt_token'] as String).isEmpty) {
        throw const ModuleApiException(
            'The server response did not confirm a saved SOS request.');
      }
      await _savePending(outbox
          .where((saved) => saved['client_uuid'] != item['client_uuid'])
          .toList());
      final preferences = await SharedPreferences.getInstance();
      await preferences.setInt('activeSosId', data['id'] as int);
      await preferences.setString(
          'activeSosReceiptToken', data['receipt_token'] as String);
      await preferences.setString('activeSosStatus', data['status'] as String);
      await preferences.setBool('activeSosNeedsGps',
          item['_share_gps'] == true && data['has_location'] != true);
      return Map<String, dynamic>.from(data);
    } on ModuleApiException {
      rethrow;
    } on Exception {
      throw const ModuleApiException(
          'SOS is saved on this device, but the server has not confirmed receipt. Retry when connected.');
    }
  }

  Future<bool> needsGps() async =>
      (await SharedPreferences.getInstance()).getBool('activeSosNeedsGps') ??
      false;

  Future<void> updateLocation({
    required int id,
    required String receiptToken,
    required double latitude,
    required double longitude,
    double? accuracyM,
  }) async {
    final response = await _client
        .patch(
          _uri('/sos/$id/location')
              .replace(queryParameters: {'receipt_token': receiptToken}),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({
            'lat': latitude,
            'lon': longitude,
            'location_accuracy_m': accuracyM,
          }),
        )
        .timeout(const Duration(seconds: 15));
    final data = _decode(response);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ModuleApiException(
          _errorMessage(data, response.statusCode), response.statusCode);
    }
    if (data is! Map || data['id'] != id || data['has_location'] != true) {
      throw const ModuleApiException(
          'The updated GPS location has not been confirmed.');
    }
    final preferences = await SharedPreferences.getInstance();
    if (preferences.getInt('activeSosId') == id &&
        preferences.getString('activeSosReceiptToken') == receiptToken) {
      await preferences.setBool('activeSosNeedsGps', false);
    }
  }

  Future<Map<String, dynamic>> status(
      {required int id, required String receiptToken}) async {
    final response = await _client.get(
      _uri('/sos/$id/status')
          .replace(queryParameters: {'receipt_token': receiptToken}),
      headers: const {'Accept': 'application/json'},
    ).timeout(const Duration(seconds: 15));
    final data = _decode(response);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ModuleApiException(
          _errorMessage(data, response.statusCode), response.statusCode);
    }
    if (data is! Map<String, dynamic> ||
        data['id'] != id ||
        data['status'] is! String) {
      throw const ModuleApiException('The server returned invalid SOS status.');
    }
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('activeSosStatus', data['status'] as String);
    return Map<String, dynamic>.from(data);
  }

  dynamic _decode(http.Response response) {
    try {
      return response.body.isEmpty ? null : jsonDecode(response.body);
    } on FormatException {
      throw const ModuleApiException(
          'The API returned an unreadable response.');
    }
  }

  String _errorMessage(dynamic data, int status) {
    final detail = data is Map ? data['detail'] : null;
    return detail is String ? detail : 'Request failed (HTTP $status).';
  }

  void close() => _client.close();
}

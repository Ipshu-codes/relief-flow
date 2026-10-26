import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

String get defaultBackendUrl {
  const configured = String.fromEnvironment('BACKEND_BASE_URL');
  return resolveBackendUrl(
    configured: configured,
    page: kIsWeb ? Uri.base : null,
    development: kDebugMode,
  );
}

String resolveBackendUrl({
  String configured = '',
  Uri? page,
  bool development = false,
}) {
  if (configured.isNotEmpty) return configured;
  if (page != null && ['http', 'https'].contains(page.scheme)) {
    // Flutter debug servers use arbitrary ports and do not host the API.
    // Keep the page host so a phone can reach the developer machine over LAN.
    if (development && page.scheme == 'http' && page.port != 8000) {
      return page.replace(port: 8000).origin;
    }
    return page.origin;
  }
  return 'http://127.0.0.1:8000';
}

class BackendAddress {
  static Future<String> load() async {
    final preferences = await SharedPreferences.getInstance();
    // Old editable addresses must not override the deployment configuration.
    for (final key in ['backendBaseUrl', 'moduleApiUrl', 'stationUrl']) {
      await preferences.remove(key);
    }
    return defaultBackendUrl;
  }
}

class ModuleApiException implements Exception {
  final String message;
  final int? status;
  const ModuleApiException(this.message, [this.status]);

  @override
  String toString() => message;
}

class ModuleApi {
  final http.Client _client;
  final Map<String, String> _pending = {};
  String baseUrl;
  String? token;

  ModuleApi({
    String? baseUrl,
    http.Client? client,
  })  : baseUrl = baseUrl ?? defaultBackendUrl,
        _client = client ?? http.Client();

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
    bool retrySafe = false,
  }) async {
    final retryKey = '$method:$path:${jsonEncode(body)}';
    final payload = body == null ? null : Map<String, dynamic>.from(body);
    if (retrySafe && payload != null) {
      payload['client_uuid'] =
          _pending.putIfAbsent(retryKey, () => const Uuid().v4());
    }
    final uri = Uri.parse('${baseUrl.replaceFirst(RegExp(r'/+$'), '')}$path');
    final request = http.Request(method, uri);
    request.headers['Accept'] = 'application/json';
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    if (payload != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(payload);
    }
    try {
      final response =
          await http.Response.fromStream(await _client.send(request))
              .timeout(const Duration(seconds: 150));
      dynamic data;
      try {
        data = response.body.isEmpty ? null : jsonDecode(response.body);
      } on FormatException {
        throw ModuleApiException(
            'The API returned an unreadable response.', response.statusCode);
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final detail = data is Map ? data['detail'] : null;
        final message = detail is String
            ? detail
            : detail is List
                ? detail
                    .map((item) => item['msg'] ?? item.toString())
                    .join('; ')
                : 'Request failed (HTTP ${response.statusCode}).';
        throw ModuleApiException(message, response.statusCode);
      }
      _pending.remove(retryKey);
      return data;
    } on TimeoutException {
      throw const ModuleApiException(
          'The request timed out. Retry to check the same operation.');
    } on http.ClientException {
      throw const ModuleApiException(
          'Could not reach the Rahat server. Check that the backend is running and try again.');
    }
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    final result = await request('/auth/login', method: 'POST', body: {
      'email': email.trim(),
      'password': password,
    });
    token = result['access_token'] as String;
    try {
      return Map<String, dynamic>.from(await request('/auth/me'));
    } catch (_) {
      token = null;
      rethrow;
    }
  }

  Future<void> importBaseline(String csv) async {
    final request = http.MultipartRequest(
        'POST', Uri.parse('$baseUrl/api/admin/import/baseline'));
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.files.add(http.MultipartFile.fromString('file', csv,
        filename: 'settlements.csv'));
    final response = await http.Response.fromStream(await _client.send(request))
        .timeout(const Duration(seconds: 30));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final result = jsonDecode(response.body);
      throw ModuleApiException('${result['detail']}', response.statusCode);
    }
  }

  void close() => _client.close();
}

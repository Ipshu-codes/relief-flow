
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/relief_request.dart';

class RequestStorage {
  static const String _storageKey = 'rahat_requests';

  static Future<List<ReliefRequest>> getRequests() async {
    final preferences = await SharedPreferences.getInstance();
    final savedRequests = preferences.getString(_storageKey);

    if (savedRequests == null) {
      return [];
    }

    final List<dynamic> decoded = jsonDecode(savedRequests);

    return decoded.map((request) {
      return ReliefRequest.fromJson(
        Map<String, dynamic>.from(request as Map),
      );
    }).toList();
  }

  static Future<void> saveRequest(ReliefRequest request) async {
    final requests = await getRequests();
    requests.insert(0, request);

    final preferences = await SharedPreferences.getInstance();

    await preferences.setString(
      _storageKey,
      jsonEncode(
        requests.map((request) => request.toJson()).toList(),
      ),
    );
  }
}

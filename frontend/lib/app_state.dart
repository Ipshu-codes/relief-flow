import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'module_api.dart';

class AppState extends ChangeNotifier {
  Locale _locale = const Locale('en', '');
  bool _meshEnabled = true;
  bool _batterySaver = false;
  String _backendUrl = defaultBackendUrl;
  String _status = 'idle';
  int _hops = 0;
  String _deliveryLabel = 'No SOS sent';
  String? _peerCount;
  int? _incidentId;
  String? _receiptToken;

  Locale get locale => _locale;
  bool get meshEnabled => _meshEnabled;
  bool get batterySaver => _batterySaver;
  String get stationUrl => _backendUrl;
  String get backendUrl => _backendUrl;
  String get status => _status;
  int get hops => _hops;
  String get deliveryLabel => _deliveryLabel;
  String? get peerCount => _peerCount;
  int? get incidentId => _incidentId;
  String? get receiptToken => _receiptToken;

  AppState() {
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final lang = prefs.getString('lang') ?? 'en';
    _locale = Locale(lang, '');
    _meshEnabled = prefs.getBool('meshEnabled') ?? true;
    _batterySaver = prefs.getBool('batterySaver') ?? false;
    _backendUrl = await BackendAddress.load();
    _incidentId = prefs.getInt('activeSosId');
    _receiptToken = prefs.getString('activeSosReceiptToken');
    _status = prefs.getString('activeSosStatus') ?? 'idle';
    if (_status != 'idle') {
      _deliveryLabel = _status == 'queued'
          ? 'Saved on this device · not received'
          : _status.replaceAll('_', ' ');
    }
    notifyListeners();
  }

  Future<void> setLocale(String code) async {
    final prefs = await SharedPreferences.getInstance();
    _locale = Locale(code, '');
    await prefs.setString('lang', code);
    notifyListeners();
  }

  Future<void> setMeshEnabled(bool v) async {
    final prefs = await SharedPreferences.getInstance();
    _meshEnabled = v;
    await prefs.setBool('meshEnabled', v);
    notifyListeners();
  }

  Future<void> setBatterySaver(bool v) async {
    final prefs = await SharedPreferences.getInstance();
    _batterySaver = v;
    await prefs.setBool('batterySaver', v);
    notifyListeners();
  }

  Future<void> setDelivery({
    required String status,
    int hops = 0,
    String? label,
    String? peerCount,
    int? incidentId,
    String? receiptToken,
  }) async {
    _status = status;
    _hops = hops;
    _deliveryLabel = label ?? status;
    final prefs = await SharedPreferences.getInstance();
    if (status == 'queued') {
      _incidentId = null;
      _receiptToken = null;
      await prefs.remove('activeSosId');
      await prefs.remove('activeSosReceiptToken');
    }
    if (incidentId != null) {
      _incidentId = incidentId;
      await prefs.setInt('activeSosId', incidentId);
    }
    if (receiptToken != null) {
      _receiptToken = receiptToken;
      await prefs.setString('activeSosReceiptToken', receiptToken);
    }
    await prefs.setString('activeSosStatus', status);
    _peerCount = peerCount;
    notifyListeners();
  }

  static Color severityColor(String sev) {
    switch (sev.toLowerCase()) {
      case 'critical':
        return const Color(0xFFD32F2F);
      case 'high':
        return const Color(0xFFF57C00);
      case 'medium':
        return const Color(0xFFFBC02D);
      case 'low':
        return const Color(0xFF388E3C);
      default:
        return const Color(0xFF9AA9B3);
    }
  }

  String t(BuildContext ctx, String en, String ne) {
    if (_locale.languageCode == 'ne') return ne;
    return en;
  }
}

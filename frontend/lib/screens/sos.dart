import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api.dart';
import '../app_state.dart';
import '../module_api.dart';
import '../device_location.dart';
import '../widgets/emergency_calls.dart';

typedef SOSLocation = ({double latitude, double longitude});

class SOSScreen extends StatefulWidget {
  final SOSClient? client;
  final Future<SOSLocation?> Function()? locate;
  const SOSScreen({super.key, this.client, this.locate});

  @override
  State<SOSScreen> createState() => _SOSScreenState();
}

class _SOSScreenState extends State<SOSScreen> with WidgetsBindingObserver {
  String? _category;
  int? _urgency;
  String _note = '';
  bool _sending = false;
  bool _locating = false;
  SOSLocation? _location;
  double? _accuracy;
  String? _error;
  bool _received = false;
  Map<String, dynamic>? _pending;
  late SOSClient _client;
  final _address = {
    'district': TextEditingController(),
    'city': TextEditingController(),
    'ward': TextEditingController(),
    'road': TextEditingController(),
    'landmark': TextEditingController(),
  };
  bool _shareGps = true;
  String? _locationError;
  Timer? _retryTimer;

  static const _categories = [
    (
      id: 'medical',
      api: 'MEDICINE',
      en: 'Medical',
      ne: 'चिकित्सा',
      icon: Icons.medical_services_outlined
    ),
    (
      id: 'trapped',
      api: 'TRAPPED',
      en: 'Trapped',
      ne: 'फसेको',
      icon: Icons.person_search_outlined
    ),
    (
      id: 'fire',
      api: 'RESCUE',
      en: 'Fire',
      ne: 'आगलागी',
      icon: Icons.local_fire_department_outlined
    ),
    (
      id: 'flood',
      api: 'RESCUE',
      en: 'Flood',
      ne: 'बाढी',
      icon: Icons.flood_outlined
    ),
    (
      id: 'food_water',
      api: 'FOOD',
      en: 'Food & water',
      ne: 'खाना र पानी',
      icon: Icons.water_drop_outlined
    ),
    (
      id: 'shelter',
      api: 'OTHER',
      en: 'Shelter',
      ne: 'आश्रय',
      icon: Icons.house_outlined
    ),
    (
      id: 'missing',
      api: 'OTHER',
      en: 'Missing person',
      ne: 'बेपत्ता',
      icon: Icons.search
    ),
    (
      id: 'road_blocked',
      api: 'OTHER',
      en: 'Road blocked',
      ne: 'बाटो बन्द',
      icon: Icons.wrong_location_outlined
    ),
  ];

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? SOSClient(defaultBackendUrl);
    _findLocation();
    _restorePending();
    WidgetsBinding.instance.addObserver(this);
    _retryTimer =
        Timer.periodic(const Duration(seconds: 20), (_) => _retryPending());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _retryPending();
  }

  Future<void> _retryPending() async {
    if (!mounted || _sending || _locating) return;
    if (_received && _shareGps && await _client.needsGps()) {
      await _findLocation();
      if (!mounted || _location == null) return;
      final state = context.read<AppState>();
      final id = state.incidentId;
      final token = state.receiptToken;
      if (id != null && token != null) {
        try {
          await _client.updateLocation(
              id: id,
              receiptToken: token,
              latitude: _location!.latitude,
              longitude: _location!.longitude,
              accuracyM: _accuracy);
          if (mounted) {
            setState(() => _locationError =
                'GPS coordinates shared with the response team.');
          }
        } on Exception catch (error) {
          if (mounted) {
            setState(
                () => _locationError = 'GPS has not been shared yet: $error');
          }
        }
      }
      return;
    }
    if (_pending == null) return;
    if (_shareGps && _location == null) await _findLocation();
    if (mounted && !_sending) await _send();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.client == null) {
      final url = context.read<AppState>().backendUrl;
      if (_client.baseUrl != url) {
        _client.close();
        _client = SOSClient(url);
      }
    }
  }

  Future<void> _restorePending() async {
    try {
      final items = await _client.pending();
      if (!mounted || items.isEmpty) return;
      final item = items.first;
      setState(() {
        _pending = item;
        _category = _categories
            .firstWhere(
                (category) =>
                    category.id == item['_ui_category'] ||
                    (item['_ui_category'] == null &&
                        category.api == item['category']),
                orElse: () => _categories.last)
            .id;
        _note = (item['_ui_note'] ?? item['message'] ?? '').toString();
        _urgency = item['urgency'] is num ? (item['urgency'] as num).toInt() : null;
        final address = item['address'];
        if (address is Map) {
          for (final entry in _address.entries) {
            entry.value.text = (address[entry.key] ?? '').toString();
          }
        }
        _shareGps = item['_share_gps'] == true;
        final lat = item['lat'];
        final lon = item['lon'];
        if (lat is num && lon is num) {
          _location = (latitude: lat.toDouble(), longitude: lon.toDouble());
        }
      });
    } on ModuleApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _findLocation({bool requestPermission = false}) async {
    if (_locating) return;
    if (mounted) setState(() => _locating = true);
    SOSLocation? location;
    double? accuracy;
    try {
      if (widget.locate != null) {
        location = await widget.locate!();
      } else {
        final position =
            await currentDevicePosition(requestPermission: requestPermission);
        location = (latitude: position.latitude, longitude: position.longitude);
        accuracy = position.accuracy;
      }
      if (mounted) {
        setState(() => _locationError = location == null
            ? 'GPS is unavailable. Write any address or landmark you know.'
            : null);
      }
    } on Exception catch (error) {
      if (mounted) {
        setState(() => _locationError = error is ModuleApiException
            ? error.message
            : 'Could not get GPS. Write your address or try GPS again.');
      }
    }
    if (!mounted) return;
    setState(() {
      if (location != null) {
        _location = location;
        _accuracy = accuracy;
      }
      _locating = false;
    });
  }

  Future<void> _manualLocation() async {
    final latitude =
        TextEditingController(text: _location?.latitude.toString() ?? '');
    final longitude =
        TextEditingController(text: _location?.longitude.toString() ?? '');
    final formKey = GlobalKey<FormState>();
    final result = await showDialog<SOSLocation>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Enter location manually'),
        content: Form(
          key: formKey,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextFormField(
              controller: latitude,
              keyboardType: const TextInputType.numberWithOptions(
                  decimal: true, signed: true),
              decoration: const InputDecoration(labelText: 'Latitude'),
              validator: (value) => _coordinateError(value, -90, 90),
            ),
            TextFormField(
              controller: longitude,
              keyboardType: const TextInputType.numberWithOptions(
                  decimal: true, signed: true),
              decoration: const InputDecoration(labelText: 'Longitude'),
              validator: (value) => _coordinateError(value, -180, 180),
            ),
          ]),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) {
                Navigator.pop(
                  context,
                  (
                    latitude: double.parse(latitude.text),
                    longitude: double.parse(longitude.text)
                  ),
                );
              }
            },
            child: const Text('Use this location'),
          )
        ],
      ),
    );
    latitude.dispose();
    longitude.dispose();
    if (result != null) {
      setState(() {
        _location = result;
        _accuracy = null;
      });
    }
  }

  String? _coordinateError(String? input, double min, double max) {
    final value = double.tryParse(input ?? '');
    if (value == null || !value.isFinite || value < min || value > max) {
      return 'Enter a value from $min to $max';
    }
    return null;
  }

  Future<void> _send() async {
    if (_sending || (_category == null && _pending == null)) return;
    final state = context.read<AppState>();
    _syncClient(state.backendUrl);
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final category = _categories.firstWhere((item) => item.id == _category);
      final categoryLabel = category.en;
      final result = await _client.submit(
        category: category.api,
        lat: _location?.latitude,
        lon: _location?.longitude,
        accuracyM: _accuracy,
        displayCategory: _category,
        displayNote: _note,
        urgency: _urgency,
        address: {
          for (final entry in _address.entries)
            entry.key: entry.value.text.trim(),
        },
        shareGpsWhenAvailable: _shareGps,
        message: _message(categoryLabel, _note),
        pendingItem: _pending,
      );
      await state.setDelivery(
        status: result['status'] as String,
        label: 'Sent to service station',
        incidentId: result['id'] as int,
        receiptToken: result['receipt_token'] as String,
      );
      if (!mounted) return;
      setState(() {
        _received = true;
        _pending = null;
        _sending = false;
      });
    } catch (error) {
      if (!mounted) return;
      List<Map<String, dynamic>> outbox;
      try {
        outbox = await _client.pending();
      } on ModuleApiException catch (queueError) {
        if (mounted) {
          setState(() {
            _sending = false;
            _error = queueError.message;
          });
        }
        return;
      }
      if (!mounted) return;
      setState(() {
        _pending = outbox.isEmpty ? _pending : outbox.first;
        _sending = false;
        _error = error is ModuleApiException
            ? error.message
            : 'SOS has not been confirmed by the server. Your saved request can be retried.';
      });
      if (outbox.isNotEmpty) {
        await state.setDelivery(
            status: 'queued', label: 'Saved on this device · not received');
      }
    }
  }

  void _syncClient(String url) {
    if (widget.client == null && _client.baseUrl != url) {
      _client.close();
      _client = SOSClient(url);
    }
  }

  String _message(String category, String note) {
    final text = note.trim();
    final message =
        text.isEmpty ? 'Requesting help: $category' : '$category: $text';
    return message.length > 500 ? message.substring(0, 500) : message;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _retryTimer?.cancel();
    for (final controller in _address.values) {
      controller.dispose();
    }
    if (widget.client == null) _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
          title: Text(state.t(context, 'Request help', 'मद्दत माग्नुहोस्'))),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 700),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: _received
                ? [
                    const SizedBox(height: 24),
                    const Icon(Icons.mark_email_read_outlined,
                        color: Color(0xFF75D4A0), size: 56),
                    const SizedBox(height: 20),
                    const Text('SOS sent to service station',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 24, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    Text('SOS #${state.incidentId}',
                        textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    const Text(
                        'The service station has received your request. Coordinators and eligible responders can now see it; dispatch is a separate step.',
                        textAlign: TextAlign.center),
                    if (_shareGps)
                      const Padding(
                          padding: EdgeInsets.only(top: 12),
                          child: Text(
                              'GPS sharing will retry while this screen or SOS status is open. Your written address stays attached.',
                              textAlign: TextAlign.center)),
                    if (_locationError != null)
                      Text(_locationError!, textAlign: TextAlign.center),
                  ]
                : [
                    if (_pending != null)
                      const Card(
                        color: Color(0xFF342F1C),
                        child: ListTile(
                          leading:
                              Icon(Icons.cloud_off, color: Color(0xFFFBC02D)),
                          title: Text('Saved request awaiting delivery'),
                          subtitle: Text(
                              'Not received yet. This screen retries every 20 seconds while open and when you return. The same request ID and written address are kept.'),
                        ),
                      ),
                    Text(state.t(context, 'Type of help', 'सहायताको प्रकार'),
                        style: const TextStyle(
                            fontSize: 22, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 16),
                    LayoutBuilder(
                      builder: (context, constraints) => GridView.count(
                        crossAxisCount: constraints.maxWidth >= 560 ? 4 : 2,
                        mainAxisSpacing: 12,
                        crossAxisSpacing: 12,
                        mainAxisExtent: 128 *
                            MediaQuery.textScalerOf(context)
                                .scale(1)
                                .clamp(1, 1.8),
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        children: _categories.map((category) {
                          final isSelected = _category == category.id;
                          return Semantics(
                            selected: isSelected,
                            child: OutlinedButton(
                              onPressed: _sending || _pending != null
                                  ? null
                                  : () =>
                                      setState(() => _category = category.id),
                              style: OutlinedButton.styleFrom(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 12),
                                backgroundColor: isSelected
                                    ? const Color(0xFF4A2323)
                                    : const Color(0xFF151B1F),
                                foregroundColor: Colors.white,
                                side: BorderSide(
                                    color: isSelected
                                        ? const Color(0xFFFF8D8D)
                                        : const Color(0xFF40505A),
                                    width: isSelected ? 2 : 1),
                              ),
                              child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(category.icon,
                                        size: 28,
                                        color: isSelected
                                            ? const Color(0xFFFFAAAA)
                                            : const Color(0xFFB9C6CD)),
                                    const SizedBox(height: 8),
                                    Text(
                                        state.t(
                                            context, category.en, category.ne),
                                        textAlign: TextAlign.center,
                                        style: const TextStyle(fontSize: 16)),
                                  ]),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                    const SizedBox(height: 20),
                    const Text('How urgent is this?',
                        style: TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    const Text(
                        'Choose a color if you can. If you leave it unset, Rahat AI will assess urgency from your message.'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final level in const [
                          (1, 'Green · can wait', Color(0xFF4CAF7D)),
                          (2, 'Yellow · soon', Color(0xFFFBC02D)),
                          (3, 'Orange · urgent', Color(0xFFFF8A00)),
                          (4, 'Red · high', Color(0xFFE65100)),
                          (5, 'Red · life-threatening', Color(0xFFD32F2F)),
                        ])
                          ChoiceChip(
                            label: Text(level.$2),
                            selected: _urgency == level.$1,
                            selectedColor: level.$3,
                            onSelected: _sending || _pending != null
                                ? null
                                : (selected) => setState(() =>
                                    _urgency = selected ? level.$1 : null),
                          ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                          _location == null
                              ? Icons.location_off_outlined
                              : Icons.my_location,
                          color: _location == null
                              ? const Color(0xFFFBC02D)
                              : const Color(0xFF75D4A0)),
                      title: Text(_locating
                          ? 'Checking GPS'
                          : _location == null
                              ? 'Location unavailable — request can still be sent'
                              : _accuracy == null
                                  ? 'Manual location attached'
                                  : 'GPS location attached'),
                      subtitle: _location == null
                          ? const Text(
                              'Write your location below. You do not need to know GPS coordinates.')
                          : Text(
                              '${_location!.latitude.toStringAsFixed(5)}, ${_location!.longitude.toStringAsFixed(5)}${_accuracy == null ? '' : ' · ±${_accuracy!.round()} m'}'),
                      trailing: Wrap(
                        children: [
                          IconButton(
                              tooltip: 'Use GPS location',
                              onPressed: _sending || _locating
                                  ? null
                                  : () =>
                                      _findLocation(requestPermission: true),
                              icon: const Icon(Icons.my_location)),
                          IconButton(
                              tooltip: 'Enter location manually',
                              onPressed: _sending ? null : _manualLocation,
                              icon: const Icon(Icons.edit_location_alt)),
                        ],
                      ),
                    ),
                    if (_locationError != null && _location == null)
                      Text(_locationError!,
                          style: const TextStyle(color: Color(0xFFFBC02D))),
                    const SizedBox(height: 12),
                    const Text('Where do you need help?',
                        style: TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w600)),
                    const Text(
                        'Fill in what you know. A school, hospital, temple, or other landmark helps rescuers find you. All fields are optional.'),
                    Padding(
                      padding: const EdgeInsets.only(left: 8, top: 12),
                      child: Column(children: [
                        _addressField('district', 'District', 80),
                        Padding(
                          padding: const EdgeInsets.only(left: 12),
                          child: Column(children: [
                            _addressField(
                                'city', 'City / municipality / village', 100),
                            Padding(
                              padding: const EdgeInsets.only(left: 12),
                              child: Column(children: [
                                _addressField('ward', 'Ward', 20),
                                _addressField(
                                    'road', 'Road / street / tole', 120),
                                _addressField('landmark',
                                    'Nearby school, hospital or landmark', 180),
                              ]),
                            ),
                          ]),
                        ),
                      ]),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Share GPS when available'),
                      subtitle: const Text(
                          'Keep this screen or SOS status open. With location permission, GPS can work without internet; coordinates are sent when connected. This is your current device location.'),
                      value: _shareGps,
                      onChanged: _sending || _pending != null
                          ? null
                          : (value) => setState(() => _shareGps = value),
                    ),
                    if (_location != null)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: _sending
                              ? null
                              : () => setState(() {
                                    _location = null;
                                    _accuracy = null;
                                    _shareGps = false;
                                  }),
                          icon: const Icon(Icons.location_off_outlined),
                          label: const Text('Send without location'),
                        ),
                      ),
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('Add details (optional)'),
                      children: [
                        TextField(
                          enabled: !_sending && _pending == null,
                          maxLines: 4,
                          maxLength: 480,
                          decoration: const InputDecoration(
                              labelText: 'What happened?',
                              alignLabelWithHint: true),
                          onChanged: (value) => _note = value,
                        )
                      ],
                    ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 16),
                        child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Icon(Icons.error_outline,
                                  color: Color(0xFFFF9D9D)),
                              const SizedBox(width: 10),
                              Expanded(
                                  child: Text(_error!,
                                      style: const TextStyle(
                                          color: Color(0xFFFFB4B4)))),
                            ]),
                      ),
                  ],
          ),
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Container(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
          decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: Color(0xFF263038)))),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(56),
                  backgroundColor: _received
                      ? const Color(0xFF4CAF7D)
                      : const Color(0xFFD32F2F),
                  foregroundColor: Colors.white),
              onPressed: _received
                  ? () => Navigator.pushReplacementNamed(context, '/status')
                  : (_category == null && _pending == null) || _sending
                      ? null
                      : _send,
              icon: _sending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white))
                  : Icon(_received ? Icons.timeline : Icons.send),
              label: Text(_received
                  ? 'View request status'
                  : _sending
                      ? 'Sending request'
                      : _pending != null
                          ? 'Retry saved SOS'
                          : 'Send SOS'),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
                onPressed: () => showModalBottomSheet<void>(
                    context: context,
                    isScrollControlled: true,
                    builder: (_) => const SafeArea(
                        child: SingleChildScrollView(
                            padding: EdgeInsets.all(20),
                            child: EmergencyCalls()))),
                icon: const Icon(Icons.call),
                label: const Text('Emergency calls')),
          ]),
        ),
      ),
    );
  }

  Widget _addressField(String key, String label, int maxLength) => Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
          key: ValueKey('address_$key'),
          controller: _address[key],
          enabled: !_sending && _pending == null,
          maxLength: maxLength,
          decoration: InputDecoration(
              labelText: label,
              counterText: '',
              border: const OutlineInputBorder())));
}

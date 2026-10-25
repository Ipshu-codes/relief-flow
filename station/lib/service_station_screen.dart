import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:rahat_mobile/app_state.dart';
import 'package:rahat_mobile/module_api.dart';

/// Rahat Service Station — Station E.
///
/// A dedicated station-level dashboard that only handles *services* (service
/// requests coming in and service offerings going out). It intentionally uses
/// service-station language throughout ("service request", "acknowledge",
/// "fulfill", "assign", "dispatch") and avoids any end-user "request service"
/// or SOS wording.
///
/// Visual design mirrors the Rahat command-station dashboard (dark panels,
/// severity colour coding, priority queue) tailored to a single station level
/// (Station E).
class ServiceStationScreen extends StatefulWidget {
  final ModuleApi? api;
  const ServiceStationScreen({super.key, this.api});

  @override
  State<ServiceStationScreen> createState() => _ServiceStationScreenState();
}

class _ServiceStationScreenState extends State<ServiceStationScreen> {
  late final ModuleApi _api;
  Timer? _refreshTimer;

  // ---------- Station identity ----------
  static const String _stationName = 'Station E';
  static const String _stationCode = 'RAHAT-E';

  // ---------- Data ----------
  Map<String, dynamic>? _user;
  int? _incidentId;
  List<Map<String, dynamic>> _serviceRequests = []; // needs from backend
  List<Map<String, dynamic>> _serviceOfferings = []; // help offers from backend
  List<Map<String, dynamic>> _assignments = [];
  List<Map<String, dynamic>> _stock = [];
  List<Map<String, dynamic>> _locations = [];
  String? _error;
  bool _busy = false;

  // ---------- Tab state ----------
  int _tabIndex = 0; // 0 = Operations, 1 = Insights, 2 = Mesh Lab
  Map<String, dynamic>? _selectedRequest;

  // Service category quick filters (service-focused labels).
  static const List<Map<String, dynamic>> _categories = [
    {'id': 'medical', 'name': 'Medical', 'icon': Icons.local_hospital, 'color': Color(0xFF4CAF7D)},
    {'id': 'food_water', 'name': 'Food & Water', 'icon': Icons.restaurant, 'color': Color(0xFFFBC02D)},
    {'id': 'shelter', 'name': 'Shelter', 'icon': Icons.house, 'color': Color(0xFF3A86FF)},
    {'id': 'transport', 'name': 'Transport', 'icon': Icons.directions_car, 'color': Color(0xFF9B5DE5)},
    {'id': 'other', 'name': 'Other Services', 'icon': Icons.build, 'color': Color(0xFFADB9BF)},
  ];

  String? _selectedCategoryId;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? ModuleApi();
    _refreshTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      if (mounted && _user != null && !_busy) _run(_loadAll);
    });
    _run(_loadAll);
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _api.close();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() operation) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await operation();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadAll() async {
    final user = Map<String, dynamic>.from(await _api.request('/auth/me'));
    final workspace = Map<String, dynamic>.from(await _api.request('/workspace'));

    final incidents = (workspace['incidents'] as List? ?? [])
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
    final selected = incidents.any((row) => row['id'] == _incidentId)
        ? _incidentId
        : incidents.isEmpty ? null : incidents.first['id'] as int;

    final query = selected == null ? '' : '?incident_id=$selected';
    final needsRaw = await _api.request('/needs$query');
    final offersRaw = await _api.request('/help/offers');
    final assignmentsRaw = await _api.request('/assignments$query');
    final stockRaw = await _api.request('/resources/stock');
    final locationsRaw = await _api.request('/locations');

    List<Map<String, dynamic>> parseList(dynamic data) {
      if (data == null) return <Map<String, dynamic>>[];
      final list = data;
      return (list as List).map((item) => Map<String, dynamic>.from(item as Map)).toList();
    }

    if (!mounted) return;
    setState(() {
      _user = user;
      _incidentId = selected;
      _serviceRequests = parseList(needsRaw)
          .where((item) {
            if (_selectedCategoryId == null) return true;
            return item['category'] == _selectedCategoryId;
          })
          .toList();
      _serviceOfferings = parseList(offersRaw);
      _assignments = parseList(assignmentsRaw);
      _stock = parseList(stockRaw);
      _locations = parseList(locationsRaw);
    });
  }

  String _locationName(dynamic id) {
    if (id == null) return 'Location not set';
    try {
      return _locations.firstWhere((row) => row['id'] == id)['name'] as String;
    } catch (_) {
      return 'Location #$id';
    }
  }

  String _label(dynamic value) =>
      (value ?? 'Unknown').toString().replaceAll('_', ' ');

  Color _severityColor(String severity) {
    switch (severity.toLowerCase()) {
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

  // Map backend urgency (1-5) to a severity label for colour coding.
  String _urgencyLabel(num urgency) {
    final u = (urgency as num).toInt();
    if (u >= 4) return 'critical';
    if (u == 3) return 'high';
    if (u == 2) return 'medium';
    return 'low';
  }

  // ---------- Actions (service-station language) ----------
  Future<void> _acknowledgeRequest(Map<String, dynamic> request) async {
    await _run(() async {
      await _api.request('/needs/${request['id']}', method: 'PATCH', body: {
        'verification_status': 'verified',
        'confidence': 'high',
      });
    });
  }

  Future<void> _fulfillRequest(Map<String, dynamic> request) async {
    final controller = TextEditingController(
        text: '${request['quantity_requested'] ?? 1}');
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Fulfill Service'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(
              'Service #${request['id']} · ${_label(request['category'])}'),
          const SizedBox(height: 12),
          TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: 'Quantity fulfilled',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.numberWithOptions(decimal: true),
          ),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Confirm fulfillment')),
        ],
      ),
    );
    if (confirmed != true) return;
    await _run(() async {
      final quantity = double.tryParse(controller.text.trim()) ??
          (request['quantity_requested'] as num? ?? 0).toDouble();
      await _api.request('/needs/${request['id']}', method: 'PATCH', body: {
        'quantity_fulfilled': quantity,
        'status': 'fulfilled',
        'verification_status': 'verified',
      });
    });
  }

  Future<void> _assignVolunteer(Map<String, dynamic> request) async {
    final available = _assignments
        .where((a) {
          final status = a['status'] as String?;
          return status == 'proposed' ||
              status == 'accepted' ||
              status == 'en_route' ||
              status == 'on_site';
        })
        .toList();
    if (available.isEmpty) {
      setState(() => _error = 'No active assignment available for this service.');
      return;
    }
    final selectedId = await showDialog<int?>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: const Text('Assign Service'),
        children: [
          for (final a in available)
            ListTile(
              title: Text('Assignment #${a['id']}'),
              subtitle: Text(
                  'Volunteer ${a['volunteer_id']} · ${_label(a['status'])}'),
              onTap: () => Navigator.pop(dialogContext, a['id'] as int),
            ),
        ],
      ),
    );
    if (selectedId == null) return;
    await _run(() async {
      await _api.request('/assignments/$selectedId/confirm', method: 'POST', body: {
        'status': 'en_route',
      });
    });
  }

  Future<void> _claimOffer(Map<String, dynamic> offer) async {
    if (offer['offered_by'] == _user?['id']) return;
    await _run(() async {
      await _api.request('/help/offers/${offer['id']}/claim', method: 'POST');
    });
  }

  // ---------- Widgets ----------
  Widget _statCard(String title, String value, IconData icon, Color color) =>
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF151B1F),
          border: Border.all(color: const Color(0xFF263038)),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 13,
                  backgroundColor: color.withValues(alpha: 0.18),
                  child: Icon(icon, size: 18, color: color),
                ),
                const Spacer(),
              ],
            ),
            const SizedBox(height: 10),
            Text(value,
                style: const TextStyle(
                    fontSize: 24, fontWeight: FontWeight.w800, color: Colors.white)),
            const SizedBox(height: 4),
            Text(title,
                style: const TextStyle(
                    fontSize: 12, color: Color(0xFF9AA9B3), height: 1.3)),
          ],
        ),
      );

  Widget _categoryChip(Map<String, dynamic> category) {
    final selected = _selectedCategoryId == category['id'];
    return FilterChip(
      label: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(category['icon'], size: 16,
              color: selected ? Colors.white : category['color']),
          const SizedBox(width: 6),
          Text(category['name']),
        ],
      ),
      selected: selected,
      onSelected: (value) => setState(() =>
          _selectedCategoryId = selected ? null : category['id'] as String),
      backgroundColor: const Color(0xFF151B1F),
      selectedColor: category['color'],
      checkmarkColor: Colors.white,
      labelStyle: TextStyle(
        color: selected ? Colors.white : category['color'],
        fontWeight: FontWeight.w600,
      ),
      side: BorderSide(
        color: selected ? category['color'] : const Color(0xFF263038),
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    );
  }

  Widget _requestCard(Map<String, dynamic> request) {
    final urgency = (request['urgency'] as num? ?? 3);
    final severity = _urgencyLabel(urgency);
    final color = _severityColor(severity);
    final isSelected = _selectedRequest != null &&
        _selectedRequest!['id'] == request['id'];

    return InkWell(
      onTap: () => setState(() => _selectedRequest = request),
      borderRadius: BorderRadius.circular(10),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: const Color(0xFF151B1F),
          border: Border(
            left: BorderSide(color: color, width: 5),
            right: BorderSide(
                color: isSelected ? color : const Color(0xFF263038),
                width: isSelected ? 2 : 1),
            top: BorderSide(
                color: isSelected ? color : const Color(0xFF263038),
                width: isSelected ? 2 : 1),
            bottom: BorderSide(
                color: isSelected ? color : const Color(0xFF263038),
                width: isSelected ? 2 : 1),
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                            'Service #${request['id']} · ${_label(request['category'])}',
                            style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: Colors.white)),
                        const SizedBox(height: 4),
                        Text(
                            '${_locationName(request['location_id'])} · ${_label(request['status'])}',
                            style: const TextStyle(
                                fontSize: 12, color: Color(0xFF9AA9B3))),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.18),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text('Urgency $urgency/5',
                        style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: color)),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              if (request['description'] != null &&
                  request['description'].toString().isNotEmpty)
                Text(request['description'].toString(),
                    style: const TextStyle(
                        fontSize: 13, color: Color(0xFFE8EAED), height: 1.4)),
              const SizedBox(height: 10),
              Row(
                children: [
                  _chip('${request['quantity_requested']} ${request['unit']}'),
                  const SizedBox(width: 8),
                  _chip('${_label(request['verification_status'])} · ${_label(request['confidence'])}',
                      warning: request['verification_status'] != 'verified'),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _serviceButton('Acknowledge', Icons.fact_check_outlined,
                      const Color(0xFF3A86FF), () => _acknowledgeRequest(request)),
                  _serviceButton('Fulfill', Icons.check_circle_outline,
                      const Color(0xFF4CAF7D), () => _fulfillRequest(request)),
                  _serviceButton('Assign', Icons.person_add_alt,
                      const Color(0xFFFBC02D), () => _assignVolunteer(request)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(String text, {bool warning = false}) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: warning ? const Color(0xFF342F1C) : const Color(0xFF18362A),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(text,
            style: TextStyle(
                fontSize: 11,
                color: warning
                    ? const Color(0xFFFBC02D)
                    : const Color(0xFF75D4A0))),
      );

  Widget _serviceButton(String label, IconData icon, Color color,
          VoidCallback onPressed) =>
      FilledButton.icon(
        onPressed: _busy ? null : onPressed,
        icon: Icon(icon, size: 16),
        label: Text(label, style: const TextStyle(fontSize: 12)),
        style: FilledButton.styleFrom(
          backgroundColor: color,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      );

  Widget _offerCard(Map<String, dynamic> offer) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF151B1F),
        border: Border.all(color: const Color(0xFF263038)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                          'Service Offer · ${_label(offer['category'])}',
                          style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: Colors.white)),
                      const SizedBox(height: 4),
                      Text('${offer['quantity']} ${offer['unit']}',
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xFF9AA9B3))),
                    ],
                  ),
                ),
                _chip(_label(offer['status'])),
              ],
            ),
            const SizedBox(height: 8),
            if (offer['description'] != null &&
                offer['description'].toString().isNotEmpty)
              Text(offer['description'].toString(),
                  style: const TextStyle(
                      fontSize: 13, color: Color(0xFFE8EAED), height: 1.4)),
            const SizedBox(height: 8),
            Text('Available at: ${offer['location_text']}',
                style: const TextStyle(
                    fontSize: 12, color: Color(0xFF9AA9B3))),
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _busy ? null : () => _claimOffer(offer),
                child: const Text('Claim Offer'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _emptyState(String title, String subtitle, IconData icon) => Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 56, color: const Color(0xFF9AA9B3)),
            const SizedBox(height: 14),
            Text(title,
                style: const TextStyle(
                    fontSize: 17, fontWeight: FontWeight.w600, color: Colors.white)),
            const SizedBox(height: 6),
            Text(subtitle,
                style: const TextStyle(
                    fontSize: 13, color: Color(0xFF9AA9B3)),
                textAlign: TextAlign.center),
          ],
        ),
      );

  // ---------- Tabs ----------
  Widget _tabButton(int index, String label, IconData icon) {
    final active = _tabIndex == index;
    return InkWell(
      onTap: () => setState(() => _tabIndex = index),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: active ? const Color(0xFF1B2328) : Colors.transparent,
          border: Border.all(
              color: active ? const Color(0xFF4CAF7D) : Colors.transparent),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16,
                color: active ? const Color(0xFF4CAF7D) : const Color(0xFF9AA9B3)),
            const SizedBox(width: 6),
            Text(label,
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: active ? Colors.white : const Color(0xFF9AA9B3))),
          ],
        ),
      ),
    );
  }

  Widget _pill(String label, Color color, String value) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: const Color(0xFF1B2328),
          border: Border.all(color: const Color(0xFF263038)),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
            Text('$label: $value',
                style: const TextStyle(
                    fontSize: 12, color: Color(0xFF9AA9B3))),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final activeRequests = _serviceRequests
        .where((r) => !['fulfilled', 'closed', 'rejected'].contains(r['status']))
        .toList();
    final fulfilled = _serviceRequests
        .where((r) => r['status'] == 'fulfilled')
        .toList();

    return Scaffold(
      backgroundColor: const Color(0xFF0D1114),
      // ---------- Topbar (dashboard style) ----------
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(64),
        child: Container(
          color: const Color(0xFF151B1F),
          child: SafeArea(
            child: Column(
              children: [
                const SizedBox(height: 4),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          // Brand mark + name.
                          const Text('🐸', style: TextStyle(fontSize: 26)),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Row(
                                  children: [
                                    const Text('Rahat ',
                                        style: TextStyle(
                                            fontSize: 19,
                                            fontWeight: FontWeight.w800,
                                            color: Colors.white)),
                                    Text('राहत',
                                        style: const TextStyle(
                                            fontSize: 15,
                                            fontWeight: FontWeight.w500,
                                            color: Color(0xFF9AA9B3))),
                                  ],
                                ),
                                const SizedBox(height: 2),
                                Text('$_stationName · $_stationCode',
                                    style: const TextStyle(
                                        fontSize: 11,
                                        color: Color(0xFF9AA9B3),
                                        letterSpacing: 1)),
                              ],
                            ),
                          ),
                          // Tabs.
                          _tabButton(0, 'Operations', Icons.list_alt_outlined),
                          const SizedBox(width: 6),
                          _tabButton(1, 'Insights', Icons.analytics_outlined),
                          const SizedBox(width: 6),
                          _tabButton(2, 'Mesh Lab', Icons.wifi_outlined),
                          const Spacer(),
                          // Health pills.
                          Consumer<AppState>(
                            builder: (_, appState, __) => Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                _pill('Station', const Color(0xFF388E3C), 'online'),
                                const SizedBox(width: 8),
                                _pill('AI', const Color(0xFF9AA9B3), 'mock'),
                                const SizedBox(width: 8),
                                _pill('Mesh', const Color(0xFF9AA9B3), 'offline'),
                              ],
                            ),
                          ),
                          const SizedBox(width: 12),
                          Consumer<AppState>(
                            builder: (_, appState, __) => IconButton(
                              tooltip: 'Language',
                              icon: Text(appState.t(context, 'English', 'English'),
                                  style: const TextStyle(fontSize: 12)),
                              onPressed: () => showDialog<String>(
                                context: context,
                                builder: (d) => AlertDialog(
                                  title: const Text('Language'),
                                  content: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      ListTile(
                                        title: const Text('English'),
                                        onTap: () {
                                          Navigator.pop(d);
                                          context.read<AppState>().setLocale('en');
                                        },
                                      ),
                                      ListTile(
                                        title: const Text('नेपाली'),
                                        onTap: () {
                                          Navigator.pop(d);
                                          context.read<AppState>().setLocale('ne');
                                        },
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          IconButton(
                            tooltip: 'Refresh',
                            icon: const Icon(Icons.refresh, size: 18),
                            onPressed: _busy ? null : () => _run(_loadAll),
                          ),
                        ],
                      ),
                      // Error banner.
                      if (_error != null)
                        Container(
                          margin: const EdgeInsets.only(top: 8),
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: const Color(0xFF2B1B1B),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            children: [
                              const Icon(Icons.error_outline,
                                  size: 16, color: Color(0xFFD32F2F)),
                              const SizedBox(width: 8),
                              Expanded(
                                  child: Text(_error!,
                                      style: const TextStyle(
                                          fontSize: 12,
                                          color: Color(0xFFFFB3B3)))),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 4),
              ],
            ),
          ),
        ),
      ),
      // ---------- Body ----------
      body: RefreshIndicator(
        onRefresh: () => _run(_loadAll),
        color: const Color(0xFF4CAF7D),
        child: _tabIndex == 0 ? _operationsBody(activeRequests, fulfilled) : _placeholderTab(),
      ),
    );
  }

  Widget _operationsBody(List<Map<String, dynamic>> activeRequests,
      List<Map<String, dynamic>> fulfilled) {
    return CustomScrollView(
      slivers: [
        // Stat cards.
        SliverToBoxAdapter(
          child: Container(
            margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Column(
              children: [
                const SizedBox(height: 8),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Row(
                    children: [
                      Expanded(child: _statCard('Active Service Requests',
                          activeRequests.length.toString(), Icons.list_alt,
                          const Color(0xFFFBC02D))),
                      const SizedBox(width: 10),
                      Expanded(child: _statCard('Fulfilled',
                          fulfilled.length.toString(), Icons.check_circle,
                          const Color(0xFF4CAF7D))),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Row(
                    children: [
                      Expanded(child: _statCard('Service Offerings',
                          _serviceOfferings.length.toString(), Icons.local_offer,
                          const Color(0xFF3A86FF))),
                      const SizedBox(width: 10),
                      Expanded(child: _statCard('Stock Items',
                          _stock.length.toString(), Icons.inventory,
                          const Color(0xFF9B5DE5))),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),

        // Category filters.
        SliverToBoxAdapter(
          child: Container(
            margin: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Service Categories',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: Colors.white)),
                const SizedBox(height: 8),
                SizedBox(
                  height: 42,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    children: _categories.map(_categoryChip).toList(),
                  ),
                ),
              ],
            ),
          ),
        ),

        // Active Service Requests (priority queue).
        SliverToBoxAdapter(
          child: Container(
            margin: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Active Service Requests',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: Colors.white)),
                TextButton(
                  onPressed: _busy ? null : () => _run(_loadAll),
                  child: const Text('Refresh'),
                ),
              ],
            ),
          ),
        ),
        if (activeRequests.isEmpty)
          SliverToBoxAdapter(
              child: Padding(
            padding: const EdgeInsets.all(20),
            child: _emptyState('No service requests',
                'Station E has no active service requests at the moment.',
                Icons.inbox),
          ))
        else
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (context, index) => _requestCard(activeRequests[index]),
              childCount: activeRequests.length,
            ),
          ),

        // Service Offerings.
        SliverToBoxAdapter(
          child: Container(
            margin: const EdgeInsets.fromLTRB(16, 22, 16, 8),
            child: const Text('Available Service Offerings',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: Colors.white)),
          ),
        ),
        if (_serviceOfferings.isEmpty)
          SliverToBoxAdapter(
              child: Padding(
            padding: const EdgeInsets.all(20),
            child: _emptyState('No service offerings',
                'No services are currently being offered nearby.',
                Icons.local_offer_outlined),
          ))
        else
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (context, index) => _offerCard(_serviceOfferings[index]),
              childCount: _serviceOfferings.length,
            ),
          ),

        const SliverToBoxAdapter(child: SizedBox(height: 24)),
      ],
    );
  }

  Widget _placeholderTab() {
    final titles = ['Insights', 'Mesh Lab'];
    final subtitles = [
      'Bottlenecks, underserved zones, and supply gaps are computed in Phase 3.',
      'The virtual mesh arrives in Phase 1: toggle nodes and links, send a service request, watch it queue offline, then sync when a peer reconnects.',
    ];
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.build_outlined, size: 56, color: const Color(0xFF9AA9B3)),
          const SizedBox(height: 16),
          Text(titles[_tabIndex - 1],
              style: const TextStyle(
                  fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 8),
          Text(subtitles[_tabIndex - 1],
              style: const TextStyle(fontSize: 14, color: Color(0xFF9AA9B3)),
              textAlign: TextAlign.center),
        ],
      ),
    );
  }
}

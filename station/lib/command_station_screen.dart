import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:rahat_mobile/module_api.dart';

import 'station_map_widget.dart';

class CommandStationScreen extends StatefulWidget {
  const CommandStationScreen({super.key});

  @override
  State<CommandStationScreen> createState() => _CommandStationScreenState();
}

class _CommandStationScreenState extends State<CommandStationScreen> {
  final _api = ModuleApi();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _areaFilter = TextEditingController();
  final Set<int> _reassigning = {};
  Timer? _refreshTimer;
  Map<String, dynamic>? _user;
  List<Map<String, dynamic>> _incidents = [];
  List<Map<String, dynamic>> _needs = [];
  List<Map<String, dynamic>> _assignments = [];
  List<Map<String, dynamic>> _offers = [];
  List<Map<String, dynamic>> _volunteers = [];
  List<Map<String, dynamic>> _locations = [];
  List<Map<String, dynamic>> _sos = [];
  Map<String, dynamic>? _selectedNeed;
  Map<String, dynamic>? _selectedSos;
  List<Map<String, dynamic>> _matches = [];
  int? _incidentFilter;
  int _page = 0;
  int _requestSection = 0;
  int _requestSubpage = 0;
  String? _categoryFilter;
  String? _disasterTypeFilter;
  String? _statusFilter;
  String? _sosStatusFilter;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _api.close();
    _email.dispose();
    _password.dispose();
    _areaFilter.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> _rows(dynamic value) => (value as List? ?? [])
      .whereType<Map>()
      .map((row) => Map<String, dynamic>.from(row))
      .toList();

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

  Future<void> _signIn() => _run(() async {
    final user = await _api.login(_email.text, _password.text);
    if (!['admin', 'coordinator'].contains(user['role'])) {
      _api.token = null;
      throw const ModuleApiException(
        'Sign in with an admin or coordinator account to use the command station.',
      );
    }
    if (!mounted) return;
    setState(() => _user = user);
    _password.clear();
    await _refresh();
    _refreshTimer ??= Timer.periodic(const Duration(seconds: 20), (_) {
      if (mounted && !_busy && _user != null) _run(_refresh);
    });
  });

  Future<void> _refresh() async {
    final workspace = Map<String, dynamic>.from(
      await _api.request('/workspace'),
    );
    final needsData = await _api.request('/needs?limit=200');
    final assignments = await _api.request('/assignments?limit=200');
    final offers = await _api.request('/help/offers?status=open&limit=100');
    final volunteers = await _api.request('/volunteers?limit=100');
    final sos = await _api.request('/sos?limit=100');
    if (!mounted) return;
    setState(() {
      _incidents = _rows(workspace['incidents']);
      _locations = _rows(workspace['locations']);
      _needs = _rows((needsData as Map)['items']);
      _assignments = _rows(assignments);
      _offers = _rows(offers);
      _volunteers = _rows(volunteers);
      _sos = _rows(sos);
      if (_incidentFilter != null &&
          !_incidents.any((row) => row['id'] == _incidentFilter)) {
        _incidentFilter = null;
      }
      if (_selectedNeed != null) {
        _selectedNeed = _needs
            .where((row) => row['id'] == _selectedNeed!['id'])
            .firstOrNull;
      }
      if (_selectedSos != null) {
        _selectedSos = _sos
            .where((row) => row['id'] == _selectedSos!['id'])
            .firstOrNull;
      }
    });
    await _autoReassignExpired();
  }

  String _label(dynamic value) =>
      (value ?? 'Unknown').toString().replaceAll('_', ' ');

  String _place(dynamic locationId) {
    final location = _locations
        .where((row) => row['id'] == locationId)
        .firstOrNull;
    return location?['name']?.toString() ?? 'Area not recorded';
  }

  Map<String, dynamic>? _incident(int? id) =>
      _incidents.where((row) => row['id'] == id).firstOrNull;

  List<String> get _incidentTypes =>
      _incidents
          .map((row) => row['incident_type']?.toString())
          .whereType<String>()
          .toSet()
          .toList()
        ..sort();

  Set<int>? get _mapIncidentIds =>
      _incidentFilter == null && _disasterTypeFilter != null
      ? _incidents
            .where((row) => row['incident_type'] == _disasterTypeFilter)
            .map((row) => row['id'] as int)
            .toSet()
      : null;

  void _setIncidentFilter(int? incidentId) => setState(() {
    _incidentFilter = incidentId;
    if (incidentId != null) _disasterTypeFilter = null;
    _selectedNeed = null;
    _matches = [];
  });

  void _setDisasterTypeFilter(String? type) => setState(() {
    _disasterTypeFilter = type;
    _selectedNeed = null;
    _matches = [];
  });

  List<Map<String, dynamic>> get _visibleNeeds =>
      _needs.where((need) {
        if (_incidentFilter != null && need['incident_id'] != _incidentFilter) {
          return false;
        }
        final incident = _incident(need['incident_id'] as int?);
        if (_disasterTypeFilter != null &&
            incident?['incident_type'] != _disasterTypeFilter) {
          return false;
        }
        if (_categoryFilter != null && need['category'] != _categoryFilter) {
          return false;
        }
        if (_statusFilter != null && need['status'] != _statusFilter)
          return false;
        final query = _areaFilter.text.trim().toLowerCase();
        final haystack =
            '${_place(need['location_id'])} ${incident?['name'] ?? ''} ${incident?['incident_type'] ?? ''} ${incident?['affected_area'] ?? ''} ${need['description'] ?? ''}'
                .toLowerCase();
        return query.isEmpty || haystack.contains(query);
      }).toList()..sort(
        (a, b) => ((b['urgency'] as num?) ?? 0).compareTo(
          (a['urgency'] as num?) ?? 0,
        ),
      );

  List<Map<String, dynamic>> get _visibleSos =>
      _sos.where((event) {
        if (_incidentFilter != null && event['incident_id'] != _incidentFilter)
          return false;
        final incident = _incident(event['incident_id'] as int?);
        if (_disasterTypeFilter != null &&
            incident?['incident_type'] != _disasterTypeFilter) {
          return false;
        }
        if (_sosStatusFilter != null && event['status'] != _sosStatusFilter)
          return false;
        final query = _areaFilter.text.trim().toLowerCase();
        final address = event['address'] is Map
            ? (event['address'] as Map).values.join(' ')
            : '';
        final interpretation = event['interpretation'] is Map
            ? event['interpretation'] as Map
            : const {};
        final area =
            '${address} ${interpretation['location_text'] ?? ''} ${incident?['name'] ?? ''} ${incident?['incident_type'] ?? ''} ${event['message'] ?? ''}'
                .toLowerCase();
        return query.isEmpty || area.contains(query);
      }).toList()..sort(
        (a, b) => ((b['urgency'] as num?) ?? 0).compareTo(
          (a['urgency'] as num?) ?? 0,
        ),
      );

  List<Map<String, dynamic>> _needAssignments(Map<String, dynamic> need) =>
      _assignments.where((row) => row['need_id'] == need['id']).toList();

  bool _responseExpired(Map<String, dynamic> assignment) {
    if (assignment['status'] == 'rejected') return true;
    final responseAt = DateTime.tryParse(
      '${assignment['updated_at'] ?? assignment['created_at'] ?? ''}',
    );
    return responseAt != null &&
        DateTime.now().toUtc().difference(responseAt.toUtc()) >=
            const Duration(minutes: 15);
  }

  List<Map<String, dynamic>> _needOffers(Map<String, dynamic> need) => _offers
      .where(
        (offer) =>
            offer['need_id'] == need['id'] ||
            (offer['need_id'] == null &&
                offer['category'] == need['category'] &&
                offer['incident_id'] == need['incident_id']),
      )
      .toList();

  Future<void> _match(Map<String, dynamic> need) => _run(() async {
    final result = await _api.request(
      '/needs/${need['id']}/match?explain=true',
      method: 'POST',
    );
    setState(() {
      _selectedNeed = need;
      _matches = _rows((result as Map)['candidates']);
      _page = 1;
      _requestSection = 1;
    });
  });

  Future<void> _aiAssign(Map<String, dynamic> need) => _run(() async {
    final result = Map<String, dynamic>.from(
      await _api.request(
        '/needs/${need['id']}/assignment-proposal',
        method: 'POST',
      ),
    );
    final assignment = Map<String, dynamic>.from(result['assignment']);
    await _api.request(
      '/assignments/${assignment['id']}/approve',
      method: 'POST',
    );
    await _refresh();
    if (!mounted) return;
    final selected = Map<String, dynamic>.from(result['selected_candidate']);
    final route = Map<String, dynamic>.from(selected['route']);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'AI assigned volunteer #${selected['volunteer_id']} · ${route['distance_km']} km, ${route['duration_min']} min. Waiting for their response.',
        ),
        duration: const Duration(seconds: 6),
      ),
    );
    setState(() {
      _selectedNeed = need;
      _page = 1;
      _requestSection = 0;
      _requestSubpage = 1;
    });
  });

  Future<void> _assign(
    Map<String, dynamic> need,
    int volunteerId,
  ) => _run(() async {
    final assignment = Map<String, dynamic>.from(
      await _api.request(
        '/assignments',
        method: 'POST',
        body: {'need_id': need['id'], 'volunteer_id': volunteerId},
      ),
    );
    await _api.request(
      '/assignments/${assignment['id']}/approve',
      method: 'POST',
    );
    await _refresh();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Assignment #${assignment['id']} is active and waiting for the professional to accept.',
        ),
      ),
    );
  });

  Future<void> _assignmentAction(
    Map<String, dynamic> assignment,
    String action, {
    String method = 'POST',
    Map<String, dynamic>? body,
  }) => _run(() async {
    await _api.request(
      '/assignments/${assignment['id']}/$action',
      method: method,
      body: body,
    );
    await _refresh();
  });

  Future<void> _sosState(Map<String, dynamic> event, String state) =>
      _run(() async {
        await _api.request(
          '/sos/${event['id']}/state',
          method: 'PATCH',
          body: {'state': state},
        );
        await _refresh();
      });

  Future<void> _claimOffer(Map<String, dynamic> offer) => _run(() async {
    await _api.request('/help/offers/${offer['id']}/claim', method: 'POST');
    await _refresh();
  });

  double? _distance(Map<String, dynamic>? from, Map<String, dynamic>? to) {
    final lat1 = from?['latitude'];
    final lon1 = from?['longitude'];
    final lat2 = to?['latitude'];
    final lon2 = to?['longitude'];
    if ([lat1, lon1, lat2, lon2].any((value) => value is! num)) return null;
    const radius = 6371.0;
    final p1 = (lat1 as num).toDouble() * math.pi / 180;
    final p2 = (lat2 as num).toDouble() * math.pi / 180;
    final dp = p2 - p1;
    final dl =
        ((lon2 as num).toDouble() - (lon1 as num).toDouble()) * math.pi / 180;
    final h =
        math.sin(dp / 2) * math.sin(dp / 2) +
        math.cos(p1) * math.cos(p2) * math.sin(dl / 2) * math.sin(dl / 2);
    return radius * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h));
  }

  Color _urgencyColor(dynamic value) {
    final urgency = (value as num? ?? 2).toInt();
    if (urgency >= 5) return const Color(0xFFD32F2F);
    if (urgency >= 4) return const Color(0xFFF57C00);
    if (urgency >= 3) return const Color(0xFFFBC02D);
    return const Color(0xFF4CAF7D);
  }

  Widget _panel({
    required Widget child,
    EdgeInsets padding = const EdgeInsets.all(16),
  }) => Container(
    padding: padding,
    decoration: BoxDecoration(
      color: const Color(0xFF151B1F),
      border: Border.all(color: const Color(0xFF263038)),
      borderRadius: BorderRadius.circular(10),
    ),
    child: child,
  );

  Widget _badge(String value, {Color? color}) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: (color ?? const Color(0xFF4CAF7D)).withValues(alpha: .15),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(
      value,
      style: TextStyle(color: color ?? const Color(0xFF75D4A0), fontSize: 12),
    ),
  );

  Widget _login() => Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 420),
      child: _panel(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.hub_outlined, size: 46, color: Color(0xFF4CAF7D)),
            const SizedBox(height: 8),
            const Text(
              'Rahat Command Station',
              style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 20),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Color(0xFFFF8A80)),
                ),
              ),
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Coordinator email'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _password,
              obscureText: true,
              onSubmitted: (_) => _signIn(),
              decoration: const InputDecoration(labelText: 'Password'),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _busy ? null : _signIn,
                icon: const Icon(Icons.login),
                label: const Text('Sign in to station'),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _topTabs() => Wrap(
    spacing: 6,
    children: [
      _tab(0, 'Operations', Icons.radar),
      _tab(1, 'Request & Response', Icons.assignment_outlined),
      _tab(2, 'Insights', Icons.analytics_outlined),
      _tab(3, 'Mesh Lab', Icons.wifi_outlined),
    ],
  );

  Widget _tab(int index, String title, IconData icon) => TextButton.icon(
    onPressed: () => setState(() => _page = index),
    icon: Icon(icon, color: _page == index ? const Color(0xFF4CAF7D) : null),
    label: Text(
      title,
      style: TextStyle(
        color: _page == index ? Colors.white : const Color(0xFFADB9BF),
      ),
    ),
  );

  String _address(dynamic value) {
    if (value is! Map) return 'Area not recorded';
    final parts = ['district', 'city', 'ward', 'road', 'landmark']
        .map((key) => value[key])
        .where((item) => item != null && item.toString().trim().isNotEmpty)
        .map((item) => item.toString())
        .toList();
    return parts.isEmpty ? 'Area not recorded' : parts.join(' · ');
  }

  Widget _operations() {
    final events = _visibleSos;
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 1000;
        final mapHeight = compact
            ? 360.0
            : constraints.maxHeight.isFinite
            ? constraints.maxHeight
            : 620.0;
        final queue = _panel(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'EMERGENCY REQUEST QUEUE',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                  _badge(
                    '${events.length} requests',
                    color: const Color(0xFFF57C00),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<int?>(
                value: _incidentFilter,
                decoration: const InputDecoration(
                  labelText: 'Disaster / incident',
                ),
                items: [
                  const DropdownMenuItem<int?>(
                    value: null,
                    child: Text('All incidents'),
                  ),
                  ..._incidents.map(
                    (row) => DropdownMenuItem<int?>(
                      value: row['id'] as int,
                      child: Text(
                        '${row['incident_type'] ?? row['name']} · ${row['name']}',
                      ),
                    ),
                  ),
                ],
                onChanged: _setIncidentFilter,
              ),
              DropdownButtonFormField<String?>(
                value: _disasterTypeFilter,
                decoration: const InputDecoration(labelText: 'Disaster type'),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('All disaster types'),
                  ),
                  ..._incidentTypes.map(
                    (type) => DropdownMenuItem<String?>(
                      value: type,
                      child: Text(_label(type)),
                    ),
                  ),
                ],
                onChanged: _setDisasterTypeFilter,
              ),
              DropdownButtonFormField<String?>(
                value: _sosStatusFilter,
                decoration: const InputDecoration(
                  labelText: 'Emergency status',
                ),
                items: [
                  DropdownMenuItem<String?>(
                    value: null,
                    child: Text('All emergency statuses'),
                  ),
                  ...[
                    'new',
                    'received',
                    'acknowledged',
                    'verified',
                    'awaiting_dispatch',
                    'assigned',
                    'responding',
                    'on_scene',
                    'dispatched',
                    'resolved',
                    'cancelled',
                    'false_alarm',
                  ].map(
                    (item) => DropdownMenuItem<String?>(
                      value: item,
                      child: Text(item),
                    ),
                  ),
                ],
                onChanged: (value) => setState(() => _sosStatusFilter = value),
              ),
              TextField(
                controller: _areaFilter,
                decoration: const InputDecoration(
                  labelText: 'Filter district, city, area or report',
                  prefixIcon: Icon(Icons.search),
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView(
                  children: [
                    for (final event in events)
                      ListTile(
                        selected: _selectedSos?['id'] == event['id'],
                        leading: CircleAvatar(
                          backgroundColor: _urgencyColor(event['urgency']),
                          child: Text(
                            '${event['urgency']}/5',
                            style: const TextStyle(fontSize: 10),
                          ),
                        ),
                        title: Text(
                          '${_label(event['category'])} · ${event['message']}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Text(
                          '${_address(event['address'])} · ${_label(event['status'])} · ${_label(event['channel'])}',
                        ),
                        onTap: () => setState(() => _selectedSos = event),
                      ),
                    if (events.isEmpty)
                      const Padding(
                        padding: EdgeInsets.all(24),
                        child: Text(
                          'No emergency requests match these filters.',
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        );
        final map = _panel(
          padding: const EdgeInsets.all(4),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              height: mapHeight,
              child: StationMapView(
                api: _api,
                incidentId: _incidentFilter,
                incidentIds: _mapIncidentIds,
              ),
            ),
          ),
        );
        final detail = _sosDetail(_selectedSos);
        if (compact) {
          return ListView(
            padding: const EdgeInsets.all(12),
            children: [
              SizedBox(height: 350, child: queue),
              const SizedBox(height: 10),
              map,
              const SizedBox(height: 10),
              detail,
            ],
          );
        }
        return Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(width: 340, child: queue),
              const SizedBox(width: 10),
              Expanded(flex: 5, child: map),
              const SizedBox(width: 10),
              SizedBox(width: 340, child: detail),
            ],
          ),
        );
      },
    );
  }

  Widget _sosDetail(Map<String, dynamic>? event) {
    if (event == null) {
      return _panel(
        child: const Center(
          child: Text('Choose an emergency request to view details.'),
        ),
      );
    }
    final interpretation = event['interpretation'] is Map
        ? Map<String, dynamic>.from(event['interpretation'])
        : <String, dynamic>{};
    final recordedAddress = _address(event['address']);
    final address =
        recordedAddress == 'Area not recorded' &&
            interpretation['location_text']?.toString().trim().isNotEmpty ==
                true
        ? interpretation['location_text'].toString()
        : recordedAddress;
    final linkedNeedId = event['linked_need_id'];
    return _panel(
      child: ListView(
        shrinkWrap: true,
        children: [
          Text(
            '${_label(event['category'])} emergency · #${event['id']}',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            children: [
              _badge(
                'Urgency ${event['urgency']}/5',
                color: _urgencyColor(event['urgency']),
              ),
              _badge(_label(event['status'])),
              _badge(
                event['transmission_status'] == 'received'
                    ? 'Received by station'
                    : _label(event['transmission_status']),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(address, style: const TextStyle(color: Color(0xFFADB9BF))),
          const SizedBox(height: 12),
          const Text(
            'EMERGENCY MESSAGE',
            style: TextStyle(
              fontSize: 11,
              letterSpacing: 1,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text('${event['message'] ?? 'No message'}'),
          const SizedBox(height: 12),
          const Text(
            'AI EXTRACTED NEEDS',
            style: TextStyle(
              fontSize: 11,
              letterSpacing: 1,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text('Needs: ${(interpretation['needs'] as List? ?? []).join(', ')}'),
          Text(
            'Skills: ${(interpretation['required_skills'] as List? ?? []).join(', ')}',
          ),
          if (linkedNeedId != null) Text('Linked request: #$linkedNeedId'),
          if (linkedNeedId == null)
            Text(
              interpretation.isEmpty
                  ? 'AI is extracting a need from this message. It will appear in the request controller when interpretation finishes.'
                  : 'No need is linked yet. Review the extracted request after the next refresh.',
              style: const TextStyle(color: Color(0xFFFBC02D)),
            ),
          if (event['status'] == 'new')
            FilledButton.icon(
              onPressed: _busy ? null : () => _sosState(event, 'acknowledged'),
              icon: const Icon(Icons.visibility_outlined),
              label: const Text('Acknowledge request'),
            ),
          if (linkedNeedId != null)
            OutlinedButton.icon(
              onPressed: () {
                final need = _needs
                    .where((row) => row['id'] == linkedNeedId)
                    .firstOrNull;
                if (need != null)
                  setState(() {
                    _selectedNeed = need;
                    _page = 1;
                    _requestSection = 0;
                    _requestSubpage = 0;
                  });
              },
              icon: const Icon(Icons.assignment_outlined),
              label: const Text('Open linked need'),
            ),
        ],
      ),
    );
  }

  Widget _filters() => Wrap(
    spacing: 10,
    runSpacing: 8,
    children: [
      SizedBox(
        width: 280,
        child: DropdownButtonFormField<int?>(
          value: _incidentFilter,
          decoration: const InputDecoration(labelText: 'Incident filter'),
          items: [
            const DropdownMenuItem<int?>(
              value: null,
              child: Text('All incidents'),
            ),
            ..._incidents.map(
              (row) => DropdownMenuItem<int?>(
                value: row['id'] as int,
                child: Text(
                  '${row['incident_type'] ?? 'Incident'} · ${row['name']}',
                ),
              ),
            ),
          ],
          onChanged: _setIncidentFilter,
        ),
      ),
      SizedBox(
        width: 180,
        child: DropdownButtonFormField<String?>(
          value: _disasterTypeFilter,
          decoration: const InputDecoration(labelText: 'Disaster type'),
          items: [
            const DropdownMenuItem<String?>(
              value: null,
              child: Text('All disaster types'),
            ),
            ..._incidentTypes.map(
              (type) => DropdownMenuItem<String?>(
                value: type,
                child: Text(_label(type)),
              ),
            ),
          ],
          onChanged: _setDisasterTypeFilter,
        ),
      ),
      SizedBox(
        width: 180,
        child: DropdownButtonFormField<String?>(
          value: _categoryFilter,
          decoration: const InputDecoration(labelText: 'Need category'),
          items: [
            DropdownMenuItem<String?>(
              value: null,
              child: Text('All categories'),
            ),
            ...[
              'rescue',
              'medical',
              'water',
              'food',
              'shelter',
              'technical_repair',
              'other',
            ].map(
              (item) =>
                  DropdownMenuItem<String?>(value: item, child: Text(item)),
            ),
          ],
          onChanged: (value) => setState(() => _categoryFilter = value),
        ),
      ),
      SizedBox(
        width: 170,
        child: DropdownButtonFormField<String?>(
          value: _statusFilter,
          decoration: const InputDecoration(labelText: 'Status'),
          items: [
            DropdownMenuItem<String?>(value: null, child: Text('Any status')),
            ...[
              'open',
              'partially_fulfilled',
              'in_progress',
              'fulfilled',
              'closed',
            ].map(
              (item) =>
                  DropdownMenuItem<String?>(value: item, child: Text(item)),
            ),
          ],
          onChanged: (value) => setState(() => _statusFilter = value),
        ),
      ),
      SizedBox(
        width: 260,
        child: TextField(
          controller: _areaFilter,
          decoration: const InputDecoration(
            labelText: 'District, city, ward or area',
            prefixIcon: Icon(Icons.location_on_outlined),
          ),
          onChanged: (_) => setState(() {}),
        ),
      ),
    ],
  );

  Widget _requestResponsePage() => Column(
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
        child: Align(
          alignment: Alignment.centerLeft,
          child: SegmentedButton<int>(
            segments: const [
              ButtonSegment(
                value: 0,
                label: Text('Request controller'),
                icon: Icon(Icons.assignment_outlined),
              ),
              ButtonSegment(
                value: 1,
                label: Text('Required professionals'),
                icon: Icon(Icons.volunteer_activism_outlined),
              ),
            ],
            selected: {_requestSection},
            onSelectionChanged: (value) =>
                setState(() => _requestSection = value.first),
          ),
        ),
      ),
      Expanded(
        child: _requestSection == 0 ? _requestController() : _volunteerPage(),
      ),
    ],
  );

  Widget _requestController() => LayoutBuilder(
    builder: (context, constraints) {
      final split = constraints.maxWidth >= 1050;
      return Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: _filters(),
          ),
          if (!split)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Align(
                alignment: Alignment.centerLeft,
                child: SegmentedButton<int>(
                  segments: const [
                    ButtonSegment(
                      value: 0,
                      label: Text('Needs & requests'),
                      icon: Icon(Icons.inbox_outlined),
                    ),
                    ButtonSegment(
                      value: 1,
                      label: Text('Responses & offers'),
                      icon: Icon(Icons.volunteer_activism_outlined),
                    ),
                  ],
                  selected: {_requestSubpage},
                  onSelectionChanged: (selected) =>
                      setState(() => _requestSubpage = selected.first),
                ),
              ),
            ),
          Expanded(
            child: split
                ? Row(
                    children: [
                      Expanded(
                        child: Column(
                          children: [
                            const ListTile(
                              title: Text('Reported needs'),
                              subtitle: Text(
                                'Select a need to review its responses.',
                              ),
                            ),
                            Expanded(child: _needsList()),
                          ],
                        ),
                      ),
                      const VerticalDivider(width: 1),
                      Expanded(
                        child: Column(
                          children: [
                            const ListTile(
                              title: Text('Responses'),
                              subtitle: Text(
                                'Professional assignments and community offers.',
                              ),
                            ),
                            Expanded(child: _responsesList()),
                          ],
                        ),
                      ),
                    ],
                  )
                : _requestSubpage == 0
                ? _needsList()
                : _responsesList(),
          ),
        ],
      );
    },
  );

  Widget _needsList() => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      for (final need in _visibleNeeds) _needCard(need),
      if (_visibleNeeds.isEmpty)
        const Padding(
          padding: EdgeInsets.all(32),
          child: Text('No requests match the selected filters.'),
        ),
    ],
  );

  Widget _needCard(Map<String, dynamic> need) {
    final chosen = _selectedNeed?['id'] == need['id'];
    final incident = _incident(need['incident_id'] as int?);
    final assigned = _needAssignments(need);
    return Card(
      color: chosen ? const Color(0xFF20382D) : const Color(0xFF151B1F),
      child: InkWell(
        onTap: () => setState(() => _selectedNeed = need),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '#${need['id']} · ${_label(need['category'])}',
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  _badge(
                    'Urgency ${need['urgency']}/5',
                    color: _urgencyColor(need['urgency']),
                  ),
                  const SizedBox(width: 8),
                  _badge(_label(need['status'])),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                '${incident?['incident_type'] ?? 'Incident'} · ${incident?['name'] ?? 'Unassigned incident'} · ${_place(need['location_id'])}',
              ),
              Text(
                '${need['description']} · ${need['quantity_requested']} ${need['unit']} requested, ${need['quantity_fulfilled']} fulfilled',
              ),
              Text(
                'Skills: ${(need['required_skills'] as List? ?? []).join(', ').ifEmpty('Not specified')} · Materials: ${(need['required_equipment'] as List? ?? []).join(', ').ifEmpty('not specified')} · ${_label(need['verification_status'])}',
              ),
              if (assigned.isNotEmpty)
                Text(
                  'Response: ${assigned.map((row) => 'Volunteer #${row['volunteer_id']} · ${_label(row['status'])}').join(' | ')}',
                ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: [
                  if (need['verification_status'] != 'verified')
                    OutlinedButton.icon(
                      onPressed: _busy
                          ? null
                          : () => _run(() async {
                              await _api.request(
                                '/needs/${need['id']}',
                                method: 'PATCH',
                                body: {'verification_status': 'verified'},
                              );
                              await _refresh();
                            }),
                      icon: const Icon(Icons.fact_check_outlined),
                      label: const Text('Verify need'),
                    ),
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _match(need),
                    icon: const Icon(Icons.travel_explore),
                    label: const Text('Compare professionals'),
                  ),
                  FilledButton.icon(
                    onPressed: _busy ? null : () => _aiAssign(need),
                    icon: const Icon(Icons.auto_awesome),
                    label: const Text('AI match'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _responsesList() {
    final offers = _offers.where((offer) {
      if (_incidentFilter == null && _selectedNeed == null) return true;
      if (_selectedNeed != null)
        return _needOffers(_selectedNeed!).contains(offer);
      return _needs.any(
        (need) =>
            need['incident_id'] == _incidentFilter &&
            _needOffers(need).contains(offer),
      );
    }).toList();
    final assignments = _assignments.where((assignment) {
      if (_selectedNeed != null)
        return assignment['need_id'] == _selectedNeed!['id'];
      if (_incidentFilter == null) return true;
      return _needs.any(
        (need) =>
            need['id'] == assignment['need_id'] &&
            need['incident_id'] == _incidentFilter,
      );
    }).toList();
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          _selectedNeed == null
              ? 'Responses for selected incident'
              : 'Responses to Need #${_selectedNeed!['id']}',
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        for (final assignment in assignments) _assignmentCard(assignment),
        if (assignments.isEmpty)
          const Text('No professional assignments for this filter.'),
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 18),
          child: Divider(),
        ),
        const Text(
          'Community offers matched to these needs',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        for (final offer in offers) _offerCard(offer),
        if (offers.isEmpty)
          const Text(
            'No offers target these needs yet. Community offers are shown when their category and incident match.',
          ),
      ],
    );
  }

  Widget _assignmentCard(Map<String, dynamic> assignment) {
    final need = _needs
        .where((row) => row['id'] == assignment['need_id'])
        .firstOrNull;
    final volunteer = _volunteers
        .where((row) => row['id'] == assignment['volunteer_id'])
        .firstOrNull;
    final pending = assignment['status'] == 'proposed';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Need #${assignment['need_id']} · ${volunteer?['full_name'] ?? 'Professional #${assignment['volunteer_id']}'}',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            Text(
              'Status: ${_label(assignment['status'])} · ${need == null ? 'Need details unavailable' : _place(need['location_id'])} · ETA ${assignment['eta'] ?? 'pending'}',
            ),
            if (pending)
              Wrap(
                spacing: 8,
                children: [
                  FilledButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _assignmentAction(assignment, 'approve'),
                    icon: const Icon(Icons.check),
                    label: const Text('Approve & notify'),
                  ),
                  TextButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _assignmentAction(assignment, 'reject'),
                    icon: const Icon(Icons.close),
                    label: const Text('Reject match'),
                  ),
                ],
              ),
            if (assignment['status'] == 'approved')
              _badge(
                'Waiting for volunteer response',
                color: const Color(0xFFFBC02D),
              ),
            if (assignment['status'] == 'approved' &&
                _responseExpired(assignment))
              TextButton.icon(
                onPressed: _busy || need == null
                    ? null
                    : () => _retryAssignment(assignment, need),
                icon: const Icon(Icons.autorenew),
                label: const Text(
                  'No reply after 15 min · offer to another professional',
                ),
              ),
            if (assignment['status'] == 'approved' &&
                !_responseExpired(assignment))
              const Text(
                'Waiting 15 minutes for the volunteer to accept before offering this request to another professional.',
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _retryAssignment(
    Map<String, dynamic> assignment,
    Map<String, dynamic> need,
  ) => _run(() async {
    await _createBackupProposal(assignment, need);
    await _refresh();
  });

  Future<void> _autoReassignExpired() async {
    final expired = _assignments
        .where(
          (row) =>
              ['approved', 'rejected'].contains(row['status']) &&
              _responseExpired(row),
        )
        .toList();
    for (final assignment in expired) {
      final assignmentId = assignment['id'] as int;
      if (!_reassigning.add(assignmentId)) continue;
      final need = _needs
          .where((row) => row['id'] == assignment['need_id'])
          .firstOrNull;
      if (need == null) {
        _reassigning.remove(assignmentId);
        continue;
      }
      try {
        final candidate = await _createBackupProposal(assignment, need);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                candidate == null
                    ? 'No other verified professional is available for Need #${need['id']}. The unanswered assignment was cancelled.'
                    : assignment['status'] == 'rejected'
                    ? 'The professional declined. Need #${need['id']} was reassigned to ${candidate['full_name']}; waiting for their acceptance.'
                    : 'No response after 15 minutes. Need #${need['id']} was reassigned to ${candidate['full_name']}; waiting for their acceptance.',
              ),
            ),
          );
        }
      } catch (error) {
        _reassigning.remove(assignmentId);
        if (mounted) setState(() => _error = 'Automatic reassignment: $error');
      }
    }
    if (expired.isNotEmpty && mounted) {
      _assignments = _rows(await _api.request('/assignments?limit=200'));
      setState(() {});
    }
  }

  Future<Map<String, dynamic>?> _createBackupProposal(
    Map<String, dynamic> assignment,
    Map<String, dynamic> need,
  ) async {
    if (assignment['status'] != 'rejected') {
      await _api.request(
        '/assignments/${assignment['id']}/status',
        method: 'PATCH',
        body: {'status': 'cancelled'},
      );
    }
    final result = await _api.request(
      '/needs/${need['id']}/match?explain=true',
      method: 'POST',
    );
    final candidates = _rows((result as Map)['candidates'])
        .where((row) => row['volunteer_id'] != assignment['volunteer_id'])
        .toList();
    if (candidates.isEmpty) return null;
    final chosen = candidates.first;
    final backup = Map<String, dynamic>.from(
      await _api.request(
        '/assignments',
        method: 'POST',
        body: {'need_id': need['id'], 'volunteer_id': chosen['volunteer_id']},
      ),
    );
    await _api.request('/assignments/${backup['id']}/approve', method: 'POST');
    return chosen;
  }

  Widget _offerCard(Map<String, dynamic> offer) {
    final targetNeed = _needs
        .where((need) => need['id'] == offer['need_id'])
        .firstOrNull;
    return Card(
      child: ListTile(
        leading: const Icon(Icons.volunteer_activism, color: Color(0xFF4CAF7D)),
        title: Text(
          '${offer['offered_by_name']} · ${_label(offer['category'])} · ${offer['quantity']} ${offer['unit']}',
        ),
        subtitle: Text(
          '${offer['description']}\n${offer['location_text']} · Target: ${targetNeed == null ? 'matching need' : 'Need #${targetNeed['id']} at ${_place(targetNeed['location_id'])}'}',
        ),
        isThreeLine: true,
        trailing: offer['status'] == 'open'
            ? TextButton(
                onPressed: _busy ? null : () => _claimOffer(offer),
                child: const Text('Take ownership'),
              )
            : _badge(_label(offer['status'])),
      ),
    );
  }

  Widget _volunteerPage() {
    final need =
        _visibleNeeds
            .where((row) => row['id'] == _selectedNeed?['id'])
            .firstOrNull ??
        _visibleNeeds.firstOrNull;
    final target = need == null
        ? null
        : _locations
              .where((row) => row['id'] == need['location_id'])
              .firstOrNull;
    final matchedIds = _matches.map((row) => row['volunteer_id']).toSet();
    final volunteers =
        (_matches.isEmpty
              ? [..._volunteers]
              : _volunteers
                    .where((row) => matchedIds.contains(row['id']))
                    .toList())
          ..sort((a, b) {
            final aLoc = _locations
                .where((row) => row['id'] == a['base_location_id'])
                .firstOrNull;
            final bLoc = _locations
                .where((row) => row['id'] == b['base_location_id'])
                .firstOrNull;
            return (_distance(aLoc, target) ?? double.infinity).compareTo(
              _distance(bLoc, target) ?? double.infinity,
            );
          });
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: DropdownButtonFormField<int?>(
            value: need?['id'] as int?,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Request to staff',
              helperText:
                  'Choose a reported need to compare nearby professionals.',
            ),
            items: _visibleNeeds
                .map(
                  (row) => DropdownMenuItem<int?>(
                    value: row['id'] as int,
                    child: Text(
                      '#${row['id']} · ${_label(row['category'])} · ${_place(row['location_id'])} · ${row['description']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                )
                .toList(),
            onChanged: (value) => setState(() {
              _selectedNeed = _visibleNeeds
                  .where((row) => row['id'] == value)
                  .firstOrNull;
              _matches = [];
            }),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  need == null
                      ? 'Select a request to compare responders.'
                      : 'Professionals near ${_place(need['location_id'])} · Need #${need['id']}',
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              if (need != null)
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _match(need),
                  icon: const Icon(Icons.auto_awesome),
                  label: const Text('AI skill & route match'),
                ),
            ],
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              for (final volunteer in volunteers)
                _professionalCard(volunteer, need, target),
              if (volunteers.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('No professionals are registered yet.'),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _professionalCard(
    Map<String, dynamic> person,
    Map<String, dynamic>? need,
    Map<String, dynamic>? target,
  ) {
    final base = _locations
        .where((row) => row['id'] == person['base_location_id'])
        .firstOrNull;
    final distance = _distance(base, target);
    final matching = _matches
        .where((row) => row['volunteer_id'] == person['id'])
        .firstOrNull;
    final skills = (person['skills'] as List? ?? [])
        .whereType<Map>()
        .map(
          (skill) => '${skill['name']}${skill['verified'] == true ? ' ✓' : ''}',
        )
        .join(', ');
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          child: Text(
            '${person['full_name'] ?? '?'}'.characters.first.toUpperCase(),
          ),
        ),
        title: Text(
          '${person['full_name']} · ${_label(person['availability_status'])}',
        ),
        subtitle: Text(
          'Based at ${base?['name'] ?? 'area not recorded'}${distance == null ? '' : ' · ${distance.toStringAsFixed(1)} km straight-line'}\n$skills${matching == null ? '' : '\nRoute ${matching['route']['distance_km']} km · ETA ${matching['route']['duration_min']} min · Score ${matching['score']}'}',
        ),
        isThreeLine: true,
        trailing: need == null
            ? null
            : FilledButton(
                onPressed: _busy
                    ? null
                    : () => _assign(need, person['id'] as int),
                child: const Text('Assign professional'),
              ),
      ),
    );
  }

  Widget _insights() => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      Wrap(
        spacing: 14,
        runSpacing: 14,
        children: [
          _metric(
            'Emergency requests',
            '${_sos.where((row) => !['resolved', 'cancelled', 'false_alarm'].contains(row['status'])).length}',
            Icons.sos,
            const Color(0xFFD32F2F),
          ),
          _metric(
            'Open needs',
            '${_needs.where((row) => ['open', 'partially_fulfilled', 'in_progress'].contains(row['status'])).length}',
            Icons.assignment_late_outlined,
            const Color(0xFFFBC02D),
          ),
          _metric(
            'Waiting assignments',
            '${_assignments.where((row) => ['proposed', 'approved'].contains(row['status'])).length}',
            Icons.hourglass_top,
            const Color(0xFF3A86FF),
          ),
          _metric(
            'Open community offers',
            '${_offers.length}',
            Icons.volunteer_activism_outlined,
            const Color(0xFF4CAF7D),
          ),
        ],
      ),
    ],
  );

  Widget _metric(String title, String value, IconData icon, Color color) =>
      SizedBox(
        width: 240,
        child: _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: color),
              const SizedBox(height: 12),
              Text(
                value,
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(title),
            ],
          ),
        ),
      );

  Widget _meshLab() => Center(
    child: _panel(
      child: const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.wifi_tethering, size: 46, color: Color(0xFF4CAF7D)),
          SizedBox(height: 12),
          Text(
            'Mesh communications',
            style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 8),
          Text(
            'Offline SOS reports sync to this station when a gateway reconnects.',
          ),
          SizedBox(height: 8),
          Text('Mesh status is provided by connected gateways.'),
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: const Color(0xFF0D1114),
    appBar: _user == null
        ? null
        : AppBar(
            title: const Row(
              children: [
                Icon(Icons.emergency, color: Color(0xFF4CAF7D)),
                SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Rahat Command Station',
                      style: TextStyle(fontSize: 18),
                    ),
                    Text(
                      'EMERGENCY RESPONSE OPERATIONS',
                      style: TextStyle(
                        fontSize: 10,
                        letterSpacing: 1.2,
                        color: Color(0xFFADB9BF),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            actions: [
              if (_busy)
                const SizedBox(width: 90, child: LinearProgressIndicator()),
              if (_error != null)
                IconButton(
                  tooltip: _error,
                  icon: const Icon(Icons.cloud_off, color: Color(0xFFD32F2F)),
                  onPressed: () => setState(() => _error = null),
                ),
              IconButton(
                tooltip: 'Refresh',
                onPressed: _busy ? null : () => _run(_refresh),
                icon: const Icon(Icons.refresh),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Center(
                  child: _badge(
                    '${_user?['full_name']} · ${_label(_user?['role'])}',
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Sign out',
                onPressed: () => setState(() {
                  _api.token = null;
                  _user = null;
                  _incidents = [];
                  _needs = [];
                  _assignments = [];
                  _sos = [];
                }),
                icon: const Icon(Icons.logout),
              ),
            ],
            bottom: PreferredSize(
              preferredSize: const Size.fromHeight(54),
              child: Align(
                alignment: Alignment.centerLeft,
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: _topTabs(),
                ),
              ),
            ),
          ),
    body: _user == null
        ? Center(child: _login())
        : Column(
            children: [
              if (_error != null)
                MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
              Expanded(
                child: IndexedStack(
                  index: _page,
                  children: [
                    _operations(),
                    _requestResponsePage(),
                    _insights(),
                    _meshLab(),
                  ],
                ),
              ),
            ],
          ),
  );
}

extension on String {
  String ifEmpty(String replacement) => isEmpty ? replacement : this;
}

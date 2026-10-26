import 'dart:async';

import 'package:flutter/material.dart';
import '../module_api.dart';
import 'map.dart';

class CoordinationSession extends ChangeNotifier {
  final ModuleApi api;
  final bool ownsApi;
  Map<String, dynamic>? user;

  CoordinationSession({ModuleApi? api, this.ownsApi = true})
      : api = api ?? ModuleApi();

  void setUser(Map<String, dynamic>? value) {
    user = value;
    notifyListeners();
  }

  void signOut() {
    api.token = null;
    setUser(null);
  }

  @override
  void dispose() {
    if (ownsApi) api.close();
    super.dispose();
  }
}

class CoordinationScreen extends StatefulWidget {
  final ModuleApi? api;
  final bool embedded;
  final String section;
  final bool stationMode;
  final CoordinationSession? session;
  const CoordinationScreen(
      {super.key,
      this.api,
      this.embedded = false,
      this.section = 'all',
      this.stationMode = false,
      this.session});

  @override
  State<CoordinationScreen> createState() => _CoordinationScreenState();
}

class _CoordinationScreenState extends State<CoordinationScreen> {
  late final CoordinationSession _session;
  bool _ownsSession = false;
  int? _observedUserId;
  ModuleApi get _api => _session.api;
  Map<String, dynamic>? get _user => _session.user;
  final _email = TextEditingController();
  final _password = TextEditingController();
  Map<String, dynamic> _workspace = {};
  List<Map<String, dynamic>> _needs = [], _volunteers = [], _assignments = [];
  List<Map<String, dynamic>> _stock = [],
      _movements = [],
      _flags = [],
      _skills = [],
      _proposals = [],
      _sosEvents = [],
      _offers = [],
      _notifications = [];
  Map<String, dynamic> _situation = {};
  Map<String, dynamic> _meshState = {};
  Map<String, dynamic> _profile = {};
  int? _incident;
  String? _error;
  bool _busy = false;
  bool _register = false;
  final _name = TextEditingController();
  Timer? _refreshTimer;

  bool get _manager => ['admin', 'coordinator'].contains(_user?['role']);
  bool get _provider => _manager || _user?['role'] == 'org_admin';
  List<Map<String, dynamic>> _rows(dynamic data) => (data as List? ?? [])
      .map((item) => Map<String, dynamic>.from(item as Map))
      .toList();
  List<Map<String, dynamic>> get _locations => _rows(_workspace['locations']);

  @override
  void initState() {
    super.initState();
    _session = widget.session ??
        CoordinationSession(api: widget.api, ownsApi: widget.api == null);
    _ownsSession = widget.session == null;
    _session.addListener(_sessionChanged);
    _refreshTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (mounted && _user != null && !_busy) _run(_refresh);
    });
  }

  void _sessionChanged() {
    final userId = _user?['id'] as int?;
    final shouldLoad = _observedUserId == null && userId != null;
    _observedUserId = userId;
    if (mounted) {
      setState(() {});
      if (shouldLoad) _run(_refresh);
    }
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _session.removeListener(_sessionChanged);
    if (_ownsSession) _session.dispose();
    _email.dispose();
    _password.dispose();
    _name.dispose();
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

  Future<void> _login() => _run(() async {
        if (_register) {
          await _api.request('/auth/register', method: 'POST', body: {
            'email': _email.text.trim(),
            'password': _password.text,
            'full_name': _name.text.trim(),
          });
        }
        final user = await _api.login(_email.text, _password.text);
        if (!mounted) return;
        _session.setUser(user);
        _password.clear();
        await _refresh();
      });

  Future<void> _refresh() async {
    final workspace =
        Map<String, dynamic>.from(await _api.request('/workspace'));
    final profile =
        Map<String, dynamic>.from(await _api.request('/auth/me/profile'));
    final incidents = _rows(workspace['incidents']);
    // Start with the full response picture. Coordinators can narrow it to one
    // incident from the selector when they need to work a specific event.
    final selected =
        incidents.any((row) => row['id'] == _incident) ? _incident : null;
    final query = selected == null ? '' : '?incident_id=$selected';
    final needs = await _api.request('/needs$query');
    final assignments = await _api.request('/assignments$query');
    final movements = await _api.request('/movements$query');
    final skills = await _api.request('/skills');
    final volunteers = _user?['role'] == 'community_member'
        ? []
        : await _api.request('/volunteers');
    final stock = _provider ? await _api.request('/resources/stock') : [];
    final situation = _manager && selected != null
        ? await _api.request('/situation$query')
        : <String, dynamic>{};
    final flags = _manager && selected != null
        ? await _api.request('/bottlenecks$query')
        : [];
    final proposals = _manager && selected != null
        ? await _api.request('/ai/proposals$query')
        : {'items': []};
    final sosEvents = _manager ? await _api.request('/sos') : [];
    final offers = await _api.request('/help/offers');
    final notifications =
        await _api.request('/help/notifications?unread_only=true');
    if (!mounted) return;
    setState(() {
      _workspace = workspace;
      _profile = profile;
      _incident = selected;
      _needs = _rows(needs['items']);
      _assignments = _rows(assignments);
      _movements = _rows(movements);
      _skills = _rows(skills);
      _volunteers = _rows(volunteers);
      _stock = _rows(stock);
      _situation = Map<String, dynamic>.from(situation);
      _flags = _rows(flags);
      _proposals = _rows(proposals['items']);
      _sosEvents = _rows(sosEvents);
      _offers = _rows(offers)
          .where(
              (offer) => selected == null || offer['incident_id'] == selected)
          .toList();
      _notifications = _rows(notifications);
    });
  }

  Future<void> _write(String path,
          {String method = 'POST',
          Map<String, dynamic>? body,
          bool retrySafe = false}) =>
      _run(() async {
        await _api.request(path,
            method: method, body: body, retrySafe: retrySafe);
        await _refresh();
      });

  String _label(dynamic value) =>
      (value ?? 'Unknown').toString().replaceAll('_', ' ');
  String _location(dynamic id) =>
      _locations
          .where((row) => row['id'] == id)
          .map((row) => row['name'].toString())
          .firstOrNull ??
      'Location #$id';
  bool _ownAssignment(Map<String, dynamic> assignment) =>
      _volunteers.any((row) =>
          row['id'] == assignment['volunteer_id'] &&
          row['user_id'] == _user?['id']);

  Widget _button(String label, IconData icon, VoidCallback action) =>
      TextButton.icon(
        onPressed: _busy ? null : action,
        icon: Icon(icon, size: 18),
        label: Text(label),
      );

  Widget _badge(String text, {bool warning = false}) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: warning ? const Color(0xFF342F1C) : const Color(0xFF18362A),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(text,
            style: TextStyle(
                fontSize: 12,
                color: warning
                    ? const Color(0xFFFBC02D)
                    : const Color(0xFF75D4A0))),
      );

  Widget _entry(String title, String subtitle,
          {List<Widget> children = const []}) =>
      Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: Color(0xFF263038)))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title,
              style:
                  const TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(subtitle,
              style: const TextStyle(color: Color(0xFFADB9BF), height: 1.4)),
          if (children.isNotEmpty) ...[const SizedBox(height: 10), ...children],
        ]),
      );

  Widget _list(List<Widget> children, {String empty = 'No records'}) =>
      ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        children: children.isEmpty
            ? [Padding(padding: const EdgeInsets.all(24), child: Text(empty))]
            : children,
      );

  Future<Map<String, dynamic>?> _form(String title, List<_Field> fields) async {
    final key = GlobalKey<FormState>();
    final values = <String, dynamic>{};
    for (final field in fields) {
      values[field.key] = field.initial ??
          (field.options?.isNotEmpty == true
              ? field.options!.first['id']
              : field.boolean
                  ? false
                  : '');
    }
    return showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
          builder: (context, update) => AlertDialog(
                title: Text(title),
                content: SizedBox(
                    width: 420,
                    child: SingleChildScrollView(
                        child: Form(
                      key: key,
                      child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: fields
                              .map((field) => Padding(
                                    padding: const EdgeInsets.only(bottom: 14),
                                    child: field.boolean
                                        ? CheckboxListTile(
                                            contentPadding: EdgeInsets.zero,
                                            title: Text(field.label),
                                            value: values[field.key] as bool,
                                            onChanged: (value) => update(() =>
                                                values[field.key] =
                                                    value ?? false))
                                        : field.options != null
                                            ? DropdownButtonFormField<dynamic>(
                                                initialValue: values[field.key],
                                                isExpanded: true,
                                                decoration: InputDecoration(
                                                    labelText: field.label),
                                                items: field.options!
                                                    .map((option) => DropdownMenuItem<
                                                            dynamic>(
                                                        value: option['id'],
                                                        child: Text(
                                                            '${option['name']}',
                                                            overflow:
                                                                TextOverflow
                                                                    .ellipsis)))
                                                    .toList(),
                                                validator: (value) =>
                                                    field.required &&
                                                            value == null
                                                        ? 'Choose a value'
                                                        : null,
                                                onChanged: (value) =>
                                                    values[field.key] = value,
                                              )
                                            : TextFormField(
                                                initialValue:
                                                    '${values[field.key]}',
                                                decoration: InputDecoration(
                                                    labelText: field.label),
                                                maxLines:
                                                    field.multiline ? 4 : 1,
                                                keyboardType: field.number
                                                    ? const TextInputType
                                                        .numberWithOptions(
                                                        decimal: true,
                                                        signed: true)
                                                    : TextInputType.text,
                                                validator: (value) {
                                                  if (field.required &&
                                                      (value == null ||
                                                          value
                                                              .trim()
                                                              .isEmpty)) {
                                                    return 'Required';
                                                  }
                                                  if (field.number &&
                                                      (double.tryParse(value ??
                                                                  '') ==
                                                              null ||
                                                          !double.parse(
                                                                  value ?? '')
                                                              .isFinite)) {
                                                    return 'Enter a number';
                                                  }
                                                  return null;
                                                },
                                                onChanged: (value) =>
                                                    values[field.key] = field
                                                            .number
                                                        ? num.tryParse(value)
                                                        : value.trim(),
                                              ),
                                  ))
                              .toList()),
                    ))),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(dialogContext),
                      child: const Text('Cancel')),
                  FilledButton(
                      onPressed: () {
                        if (key.currentState!.validate()) {
                          for (final field
                              in fields.where((field) => field.number)) {
                            values[field.key] =
                                num.parse('${values[field.key]}');
                          }
                          Navigator.pop(dialogContext, values);
                        }
                      },
                      child: const Text('Confirm')),
                ],
              )),
    );
  }

  Future<void> _showData(String title, dynamic data) async {
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.75,
        builder: (context, controller) => ListView(
            controller: controller,
            padding: const EdgeInsets.all(20),
            children: [
              Row(children: [
                Expanded(
                    child: Text(title,
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.bold))),
                IconButton(
                    tooltip: 'Close',
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close))
              ]),
              const SizedBox(height: 16),
              _data(data),
            ]),
      ),
    );
  }

  Widget _data(dynamic value) {
    if (value is Map) {
      return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: value.entries
              .map((entry) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(_label(entry.key),
                              style: const TextStyle(
                                  color: Color(0xFF75D4A0),
                                  fontWeight: FontWeight.w600)),
                          const SizedBox(height: 4),
                          _data(entry.value),
                        ]),
                  ))
              .toList());
    }
    if (value is List) {
      return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: value.isEmpty
              ? [const Text('None recorded')]
              : value
                  .map((item) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _data(item)))
                  .toList());
    }
    return SelectableText(value == null ? 'Not recorded' : '$value');
  }

  Future<void> _report() async {
    if (_incident == null) return;
    final values = await _form('Report a Need', [
      _Field('location_id', 'Location', options: _locations),
      const _Field('text', 'Report', multiline: true),
    ]);
    if (values != null) {
      await _write('/reports',
          body: {...values, 'incident_id': _incident, 'channel': 'app'},
          retrySafe: true);
    }
  }

  Future<void> _match(Map<String, dynamic> need) => _run(() async {
        final result = await _api.request(
            '/needs/${need['id']}/match?explain=true',
            method: 'POST',
            body: {});
        if (!mounted) return;
        final candidates = _rows(result['candidates']);
        await showModalBottomSheet<int>(
            context: context,
            isScrollControlled: true,
            useSafeArea: true,
            builder: (context) => SizedBox(
                  height: MediaQuery.sizeOf(context).height * 0.75,
                  child: _list([
                    const Text('Ranked Candidates',
                        style: TextStyle(
                            fontSize: 20, fontWeight: FontWeight.bold)),
                    if (candidates.isEmpty)
                      const Padding(
                          padding: EdgeInsets.all(20),
                          child: Text(
                              'No verified, available volunteer meets this need.')),
                    for (final candidate in candidates)
                      _entry(
                          '${candidate['full_name'] ?? candidate['volunteer_name'] ?? 'Volunteer #${candidate['volunteer_id']}'}',
                          'Score ${candidate['score']} · ${candidate['route']?['duration_min']} min · Estimated route',
                          children: [
                            if (candidate['explanation'] != null)
                              Text('${candidate['explanation']}'),
                            _data(candidate['score_breakdown']),
                            FilledButton.icon(
                                icon: const Icon(Icons.person_add_alt),
                                label: const Text('Propose Assignment'),
                                onPressed: () => Navigator.pop(
                                    context, candidate['volunteer_id'])),
                          ]),
                  ]),
                )).then((volunteerId) async {
          if (volunteerId != null) {
            await _api.request('/assignments',
                method: 'POST',
                body: {'need_id': need['id'], 'volunteer_id': volunteerId});
            await _refresh();
          }
        });
      });

  Future<void> _editNeed(Map<String, dynamic> need) async {
    final values = await _form('Review Need #${need['id']}', [
      _Field('quantity_requested', 'Requested quantity',
          initial: need['quantity_requested'], number: true),
      _Field('unit', 'Unit', initial: need['unit']),
      _Field('urgency', 'Urgency (1–5)',
          initial: need['urgency'], number: true),
      _Field('verification_status', 'Verification',
          initial: need['verification_status'],
          options: [
            for (final value in ['unverified', 'verified', 'rejected'])
              {'id': value, 'name': value},
          ]),
    ]);
    if (values != null) {
      await _write('/needs/${need['id']}', method: 'PATCH', body: values);
    }
  }

  Widget _needsView() => _list([
        Align(
            alignment: Alignment.centerLeft,
            child: _button('Report Need', Icons.add, _report)),
        if (_needs.isEmpty) const Text('No needs recorded for this incident.'),
        for (final need in _needs)
          _entry('#${need['id']} · ${_label(need['category'])}',
              '${_location(need['location_id'])}\n${need['description']}',
              children: [
                Wrap(spacing: 8, runSpacing: 8, children: [
                  _badge(_label(need['status'])),
                  _badge(
                      '${need['verification_status']} · ${need['confidence']} confidence',
                      warning: need['verification_status'] != 'verified'),
                  _badge('Urgency ${need['urgency']}/5',
                      warning: (need['urgency'] as num) >= 4),
                ]),
                const SizedBox(height: 10),
                Text(
                    '${need['quantity_fulfilled']} / ${need['quantity_requested']} ${need['unit']} confirmed'),
                if ((need['required_skills'] as List).isNotEmpty)
                  Text(
                      'Skills: ${(need['required_skills'] as List).join(', ')}'),
                Wrap(spacing: 8, children: [
                  _button(
                      'Progress',
                      Icons.timeline,
                      () => _run(() async => _showData(
                          'Need #${need['id']} Progress',
                          await _api
                              .request('/needs/${need['id']}/progress')))),
                  if (_manager)
                    _button('Review', Icons.fact_check_outlined,
                        () => _editNeed(need)),
                  if (_manager &&
                      !['fulfilled', 'closed'].contains(need['status'])) ...[
                    _button('Match Volunteers', Icons.people_alt_outlined,
                        () => _match(need)),
                    _button(
                        'AI Draft',
                        Icons.auto_awesome_outlined,
                        () => _write('/needs/${need['id']}/assignment-proposal',
                            body: {})),
                    if (['water', 'food', 'medical', 'shelter']
                        .contains(need['category']))
                      _button(
                          'AI Supply Draft',
                          Icons.inventory_outlined,
                          () => _write(
                              '/needs/${need['id']}/allocation-proposal',
                              body: {},
                              retrySafe: true)),
                  ],
                ]),
              ]),
      ]);

  Future<void> _registerVolunteer() async {
    final values = await _form('Volunteer Profile', [
      _Field('base_location_id', 'Home / usual response area (optional)',
          options: _locations, required: false),
      const _Field('contact_info', 'Contact information', required: false),
      const _Field('languages', 'Languages (comma separated)', required: false),
      const _Field('equipment', 'Equipment you can bring (comma separated)',
          required: false),
      const _Field('max_travel_km', 'Maximum travel (km)',
          initial: 50, number: true),
      const _Field('willing_to_relocate', 'Willing to relocate', boolean: true),
      const _Field('notes', 'Experience or safety notes',
          multiline: true, required: false),
    ]);
    if (values != null) {
      await _run(() async {
        for (final key in ['languages', 'equipment']) {
          values[key] = (values[key] as String)
              .split(',')
              .map((value) => value.trim())
              .where((value) => value.isNotEmpty)
              .toList();
        }
        await _api.request('/volunteers', method: 'POST', body: values);
        final user = await _api.request('/auth/me');
        if (mounted) _session.setUser(Map<String, dynamic>.from(user));
        await _refresh();
      });
      final own = _volunteers
          .where((profile) => profile['user_id'] == _user?['id'])
          .firstOrNull;
      if (own != null && _skills.isNotEmpty) await _addSkill(own);
    }
  }

  Future<void> _editProfile() async {
    final address =
        Map<String, dynamic>.from(_profile['address'] as Map? ?? {});
    final contacts = _rows(_profile['emergency_contacts']);
    final values = await _form('My emergency profile', [
      _Field('phone_number', 'Your phone number',
          initial: _profile['phone_number'] ?? '', required: false),
      _Field('district', 'District',
          initial: address['district'] ?? '', required: false),
      _Field('city', 'City / municipality / village',
          initial: address['city'] ?? '', required: false),
      _Field('ward', 'Ward', initial: address['ward'] ?? '', required: false),
      _Field('road', 'Road / street / tole',
          initial: address['road'] ?? '', required: false),
      _Field('landmark', 'Nearby landmark',
          initial: address['landmark'] ?? '', required: false),
      _Field('profile_notes', 'Other information (medical/accessibility)',
          initial: _profile['profile_notes'] ?? '',
          multiline: true,
          required: false),
      _Field('contact_name', 'Emergency contact name',
          initial: contacts.isEmpty ? '' : contacts.first['name'] ?? '',
          required: false),
      _Field('contact_relationship', 'Relationship',
          initial: contacts.isEmpty ? '' : contacts.first['relationship'] ?? '',
          required: false),
      _Field('contact_phone', 'Emergency contact phone',
          initial: contacts.isEmpty ? '' : contacts.first['phone'] ?? '',
          required: false),
      _Field('contact_share_location', 'Share location with this contact',
          initial: contacts.isEmpty
              ? true
              : contacts.first['share_location'] != false,
          boolean: true),
    ]);
    if (values == null) return;
    final contactName = (values.remove('contact_name') as String).trim();
    final contactRelationship =
        (values.remove('contact_relationship') as String).trim();
    final contactPhone = (values.remove('contact_phone') as String).trim();
    final shareLocation = values.remove('contact_share_location') == true;
    final hasAnyContact = contactName.isNotEmpty ||
        contactRelationship.isNotEmpty ||
        contactPhone.isNotEmpty;
    if (hasAnyContact &&
        (contactName.isEmpty ||
            contactRelationship.isEmpty ||
            contactPhone.isEmpty)) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'Enter the emergency contact name, relationship, and phone together.')));
      }
      return;
    }
    final profileAddress = <String, String>{};
    for (final key in ['district', 'city', 'ward', 'road', 'landmark']) {
      final value = (values.remove(key) as String).trim();
      if (value.isNotEmpty) profileAddress[key] = value;
    }
    final submitted = <String, dynamic>{
      ...values,
      'address': profileAddress,
      'emergency_contacts': contactName.isEmpty &&
              contactRelationship.isEmpty &&
              contactPhone.isEmpty
          ? []
          : [
              {
                'name': contactName,
                'relationship': contactRelationship,
                'phone': contactPhone,
                'priority': 1,
                'share_location': shareLocation,
                'consent_to_notify': true,
              }
            ],
    };
    await _write('/auth/me/profile', method: 'PATCH', body: submitted);
  }

  Future<void> _availability(Map<String, dynamic> profile) async {
    final values = await _form('Availability', [
      _Field('status', 'Status',
          initial: profile['availability_status'],
          options: [
            for (final value in [
              'available',
              'assigned',
              'unavailable',
              'off_duty'
            ])
              {'id': value, 'name': _label(value)},
          ]),
      const _Field('hours', 'Available for the next (hours)',
          initial: 24, number: true),
    ]);
    if (values == null) return;
    final now = DateTime.now().toUtc();
    await _write('/volunteers/${profile['id']}/availability',
        method: 'PATCH',
        body: {
          'status': values['status'],
          'windows': values['status'] == 'available'
              ? [
                  {
                    'starts_at': now.toIso8601String(),
                    'ends_at': now
                        .add(Duration(
                            minutes: ((values['hours'] as num) * 60).round()))
                        .toIso8601String()
                  }
                ]
              : [],
        });
  }

  Future<void> _addSkill(Map<String, dynamic> profile) async {
    final existing =
        (profile['skills'] as List).map((row) => row['skill_id']).toSet();
    final options = _skills
        .where((row) => !existing.contains(row['id']))
        .map((row) => {'id': row['id'], 'name': row['name']})
        .toList();
    final values = await _form('Add Skill', [
      _Field('skill_id', 'Skill', options: options),
      const _Field('level', 'Level (1–5)', initial: 1, number: true),
    ]);
    if (values != null) {
      await _write('/volunteers/${profile['id']}/skills', body: values);
    }
  }

  Widget _volunteersView() => _list([
        const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child: Text(
                'Register before an incident: your home/usual response area helps matching, but it is not your employer or a work assignment. Add your skills and proficiency after creating the profile.',
                style: TextStyle(color: Color(0xFFADB9BF), height: 1.4))),
        if (_user?['role'] == 'community_member')
          Align(
              alignment: Alignment.centerLeft,
              child: _button('Register my organization',
                  Icons.business_outlined, _createOrganization)),
        if (_provider)
          Align(
              alignment: Alignment.centerLeft,
              child: _button('Register organization employee',
                  Icons.person_add_alt_1, _registerEmployee)),
        if (!_volunteers.any((row) => row['user_id'] == _user?['id']))
          Align(
              alignment: Alignment.centerLeft,
              child: _button('Create My Profile', Icons.person_add_alt,
                  _registerVolunteer)),
        if (_volunteers.isEmpty) const Text('No volunteer profiles available.'),
        for (final profile in _volunteers)
          _entry('${profile['full_name']}',
              '${profile['base_location_id'] == null ? 'Response area not set' : _location(profile['base_location_id'])} · ${profile['max_travel_km']} km travel range',
              children: [
                _badge(_label(profile['availability_status']),
                    warning: profile['availability_status'] != 'available'),
                for (final skill in _rows(profile['skills']))
                  Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Wrap(
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 8,
                          children: [
                            Text(
                                '${_label(skill['name'])} · level ${skill['level']}'),
                            _badge(
                                skill['verified'] == true
                                    ? 'Verified'
                                    : 'Unverified',
                                warning: skill['verified'] != true),
                            if (_provider && skill['verified'] != true)
                              _button(
                                  'Verify',
                                  Icons.verified_outlined,
                                  () => _write(
                                      '/volunteers/${profile['id']}/skills/${skill['skill_id']}/verify')),
                          ])),
                Wrap(children: [
                  _button('Availability', Icons.event_available,
                      () => _availability(profile)),
                  _button(
                      'Add Skill', Icons.add_task, () => _addSkill(profile)),
                ]),
              ]),
      ]);

  Future<void> _offerHelp({int? targetNeedId}) async {
    final openNeeds = _needs
        .where((need) => !['fulfilled', 'closed'].contains(need['status']))
        .map((need) {
      final incident = _rows(_workspace['incidents'])
          .where((row) => row['id'] == need['incident_id'])
          .firstOrNull;
      return {
        ...need,
        'name':
            '#${need['id']} · ${_label(need['category'])} · ${incident?['incident_type'] ?? 'Incident'} · ${incident?['name'] ?? 'Area not recorded'} · ${_location(need['location_id'])}',
      };
    }).toList();
    if (openNeeds.isEmpty) {
      setState(() => _error =
          'There are no open needs to target. Choose another incident or wait for a request to be reported.');
      return;
    }
    final values = await _form('Offer help nearby', [
      _Field('need_id', 'Choose a request to help',
          required: true,
          initial: targetNeedId,
          options: openNeeds
              .map((need) => {
                    'id': need['id'],
                    'name':
                        '${need['name']} · ${need['description']} · Materials: ${(need['required_equipment'] as List? ?? []).isEmpty ? 'not specified' : (need['required_equipment'] as List).join(', ')}',
                  })
              .toList()),
      const _Field('category', 'What can you provide?', options: [
        {'id': 'water', 'name': 'Water'},
        {'id': 'food', 'name': 'Food'},
        {'id': 'medicine', 'name': 'Medicine'},
        {'id': 'shelter', 'name': 'Shelter'},
        {'id': 'transport', 'name': 'Transport'},
        {'id': 'skill', 'name': 'Skilled help'},
        {'id': 'other', 'name': 'Other'},
      ]),
      const _Field('description', 'Extra details or materials included'),
      const _Field('quantity', 'Quantity', number: true),
      const _Field('unit', 'Unit (litres, meals, hours...)'),
      const _Field('location_text', 'Where is it available?'),
    ]);
    if (values != null) {
      await _write('/help/offers', body: values);
    }
  }

  Widget _offersView() => _list([
        Align(
            alignment: Alignment.centerLeft,
            child: _button(
                'Offer help', Icons.volunteer_activism_outlined, _offerHelp)),
        const Text(
            'Choose a reported request and offer the materials, transport, or skills it needs. A coordinator reviews offers before deployment.',
            style: TextStyle(color: Color(0xFFADB9BF), height: 1.4)),
        const SizedBox(height: 12),
        const Text('Open requests you can help with',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
        for (final need in _needs
            .where((row) => !['fulfilled', 'closed'].contains(row['status'])))
          _entry(
              '#${need['id']} · ${_label(need['category'])} · ${_location(need['location_id'])}',
              '${need['description']}\n${need['quantity_fulfilled']} / ${need['quantity_requested']} ${need['unit']} fulfilled · Materials: ${(need['required_equipment'] as List? ?? []).isEmpty ? 'not specified' : (need['required_equipment'] as List).join(', ')} · Status: ${_label(need['status'])}',
              children: [
                _button('Offer for this request', Icons.volunteer_activism,
                    () => _offerHelp(targetNeedId: need['id'] as int)),
              ]),
        const SizedBox(height: 12),
        const Text('Community offers',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
        if (_offers.isEmpty) const Text('No open community offers nearby.'),
        for (final offer in _offers)
          _entry(
              '${_label(offer['category'])} · ${offer['quantity']} ${offer['unit']}',
              '${offer['description']}\nAvailable at: ${offer['location_text']}\nOffered by ${offer['offered_by_name']}\n${offer['need_id'] == null ? 'General incident offer' : 'For Need #${offer['need_id']}'}',
              children: [
                if (offer['offered_by'] != _user?['id'])
                  _button('Respond', Icons.reply_outlined,
                      () => _write('/help/offers/${offer['id']}/claim')),
                _badge(_label(offer['status'])),
              ]),
      ]);

  Future<void> _createOrganization() async {
    final values = await _form('Register Organization', [
      const _Field('name', 'Organization name'),
      const _Field('organization_type', 'Organization type', options: [
        {'id': 'ngo', 'name': 'NGO'},
        {'id': 'community', 'name': 'Community organization'},
        {'id': 'business', 'name': 'Business'},
        {'id': 'government', 'name': 'Government'},
        {'id': 'other', 'name': 'Other'},
      ]),
    ]);
    if (values == null) return;
    await _run(() async {
      await _api.request('/organizations', method: 'POST', body: values);
      final user = await _api.request('/auth/me');
      if (mounted) _session.setUser(Map<String, dynamic>.from(user));
      await _refresh();
    });
  }

  Future<void> _registerEmployee() async {
    final organizations = _rows(_workspace['organizations']);
    if (organizations.isEmpty) {
      setState(() => _error =
          'No organization is available to this account. Register an organization first.');
      return;
    }
    final name = TextEditingController();
    final email = TextEditingController();
    final password = TextEditingController();
    final contact = TextEditingController();
    final form = GlobalKey<FormState>();
    final selectedSkills = <int, int>{};
    var organizationId = organizations.first['id'] as int;
    var baseLocationId =
        _locations.isEmpty ? null : _locations.first['id'] as int?;
    var maxTravelKm = 50.0;
    var willingToRelocate = false;
    final values = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('Register organization employee'),
          content: SizedBox(
            width: 520,
            child: Form(
              key: form,
              child: SingleChildScrollView(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  DropdownButtonFormField<int>(
                    initialValue: organizationId,
                    decoration:
                        const InputDecoration(labelText: 'Organization'),
                    items: organizations
                        .map((row) => DropdownMenuItem<int>(
                            value: row['id'] as int,
                            child: Text('${row['name']}')))
                        .toList(),
                    onChanged: (value) {
                      if (value != null) organizationId = value;
                    },
                  ),
                  TextFormField(
                    controller: name,
                    decoration: const InputDecoration(labelText: 'Full name'),
                    validator: _required,
                  ),
                  TextFormField(
                    controller: email,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                    validator: (value) {
                      if (value == null ||
                          !RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
                              .hasMatch(value.trim())) {
                        return 'Enter a valid email';
                      }
                      return null;
                    },
                  ),
                  TextFormField(
                    controller: password,
                    decoration: const InputDecoration(
                        labelText: 'Initial password (min 8 characters)'),
                    obscureText: true,
                    validator: (value) => (value?.length ?? 0) < 8
                        ? 'Use at least 8 characters'
                        : null,
                  ),
                  TextFormField(
                    controller: contact,
                    decoration: const InputDecoration(
                        labelText: 'Contact information (optional)'),
                    maxLength: 240,
                  ),
                  if (_locations.isNotEmpty)
                    DropdownButtonFormField<int?>(
                      initialValue: baseLocationId,
                      decoration:
                          const InputDecoration(labelText: 'Base location'),
                      items: [
                        const DropdownMenuItem<int?>(
                            value: null, child: Text('Not specified')),
                        ..._locations.map((row) => DropdownMenuItem<int?>(
                            value: row['id'] as int,
                            child: Text('${row['name']}'))),
                      ],
                      onChanged: (value) => baseLocationId = value,
                    ),
                  TextFormField(
                    initialValue: '50',
                    decoration: const InputDecoration(
                        labelText: 'Maximum travel distance (km)'),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    validator: (value) {
                      final number = double.tryParse(value ?? '');
                      return number == null || number <= 0
                          ? 'Enter a positive distance'
                          : null;
                    },
                    onChanged: (value) =>
                        maxTravelKm = double.tryParse(value) ?? maxTravelKm,
                  ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Willing to relocate'),
                    value: willingToRelocate,
                    onChanged: (value) =>
                        update(() => willingToRelocate = value),
                  ),
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Padding(
                      padding: EdgeInsets.only(top: 12, bottom: 4),
                      child: Text('Skills (all start unverified)',
                          style: TextStyle(fontWeight: FontWeight.w600)),
                    ),
                  ),
                  ..._skills.map((skill) {
                    final id = skill['id'] as int;
                    final selected = selectedSkills.containsKey(id);
                    return Row(children: [
                      Expanded(
                        child: CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text('${skill['name']}'),
                          value: selected,
                          onChanged: (value) => update(() {
                            if (value == true) {
                              selectedSkills[id] = 3;
                            } else {
                              selectedSkills.remove(id);
                            }
                          }),
                        ),
                      ),
                      if (selected)
                        DropdownButton<int>(
                          value: selectedSkills[id],
                          items: List.generate(
                              5,
                              (index) => DropdownMenuItem(
                                  value: index + 1,
                                  child: Text('Level ${index + 1}'))),
                          onChanged: (value) {
                            if (value != null) {
                              update(() => selectedSkills[id] = value);
                            }
                          },
                        )
                    ]);
                  }),
                ]),
              ),
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (!form.currentState!.validate()) return;
                if (selectedSkills.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Choose at least one skill')));
                  return;
                }
                Navigator.pop(dialogContext, {
                  'organization_id': organizationId,
                  'full_name': name.text.trim(),
                  'email': email.text.trim(),
                  'password': password.text,
                  'contact_info':
                      contact.text.trim().isEmpty ? null : contact.text.trim(),
                  'base_location_id': baseLocationId,
                  'max_travel_km': maxTravelKm,
                  'willing_to_relocate': willingToRelocate,
                  'languages': <String>[],
                  'equipment': <String>[],
                  'skills': selectedSkills.entries
                      .map((entry) => {
                            'skill_id': entry.key,
                            'level': entry.value,
                          })
                      .toList(),
                });
              },
              child: const Text('Register employee'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    email.dispose();
    password.dispose();
    contact.dispose();
    if (values != null) {
      await _write(
          '/organizations/${values.remove('organization_id')}/employees',
          body: values);
    }
  }

  String? _required(String? value) =>
      value == null || value.trim().isEmpty ? 'Required' : null;

  Future<void> _meshAction(String path, {Map<String, dynamic>? body}) =>
      _run(() async {
        final result = await _api.request(path,
            method: body == null && path.endsWith('/state') ? 'GET' : 'POST',
            body: body);
        if (mounted) {
          setState(() => _meshState = Map<String, dynamic>.from(result));
        }
        await _refresh();
      });

  Widget _meshLabView() => _list([
        const Text('Mesh Lab - simulation',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
        const Text(
            'Inherited signed RMP codec and store-and-forward demo. This simulates a disconnected bridge; it is not Bluetooth hardware. Queues are in memory and clear on server restart.'),
        Wrap(spacing: 8, children: [
          _button('Check bridge', Icons.refresh,
              () => _meshAction('/api/v1/demo/state')),
          _button('Toggle bridge', Icons.wifi,
              () => _meshAction('/api/v1/demo/bridge/toggle')),
          _button(
              'Send test SOS',
              Icons.science_outlined,
              () => _meshAction('/api/v1/demo/sos', body: {
                    'category': 'trapped',
                    'text': '[SIMULATION] Testing queued relief request',
                  })),
        ]),
        _data(_meshState),
        const Text(
            'Reconnect the bridge, then open SOS Queue to see delivered test requests in the same database.'),
      ]);

  Future<void> _createIncident() async {
    final data = await _form('Create incident', const [
      _Field('incident_type', 'Disaster type'),
      _Field('affected_area', 'Affected area'),
    ]);
    if (data != null) await _write('/incidents', body: data);
  }

  Future<void> _createLocation() async {
    final data = await _form('Add response location', [
      const _Field('name', 'Location name'),
      _Field('location_type', 'Type', options: [
        for (final type in ['settlement', 'ward', 'shelter', 'health_post'])
          {'id': type, 'name': type.replaceAll('_', ' ')}
      ]),
      const _Field('latitude', 'Latitude', number: true),
      const _Field('longitude', 'Longitude', number: true),
    ]);
    if (data != null) await _write('/locations', body: data);
  }

  Future<void> _acknowledgeSos(Map<String, dynamic> event) =>
      _write('/sos/${event['id']}/ack');

  Future<void> _dispatchSos(Map<String, dynamic> event) async {
    final ready = _assignments
        .where((row) =>
            ['approved', 'accepted', 'en_route', 'on_site']
                .contains(row['status']) &&
            (event['linked_need_id'] == null ||
                row['need_id'] == event['linked_need_id']))
        .toList();
    if (ready.isEmpty) {
      setState(() => _error =
          'No approved or active assignment is available to dispatch to this SOS.');
      return;
    }
    final values = await _form('Dispatch SOS', [
      _Field('assignment_id', 'Approved assignment',
          options: ready
              .map((row) => {
                    'id': row['id'],
                    'name':
                        '#${row['id']} · ${_location(row['location_id'] ?? row['need_location_id'])}'
                  })
              .toList()),
    ]);
    if (values != null) {
      await _write('/sos/${event['id']}/dispatch', body: values);
    }
  }

  Future<void> _resolveSos(Map<String, dynamic> event,
      {bool falseAlarm = false}) async {
    final values = await _form(falseAlarm ? 'Mark false alarm' : 'Resolve SOS',
        const [_Field('notes', 'Resolution notes', multiline: true)]);
    if (values != null) {
      await _write('/sos/${event['id']}/resolve', body: {
        'status': falseAlarm ? 'false_alarm' : 'resolved',
        'notes': values['notes']
      });
    }
  }

  Widget _sosQueueView() => _list([
        Align(
            alignment: Alignment.centerLeft,
            child:
                _button('Refresh queue', Icons.refresh, () => _run(_refresh))),
        for (final event in _sosEvents)
          _entry(
            'SOS #${event['id']} · ${_label(event['category'])}',
            '${event['message']}\n${event['has_location'] == true ? '${event['latitude']}, ${event['longitude']}' : 'Location unavailable'} · ${event['received_at_server']}',
            children: [
              if (event['address'] is Map)
                Text((event['address'] as Map)
                    .entries
                    .where((entry) => entry.value.toString().trim().isNotEmpty)
                    .map((entry) => '${_label(entry.key)}: ${entry.value}')
                    .join(' · ')),
              if (event['location_updated_at'] != null)
                Text(
                    'GPS updated: ${event['location_updated_at']} (reported device location)'),
              _badge(
                  'Urgency ${event['urgency']}/5${event['urgency_override'] == true ? ' · sender selected' : ' · AI assessed'}',
                  warning: (event['urgency'] as num? ?? 0) >= 4),
              if (event['interpretation'] is Map) ...[
                if ((event['interpretation']['location_text'] ?? '')
                    .toString()
                    .isNotEmpty)
                  Text(
                      'AI location wording: ${event['interpretation']['location_text']}'),
                if ((event['interpretation']['people_affected'] ?? 0) is num &&
                    (event['interpretation']['people_affected'] ?? 0) > 0)
                  Text(
                      'People affected: ${event['interpretation']['people_affected']}'),
                if ((event['interpretation']['needs'] as List? ?? [])
                    .isNotEmpty)
                  Text(
                      'Additional needs: ${(event['interpretation']['needs'] as List).join(', ')}'),
                if ((event['interpretation']['vulnerable_groups'] as List? ??
                        [])
                    .isNotEmpty)
                  Text(
                      'Vulnerable groups: ${(event['interpretation']['vulnerable_groups'] as List).join(', ')}'),
              ],
              _badge(_label(event['status']),
                  warning:
                      !['resolved', 'false_alarm'].contains(event['status'])),
              if (event['status'] == 'new')
                _button('Acknowledge', Icons.fact_check_outlined,
                    () => _acknowledgeSos(event)),
              if (['new', 'acknowledged'].contains(event['status']))
                _button('Dispatch', Icons.local_shipping_outlined,
                    () => _dispatchSos(event)),
              if (!['resolved', 'false_alarm'].contains(event['status'])) ...[
                _button('Resolve', Icons.check_circle_outline,
                    () => _resolveSos(event)),
                _button('False alarm', Icons.report_gmailerrorred_outlined,
                    () => _resolveSos(event, falseAlarm: true)),
              ],
            ],
          ),
      ], empty: 'No incoming SOS requests.');

  Future<void> _complete(Map<String, dynamic> assignment) async {
    final values = await _form('Complete Assignment', const [
      _Field('outcome_notes', 'Field outcome', multiline: true),
      _Field('completion_criteria_met', 'Completion criteria met',
          boolean: true),
    ]);
    if (values != null) {
      await _write('/assignments/${assignment['id']}/complete', body: values);
    }
  }

  Widget _assignmentsView() => _list([
        for (final assignment in _assignments)
          _entry('Assignment #${assignment['id']}',
              'Need #${assignment['need_id']} · Volunteer #${assignment['volunteer_id']}\nETA ${assignment['eta'] ?? 'Not available'}',
              children: [
                _badge(_label(assignment['status']),
                    warning: assignment['status'] == 'proposed'),
                if (assignment['outcome_notes'] != null)
                  Text('${assignment['outcome_notes']}'),
                Wrap(spacing: 8, children: [
                  if (_manager && assignment['status'] == 'proposed') ...[
                    _button(
                        'Approve',
                        Icons.check,
                        () =>
                            _write('/assignments/${assignment['id']}/approve')),
                    _button(
                        'Reject',
                        Icons.close,
                        () =>
                            _write('/assignments/${assignment['id']}/reject')),
                  ],
                  if (_ownAssignment(assignment) &&
                      assignment['status'] == 'approved') ...[
                    _button(
                        'Accept',
                        Icons.check,
                        () =>
                            _write('/assignments/${assignment['id']}/accept')),
                    _button(
                        'Reject',
                        Icons.close,
                        () =>
                            _write('/assignments/${assignment['id']}/reject')),
                  ],
                  if ((_manager || _ownAssignment(assignment)) &&
                      assignment['status'] == 'accepted')
                    _button(
                        'En Route',
                        Icons.directions_walk,
                        () => _write('/assignments/${assignment['id']}/status',
                            method: 'PATCH', body: {'status': 'en_route'})),
                  if ((_manager || _ownAssignment(assignment)) &&
                      assignment['status'] == 'en_route')
                    _button(
                        'On Site',
                        Icons.location_on_outlined,
                        () => _write('/assignments/${assignment['id']}/status',
                            method: 'PATCH', body: {'status': 'on_site'})),
                  if ((_manager || _ownAssignment(assignment)) &&
                      assignment['status'] == 'on_site')
                    _button('Record Outcome', Icons.task_alt,
                        () => _complete(assignment)),
                  if ((_manager || _ownAssignment(assignment)) &&
                      ['accepted', 'en_route', 'on_site']
                          .contains(assignment['status']))
                    _button(
                        'Cancel',
                        Icons.cancel_outlined,
                        () => _write('/assignments/${assignment['id']}/status',
                            method: 'PATCH', body: {'status': 'cancelled'})),
                ]),
              ]),
      ], empty: 'No assignments for this incident.');

  Future<void> _allocate(Map<String, dynamic> stock) async {
    final category = stock['resource_type'] == 'medicine'
        ? 'medical'
        : stock['resource_type'];
    final needs = _needs
        .where((need) =>
            need['category'] == category &&
            !['fulfilled', 'closed'].contains(need['status']))
        .toList();
    final values = await _form('Allocate ${stock['resource_type']}', [
      _Field('need_id', 'Need',
          options: needs
              .map((need) => {
                    'id': need['id'],
                    'name': '#${need['id']} · ${_location(need['location_id'])}'
                  })
              .toList()),
      _Field('quantity', 'Quantity (${stock['unit']})', number: true),
    ]);
    if (values != null) {
      await _write('/allocations',
          body: {...values, 'stock_id': stock['id']}, retrySafe: true);
    }
  }

  Future<void> _addStock() async {
    final values = await _form('Add Stock', [
      _Field('resource_id', 'Resource',
          options: _rows(_workspace['resources'])),
      _Field('organization_id', 'Organization',
          options: _rows(_workspace['organizations'])),
      _Field('location_id', 'Depot', options: _locations),
      const _Field('quantity_available', 'Quantity', number: true),
    ]);
    if (values != null) {
      await _write('/resources/stock', body: values);
    }
  }

  Future<void> _confirm(Map<String, dynamic> movement) async {
    final outstanding =
        (movement['quantity'] as num) - (movement['quantity_confirmed'] as num);
    final values = await _form('Confirm Receipt', [
      _Field('quantity_received', 'Quantity received (up to $outstanding)',
          initial: outstanding, number: true),
      const _Field('notes', 'Receipt notes', multiline: true),
    ]);
    if (values == null) return;
    final quantity = values['quantity_received'] as num;
    await _write('/movements/${movement['id']}/confirm',
        body: {
          ...values,
          'status': quantity == 0
              ? 'not_received'
              : quantity == outstanding
                  ? 'full'
                  : 'partial',
        },
        retrySafe: true);
  }

  Widget _suppliesView() => _list([
        if (_provider)
          Align(
              alignment: Alignment.centerLeft,
              child:
                  _button('Add Stock', Icons.inventory_2_outlined, _addStock)),
        for (final stock in _stock)
          _entry('${stock['resource_type']} · ${stock['organization_name']}',
              '${stock['quantity_available']} ${stock['unit']} available · ${stock['quantity_reserved']} reserved',
              children: [
                _button('Allocate', Icons.local_shipping_outlined,
                    () => _allocate(stock)),
              ]),
        const Padding(
            padding: EdgeInsets.only(top: 20),
            child: Text('Deliveries',
                style: TextStyle(fontSize: 19, fontWeight: FontWeight.w600))),
        if (_movements.isNotEmpty)
          _entry(
              'Delivery totals',
              '${_quantityTotal('quantity_dispatched')} dispatched · '
                  '${_quantityTotal('quantity_received')} received · '
                  '${_quantityTotal('quantity_remaining')} remaining'),
        if (_movements.isEmpty) const Text('No resource movements recorded.'),
        for (final movement in _movements)
          _entry(
              'Delivery #${movement['id']} · Need #${movement['need_id']}',
              'Allocated ${movement['quantity_allocated']} · '
                  'Dispatched ${movement['quantity_dispatched']} · '
                  'Received ${movement['quantity_received']} · '
                  'Remaining ${movement['quantity_remaining']}',
              children: [
                _badge(_label(movement['status']),
                    warning: movement['status'] != 'confirmed'),
                Wrap(spacing: 8, children: [
                  if (_provider && movement['status'] == 'allocated')
                    _button(
                        'Dispatch',
                        Icons.local_shipping_outlined,
                        () => _write('/movements/${movement['id']}/status',
                            method: 'PATCH', body: {'status': 'dispatched'})),
                  if (_provider && movement['status'] == 'dispatched')
                    _button(
                        'Mark Delivered',
                        Icons.where_to_vote_outlined,
                        () => _write('/movements/${movement['id']}/status',
                            method: 'PATCH', body: {'status': 'delivered'})),
                  if (movement['status'] == 'delivered')
                    _button('Confirm Receipt', Icons.fact_check_outlined,
                        () => _confirm(movement)),
                ]),
              ]),
      ]);

  String _quantityTotal(String key) {
    final total = _movements.fold<double>(
        0, (sum, movement) => sum + ((movement[key] as num?)?.toDouble() ?? 0));
    return total.toStringAsFixed(total == total.roundToDouble() ? 0 : 2);
  }

  Future<void> _blockage() async {
    final values = await _form('Report Road Blockage', const [
      _Field('latitude', 'Latitude', number: true),
      _Field('longitude', 'Longitude', number: true),
      _Field('radius_km', 'Affected radius (km)', initial: 0.25, number: true),
      _Field('notes', 'Observed obstruction', multiline: true),
    ]);
    if (values != null) await _write('/blockages', body: values);
  }

  Future<void> _importBaseline() async {
    final values = await _form('Import Settlement Baseline', const [
      _Field('csv', 'CSV', multiline: true),
    ]);
    if (values != null) {
      await _run(() async {
        await _api.importBaseline(values['csv'] as String);
        await _refresh();
      });
    }
  }

  Future<void> _reassignments() => _run(() async {
        final result = await _api
            .request('/reassignment-suggestions?incident_id=$_incident');
        final suggestions = _rows(result['suggestions']);
        if (!mounted) return;
        final chosen = await showModalBottomSheet<Map<String, dynamic>>(
          context: context,
          isScrollControlled: true,
          useSafeArea: true,
          builder: (context) => SizedBox(
              height: MediaQuery.sizeOf(context).height * 0.75,
              child: _list([
                const Text('Reassignment Suggestions',
                    style:
                        TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
                if (suggestions.isEmpty)
                  const Text(
                      'No safe surplus-to-shortage transfer is available.'),
                for (final suggestion in suggestions)
                  _entry(
                      'Volunteer #${suggestion['volunteer_id']} → Need #${suggestion['need_id']}',
                      '${suggestion['explanation']}',
                      children: [
                        Text(
                            'Estimated travel: ${suggestion['route']?['duration_min']} min'),
                        FilledButton.icon(
                            onPressed: () => Navigator.pop(
                                context,
                                Map<String, dynamic>.from(
                                    suggestion['proposed_assignment'])),
                            icon: const Icon(Icons.swap_horiz),
                            label: const Text('Create Draft')),
                      ]),
              ])),
        );
        if (chosen != null) {
          await _api.request('/assignments', method: 'POST', body: {
            'need_id': chosen['need_id'],
            'volunteer_id': chosen['volunteer_id']
          });
          await _refresh();
        }
      });

  Future<void> _blockages() => _run(() async {
        final result = await _api.request('/blockages');
        final rows = result is List ? _rows(result) : _rows(result['items']);
        if (!mounted) return;
        final cleared = await showModalBottomSheet<int>(
          context: context,
          isScrollControlled: true,
          useSafeArea: true,
          builder: (context) => SizedBox(
              height: MediaQuery.sizeOf(context).height * 0.75,
              child: _list([
                const Text('Road Blockages',
                    style:
                        TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
                if (rows.isEmpty) const Text('No road blockages reported.'),
                for (final row in rows)
                  _entry('Blockage #${row['id']}',
                      '${row['notes'] ?? row['road_name'] ?? 'No notes'}',
                      children: [
                        Text('${row['latitude']}, ${row['longitude']}'),
                        _badge(
                            row['verified'] == true ? 'Verified' : 'Unverified',
                            warning: row['verified'] != true),
                        if (row['cleared_at'] == null)
                          FilledButton.icon(
                              onPressed: () =>
                                  Navigator.pop(context, row['id'] as int),
                              icon: const Icon(Icons.check_circle_outline),
                              label: const Text('Mark Cleared')),
                      ]),
              ])),
        );
        if (cleared != null) {
          await _api.request('/blockages/$cleared/clear', method: 'PATCH');
          await _refresh();
        }
      });

  Future<void> _damage(Map<String, dynamic> location) async {
    final values = await _form('Verify Damage Assessment', [
      const _Field('kind', 'Assessment', options: [
        {'id': 'post', 'name': 'Post-disaster'},
        {'id': 'pre', 'name': 'Pre-disaster'}
      ]),
      const _Field('damage_level', 'Damage level (0-5)',
          number: true, initial: 0),
      const _Field('details', 'Observed damage', multiline: true),
    ]);
    if (values != null) {
      await _write('/locations/${location['id']}/damage-assessments',
          body: values);
    }
  }

  Widget _intelligenceView() {
    if (!_manager) {
      return _list([
        const Text('Coordinator access is required for disaster intelligence.')
      ]);
    }
    return _list([
      if (_incident != null)
        Wrap(spacing: 8, runSpacing: 4, children: [
          _button('Scan Bottlenecks', Icons.radar,
              () => _write('/bottlenecks/scan?incident_id=$_incident')),
          _button(
              'Coverage',
              Icons.groups_outlined,
              () => _run(() async => _showData('Skill Coverage',
                  await _api.request('/coverage?incident_id=$_incident')))),
          _button('Reassignments', Icons.swap_horiz, _reassignments),
          _button(
              'Recovery',
              Icons.summarize_outlined,
              () => _run(() async => _showData(
                  'Recovery Report',
                  await _api
                      .request('/reports/recovery?incident_id=$_incident')))),
          _button('Import Baseline', Icons.upload_file, _importBaseline),
          _button('Road Blockage', Icons.add_road, _blockage),
          _button('Blockages', Icons.wrong_location_outlined, _blockages),
        ]),
      if (_situation['counts'] != null)
        Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Wrap(spacing: 18, runSpacing: 12, children: [
              for (final entry in (_situation['counts'] as Map).entries)
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${entry.value}',
                      style: const TextStyle(
                          fontSize: 26, fontWeight: FontWeight.w600)),
                  Text(_label(entry.key)),
                ]),
            ])),
      for (final location in _locations)
        _entry('${location['name']}', 'Location profile', children: [
          _button(
              'View Profile',
              Icons.location_city_outlined,
              () => _run(() async => _showData('${location['name']}',
                  await _api.request('/locations/${location['id']}/profile')))),
          _button('Verify Damage', Icons.fact_check_outlined,
              () => _damage(location)),
        ]),
      const Padding(
          padding: EdgeInsets.only(top: 20),
          child: Text('Bottlenecks',
              style: TextStyle(fontSize: 19, fontWeight: FontWeight.w600))),
      if (_flags.isEmpty) const Text('No flags recorded.'),
      for (final flag in _flags)
        _entry(
            _label(flag['type'] ?? flag['flag_type']), '${flag['explanation']}',
            children: [
              Wrap(spacing: 8, children: [
                _badge('Severity ${flag['severity']}/5', warning: true),
                _badge(_label(flag['status']))
              ]),
              if (flag['suggested_action'] != null)
                Text('${flag['suggested_action']}'),
              Wrap(children: [
                _button('Evidence', Icons.manage_search,
                    () => _showData('Evidence', flag['evidence'])),
                if (flag['status'] == 'open')
                  _button(
                      'Acknowledge',
                      Icons.visibility_outlined,
                      () => _write('/bottlenecks/${flag['id']}',
                          method: 'PATCH', body: {'status': 'acknowledged'})),
                if (flag['status'] != 'resolved')
                  _button(
                      'Resolve',
                      Icons.check_circle_outline,
                      () => _write('/bottlenecks/${flag['id']}',
                          method: 'PATCH', body: {'status': 'resolved'})),
              ]),
            ]),
    ]);
  }

  Widget _proposalsView() => _list([
        for (final proposal in _proposals)
          _entry('Draft #${proposal['id']} · ${_label(proposal['type'])}',
              '${proposal['rationale']}',
              children: [
                Wrap(spacing: 8, children: [
                  _badge(
                      '${proposal['source']} · ${proposal['confidence']} confidence',
                      warning: proposal['source'] == 'fallback'),
                  _badge('Awaiting approval', warning: true)
                ]),
                const SizedBox(height: 8),
                _data(proposal['payload']),
                if (['assignment', 'allocation'].contains(proposal['type']))
                  Wrap(children: [
                    _button(
                        'Approve',
                        Icons.check,
                        () => _write(proposal['type'] == 'assignment'
                            ? '/assignments/${proposal['result_id']}/approve'
                            : '/ai/proposals/${proposal['id']}/approve')),
                    _button(
                        'Reject',
                        Icons.close,
                        () => _write(proposal['type'] == 'assignment'
                            ? '/assignments/${proposal['result_id']}/reject'
                            : '/ai/proposals/${proposal['id']}/reject')),
                  ]),
              ]),
      ], empty: 'No draft proposals awaiting review.');

  Widget _loginView() => Center(
      child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.all(24),
            children: [
              const Icon(Icons.hub_outlined,
                  size: 48, color: Color(0xFF4CAF7D)),
              const SizedBox(height: 20),
              const Text('Rahat',
                  style: TextStyle(fontSize: 26, fontWeight: FontWeight.w600)),
              const SizedBox(height: 24),
              if (_register) ...[
                TextField(
                    controller: _name,
                    decoration: const InputDecoration(labelText: 'Full name')),
                const SizedBox(height: 14)
              ],
              TextField(
                  controller: _email,
                  decoration: const InputDecoration(labelText: 'Email'),
                  keyboardType: TextInputType.emailAddress),
              const SizedBox(height: 14),
              TextField(
                  controller: _password,
                  decoration: const InputDecoration(labelText: 'Password'),
                  obscureText: true,
                  onSubmitted: (_) {
                    if (!_busy) _login();
                  }),
              const SizedBox(height: 24),
              FilledButton.icon(
                  onPressed: _busy ? null : _login,
                  icon: const Icon(Icons.login),
                  label: Text(_register ? 'Create Account' : 'Sign In')),
              if (!widget.stationMode)
                TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => _register = !_register),
                    child: Text(_register
                        ? 'Sign in instead'
                        : 'Create community account')),
            ],
          )));

  @override
  Widget build(BuildContext context) {
    final incidents = _rows(_workspace['incidents']);
    final pages = <String, Widget>{
      if (widget.stationMode && _manager) 'SOS Queue': _sosQueueView(),
      if (widget.section != 'volunteer') 'Needs': _needsView(),
      if (widget.section != 'response') ...{
        'Assignments': _assignmentsView(),
        'Volunteers': _volunteersView(),
        'Help nearby': _offersView(),
      },
      if (widget.section != 'volunteer') 'Supplies': _suppliesView(),
      if (_manager && widget.section != 'volunteer') ...{
        if (!widget.stationMode) 'SOS Queue': _sosQueueView(),
        if (!widget.stationMode) 'Nepal Map': MapScreen(api: _api),
        'Mesh Lab': _meshLabView(),
        'Intelligence': _intelligenceView(),
        'Drafts': _proposalsView(),
      },
    };
    return DefaultTabController(
        key: ValueKey('${widget.section}:$_manager'),
        length: pages.length,
        child: Scaffold(
          appBar: widget.embedded
              ? null
              : AppBar(
                  title: const Text('Rahat'),
                  actions: [
                    if (_user != null) ...[
                      IconButton(
                          tooltip: 'Refresh',
                          onPressed: _busy ? null : () => _run(_refresh),
                          icon: const Icon(Icons.refresh)),
                      IconButton(
                          tooltip: 'Sign out',
                          onPressed: _busy
                              ? null
                              : () {
                                  setState(() => _workspace = {});
                                  _session.signOut();
                                },
                          icon: const Icon(Icons.logout)),
                    ],
                  ],
                ),
          body: Column(children: [
            if (_busy) const LinearProgressIndicator(minHeight: 3),
            if (_error != null)
              Container(
                  width: double.infinity,
                  color: const Color(0xFF422323),
                  padding: const EdgeInsets.all(12),
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.error_outline, size: 20),
                        const SizedBox(width: 8),
                        Expanded(child: Text(_error!)),
                        IconButton(
                            tooltip: 'Dismiss error',
                            onPressed: () => setState(() => _error = null),
                            icon: const Icon(Icons.close)),
                      ])),
            if (_user == null)
              Expanded(child: _loginView())
            else ...[
              Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                  child: Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text('${_user!['full_name']}'),
                        _badge(_label(_user!['role'])),
                        if (!widget.stationMode)
                          _button('My profile',
                              Icons.contact_emergency_outlined, _editProfile),
                        if (_notifications.isNotEmpty)
                          _button(
                              'Alerts (${_notifications.length})',
                              Icons.notifications_active_outlined,
                              () => _showData(
                                  'Unread notifications', _notifications)),
                        if (_manager) ...[
                          _button('New incident', Icons.add_alert_outlined,
                              _createIncident),
                          _button('Add location',
                              Icons.add_location_alt_outlined, _createLocation),
                        ],
                        if (widget.embedded) ...[
                          IconButton(
                              tooltip: 'Refresh response data',
                              onPressed: _busy ? null : () => _run(_refresh),
                              icon: const Icon(Icons.refresh)),
                          IconButton(
                              tooltip: 'Sign out',
                              onPressed: _busy
                                  ? null
                                  : () {
                                      setState(() => _workspace = {});
                                      _session.signOut();
                                    },
                              icon: const Icon(Icons.logout)),
                        ],
                        if (incidents.isNotEmpty)
                          SizedBox(
                              width: 260,
                              child: DropdownButtonFormField<int?>(
                                key: ValueKey(_incident),
                                initialValue: _incident,
                                isExpanded: true,
                                decoration: const InputDecoration(
                                    labelText: 'Incident'),
                                items: [
                                  const DropdownMenuItem<int?>(
                                      value: null,
                                      child: Text('All incidents')),
                                  ...incidents.map((row) => DropdownMenuItem<
                                          int?>(
                                      value: row['id'] as int,
                                      child: Text(
                                          '${_label(row['incident_type'])} · ${row['name']}',
                                          overflow: TextOverflow.ellipsis))),
                                ],
                                onChanged: _busy
                                    ? null
                                    : (value) {
                                        setState(() => _incident = value);
                                        _run(_refresh);
                                      },
                              )),
                      ])),
              const Divider(height: 1),
              if (widget.stationMode && _manager) ...[
                const Padding(
                  padding: EdgeInsets.fromLTRB(20, 12, 20, 4),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text('Live operations map',
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w600)),
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 20),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                        'Real SOS locations from the shared backend. Map markers never imply delivery, dispatch, or road closure without evidence.'),
                  ),
                ),
                SizedBox(
                  height: 380,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: MapScreen(api: _api),
                  ),
                ),
                const Divider(height: 1),
              ],
              TabBar(
                  isScrollable: true,
                  tabAlignment: TabAlignment.start,
                  tabs: pages.keys.map((label) => Tab(text: label)).toList()),
              Expanded(child: TabBarView(children: pages.values.toList())),
            ],
          ]),
        ));
  }
}

class _Field {
  final String key;
  final String label;
  final dynamic initial;
  final bool number;
  final bool multiline;
  final bool boolean;
  final bool required;
  final List<Map<String, dynamic>>? options;
  const _Field(this.key, this.label,
      {this.initial,
      this.number = false,
      this.multiline = false,
      this.boolean = false,
      this.required = true,
      this.options});
}

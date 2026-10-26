import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../module_api.dart';
import 'coordination.dart';
import 'mesh.dart';
import 'settings.dart';
import '../widgets/emergency_calls.dart';
import '../mesh_service.dart';

class HomeScreen extends StatefulWidget {
  final ModuleApi? moduleApi;
  final CoordinationSession? session;
  final bool showNavigation;
  const HomeScreen(
      {super.key, this.moduleApi, this.session, this.showNavigation = true});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;
  late final CoordinationSession _coordinationSession;
  late final bool _ownsCoordinationSession;

  @override
  void initState() {
    super.initState();
    _ownsCoordinationSession = widget.session == null;
    _coordinationSession = widget.session ??
        CoordinationSession(
          api: widget.moduleApi,
          ownsApi: widget.moduleApi == null,
        );
  }

  @override
  void dispose() {
    if (_ownsCoordinationSession) _coordinationSession.dispose();
    super.dispose();
  }

  void _select(int index) => setState(() => _selectedIndex = index);

  @override
  Widget build(BuildContext context) {
    const titles = ['Rahat', 'Volunteer', 'Response', 'Mesh', 'Settings'];
    final pageIndex = _selectedIndex;
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.emergency, size: 26),
            const SizedBox(width: 8),
            Text(titles[_selectedIndex]),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Request status',
            icon: const Icon(Icons.timeline),
            onPressed: () => Navigator.pushNamed(context, '/status'),
          ),
          Consumer<AppState>(
            builder: (_, appState, __) => IconButton(
              icon: Text(appState.t(context, 'English', 'English'),
                  style: const TextStyle(fontSize: 14)),
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
        ],
      ),
      body: SafeArea(
          child: IndexedStack(index: pageIndex, children: [
        _OpsView(onNavigate: _select),
        CoordinationScreen(
            session: _coordinationSession,
            embedded: true,
            section: 'volunteer'),
        CoordinationScreen(
            session: _coordinationSession, embedded: true, section: 'response'),
        const MeshScreen(embedded: true),
        const SettingsScreen(embedded: true),
      ])),
      bottomNavigationBar: widget.showNavigation
          ? NavigationBar(
              selectedIndex: _selectedIndex,
              onDestinationSelected: (i) => setState(() => _selectedIndex = i),
              destinations: const [
                NavigationDestination(
                    icon: Icon(Icons.home_outlined), label: 'Home'),
                NavigationDestination(
                    icon: Icon(Icons.volunteer_activism_outlined),
                    label: 'Volunteer'),
                NavigationDestination(
                    icon: Icon(Icons.assignment_outlined),
                    label: 'Request and Response'),
                NavigationDestination(
                    icon: Icon(Icons.wifi_outlined), label: 'Mesh'),
                NavigationDestination(
                    icon: Icon(Icons.settings_outlined), label: 'Settings'),
              ],
            )
          : null,
    );
  }
}

class _OpsView extends StatefulWidget {
  final ValueChanged<int> onNavigate;
  const _OpsView({required this.onNavigate});

  @override
  State<_OpsView> createState() => _OpsViewState();
}

class _OpsViewState extends State<_OpsView> {
  Future<List<Map<String, dynamic>>>? _incidents;
  String? _station;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final station = context.watch<AppState>().stationUrl;
    if (_station != station) {
      _station = station;
      _incidents = _loadIncidents(station);
    }
  }

  Future<List<Map<String, dynamic>>> _loadIncidents(String baseUrl) async {
    final api = ModuleApi(baseUrl: baseUrl);
    try {
      final health =
          Map<String, dynamic>.from(await api.request('/api/health'));
      if (health['status'] != 'ok') {
        throw const ModuleApiException('Backend database is unavailable.');
      }
      return [];
    } finally {
      api.close();
    }
  }

  void _refresh() => setState(() => _incidents = _loadIncidents(_station!));

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          Semantics(
            button: true,
            label: 'Direct SOS',
            child: Container(
              width: 188,
              height: 188,
              padding: const EdgeInsets.all(10),
              decoration: const BoxDecoration(
                color: Color(0xFFEF5350),
                shape: BoxShape.circle,
              ),
              child: ElevatedButton(
                onPressed: () => Navigator.pushNamed(context, '/direct-sos'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF8B0000),
                  foregroundColor: Colors.white,
                  elevation: 4,
                  shape: const CircleBorder(),
                  padding: EdgeInsets.zero,
                ),
                child: const Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.emergency, size: 42),
                    SizedBox(height: 4),
                    Text('DIRECT SOS',
                        style: TextStyle(
                            fontSize: 21, fontWeight: FontWeight.w800)),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Text('Emergency assistance',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600)),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            height: 72,
            child: ElevatedButton.icon(
              onPressed: () => Navigator.pushNamed(context, '/sos'),
              icon: const Icon(Icons.emergency, size: 28),
              label: const Text('Request emergency help',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFD32F2F),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
          const SizedBox(height: 16),
          const EmergencyCalls(),
          const SizedBox(height: 24),
          _deliveryStatus(appState),
          const SizedBox(height: 16),
          LayoutBuilder(builder: (context, constraints) {
            final compact = constraints.maxWidth < 560;
            final cardWidth = compact
                ? constraints.maxWidth
                : (constraints.maxWidth - 12) / 2;
            return Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                SizedBox(
                  width: cardWidth,
                  child: _actionCard(
                    icon: Icons.emergency_share_outlined,
                    color: const Color(0xFFD32F2F),
                    title: 'I need help',
                    description:
                        'Send an SOS or describe a local need for coordinators and responders.',
                    action: () => Navigator.pushNamed(context, '/sos'),
                  ),
                ),
                SizedBox(
                  width: cardWidth,
                  child: _actionCard(
                    icon: Icons.volunteer_activism_outlined,
                    color: const Color(0xFF4CAF7D),
                    title: 'I can help',
                    description:
                        'Register your skills, offer supplies, or respond to a nearby request.',
                    action: () => widget.onNavigate(2),
                  ),
                ),
              ],
            );
          }),
          const SizedBox(height: 20),
          Align(
            alignment: Alignment.centerLeft,
            child: Text(appState.t(context, 'System status', 'प्रणाली स्थिति'),
                style:
                    const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          ),
          const SizedBox(height: 10),
          FutureBuilder<List<Map<String, dynamic>>>(
            future: _incidents,
            builder: (ctx, snap) {
              if (snap.connectionState == ConnectionState.waiting) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snap.hasError) {
                return ListTile(
                    leading:
                        const Icon(Icons.cloud_off, color: Color(0xFFFBC02D)),
                    title: const Text('Station connection unavailable'),
                    trailing: IconButton(
                        tooltip: 'Retry connection',
                        onPressed: _refresh,
                        icon: const Icon(Icons.refresh)));
              }
              if (!snap.hasData || snap.data!.isEmpty) {
                return const Text(
                    'Backend reachable. Sign in to continue and view incidents and coordination data.',
                    style: TextStyle(color: Colors.grey));
              }

              return Column(
                children: snap.data!.take(6).map((inc) {
                  final sev = (inc['category'] ?? 'other').toString();
                  return ListTile(
                    leading: CircleAvatar(
                      backgroundColor: AppState.severityColor(sev),
                      child: Text(
                          '${inc['priority']?.toStringAsFixed(0) ?? '--'}',
                          style: const TextStyle(
                              color: Colors.white, fontSize: 12)),
                    ),
                    title: Text(
                        '${inc['name'] ?? inc['category'] ?? 'Incident'} — ${inc['affected_area'] ?? inc['area'] ?? 'Area not recorded'}'),
                    subtitle: Text(
                        '${inc['status'] ?? 'Status not recorded'} · priority ${inc['priority'] is num ? (inc['priority'] as num).toStringAsFixed(1) : '—'}'),
                  );
                }).toList(),
              );
            },
          ),
          const SizedBox(height: 20),
          _meshChip(appState),
        ],
      ),
    );
  }

  Widget _actionCard({
    required IconData icon,
    required Color color,
    required String title,
    required String description,
    required VoidCallback action,
  }) {
    return Card(
      margin: EdgeInsets.zero,
      color: const Color(0xFF151B1F),
      child: InkWell(
        onTap: action,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                backgroundColor: color.withValues(alpha: 0.18),
                foregroundColor: color,
                child: Icon(icon),
              ),
              const SizedBox(height: 12),
              Text(title,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text(description,
                  style:
                      const TextStyle(color: Color(0xFFADB9BF), height: 1.35)),
              const SizedBox(height: 12),
              Row(
                children: [
                  Text('Open',
                      style:
                          TextStyle(color: color, fontWeight: FontWeight.w600)),
                  const SizedBox(width: 4),
                  Icon(Icons.arrow_forward, size: 16, color: color),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _meshChip(AppState appState) {
    final mesh = context.watch<MeshService>();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF151B1F),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
              mesh.running
                  ? Icons.bluetooth_connected
                  : Icons.bluetooth_disabled,
              size: 16,
              color: Colors.white),
          const SizedBox(width: 6),
          Flexible(
              child: Text(
                  mesh.supported
                      ? mesh.running
                          ? 'Bluetooth relay on · ${mesh.peerCount} peer links'
                          : 'Nearby Android relay available under Mesh'
                      : 'Bluetooth relay requires the Android app',
                  style: const TextStyle(color: Colors.white, fontSize: 13))),
        ],
      ),
    );
  }

  Widget _deliveryStatus(AppState appState) {
    if (appState.status == 'idle') {
      return const ListTile(
          contentPadding: EdgeInsets.zero,
          leading: Icon(Icons.mail_outline),
          title: Text('No SOS sent'));
    }
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF151B1F),
        border: Border.all(color: const Color(0xFF263038)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            const Text('SOS status',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            Flexible(
                child: Text(appState.deliveryLabel,
                    textAlign: TextAlign.end,
                    style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Color(0xFFFBC02D)))),
          ]),
          if (appState.incidentId != null)
            Align(
                alignment: Alignment.centerLeft,
                child: Text('SOS #${appState.incidentId}')),
          if (appState.status == 'queued')
            const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                    'Saved on this device only; it has not reached the backend.')),
          Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                  onPressed: () => Navigator.pushNamed(context, '/status'),
                  child: const Text('View status'))),
        ],
      ),
    );
  }
}

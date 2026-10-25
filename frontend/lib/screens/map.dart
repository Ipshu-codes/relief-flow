import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:geolocator/geolocator.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../device_location.dart';
import '../module_api.dart';
import '../nepal_map_data.dart';

/// Nepal bounding box (matches the routing extract's coverage).
const double _north = 30.60;
const double _south = 26.28;
const double _west = 80.00;
const double _east = 88.30;

/// Longitude degrees shrink towards the poles; correct so Nepal is not stretched.
final double _cosMidLat = math.cos(((_north + _south) / 2) * math.pi / 180);

/// Places worth labelling at country scale.
const Set<String> _majorCities = {
  'Kathmandu',
  'Pokhara',
  'Biratnagar',
  'Birganj',
  'Dharan',
  'Butwal',
  'Nepalganj',
  'Hetauda',
  'Janakpur',
  'Birendranagar',
  'Dhangadhi',
  'Ilam',
  'Jomsom',
};

class MapScreen extends StatefulWidget {
  final ModuleApi? api;
  const MapScreen({super.key, this.api});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  NepalMapData? _mapData;
  List<Map<String, dynamic>> _incidents = [];
  Position? _device;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final appState = context.read<AppState>();
    setState(() {
      _loading = true;
      _error = null;
    });

    List<Map<String, dynamic>> incidents = [];
    try {
      final api = widget.api ?? ModuleApi(baseUrl: appState.backendUrl);
      try {
        final data = await api.request('/sos');
        incidents = (data as List? ?? []).whereType<Map>().map((item) {
          final event = Map<String, dynamic>.from(item);
          return {
            ...event,
            'lat': event['latitude'],
            'lon': event['longitude'],
            'title': '${event['category'] ?? 'SOS'} request',
            'priority': ((event['urgency'] as num?)?.toDouble() ?? 3) * 20,
          };
        }).toList();
      } finally {
        if (widget.api == null) api.close();
      }
    } catch (_) {
      // Offline map still works; markers just come from the last fetch.
    }

    try {
      final data = await NepalMapData.load(rootBundle);
      Position? device;
      try {
        device = await currentDevicePosition();
      } catch (_) {
        // The basemap remains useful when this device has no GPS fix.
      }
      if (!mounted) return;
      setState(() {
        _mapData = data;
        _incidents = incidents;
        _device = device;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Map data unavailable: $e';
      });
    }
  }

  Future<void> _refreshLocation() async {
    Position? device;
    try {
      device = await currentDevicePosition();
    } catch (_) {}
    if (!mounted) return;
    setState(() => _device = device);
  }

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
        title: Text(appState.t(context, 'Nepal map', 'नेपाल नक्सा')),
        actions: [
          IconButton(
            tooltip: appState.t(context, 'Find my location', 'मेरो स्थान'),
            icon: const Icon(Icons.my_location),
            onPressed: _refreshLocation,
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : LayoutBuilder(
              builder: (context, constraints) {
                final size = Size(constraints.maxWidth, constraints.maxHeight);
                final projection = _Projection.fit(size);
                return Stack(
                  children: [
                    Positioned.fill(
                      child: CustomPaint(
                        painter: _NepalBasemapPainter(
                          provinces: _mapData?.provinces ?? const [],
                          headquarters: _mapData?.headquarters ?? const [],
                        ),
                      ),
                    ),
                    if (_device != null)
                      _deviceMarker(projection, size, _device!, appState),
                    for (final incident in _incidents)
                      _incidentMarker(projection, size, incident, appState),
                    Positioned(
                      left: 12,
                      right: 12,
                      bottom: 12,
                      child: _legend(appState),
                    ),
                    if (_error != null)
                      Positioned(
                        top: 12,
                        left: 12,
                        right: 12,
                        child: _banner(_error!),
                      ),
                  ],
                );
              },
            ),
    );
  }

  Widget _deviceMarker(
    _Projection projection,
    Size size,
    Position device,
    AppState appState,
  ) {
    final accuracy = device.accuracy;
    final accuracyPx =
        math.min(120.0, math.max(14.0, accuracy / 111320.0 * projection.scale));
    final color = accuracy <= 100
        ? const Color(0xFF4EA1FF)
        : const Color(0xFFF57C00);

    final center = projection.toScreen(device.latitude, device.longitude);
    return Positioned(
      left: center.dx - accuracyPx,
      top: center.dy - accuracyPx,
      width: accuracyPx * 2,
      height: accuracyPx * 2,
      child: IgnorePointer(
        child: Container(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.14),
            border: Border.all(color: color.withValues(alpha: 0.5)),
          ),
          child: Center(
            child: Container(
              width: 14,
              height: 14,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color,
                border: Border.all(color: Colors.white, width: 2),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _incidentMarker(
    _Projection projection,
    Size size,
    Map<String, dynamic> incident,
    AppState appState,
  ) {
    final lat = _asDouble(incident['lat']);
    final lon = _asDouble(incident['lon']);
    if (lat == null || lon == null) return const SizedBox.shrink();

    final position = projection.toScreen(lat, lon);
    if (position.dx < -20 ||
        position.dy < -20 ||
        position.dx > size.width + 20 ||
        position.dy > size.height + 20) {
      return const SizedBox.shrink();
    }

    final severity = _severityOf(incident);
    final color = AppState.severityColor(severity);
    final label = _labelOf(incident);

    return Positioned(
      left: position.dx - 16,
      top: position.dy - 16,
      width: 32,
      height: 32,
      child: Tooltip(
        message: '$label\n${lat.toStringAsFixed(5)}, ${lon.toStringAsFixed(5)}',
        child: GestureDetector(
          onTap: () => _showIncident(appState, incident, lat, lon),
          child: Center(
            child: Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color.withValues(alpha: 0.25),
                border: Border.all(color: color, width: 2),
              ),
              child: Center(
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: color),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _showIncident(
    AppState appState,
    Map<String, dynamic> incident,
    double lat,
    double lon,
  ) {
    final reports = incident['report_count'] ?? 0;
    final priority = _asDouble(incident['priority']);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF151B1F),
      builder: (context) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.place, color: AppState.severityColor(_severityOf(incident))),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _labelOf(incident),
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('${lat.toStringAsFixed(5)}, ${lon.toStringAsFixed(5)}',
                style: const TextStyle(fontFamily: 'monospace')),
            const SizedBox(height: 6),
            Text(
              appState.t(
                context,
                '${incident['status'] ?? 'new'} · $reports report(s) · priority '
                    '${priority == null ? '—' : priority.toStringAsFixed(0)}',
                '${incident['status'] ?? 'new'} · $reports रिपोर्ट · प्राथमिकता '
                    '${priority == null ? '—' : priority.toStringAsFixed(0)}',
              ),
              style: const TextStyle(color: Color(0xFF9AA9B3)),
            ),
            const SizedBox(height: 12),
            Text(
              appState.t(
                context,
                'This point is where the SOS packet was received.',
                'यो बिन्दु SOS प्याकेट प्राप्त भएको स्थान हो।',
              ),
              style: const TextStyle(fontSize: 12, color: Color(0xFF9AA9B3)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _legend(AppState appState) {
    final device = _device;
    final isApproximate = device != null && device.accuracy > 100;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xE60D1216),
        border: Border.all(color: const Color(0xFF263038)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 14,
            runSpacing: 6,
            children: [
              _legendItem(
                isApproximate
                    ? const Color(0xFFF57C00)
                    : const Color(0xFF4EA1FF),
                device == null
                    ? appState.t(context, 'You (locating)', 'तपाईं (खोज्दै)')
                    : appState.t(
                        context,
                        'You ${device.latitude.toStringAsFixed(5)}, '
                            '${device.longitude.toStringAsFixed(5)}',
                        'तपाईं ${device.latitude.toStringAsFixed(5)}, '
                            '${device.longitude.toStringAsFixed(5)}',
                      ),
              ),
              _legendItem(AppState.severityColor('critical'),
                  appState.t(context, 'Critical', 'गम्भीर')),
              _legendItem(AppState.severityColor('high'),
                  appState.t(context, 'High', 'उच्च')),
              _legendItem(AppState.severityColor('medium'),
                  appState.t(context, 'Medium', 'मध्यम')),
              _legendItem(AppState.severityColor('low'),
                  appState.t(context, 'Low', 'कम')),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            appState.t(
              context,
              'Nepal · offline province boundaries · geoJSON-Nepal (MIT)',
              'नेपाल · अफलाइन प्रदेश सीमा · geoJSON-Nepal (MIT)',
            ),
            style: const TextStyle(fontSize: 10, color: Color(0xFF6B7A85)),
          ),
        ],
      ),
    );
  }

  Widget _legendItem(Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(shape: BoxShape.circle, color: color),
        ),
        const SizedBox(width: 5),
        Text(label, style: const TextStyle(fontSize: 11, color: Color(0xFF9AA9B3))),
      ],
    );
  }

  Widget _banner(String message) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xE6D32F2F),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(message, style: const TextStyle(color: Colors.white, fontSize: 12)),
    );
  }
}

double? _asDouble(dynamic value) => value is num ? value.toDouble() : null;

String _severityOf(Map<String, dynamic> incident) {
  final severity = incident['severity'];
  if (severity is String) return severity;
  final priority = _asDouble(incident['priority']);
  if (priority == null) return 'medium';
  if (priority >= 85) return 'critical';
  if (priority >= 70) return 'high';
  if (priority >= 40) return 'medium';
  return 'low';
}

String _labelOf(Map<String, dynamic> incident) {
  final title = incident['title'];
  if (title is String && title.trim().isNotEmpty) return title;
  final category = incident['category'];
  if (category is String && category.isNotEmpty) {
    final words = category.replaceAll('_', ' ');
    return '${words[0].toUpperCase()}${words.substring(1)} incident';
  }
  return 'SOS incident';
}

class _Projection {
  const _Projection(this.scale, this.origin);

  /// Pixels per degree of latitude.
  final double scale;
  final Offset origin;

  factory _Projection.fit(Size size) {
    const padding = 18.0;
    final lonSpan = (_east - _west) * _cosMidLat;
    const latSpan = _north - _south;
    final scale = math.min(
      (size.width - padding * 2) / lonSpan,
      (size.height - padding * 2) / latSpan,
    );
    final width = lonSpan * scale;
    final height = latSpan * scale;
    return _Projection(
      scale,
      Offset((size.width - width) / 2, (size.height - height) / 2),
    );
  }

  Offset toScreen(double lat, double lon) => origin +
      Offset((lon - _west) * _cosMidLat * scale, (_north - lat) * scale);
}

class _NepalBasemapPainter extends CustomPainter {
  _NepalBasemapPainter({
    required this.provinces,
    required this.headquarters,
  });

  final List<List<List<Offset>>> provinces;
  final List<Map<String, dynamic>> headquarters;

  @override
  void paint(Canvas canvas, Size size) {
    final projection = _Projection.fit(size);
    canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF0D1216));

    final fill = Paint()
      ..color = const Color(0xFF16212A)
      ..style = PaintingStyle.fill;
    final border = Paint()
      ..color = const Color(0xFF2C3A43)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    for (final polygon in provinces) {
      final path = Path()..fillType = PathFillType.evenOdd;
      for (final ring in polygon) {
        if (ring.isEmpty) continue;
        final first = projection.toScreen(ring.first.dy, ring.first.dx);
        path.moveTo(first.dx, first.dy);
        for (final point in ring.skip(1)) {
          final screen = projection.toScreen(point.dy, point.dx);
          path.lineTo(screen.dx, screen.dy);
        }
        path.close();
      }
      canvas.drawPath(path, fill);
      canvas.drawPath(path, border);
    }

    // District headquarters: small dots, labels only for major cities.
    final hqPaint = Paint()..color = const Color(0xFF54646F);
    for (final hq in headquarters) {
      final geometry = hq['geometry'];
      if (geometry is! Map) continue;
      final coordinates = geometry['coordinates'];
      if (coordinates is! List || coordinates.length < 2) continue;
      final lon = _asDouble(coordinates[0]);
      final lat = _asDouble(coordinates[1]);
      if (lon == null || lat == null) continue;
      final screen = projection.toScreen(lat, lon);
      canvas.drawCircle(screen, 2, hqPaint);

      final properties = hq['properties'];
      final name = properties is Map ? properties['name'] : null;
      if (name is String && _majorCities.contains(name)) {
        _drawLabel(canvas, screen + const Offset(6, -12), name,
            const Color(0xFF8FA3B0), 10);
      }
    }
  }

  void _drawLabel(Canvas canvas, Offset at, String text, Color color, double fontSize) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: TextStyle(color: color, fontSize: fontSize)),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, at);
  }

  @override
  bool shouldRepaint(covariant _NepalBasemapPainter oldDelegate) =>
      oldDelegate.provinces != provinces || oldDelegate.headquarters != headquarters;
}

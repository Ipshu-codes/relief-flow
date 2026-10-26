import 'dart:convert';
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show FlutterError;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:rahat_mobile/module_api.dart';

/// Browser-native offline map for the command station. SVG is drawn by the
/// browser inside an iframe, independently from Flutter's canvas renderer.
class StationMapView extends StatefulWidget {
  const StationMapView({
    super.key,
    required this.api,
    required this.incidentId,
    required this.incidentIds,
  });

  final ModuleApi api;
  final int? incidentId;
  final Set<int>? incidentIds;

  @override
  State<StationMapView> createState() => _StationMapViewState();
}

class _StationMapViewState extends State<StationMapView> {
  static int _nextViewId = 0;

  late final String _viewType;
  html.IFrameElement? _frame;
  String _document = _loadingDocument;
  bool _loading = true;
  String? _error;

  static const String _loadingDocument = '''
    <!doctype html><html><body style="margin:0;background:#101820;color:#aeb9bf;
    display:grid;place-items:center;height:100vh;font:14px Arial,sans-serif">
    Loading Nepal map…</body></html>
  ''';

  @override
  void initState() {
    super.initState();
    _viewType = 'rahat-station-nepal-map-${_nextViewId++}';
    ui.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
      final frame = html.IFrameElement()
        ..style.border = '0'
        ..style.width = '100%'
        ..style.height = '100%'
        ..setAttribute('title', 'Interactive Nepal emergency map')
        ..srcdoc = _document;
      _frame = frame;
      return frame;
    });
    _load();
  }

  @override
  void didUpdateWidget(covariant StationMapView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.incidentId != widget.incidentId ||
        !_sameIds(oldWidget.incidentIds, widget.incidentIds)) {
      _load();
    }
  }

  bool _sameIds(Set<int>? a, Set<int>? b) => a == null
      ? b == null
      : b != null && a.length == b.length && a.containsAll(b);

  Future<String> _loadAsset(String path) async {
    try {
      return await rootBundle.loadString(path);
    } on FlutterError {
      return rootBundle.loadString('packages/rahat_mobile/$path');
    }
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      // Read the station's local copy first, with the shared package asset as
      // a fallback for builds that don't include a station-local copy.
      final states = await _loadAsset('assets/nepal_states.geojson');
      final geoJson = json.decode(states);
      if (geoJson is! Map || geoJson['features'] is! List) {
        throw const FormatException('Nepal boundary data is invalid.');
      }

      List<Map<String, dynamic>> requests = [];
      try {
        final result = await widget.api
            .request('/sos')
            .timeout(const Duration(seconds: 8));
        requests = (result as List? ?? [])
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .where((item) {
              final id = item['incident_id'];
              return (widget.incidentId == null || id == widget.incidentId) &&
                  (widget.incidentIds == null ||
                      widget.incidentIds!.contains(id));
            })
            .toList();
      } catch (_) {
        // Keep the boundary map available even when the API is offline.
      }

      final document = _mapDocument(
        base64Encode(utf8.encode(states)),
        base64Encode(utf8.encode(json.encode(requests))),
      );
      if (!mounted) return;
      setState(() {
        _document = document;
        _loading = false;
      });
      _frame?.srcdoc = document;
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'Map data could not be loaded: $error';
        _loading = false;
      });
    }
  }

  String _mapDocument(String statesBase64, String requestsBase64) =>
      '''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * { box-sizing: border-box; }
  html, body { width:100%; height:100%; margin:0; overflow:hidden; }
  body { background:#101820; color:#d9e1e5; font:13px Arial,sans-serif; }
  #map { position:relative; width:100%; height:100%; }
  svg { display:block; width:100%; height:100%; }
  .land { fill:#263b48; stroke:#7893a0; stroke-width:.012; stroke-linejoin:round; }
  .land:hover { fill:#31566a; }
  .marker { stroke:#fff; stroke-width:.018; cursor:pointer; }
  .marker.urgent { fill:#ee4148; }
  .marker.normal { fill:#ffbd28; }
  .marker:hover { stroke-width:.04; }
  #legend { position:absolute; left:14px; bottom:14px; display:flex; gap:14px;
    padding:9px 12px; border:1px solid #33444d; border-radius:8px;
    background:#111a20eF; box-shadow:0 3px 12px #0006; }
  .key { display:flex; align-items:center; gap:7px; white-space:nowrap; }
  .dot { width:10px; height:10px; border-radius:50%; background:#ee4148; }
  .dot.normal { background:#ffbd28; }
  .hint { position:absolute; top:12px; right:14px; color:#9eb0b9;
    background:#111a20dd; padding:7px 10px; border-radius:6px; }
  #tip { position:absolute; display:none; z-index:2; max-width:260px;
    padding:8px 10px; border:1px solid #3a4a53; border-radius:7px;
    background:#0d1419; box-shadow:0 4px 16px #0008; pointer-events:none; }
</style>
</head>
<body><main id="map">
<svg id="nepal" viewBox="0 0 7.3 4.32" role="img" aria-label="Map of Nepal">
  <g id="provinces" fill-rule="evenodd"></g>
  <g id="requests"></g>
</svg>
<div class="hint">Nepal · emergency locations</div>
<div id="legend"><span class="key"><i class="dot"></i>Urgent request</span>
  <span class="key"><i class="dot normal"></i>Other request</span></div>
<div id="tip"></div>
</main>
<script>
const states = JSON.parse(decodeURIComponent(escape(atob('$statesBase64'))));
const requests = JSON.parse(decodeURIComponent(escape(atob('$requestsBase64'))));
const ns = 'http://www.w3.org/2000/svg';
const west = 80, east = 88.3, north = 30.6, south = 26.28;
const cosine = Math.cos(28.44 * Math.PI / 180);
const x = lon => (lon - west) * cosine;
const y = lat => (north - lat);
const provinceLayer = document.getElementById('provinces');
const markerLayer = document.getElementById('requests');
for (const feature of (states.features || [])) {
  const geometry = feature.geometry || {};
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] :
    geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  for (const polygon of polygons) {
    let d = '';
    for (const ring of polygon || []) {
      if (!ring.length) continue;
      d += 'M' + x(ring[0][0]) + ' ' + y(ring[0][1]);
      for (const point of ring.slice(1)) d += 'L' + x(point[0]) + ' ' + y(point[1]);
      d += 'Z';
    }
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', d);
    path.setAttribute('class', 'land');
    const title = document.createElementNS(ns, 'title');
    title.textContent = 'Province ' + ((feature.properties || {}).name || '');
    path.appendChild(title);
    provinceLayer.appendChild(path);
  }
}
const tip = document.getElementById('tip');
for (const request of requests) {
  const lat = Number(request.latitude), lon = Number(request.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < south || lat > north || lon < west || lon > east) continue;
  const marker = document.createElementNS(ns, 'circle');
  marker.setAttribute('cx', x(lon)); marker.setAttribute('cy', y(lat));
  marker.setAttribute('r', '.075');
  marker.setAttribute('class', 'marker ' + (Number(request.urgency) >= 4 ? 'urgent' : 'normal'));
  marker.addEventListener('mouseenter', event => {
    const address = request.address || {};
    const place = ['district','city','ward','landmark'].map(k => address[k]).filter(Boolean).join(' · ');
    tip.textContent = (request.category || 'SOS') + ' · ' + (request.message || 'Emergency request') + (place ? ' · ' + place : '');
    tip.style.display = 'block'; tip.style.left = Math.min(event.offsetX + 14, innerWidth - 280) + 'px';
    tip.style.top = Math.max(8, event.offsetY - 12) + 'px';
  });
  marker.addEventListener('mouseleave', () => tip.style.display = 'none');
  markerLayer.appendChild(marker);
}
</script>
</body></html>
''';

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Material(
        color: const Color(0xFF151B1F),
        child: SizedBox(
          height: kToolbarHeight,
          child: Row(
            children: [
              const SizedBox(width: 16),
              const Expanded(
                child: Text(
                  'Nepal map',
                  style: TextStyle(fontSize: 20, color: Colors.white),
                ),
              ),
              if (_loading)
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              IconButton(
                tooltip: 'Refresh map',
                onPressed: _load,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
        ),
      ),
      Expanded(
        child: Stack(
          fit: StackFit.expand,
          children: [
            HtmlElementView(viewType: _viewType),
            if (_error != null)
              Align(
                alignment: Alignment.topCenter,
                child: Container(
                  margin: const EdgeInsets.all(12),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFF7F1D1D),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(_error!),
                ),
              ),
          ],
        ),
      ),
    ],
  );
}

import 'package:flutter/material.dart';
import 'package:rahat_mobile/module_api.dart';
import 'package:rahat_mobile/screens/map.dart';

/// Non-web fallback; the command station itself is intended to run in a
/// browser, where [StationMapView] uses the browser's native SVG renderer.
class StationMapView extends StatelessWidget {
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
  Widget build(BuildContext context) => MapScreen(
    api: api,
    incidentId: incidentId,
    incidentIds: incidentIds,
    embedded: true,
  );
}

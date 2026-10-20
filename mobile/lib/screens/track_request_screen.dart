
import 'package:flutter/material.dart';

import '../models/relief_request.dart';
import '../services/request_storage.dart';

class TrackRequestScreen extends StatefulWidget {
  const TrackRequestScreen({super.key});

  @override
  State<TrackRequestScreen> createState() =>
      _TrackRequestScreenState();
}

class _TrackRequestScreenState extends State<TrackRequestScreen> {
  late Future<List<ReliefRequest>> _requestsFuture;

  @override
  void initState() {
    super.initState();
    _loadRequests();
  }

  void _loadRequests() {
    _requestsFuture = RequestStorage.getRequests();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Requests'),
        actions: [
          IconButton(
            onPressed: () {
              setState(_loadRequests);
            },
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh requests',
          ),
        ],
      ),
      body: FutureBuilder<List<ReliefRequest>>(
        future: _requestsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(
              child: CircularProgressIndicator(),
            );
          }

          if (snapshot.hasError) {
            return const Center(
              child: Text('Could not load saved requests.'),
            );
          }

          final requests = snapshot.data ?? [];

          if (requests.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.assignment_outlined,
                      size: 64,
                      color: Colors.blueGrey.shade300,
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'No requests yet',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Your saved relief requests will appear here.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            );
          }

          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: requests.length,
            itemBuilder: (context, index) {
              final request = requests[index];

              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(
                            Icons.assignment_outlined,
                            color: Color(0xFF153E75),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              request.needType,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          Chip(
                            label: Text(request.status),
                            visualDensity: VisualDensity.compact,
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      _infoRow('Request ID', request.id),
                      _infoRow('Urgency', request.urgency),
                      _infoRow('Location', request.location),
                      if (request.description.isNotEmpty)
                        _infoRow(
                          'Description',
                          request.description,
                        ),
                      const SizedBox(height: 8),
                      Text(
                        'Saved: ${_formatDate(request.createdAt)}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.blueGrey,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        '$label: $value',
        style: const TextStyle(height: 1.4),
      ),
    );
  }

  String _formatDate(String value) {
    final date = DateTime.tryParse(value);

    if (date == null) return value;

    final localDate = date.toLocal();

    return '${localDate.day.toString().padLeft(2, '0')}/'
        '${localDate.month.toString().padLeft(2, '0')}/'
        '${localDate.year} '
        '${localDate.hour.toString().padLeft(2, '0')}:'
        '${localDate.minute.toString().padLeft(2, '0')}';
  }
}

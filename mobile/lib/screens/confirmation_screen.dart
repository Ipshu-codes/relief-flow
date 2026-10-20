import 'package:flutter/material.dart';

const Color confirmationNavy = Color(0xFF153E75);
const Color confirmationTeal = Color(0xFF168C83);
const Color confirmationText = Color(0xFF172B4D);

class ConfirmationScreen extends StatelessWidget {
  final String needType;
  final String urgency;
  final String location;
  final String description;

  const ConfirmationScreen({
    super.key,
    required this.needType,
    required this.urgency,
    required this.location,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Review Request'),
        foregroundColor: confirmationNavy,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: confirmationTeal.withValues(alpha: 0.12),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.fact_check_outlined,
                    size: 42,
                    color: confirmationTeal,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              const Center(
                child: Text(
                  'Review your request',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: confirmationNavy,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Check these details before connecting the app to '
                'the relief coordination backend.',
                textAlign: TextAlign.center,
                style: TextStyle(color: confirmationText, height: 1.5),
              ),
              const SizedBox(height: 28),
              _DetailCard(label: 'Assistance needed', value: needType),
              _DetailCard(label: 'Urgency', value: urgency),
              _DetailCard(label: 'Location', value: location),
              _DetailCard(label: 'Description', value: description),
              const SizedBox(height: 20),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF3E0),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE6A23C)),
                ),
                child: const Text(
                  'Not submitted yet. No relief team has been notified. '
                  'This is a local preview until backend submission '
                  'is implemented.',
                  style: TextStyle(
                    color: confirmationText,
                    height: 1.5,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Edit Details'),
                ),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () => Navigator.pop(context),
                  style: FilledButton.styleFrom(
                    backgroundColor: confirmationNavy,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15),
                  ),
                  child: const Text('Back to Form'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DetailCard extends StatelessWidget {
  final String label;
  final String value;

  const _DetailCard({
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.white,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: Color(0xFFE2E8F0)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(
                color: confirmationTeal,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              value,
              style: const TextStyle(
                color: confirmationText,
                fontSize: 15,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
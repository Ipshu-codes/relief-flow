import 'package:flutter/material.dart';
import 'confirmation_screen.dart';

const Color rahatNavy = Color(0xFF153E75);
const Color rahatTeal = Color(0xFF168C83);
const Color rahatText = Color(0xFF172B4D);

class ReportNeedScreen extends StatefulWidget {
  const ReportNeedScreen({super.key});

  @override
  State<ReportNeedScreen> createState() => _ReportNeedScreenState();
}

class _ReportNeedScreenState extends State<ReportNeedScreen> {
  final _formKey = GlobalKey<FormState>();
  final _locationController = TextEditingController();
  final _descriptionController = TextEditingController();

  String _needType = 'Food';
  String _urgency = 'Urgent';

  @override
  void dispose() {
    _locationController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

void _submitRequest() {
  if (!_formKey.currentState!.validate()) return;

  Navigator.push(
    context,
    MaterialPageRoute(
      builder: (context) => ConfirmationScreen(
        needType: _needType,
        urgency: _urgency,
        location: _locationController.text.trim(),
        description: _descriptionController.text.trim(),
      ),
    ),
  );
}

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Report a Need'),
        foregroundColor: rahatNavy,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Request assistance',
                  style: TextStyle(
                    fontSize: 25,
                    fontWeight: FontWeight.bold,
                    color: rahatNavy,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Tell us what you need so relief teams can '
                  'coordinate assistance.',
                  style: TextStyle(color: rahatText, height: 1.5),
                ),
                const SizedBox(height: 24),

                const Text(
                  'Type of assistance',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _needType,
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    'Food',
                    'Drinking water',
                    'Medical aid',
                    'Rescue',
                    'Shelter',
                    'Clothing',
                    'Other',
                  ].map((type) {
                    return DropdownMenuItem(
                      value: type,
                      child: Text(type),
                    );
                  }).toList(),
                  onChanged: (value) {
                    if (value != null) {
                      setState(() => _needType = value);
                    }
                  },
                ),
                const SizedBox(height: 20),

                const Text(
                  'Urgency level',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _urgency,
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    'Critical',
                    'Urgent',
                    'Normal',
                  ].map((level) {
                    return DropdownMenuItem(
                      value: level,
                      child: Text(level),
                    );
                  }).toList(),
                  onChanged: (value) {
                    if (value != null) {
                      setState(() => _urgency = value);
                    }
                  },
                ),
                const SizedBox(height: 20),

                const Text(
                  'Location or nearby landmark',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _locationController,
                  decoration: const InputDecoration(
                    hintText: 'e.g. Thapathali, Kathmandu',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.location_on_outlined),
                  ),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return 'Please enter your location';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 20),

                const Text(
                  'Describe the situation',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _descriptionController,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText: 'What assistance is needed, and for how many people?',
                    border: OutlineInputBorder(),
                    alignLabelWithHint: true,
                  ),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return 'Please describe the assistance needed';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 28),

                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _submitRequest,
                    icon: const Icon(Icons.send_outlined),
                    label: const Text('Submit Request'),
                    style: FilledButton.styleFrom(
                      backgroundColor: rahatNavy,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'This form does not contact emergency services. '
                  'If you are in immediate danger, contact local '
                  'emergency responders.',
                  style: TextStyle(fontSize: 12, color: Colors.black54),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

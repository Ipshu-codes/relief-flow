import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';

class VolunteerScreen extends StatefulWidget {
  const VolunteerScreen({super.key});

  @override
  State<VolunteerScreen> createState() => _VolunteerScreenState();
}

class _VolunteerScreenState extends State<VolunteerScreen> {
  final _nameCtrl = TextEditingController(text: 'Ram Shrestha');
  final String _skills = 'First aid, Boat';
  bool _available = true;

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
          title: Text(
              appState.t(context, 'Volunteer profile', 'स्वयंसेवक प्रोफाइल'))),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const CircleAvatar(
              radius: 40,
              backgroundColor: Color(0xFF4CAF7D),
              child: Icon(Icons.person, size: 40, color: Colors.white)),
          const SizedBox(height: 16),
          Center(
              child: Text(_nameCtrl.text,
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.bold))),
          const SizedBox(height: 8),
          Text('${appState.t(context, 'Skills', 'कुशलता')}: $_skills',
              style: const TextStyle(color: Colors.grey)),
          const SizedBox(height: 20),
          SwitchListTile(
            title: Text(appState.t(
                context, 'Available for dispatch', 'प्रेषणको लागि उपलब्ध')),
            subtitle: Text(appState.t(
                context,
                'Receive nearby assignments offline',
                'नजिकैका असाइनमेन्टहरू प्राप्त गर्नुहोस्')),
            value: _available,
            onChanged: (v) => setState(() => _available = v),
          ),
          const SizedBox(height: 20),
          const Text('Recent assignments',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          Card(
            color: const Color(0xFF151B1F),
            child: ListTile(
              leading: const Icon(Icons.emergency, color: Color(0xFFF57C00)),
              title: const Text('Rescue — Boudha'),
              subtitle: const Text('ETA 14 min · Resolve'),
              trailing:
                  TextButton(onPressed: () {}, child: const Text('Accept')),
            ),
          ),
        ],
      ),
    );
  }
}


import 'package:flutter/material.dart';
import 'screens/report_need_screen.dart';
import 'screens/track_request_screen.dart';

void main() {
  runApp(const RahatApp());
}

const Color navy = Color(0xFF153E75);
const Color teal = Color(0xFF168C83);
const Color background = Color(0xFFF8FAFC);
const Color darkText = Color(0xFF172B4D);

class RahatApp extends StatelessWidget {
  const RahatApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'RAHAT',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: background,
        colorScheme: ColorScheme.fromSeed(
          seedColor: navy,
          primary: navy,
          secondary: teal,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: background,
          foregroundColor: navy,
          elevation: 0,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int selectedIndex = 0;

  void showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  void openRequests() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const TrackRequestScreen(),
      ),
    );
  }

  void openReportForm() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const ReportNeedScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.health_and_safety, color: teal, size: 30),
            SizedBox(width: 8),
            Text(
              'RAHAT',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                letterSpacing: 1.5,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            onPressed: () =>
                showMessage('Notifications coming soon.'),
            icon: const Icon(Icons.notifications_none),
            tooltip: 'Notifications',
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Prepared communities.',
                style: TextStyle(
                  fontSize: 27,
                  fontWeight: FontWeight.bold,
                  color: navy,
                ),
              ),
              const Text(
                'Coordinated relief.',
                style: TextStyle(
                  fontSize: 23,
                  color: teal,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Report needs, find relief resources, and stay informed.',
                style: TextStyle(fontSize: 15, color: darkText),
              ),
              const SizedBox(height: 24),

              // Emergency information banner
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF3E0),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: const Color(0xFFE6A23C),
                  ),
                ),
                child: const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.warning_amber_rounded,
                      color: Color(0xFF9A6700),
                      size: 28,
                    ),
                    SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Emergency Notice',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: darkText,
                            ),
                          ),
                          SizedBox(height: 4),
                          Text(
                            'RAHAT coordinates relief. It is not an '
                            'emergency rescue service. For immediate '
                            'danger, contact local emergency services.',
                            style: TextStyle(
                              fontSize: 13,
                              color: darkText,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              const Text(
                'How can we help?',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: darkText,
                ),
              ),
              const SizedBox(height: 14),

              // Request Help
              ActionCard(
                icon: Icons.volunteer_activism,
                title: 'Request Help',
                subtitle:
                    'Report food, water, medicine, or other needs',
                color: navy,
                onTap: openReportForm,
              ),
              const SizedBox(height: 12),

              // Track Request
              ActionCard(
                icon: Icons.track_changes,
                title: 'Track Request',
                subtitle:
                    'Check the status of an existing request',
                color: teal,
                onTap: openRequests,
              ),
              const SizedBox(height: 12),

              // Relief Map
              ActionCard(
                icon: Icons.map_outlined,
                title: 'Relief Map',
                subtitle:
                    'Explore relief centers and reported roadblocks',
                color: const Color(0xFF52677F),
                onTap: () {
                  showMessage('The relief map is coming next.');
                },
              ),
              const SizedBox(height: 24),

              // Public-safe summary
              const Text(
                'Relief Overview',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: darkText,
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: const Color(0xFFE2E8F0),
                  ),
                ),
                child: const Row(
                  children: [
                    Icon(
                      Icons.inventory_2_outlined,
                      size: 34,
                      color: teal,
                    ),
                    SizedBox(width: 14),
                    Expanded(
                      child: Text(
                        'Relief information will appear here when '
                        'verified data is available.',
                        style: TextStyle(
                          color: darkText,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
            ],
          ),
        ),
      ),

      // Bottom navigation
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) {
          setState(() {
            selectedIndex = index;
          });

          if (index == 1) {
            openRequests();
          } else if (index == 2) {
            showMessage('The relief map is coming next.');
          }
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: 'Requests',
          ),
          NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map),
            label: 'Map',
          ),
        ],
      ),
    );
  }
}

// Reusable action card
class ActionCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  const ActionCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.white,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(
          color: Color(0xFFE2E8F0),
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  icon,
                  color: color,
                  size: 28,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: darkText,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF64748B),
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.chevron_right,
                color: Color(0xFF94A3B8),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'screens/contracts_sign_screen.dart';
import 'screens/documents_screen.dart';
import 'screens/home_screen.dart';
import 'screens/projects_screen.dart';
import 'screens/verify_screen.dart';
import 'services/trustseal_api.dart';
import 'theme/trustseal_theme.dart';

class TrustSealAppShell extends StatefulWidget {
  final TrustSealApiClient api;
  final VoidCallback onSignedOut;

  const TrustSealAppShell({
    super.key,
    required this.api,
    required this.onSignedOut,
  });

  @override
  State<TrustSealAppShell> createState() => _TrustSealAppShellState();
}

class _TrustSealAppShellState extends State<TrustSealAppShell> {
  int _index = 0;

  static const _titles = [
    'TRUSTSEAL',
    'Projects & Time',
    'Contracts & Sign',
    'Documents & Stamps',
    'Verify Evidence',
  ];

  void _setTab(int i) => setState(() => _index = i);

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(api: widget.api, onNavigateTab: _setTab),
      ProjectsScreen(api: widget.api),
      ContractsSignScreen(api: widget.api),
      DocumentsScreen(api: widget.api),
      VerifyScreen(api: widget.api),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout_outlined, size: 20),
            onPressed: () async {
              await widget.api.logout();
              widget.onSignedOut();
            },
          ),
        ],
      ),
      body: screens[_index],
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: TrustSealTheme.border)),
        ),
        child: BottomNavigationBar(
          currentIndex: _index,
          onTap: _setTab,
          type: BottomNavigationBarType.fixed,
          backgroundColor: Colors.white,
          selectedItemColor: TrustSealTheme.navy,
          unselectedItemColor: TrustSealTheme.subtle,
          selectedFontSize: 12,
          unselectedFontSize: 12,
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.dashboard_outlined), label: 'Home'),
            BottomNavigationBarItem(icon: Icon(Icons.work_outline), label: 'Projects'),
            BottomNavigationBarItem(icon: Icon(Icons.draw_outlined), label: 'Sign'),
            BottomNavigationBarItem(icon: Icon(Icons.folder_outlined), label: 'Docs'),
            BottomNavigationBarItem(icon: Icon(Icons.verified_user_outlined), label: 'Verify'),
          ],
        ),
      ),
    );
  }
}

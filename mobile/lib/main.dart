import 'package:flutter/material.dart';
import 'app_shell.dart';
import 'screens/login_screen.dart';
import 'services/trustseal_api.dart';
import 'theme/trustseal_theme.dart';

void main() {
  runApp(TrustSealMobileApp(api: TrustSealApiClient()));
}

class TrustSealMobileApp extends StatefulWidget {
  final TrustSealApiClient api;

  const TrustSealMobileApp({super.key, required this.api});

  @override
  State<TrustSealMobileApp> createState() => _TrustSealMobileAppState();
}

class _TrustSealMobileAppState extends State<TrustSealMobileApp> {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TRUSTSEAL Mobile',
      debugShowCheckedModeBanner: false,
      theme: TrustSealTheme.build(),
      home: widget.api.isAuthenticated
          ? TrustSealAppShell(
              api: widget.api,
              onSignedOut: () => setState(() {}),
            )
          : LoginScreen(
              api: widget.api,
              onAuthenticated: () => setState(() {}),
            ),
    );
  }
}

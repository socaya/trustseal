import 'package:flutter/material.dart';
import '../services/trustseal_api.dart';
import '../theme/trustseal_theme.dart';

class LoginScreen extends StatefulWidget {
  final TrustSealApiClient api;
  final VoidCallback onAuthenticated;

  const LoginScreen({
    super.key,
    required this.api,
    required this.onAuthenticated,
  });

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late final TextEditingController _serverCtrl;
  final _emailCtrl = TextEditingController(text: 'admin@trustseal.local');
  final _passwordCtrl = TextEditingController(text: 'trustseal-demo-password-2026');
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _serverCtrl = TextEditingController(text: widget.api.baseUrl);
  }

  @override
  void dispose() {
    _serverCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    widget.api.baseUrl = _serverCtrl.text.trim();
    try {
      final res = await widget.api.login(_emailCtrl.text.trim(), _passwordCtrl.text);
      if (res.isOk) {
        widget.onAuthenticated();
      } else {
        setState(() {
          _error = (res.body['error'] ?? 'Invalid credentials (${res.statusCode})').toString();
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Cannot reach ${widget.api.baseUrl}: $e';
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(24, 60, 24, 28),
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [TrustSealTheme.navyDark, TrustSealTheme.navy, TrustSealTheme.navyAccent],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              border: Border(bottom: BorderSide(color: TrustSealTheme.emerald, width: 3)),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'TRUSTSEAL MOBILE',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.4,
                    color: Color(0xFF7EE29A),
                  ),
                ),
                SizedBox(height: 6),
                Text(
                  'Verified Integrity on Mobile',
                  style: TextStyle(fontSize: 25, fontWeight: FontWeight.w700, color: Colors.white),
                ),
                SizedBox(height: 6),
                Text(
                  'eIDAS 2.0 SES/AES/QES · Projects & Time · Contracts · Documents · Verify',
                  style: TextStyle(fontSize: 13.5, color: Color(0xFFD8E4F8)),
                ),
              ],
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_error != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: const BoxDecoration(
                        color: Color(0xFFFEF2F2),
                        border: Border(left: BorderSide(color: TrustSealTheme.danger, width: 3)),
                      ),
                      child: Text(_error!, style: const TextStyle(color: Color(0xFF991B1B), fontSize: 13.5)),
                    ),
                  const Text('Server URL', style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    key: const Key('login-server-field'),
                    controller: _serverCtrl,
                    decoration: const InputDecoration(hintText: 'http://127.0.0.1:5017'),
                  ),
                  const SizedBox(height: 16),
                  const Text('Work Email or Username', style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    key: const Key('login-email-field'),
                    controller: _emailCtrl,
                    keyboardType: TextInputType.emailAddress,
                  ),
                  const SizedBox(height: 16),
                  const Text('Password', style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    key: const Key('login-password-field'),
                    controller: _passwordCtrl,
                    obscureText: true,
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    key: const Key('login-submit-btn'),
                    onPressed: _loading ? null : _submit,
                    child: _loading
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('Sign in to TRUSTSEAL'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

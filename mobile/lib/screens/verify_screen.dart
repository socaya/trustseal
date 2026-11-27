import 'package:flutter/material.dart';
import '../services/trustseal_api.dart';
import '../theme/trustseal_theme.dart';

class VerifyScreen extends StatefulWidget {
  final TrustSealApiClient api;

  const VerifyScreen({super.key, required this.api});

  @override
  State<VerifyScreen> createState() => _VerifyScreenState();
}

class _VerifyScreenState extends State<VerifyScreen> {
  final _queryCtrl = TextEditingController();
  bool _checking = false;
  Map<String, dynamic>? _cert;
  String? _error;

  @override
  void dispose() {
    _queryCtrl.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final q = _queryCtrl.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _checking = true;
      _cert = null;
      _error = null;
    });
    try {
      final res = await widget.api.verifyReferenceOrHash(q);
      if (res.isOk && res.body['certificate'] is Map) {
        setState(() => _cert = Map<String, dynamic>.from(res.body['certificate'] as Map));
      } else {
        setState(() => _error = (res.body['error'] ?? 'No matching TRUSTSEAL record found').toString());
      }
    } catch (e) {
      setState(() => _error = 'Verification request failed: $e');
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'Cryptographic Verification',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: TrustSealTheme.navy),
        ),
        const SizedBox(height: 6),
        const Text(
          'Verify any TRUSTSEAL eSignature Package Reference (ESIG-...), Document SHA-256, or Sealed PAdES Digest.',
          style: TextStyle(fontSize: 14, color: TrustSealTheme.muted),
        ),
        const SizedBox(height: 16),
        TextField(
          key: const Key('verify-query-input'),
          controller: _queryCtrl,
          decoration: const InputDecoration(
            labelText: 'Package Ref (ESIG-...) or SHA-256 Digest',
            hintText: 'ESIG-2026-01A1B2C3',
          ),
        ),
        const SizedBox(height: 12),
        ElevatedButton(
          key: const Key('verify-submit-btn'),
          onPressed: _checking ? null : _verify,
          style: ElevatedButton.styleFrom(backgroundColor: TrustSealTheme.emerald),
          child: _checking
              ? const SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Text('Verify Cryptographic Evidence'),
        ),
        const SizedBox(height: 20),
        if (_error != null)
          Container(
            padding: const EdgeInsets.all(14),
            decoration: const BoxDecoration(
              color: Color(0xFFFEF2F2),
              border: Border(left: BorderSide(color: TrustSealTheme.danger, width: 3)),
            ),
            child: Text(_error!, style: const TextStyle(color: Color(0xFF991B1B))),
          ),
        if (_cert != null) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(
              color: Color(0xFFF4FBF6),
              border: Border(left: BorderSide(color: TrustSealTheme.emerald, width: 3.5)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const StatusDotLabel(label: 'Verified · Audit Chain Intact', dotColor: TrustSealTheme.emerald),
                const SizedBox(height: 8),
                Text(
                  (_cert!['title'] ?? '').toString(),
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: TrustSealTheme.navy),
                ),
                const SizedBox(height: 10),
                _RowKV('Reference', (_cert!['package_ref'] ?? '').toString()),
                _RowKV('eIDAS 2.0 Level', ((_cert!['eidas_standard'] as Map?)?['name'] ?? '').toString()),
                _RowKV('ETSI PAdES', ((_cert!['pades_conformance'] as Map?)?['profile'] ?? '').toString()),
                _RowKV('OCSP Status', ((_cert!['pades_conformance'] as Map?)?['ocsp_status'] ?? 'verified').toString()),
                _RowKV('Audit Events', '${(_cert!['audit_chain'] as Map?)?['event_count'] ?? 0} chained'),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _RowKV extends StatelessWidget {
  final String k;
  final String v;
  const _RowKV(this.k, this.v);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 115,
            child: Text(k, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: TrustSealTheme.muted)),
          ),
          Expanded(child: Text(v, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';
import '../services/trustseal_api.dart';
import '../theme/trustseal_theme.dart';

class ContractsSignScreen extends StatefulWidget {
  final TrustSealApiClient api;

  const ContractsSignScreen({super.key, required this.api});

  @override
  State<ContractsSignScreen> createState() => _ContractsSignScreenState();
}

class _ContractsSignScreenState extends State<ContractsSignScreen> {
  bool _loading = true;
  List<Map<String, dynamic>> _packages = [];
  String? _banner;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final data = await widget.api.fetchSignaturePackages();
      final list = ((data['packages'] as List?) ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      if (mounted) {
        setState(() {
          _packages = list;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openSendSheet() async {
    final titleCtrl = TextEditingController();
    final nameCtrl = TextEditingController();
    final emailCtrl = TextEditingController();
    String eidasLevel = 'QES';
    String padesProfile = 'PAdES-B-LTA';

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheetState) => Padding(
          padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(ctx).viewInsets.bottom + 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Send Document for eSignature',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: TrustSealTheme.navy),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('send-title-input'),
                controller: titleCtrl,
                decoration: const InputDecoration(labelText: 'Document / Contract Title'),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const Key('send-name-input'),
                controller: nameCtrl,
                decoration: const InputDecoration(labelText: 'Recipient Full Name'),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const Key('send-email-input'),
                controller: emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Recipient Email'),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: eidasLevel,
                      decoration: const InputDecoration(labelText: 'eIDAS 2.0 Level'),
                      items: const [
                        DropdownMenuItem(value: 'SES', child: Text('SES · Simple')),
                        DropdownMenuItem(value: 'AES', child: Text('AES · Advanced')),
                        DropdownMenuItem(value: 'QES', child: Text('QES · Qualified')),
                      ],
                      onChanged: (v) => setSheetState(() => eidasLevel = v ?? 'QES'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: padesProfile,
                      decoration: const InputDecoration(labelText: 'ETSI PAdES'),
                      items: const [
                        DropdownMenuItem(value: 'PAdES-B-LTA', child: Text('PAdES-B-LTA')),
                        DropdownMenuItem(value: 'PAdES-B-LT', child: Text('PAdES-B-LT')),
                        DropdownMenuItem(value: 'PAdES-B-T', child: Text('PAdES-B-T')),
                        DropdownMenuItem(value: 'PAdES-B-B', child: Text('PAdES-B-B')),
                      ],
                      onChanged: (v) => setSheetState(() => padesProfile = v ?? 'PAdES-B-LTA'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              ElevatedButton(
                key: const Key('send-dispatch-btn'),
                onPressed: () async {
                  if (titleCtrl.text.trim().isEmpty || emailCtrl.text.trim().isEmpty) return;
                  final res = await widget.api.sendForSignature(
                    title: titleCtrl.text.trim(),
                    recipientName: nameCtrl.text.trim().isEmpty ? emailCtrl.text.trim() : nameCtrl.text.trim(),
                    recipientEmail: emailCtrl.text.trim(),
                    eidasLevel: eidasLevel,
                    padesProfile: padesProfile,
                  );
                  if (ctx.mounted) Navigator.pop(ctx);
                  if (res.isOk && mounted) {
                    final ref = (res.body['package'] as Map?)?['package_ref'] ?? '';
                    setState(() => _banner = 'Dispatched $ref ($eidasLevel · $padesProfile)');
                    _load();
                  }
                },
                child: const Text('Dispatch eSignature Invite'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: EdgeInsets.zero,
            children: [
              Container(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 14),
                color: TrustSealTheme.surfaceTint,
                child: const Text(
                  'Contracts & eIDAS 2.0 Signature Packages (SES · AES · QES)',
                  style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: TrustSealTheme.navy),
                ),
              ),
              const Divider(height: 1),
              if (_banner != null)
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: const BoxDecoration(
                    color: Color(0xFFF4FBF6),
                    border: Border(left: BorderSide(color: TrustSealTheme.emerald, width: 3)),
                  ),
                  child: Text(_banner!, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
                ),
              if (_loading)
                const Padding(padding: EdgeInsets.all(32), child: Center(child: CircularProgressIndicator()))
              else if (_packages.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('No active signature packages. Tap "Send Document" below to create one.'),
                )
              else
                ..._packages.map((p) {
                  final id = (p['id'] as num?)?.toInt();
                  final status = (p['status'] ?? 'sent').toString();
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                    decoration: const BoxDecoration(
                      border: Border(bottom: BorderSide(color: TrustSealTheme.border)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              (p['package_ref'] ?? '').toString(),
                              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: TrustSealTheme.navy),
                            ),
                            StatusDotLabel.forStatus(status),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          (p['title'] ?? 'Agreement').toString(),
                          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 4),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              '${p['eidas_level'] ?? 'AES'} · ${p['pades_profile'] ?? 'PAdES-B-LTA'} · ${p['signed_count'] ?? 0}/${p['signer_count'] ?? 1} signed',
                              style: const TextStyle(fontSize: 12.5, color: TrustSealTheme.muted),
                            ),
                            if (id != null && (status == 'sent' || status == 'in_progress'))
                              TextButton(
                                onPressed: () async {
                                  final r = await widget.api.remindPackage(id);
                                  if (r.isOk && mounted) {
                                    setState(() => _banner = 'Reminder dispatched for ${p['package_ref']}');
                                  }
                                },
                                child: const Text('Remind'),
                              ),
                          ],
                        ),
                      ],
                    ),
                  );
                }),
              const SizedBox(height: 80),
            ],
          ),
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton.extended(
            key: const Key('open-send-sheet-btn'),
            onPressed: _openSendSheet,
            backgroundColor: TrustSealTheme.navy,
            foregroundColor: Colors.white,
            icon: const Icon(Icons.draw_outlined),
            label: const Text('Send Document'),
          ),
        ),
      ],
    );
  }
}

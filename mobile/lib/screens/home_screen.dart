import 'package:flutter/material.dart';
import '../services/trustseal_api.dart';
import '../theme/trustseal_theme.dart';

class HomeScreen extends StatefulWidget {
  final TrustSealApiClient api;
  final void Function(int tabIndex) onNavigateTab;

  const HomeScreen({
    super.key,
    required this.api,
    required this.onNavigateTab,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _loading = true;
  int _docCount = 0;
  int _projectCount = 0;
  int _awaitingCount = 0;
  int _qesCount = 0;
  List<Map<String, dynamic>> _recentPackages = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        widget.api.fetchDocuments(),
        widget.api.fetchProjects(),
        widget.api.fetchSignaturePackages(),
      ]);
      final docs = results[0] as List<Map<String, dynamic>>;
      final projects = results[1] as List<Map<String, dynamic>>;
      final sigData = results[2] as Map<String, dynamic>;
      final summary = (sigData['summary'] as Map?) ?? {};
      final pkgs = ((sigData['packages'] as List?) ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();

      if (mounted) {
        setState(() {
          _docCount = docs.length;
          _projectCount = projects.length;
          _awaitingCount = (summary['awaiting'] as num?)?.toInt() ?? 0;
          _qesCount = (summary['qes_count'] as num?)?.toInt() ?? 0;
          _recentPackages = pkgs.take(6).toList();
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final userName = (widget.api.currentUser?['first_name'] ??
            widget.api.currentUser?['username'] ??
            'Workspace')
        .toString();

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          // Deep TrustSeal Navy executive header band
          Container(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 22),
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [TrustSealTheme.navyDark, TrustSealTheme.navy, TrustSealTheme.navyAccent],
              ),
              border: Border(bottom: BorderSide(color: TrustSealTheme.emerald, width: 2.5)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'TRUSTSEAL WORKSPACE',
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    color: Color(0xFF7EE29A),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Welcome back, $userName',
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: Colors.white),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    ElevatedButton(
                      onPressed: () => widget.onNavigateTab(2),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: TrustSealTheme.navy,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                      ),
                      child: const Text('Send for Sign'),
                    ),
                    const SizedBox(width: 10),
                    ElevatedButton(
                      onPressed: () => widget.onNavigateTab(1),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: TrustSealTheme.emerald,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                      ),
                      child: const Text('Log Time'),
                    ),
                    const SizedBox(width: 10),
                    OutlinedButton(
                      onPressed: () => widget.onNavigateTab(4),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: const BorderSide(color: Color(0x66FFFFFF)),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                      ),
                      child: const Text('Verify'),
                    ),
                  ],
                ),
              ],
            ),
          ),

          // Unified single 4-metric KPI strip (zero floating cards)
          Container(
            color: TrustSealTheme.surfaceTint,
            child: Row(
              children: [
                _KpiCell(label: 'Documents', value: '$_docCount'),
                _KpiCell(label: 'Projects', value: '$_projectCount'),
                _KpiCell(label: 'Awaiting', value: '$_awaitingCount'),
                _KpiCell(label: 'QES', value: '$_qesCount', highlight: true, last: true),
              ],
            ),
          ),
          const Divider(height: 1),

          // Unified Recent Signature Workflows section
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Recent eSignature Activity',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: TrustSealTheme.navy),
                ),
                TextButton(
                  onPressed: () => widget.onNavigateTab(2),
                  child: const Text('View all →'),
                ),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20),
            child: Divider(height: 1, thickness: 1.5, color: TrustSealTheme.navy),
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(28),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_recentPackages.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No eSignature packages yet. Tap "Send for Sign" to dispatch an SES, AES, or QES workflow.',
                style: TextStyle(color: TrustSealTheme.muted),
              ),
            )
          else
            ..._recentPackages.map((pkg) {
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: TrustSealTheme.border)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            (pkg['title'] ?? 'Untitled Package').toString(),
                            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            '${pkg['package_ref'] ?? ''} · ${pkg['eidas_level'] ?? 'AES'} · ${pkg['pades_profile'] ?? 'PAdES-B-LTA'}',
                            style: const TextStyle(fontSize: 12.5, color: TrustSealTheme.muted),
                          ),
                        ],
                      ),
                    ),
                    StatusDotLabel.forStatus((pkg['status'] ?? 'sent').toString()),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

class _KpiCell extends StatelessWidget {
  final String label;
  final String value;
  final bool highlight;
  final bool last;

  const _KpiCell({
    required this.label,
    required this.value,
    this.highlight = false,
    this.last = false,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
        decoration: BoxDecoration(
          border: last ? null : const Border(right: BorderSide(color: TrustSealTheme.border)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: TrustSealTheme.muted)),
            const SizedBox(height: 4),
            Text(
              value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: highlight ? TrustSealTheme.emeraldDark : TrustSealTheme.navy,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

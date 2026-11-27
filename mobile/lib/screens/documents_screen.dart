import 'package:flutter/material.dart';
import '../services/trustseal_api.dart';
import '../theme/trustseal_theme.dart';

class DocumentsScreen extends StatefulWidget {
  final TrustSealApiClient api;

  const DocumentsScreen({super.key, required this.api});

  @override
  State<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends State<DocumentsScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  bool _loading = true;
  String _query = '';
  List<Map<String, dynamic>> _docs = [];
  List<Map<String, dynamic>> _stamps = [];

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _load();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        widget.api.fetchDocuments(),
        widget.api.fetchStamps(),
      ]);
      if (mounted) {
        setState(() {
          _docs = results[0];
          _stamps = results[1];
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final filteredDocs = _docs
        .where((d) => (d['title'] ?? '').toString().toLowerCase().contains(_query.toLowerCase()))
        .toList();

    return Column(
      children: [
        Container(
          color: TrustSealTheme.surfaceTint,
          child: TabBar(
            controller: _tabs,
            labelColor: TrustSealTheme.navy,
            unselectedLabelColor: TrustSealTheme.muted,
            indicatorColor: TrustSealTheme.navy,
            tabs: [
              Tab(text: 'Documents (${_docs.length})'),
              Tab(text: 'Official Stamps (${_stamps.length})'),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: TextField(
            onChanged: (v) => setState(() => _query = v),
            decoration: const InputDecoration(
              hintText: 'Search .tsd documents…',
              prefixIcon: Icon(Icons.search, size: 20),
            ),
          ),
        ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : TabBarView(
                  controller: _tabs,
                  children: [
                    RefreshIndicator(
                      onRefresh: _load,
                      child: filteredDocs.isEmpty
                          ? const Center(child: Text('No documents match your filter.'))
                          : ListView.separated(
                              itemCount: filteredDocs.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (_, i) {
                                final d = filteredDocs[i];
                                return ListTile(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
                                  title: Text(
                                    (d['title'] ?? 'Untitled .tsd').toString(),
                                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                                  ),
                                  subtitle: Text(
                                    'TSD-${(d['id'] ?? '').toString().padLeft(5, '0')} · v${d['version'] ?? 1}',
                                    style: const TextStyle(fontSize: 12.5, color: TrustSealTheme.muted),
                                  ),
                                  trailing: StatusDotLabel.forStatus((d['status'] ?? 'draft').toString()),
                                );
                              },
                            ),
                    ),
                    RefreshIndicator(
                      onRefresh: _load,
                      child: _stamps.isEmpty
                          ? const Center(child: Text('No corporate stamps registered.'))
                          : ListView.separated(
                              itemCount: _stamps.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (_, i) {
                                final s = _stamps[i];
                                return ListTile(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
                                  title: Text(
                                    (s['name'] ?? s['title'] ?? 'Corporate Stamp').toString(),
                                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5),
                                  ),
                                  subtitle: Text(
                                    (s['category'] ?? s['stamp_type'] ?? 'Official Seal').toString(),
                                    style: const TextStyle(fontSize: 12.5, color: TrustSealTheme.muted),
                                  ),
                                  trailing: StatusDotLabel.forStatus((s['status'] ?? 'active').toString()),
                                );
                              },
                            ),
                    ),
                  ],
                ),
        ),
      ],
    );
  }
}

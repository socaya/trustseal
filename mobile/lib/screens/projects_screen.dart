import 'package:flutter/material.dart';
import '../services/trustseal_api.dart';
import '../theme/trustseal_theme.dart';

class ProjectsScreen extends StatefulWidget {
  final TrustSealApiClient api;

  const ProjectsScreen({super.key, required this.api});

  @override
  State<ProjectsScreen> createState() => _ProjectsScreenState();
}

class _ProjectsScreenState extends State<ProjectsScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  bool _loading = true;
  List<Map<String, dynamic>> _projects = [];
  List<Map<String, dynamic>> _timesheets = [];

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
        widget.api.fetchProjects(),
        widget.api.fetchTimesheets(),
      ]);
      if (mounted) {
        setState(() {
          _projects = results[0];
          _timesheets = results[1];
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openLogTimeSheet() async {
    final hoursCtrl = TextEditingController(text: '2.0');
    final descCtrl = TextEditingController();
    int selectedProjectId = _projects.isNotEmpty ? ((_projects.first['id'] as num?)?.toInt() ?? 1) : 1;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(ctx).viewInsets.bottom + 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Log Timesheet Entry', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: TrustSealTheme.navy)),
            const SizedBox(height: 14),
            TextField(
              controller: hoursCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Hours Worked'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: descCtrl,
              decoration: const InputDecoration(labelText: 'Work Description'),
            ),
            const SizedBox(height: 18),
            ElevatedButton(
              onPressed: () async {
                final today = DateTime.now().toIso8601String().substring(0, 10);
                await widget.api.logTimesheet(
                  projectId: selectedProjectId,
                  hours: double.tryParse(hoursCtrl.text) ?? 1.0,
                  workDate: today,
                  description: descCtrl.text.trim().isEmpty ? 'Field work logged via TRUSTSEAL Mobile' : descCtrl.text.trim(),
                );
                if (ctx.mounted) Navigator.pop(ctx);
                _load();
              },
              child: const Text('Submit Timesheet'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          color: TrustSealTheme.surfaceTint,
          child: TabBar(
            controller: _tabs,
            labelColor: TrustSealTheme.navy,
            unselectedLabelColor: TrustSealTheme.muted,
            indicatorColor: TrustSealTheme.navy,
            tabs: const [
              Tab(text: 'Projects'),
              Tab(text: 'My Timesheets'),
            ],
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
                      child: _projects.isEmpty
                          ? const Center(child: Text('No active projects found.'))
                          : ListView.separated(
                              itemCount: _projects.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (_, i) {
                                final p = _projects[i];
                                final pct = ((p['progress_pct'] ?? p['progress'] ?? 0) as num).toDouble().clamp(0, 100);
                                return Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            (p['code'] ?? 'PRJ-${p['id'] ?? ''}').toString(),
                                            style: const TextStyle(
                                              fontSize: 12.5,
                                              fontWeight: FontWeight.w700,
                                              color: TrustSealTheme.navy,
                                            ),
                                          ),
                                          StatusDotLabel.forStatus((p['status'] ?? 'active').toString()),
                                        ],
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        (p['name'] ?? p['title'] ?? 'Project').toString(),
                                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                                      ),
                                      const SizedBox(height: 8),
                                      LinearProgressIndicator(
                                        value: pct / 100.0,
                                        minHeight: 5,
                                        backgroundColor: const Color(0xFFE2E8F0),
                                        valueColor: const AlwaysStoppedAnimation(TrustSealTheme.emerald),
                                      ),
                                    ],
                                  ),
                                );
                              },
                            ),
                    ),
                    Stack(
                      children: [
                        _timesheets.isEmpty
                            ? const Center(child: Text('No timesheet entries logged yet.'))
                            : ListView.separated(
                                itemCount: _timesheets.length,
                                separatorBuilder: (_, __) => const Divider(height: 1),
                                itemBuilder: (_, i) {
                                  final t = _timesheets[i];
                                  return ListTile(
                                    title: Text((t['description'] ?? 'Logged Work').toString(), style: const TextStyle(fontWeight: FontWeight.w600)),
                                    subtitle: Text('${t['work_date'] ?? ''} · ${t['hours'] ?? 0} hrs'),
                                    trailing: StatusDotLabel.forStatus((t['status'] ?? 'submitted').toString()),
                                  );
                                },
                              ),
                        Positioned(
                          right: 16,
                          bottom: 16,
                          child: FloatingActionButton.extended(
                            onPressed: _openLogTimeSheet,
                            backgroundColor: TrustSealTheme.emerald,
                            foregroundColor: Colors.white,
                            icon: const Icon(Icons.add),
                            label: const Text('Log Time'),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
        ),
      ],
    );
  }
}

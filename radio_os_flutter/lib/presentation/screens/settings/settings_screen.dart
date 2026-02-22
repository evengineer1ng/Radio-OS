/// Settings Screen — general, models, voices, environment, connection.
/// Ultra-wide: horizontal section nav + content panel.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../config/host_config.dart';
import '../../../config/themes.dart';
import '../../../domain/providers.dart';

// Theme provider for the entire app — stored as a string key.
final themeNameProvider = StateProvider<String>((ref) => 'dark');

class SettingsScreen extends ConsumerStatefulWidget {
  final String section;
  const SettingsScreen({super.key, required this.section});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  Map<String, dynamic>? _settings;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final api = ref.read(shellApiProvider);
      final res = await api.getSettings();
      if (mounted) setState(() { _settings = res; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;

    final sections = [
      _SectionDef('connection', 'Connection', Icons.wifi),
      _SectionDef('general', 'General', Icons.settings),
      _SectionDef('models', 'Models', Icons.psychology),
      _SectionDef('voices', 'Voices', Icons.record_voice_over),
      _SectionDef('environment', 'Environment', Icons.computer),
      _SectionDef('appearance', 'Appearance', Icons.palette),
    ];

    return Scaffold(
      body: Row(
        children: [
          // Left nav
          Container(
            width: isUltraWide ? 200 : 240,
            color: theme.colorScheme.surface,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Back button header
                InkWell(
                  onTap: () => context.go('/'),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Icon(Icons.arrow_back, size: 22,
                            color: theme.textTheme.bodySmall?.color),
                        const SizedBox(width: 6),
                        Text('Back', style: theme.textTheme.labelLarge),
                      ],
                    ),
                  ),
                ),
                Divider(height: 1, color: theme.dividerColor),
                const SizedBox(height: 8),
                ...sections.map((s) {
                  final isActive = s.id == widget.section;
                  return InkWell(
                    onTap: () => context.go('/settings/${s.id}'),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 10),
                      color: isActive
                          ? theme.colorScheme.primary
                              .withValues(alpha: 0.1)
                          : Colors.transparent,
                      child: Row(
                        children: [
                          Icon(s.icon,
                              size: 22,
                              color: isActive
                                  ? theme.colorScheme.primary
                                  : theme.textTheme.bodySmall?.color),
                          const SizedBox(width: 8),
                          Text(
                            s.label,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: isActive
                                  ? FontWeight.w600
                                  : FontWeight.normal,
                              color: isActive
                                  ? theme.colorScheme.primary
                                  : theme.textTheme.bodySmall?.color,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }),
              ],
            ),
          ),
          Container(width: 1, color: theme.dividerColor),
          // Content area
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _buildSection(context),
          ),
        ],
      ),
    );
  }

  Widget _buildSection(BuildContext context) {
    switch (widget.section) {
      case 'connection':
        return const _ConnectionSection();
      case 'general':
        return _GeneralSection(settings: _settings);
      case 'models':
        return _ModelsSection(settings: _settings);
      case 'voices':
        return _VoicesSection(settings: _settings);
      case 'environment':
        return _EnvironmentSection(settings: _settings);
      case 'appearance':
        return _AppearanceSection();
      default:
        return Center(child: Text('Unknown section: ${widget.section}'));
    }
  }
}

class _SectionDef {
  final String id;
  final String label;
  final IconData icon;
  const _SectionDef(this.id, this.label, this.icon);
}

// ---------------------------------------------------------------------------
// Connection — configure backend host
// ---------------------------------------------------------------------------

class _ConnectionSection extends ConsumerStatefulWidget {
  const _ConnectionSection();

  @override
  ConsumerState<_ConnectionSection> createState() => _ConnectionSectionState();
}

class _ConnectionSectionState extends ConsumerState<_ConnectionSection> {
  late TextEditingController _hostCtrl;
  late TextEditingController _portCtrl;
  bool _testing = false;
  String? _testResult;

  static const _quickHosts = [
    ('This Pi', '127.0.0.1'),
    ('Mac (10.0.0.2)', '10.0.0.2'),
  ];

  @override
  void initState() {
    super.initState();
    final cfg = ref.read(hostConfigProvider);
    _hostCtrl = TextEditingController(text: cfg.host);
    _portCtrl = TextEditingController(text: cfg.shellPort.toString());
  }

  @override
  void dispose() {
    _hostCtrl.dispose();
    _portCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final host = _hostCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text.trim()) ?? 7800;
    if (host.isEmpty) return;
    await ref.read(hostConfigProvider.notifier).setHost(host);
    await ref.read(hostConfigProvider.notifier).setShellPort(port);
    ref.read(toastsProvider.notifier)
        .show('Backend set to $host:$port', type: 'success');
  }

  Future<void> _test() async {
    setState(() { _testing = true; _testResult = null; });
    try {
      final api = ref.read(shellApiProvider);
      final ok = await api.healthCheck();
      setState(() {
        _testResult = ok ? '✓ Connected' : '✗ Server responded but reported error';
        _testing = false;
      });
    } catch (e) {
      setState(() {
        _testResult = '✗ Could not reach server: $e';
        _testing = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cfg = ref.watch(hostConfigProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Connection', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 4),
          Text(
            'Set the host where Radio OS backend (web_server.py) is running.',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 20),

          // Quick presets
          Text('Quick select', style: theme.textTheme.labelMedium),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _quickHosts.map((preset) {
              final (label, host) = preset;
              final isActive = _hostCtrl.text == host;
              return OutlinedButton(
                onPressed: () => setState(() => _hostCtrl.text = host),
                style: OutlinedButton.styleFrom(
                  foregroundColor: isActive
                      ? theme.colorScheme.primary
                      : theme.textTheme.bodySmall?.color,
                  side: BorderSide(
                    color: isActive
                        ? theme.colorScheme.primary
                        : theme.dividerColor,
                  ),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 10),
                  textStyle: theme.textTheme.labelLarge,
                ),
                child: Text(label),
              );
            }).toList(),
          ),
          const SizedBox(height: 20),

          // Host field
          Text('Host / IP address', style: theme.textTheme.labelMedium),
          const SizedBox(height: 6),
          SizedBox(
            width: 400,
            child: TextField(
              controller: _hostCtrl,
              style: theme.textTheme.bodyMedium,
              decoration: const InputDecoration(
                hintText: '127.0.0.1 or hostname.local',
                prefixIcon: Icon(Icons.dns, size: 24),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Port field
          Text('Shell server port (default 7800)',
              style: theme.textTheme.labelMedium),
          const SizedBox(height: 6),
          SizedBox(
            width: 200,
            child: TextField(
              controller: _portCtrl,
              style: theme.textTheme.bodyMedium,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                hintText: '7800',
                prefixIcon: Icon(Icons.settings_ethernet, size: 24),
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Actions
          Row(
            children: [
              ElevatedButton.icon(
                onPressed: () async {
                  await _save();
                  await _test();
                },
                icon: const Icon(Icons.save, size: 22),
                label: const Text('Save & Test'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                onPressed: _testing ? null : _test,
                icon: _testing
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.wifi_find, size: 22),
                label: Text(_testing ? 'Testing...' : 'Test connection'),
              ),
              const SizedBox(width: 12),
              TextButton(
                onPressed: () async {
                  await ref.read(hostConfigProvider.notifier).reset();
                  final cfg = ref.read(hostConfigProvider);
                  _hostCtrl.text = cfg.host;
                  _portCtrl.text = cfg.shellPort.toString();
                  ref.read(toastsProvider.notifier)
                      .show('Reset to defaults');
                },
                child: const Text('Reset'),
              ),
            ],
          ),

          // Test result
          if (_testResult != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: _testResult!.startsWith('✓')
                    ? const Color(0xFF34d399).withValues(alpha: 0.1)
                    : const Color(0xFFf87171).withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color: _testResult!.startsWith('✓')
                      ? const Color(0xFF34d399)
                      : const Color(0xFFf87171),
                ),
              ),
              child: Text(_testResult!, style: theme.textTheme.bodySmall),
            ),
          ],

          // Current config summary
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: theme.cardColor,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: theme.dividerColor),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Active configuration',
                    style: theme.textTheme.labelMedium),
                const SizedBox(height: 8),
                _SettingRow(label: 'Shell API', value: cfg.shellBaseUrl),
                _SettingRow(label: 'Game API', value: cfg.gameBaseUrl),
                _SettingRow(
                    label: 'Audio WS',
                    value: 'ws://${cfg.host}:${cfg.shellPort}/ws/audio/<id>'),
                _SettingRow(
                    label: 'Event WS',
                    value: 'ws://${cfg.host}:${cfg.shellPort}/ws/station/<id>'),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// General
// ---------------------------------------------------------------------------

class _GeneralSection extends StatelessWidget {
  final Map<String, dynamic>? settings;
  const _GeneralSection({required this.settings});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('General Settings', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 16),
          _SettingRow(
              label: 'Version',
              value: settings?['version'] as String? ?? '—'),
          _SettingRow(
              label: 'Station Directory',
              value: settings?['station_dir'] as String? ?? '—'),
          _SettingRow(
              label: 'Plugin Directory',
              value: settings?['plugin_dir'] as String? ?? '—'),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

class _ModelsSection extends ConsumerStatefulWidget {
  final Map<String, dynamic>? settings;
  const _ModelsSection({required this.settings});

  @override
  ConsumerState<_ModelsSection> createState() => _ModelsSectionState();
}

class _ModelsSectionState extends ConsumerState<_ModelsSection> {
  Map<String, dynamic>? _models;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(shellApiProvider);
      final res = await api.getModelSettings();
      if (mounted) setState(() { _models = res; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) return const Center(child: CircularProgressIndicator());

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Model Configuration', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 16),
          if (_models != null)
            ..._models!.entries.map((e) => _SettingRow(
                label: e.key,
                value: e.value?.toString() ?? '—')),
          if (_models == null || _models!.isEmpty)
            Text('No model settings found',
                style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Voices
// ---------------------------------------------------------------------------

class _VoicesSection extends ConsumerStatefulWidget {
  final Map<String, dynamic>? settings;
  const _VoicesSection({required this.settings});

  @override
  ConsumerState<_VoicesSection> createState() => _VoicesSectionState();
}

class _VoicesSectionState extends ConsumerState<_VoicesSection> {
  List<dynamic>? _voices;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(shellApiProvider);
      final res = await api.listVoices();
      if (mounted) setState(() { _voices = res; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) return const Center(child: CircularProgressIndicator());

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Available Voices', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 16),
          Expanded(
            child: _voices == null || _voices!.isEmpty
                ? Text('No voices found', style: theme.textTheme.bodySmall)
                : ListView.builder(
                    itemCount: _voices!.length,
                    itemBuilder: (context, index) {
                      final v = _voices![index];
                      final name = v is Map
                          ? (v['name'] as String? ?? v.toString())
                          : v.toString();
                      return ListTile(
                        dense: true,
                        leading: Icon(Icons.record_voice_over,
                            size: 16, color: theme.colorScheme.primary),
                        title: Text(name, style: theme.textTheme.bodySmall),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

class _EnvironmentSection extends StatelessWidget {
  final Map<String, dynamic>? settings;
  const _EnvironmentSection({required this.settings});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final env = settings?['environment'] as Map<String, dynamic>? ?? {};

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Environment', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 16),
          ...env.entries.map((e) => _SettingRow(
              label: e.key, value: e.value?.toString() ?? '—')),
          if (env.isEmpty)
            Text('No environment settings', style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Appearance
// ---------------------------------------------------------------------------

class _AppearanceSection extends ConsumerWidget {
  const _AppearanceSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final current = ref.watch(themeNameProvider);
    final themes = ['dark', 'nord', 'dracula', 'monokai', 'solarized'];

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Appearance', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 16),
          Text('Theme', style: theme.textTheme.labelMedium),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: themes.map((name) {
              final colors = RadioColors.forName(name);
              final isActive = name == current;
              return InkWell(
                onTap: () =>
                    ref.read(themeNameProvider.notifier).state = name,
                borderRadius: BorderRadius.circular(8),
                child: Container(
                  width: 100,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: colors.bgPrimary,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: isActive
                          ? colors.accent
                          : colors.border,
                      width: isActive ? 2 : 1,
                    ),
                  ),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          _dot(colors.accent),
                          const SizedBox(width: 3),
                          _dot(colors.success),
                          const SizedBox(width: 3),
                          _dot(colors.warning),
                          const SizedBox(width: 3),
                          _dot(colors.danger),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        name[0].toUpperCase() + name.substring(1),
                        style: TextStyle(
                          color: colors.textPrimary,
                          fontSize: 11,
                          fontWeight: isActive
                              ? FontWeight.w700
                              : FontWeight.normal,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _dot(Color color) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
    );
  }
}

// ---------------------------------------------------------------------------
// Shared setting row
// ---------------------------------------------------------------------------

class _SettingRow extends StatelessWidget {
  final String label;
  final String value;
  const _SettingRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 220,
            child: Text(label,
                style: theme.textTheme.labelMedium),
          ),
          Expanded(
            child: Text(value, style: theme.textTheme.bodySmall),
          ),
        ],
      ),
    );
  }
}

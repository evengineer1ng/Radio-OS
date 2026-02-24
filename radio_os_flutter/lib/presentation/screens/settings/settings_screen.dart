/// Settings Screen — general, models, voices, environment, connection, appearance.
/// Ultra-wide: horizontal section nav on left + scrollable content panel on right.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
  Map<String, dynamic>? _storageInfo;
  Map<String, dynamic>? _pluginsInfo;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(shellApiProvider);
      final results = await Future.wait([
        api.getStorageInfo(),
        api.listPlugins(),
      ]);
      if (mounted) {
        setState(() {
          _storageInfo = results[0];
          _pluginsInfo = results[1];
          _loading = false;
        });
      }
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
      _SectionDef('sound', 'Sound', Icons.speaker),
      _SectionDef('appearance', 'Appearance', Icons.palette),
      _SectionDef('bluetooth', 'Bluetooth', Icons.bluetooth),
    ];

    return Scaffold(
      body: Row(
        children: [
          // ── Left nav ──────────────────────────────────────────────────
          Container(
            width: isUltraWide ? 180 : 220,
            color: theme.colorScheme.surface,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Back button — pop if possible, else go home
                InkWell(
                  onTap: () {
                    if (context.canPop()) {
                      context.pop();
                    } else {
                      context.go('/');
                    }
                  },
                  child: Padding(
                    padding: EdgeInsets.all(isUltraWide ? 10 : 14),
                    child: Row(
                      children: [
                        Icon(Icons.arrow_back,
                            size: isUltraWide ? 18 : 22,
                            color: theme.textTheme.bodySmall?.color),
                        const SizedBox(width: 6),
                        Text('Back', style: theme.textTheme.labelLarge),
                      ],
                    ),
                  ),
                ),
                Divider(height: 1, color: theme.dividerColor),
                const SizedBox(height: 6),
                ...sections.map((s) {
                  final isActive = s.id == widget.section;
                  return InkWell(
                    onTap: () => context.go('/settings/${s.id}'),
                    child: Container(
                      width: double.infinity,
                      padding: EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: isUltraWide ? 8 : 11),
                      color: isActive
                          ? theme.colorScheme.primary.withValues(alpha: 0.12)
                          : Colors.transparent,
                      child: Row(
                        children: [
                          Icon(s.icon,
                              size: isUltraWide ? 18 : 20,
                              color: isActive
                                  ? theme.colorScheme.primary
                                  : theme.textTheme.bodySmall?.color),
                          const SizedBox(width: 8),
                          Text(
                            s.label,
                            style: TextStyle(
                              fontSize: isUltraWide ? 13 : 15,
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
          // ── Content ───────────────────────────────────────────────────
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
        return _GeneralSection(
            storageInfo: _storageInfo, pluginsInfo: _pluginsInfo);
      case 'models':
        return const _ModelsSection();
      case 'voices':
        return const _VoicesSection();
      case 'environment':
        return const _EnvironmentSection();
      case 'sound':
        return const _SoundSection();
      case 'appearance':
        return const _AppearanceSection();
      case 'bluetooth':
        return const _BluetoothSection();
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

// ─────────────────────────────────────────────────────────────────────────────
// Connection
// ─────────────────────────────────────────────────────────────────────────────

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
    ('This Pi (localhost)', '127.0.0.1'),
    ('Mac (10.0.0.2)', '10.0.0.2'),
    ('Pi (10.0.0.120)', '10.0.0.120'),
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
    if (!mounted) return;
    ref.read(toastsProvider.notifier)
        .show('Backend set to $host:$port', type: 'success');
  }

  Future<void> _test() async {
    setState(() { _testing = true; _testResult = null; });
    try {
      final api = ref.read(shellApiProvider);
      final ok = await api.healthCheck();
      if (!mounted) return;
      setState(() {
        _testResult = ok ? '✓ Connected' : '✗ Server responded with error';
        _testing = false;
      });
    } catch (e) {
      if (!mounted) return;
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
          _SectionHeader('Connection', Icons.wifi,
              'Configure the Radio OS backend host.'),
          const SizedBox(height: 20),

          Text('Quick presets', style: theme.textTheme.labelMedium),
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
                          : theme.dividerColor),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                  textStyle: const TextStyle(fontSize: 13),
                ),
                child: Text(label),
              );
            }).toList(),
          ),
          const SizedBox(height: 20),

          Text('Host / IP address', style: theme.textTheme.labelMedium),
          const SizedBox(height: 6),
          SizedBox(
            width: 380,
            child: TextField(
              controller: _hostCtrl,
              style: theme.textTheme.bodyMedium,
              decoration: const InputDecoration(
                hintText: '127.0.0.1 or hostname.local',
                prefixIcon: Icon(Icons.dns, size: 20),
              ),
            ),
          ),
          const SizedBox(height: 14),

          Text('Shell server port', style: theme.textTheme.labelMedium),
          const SizedBox(height: 6),
          SizedBox(
            width: 180,
            child: TextField(
              controller: _portCtrl,
              style: theme.textTheme.bodyMedium,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                hintText: '7800',
                prefixIcon: Icon(Icons.settings_ethernet, size: 20),
              ),
            ),
          ),
          const SizedBox(height: 22),

          Row(
            children: [
              ElevatedButton.icon(
                onPressed: () async { await _save(); await _test(); },
                icon: const Icon(Icons.save, size: 18),
                label: const Text('Save & Test'),
              ),
              const SizedBox(width: 10),
              OutlinedButton.icon(
                onPressed: _testing ? null : _test,
                icon: _testing
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.wifi_find, size: 18),
                label: Text(_testing ? 'Testing…' : 'Test'),
              ),
              const SizedBox(width: 10),
              TextButton(
                onPressed: () async {
                  final toasts = ref.read(toastsProvider.notifier);
                  await ref.read(hostConfigProvider.notifier).reset();
                  if (!mounted) return;
                  final c = ref.read(hostConfigProvider);
                  _hostCtrl.text = c.host;
                  _portCtrl.text = c.shellPort.toString();
                  toasts.show('Reset to defaults');
                },
                child: const Text('Reset'),
              ),
            ],
          ),

          if (_testResult != null) ...[
            const SizedBox(height: 14),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
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

          const SizedBox(height: 22),
          _InfoCard(children: [
            _KV('Shell API', cfg.shellBaseUrl),
            _KV('Game API', cfg.gameBaseUrl),
            _KV('Audio WS',
                'ws://${cfg.host}:${cfg.shellPort}/ws/audio/<id>'),
            _KV('Event WS',
                'ws://${cfg.host}:${cfg.shellPort}/ws/station/<id>'),
          ]),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// General — system overview
// ─────────────────────────────────────────────────────────────────────────────

class _GeneralSection extends ConsumerWidget {
  final Map<String, dynamic>? storageInfo;
  final Map<String, dynamic>? pluginsInfo;
  const _GeneralSection(
      {required this.storageInfo, required this.pluginsInfo});

  String _fmtBytes(dynamic val) {
    if (val == null) return '—';
    final b = (val as num).toDouble();
    if (b > 1e9) return '${(b / 1e9).toStringAsFixed(1)} GB';
    if (b > 1e6) return '${(b / 1e6).toStringAsFixed(1)} MB';
    if (b > 1e3) return '${(b / 1e3).toStringAsFixed(1)} KB';
    return '${b.toInt()} B';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final stationList = ref.watch(stationsProvider);
    final pluginMap = (pluginsInfo?['plugins'] as Map?)?.cast<String, dynamic>();
    final feedPlugins = pluginMap?.values
        .where((p) => (p as Map)['is_feed'] == true)
        .length ?? 0;
    final allPlugins = pluginMap?.length ?? 0;
    final stationSizes =
        (storageInfo?['station_sizes'] as Map?)?.cast<String, dynamic>();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader('General', Icons.settings, 'System overview.'),
          const SizedBox(height: 20),

          // Runtime paths
          _InfoCard(children: [
            _KV('Stations directory',
                storageInfo?['stations_dir'] as String? ?? '—'),
            _KV('Config path',
                storageInfo?['config_path'] as String? ?? '—'),
          ]),
          const SizedBox(height: 16),

          // Plugin counts
          Text('Plugins', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          _InfoCard(children: [
            _KV('Total plugins', '$allPlugins'),
            _KV('Feed plugins', '$feedPlugins'),
            _KV('Non-feed (utility)', '${allPlugins - feedPlugins}'),
          ]),
          const SizedBox(height: 16),

          // Station disk usage
          if (stationSizes != null && stationSizes.isNotEmpty) ...[
            Text('Station disk usage', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            _InfoCard(
              children: stationSizes.entries
                  .map((e) => _KV(e.key, _fmtBytes(e.value)))
                  .toList(),
            ),
            const SizedBox(height: 16),
          ],

          // Station roster
          Text('Stations (${stationList.length})',
              style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          ...stationList.map((s) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    Icon(Icons.radio,
                        size: 14,
                        color: s.status.name == 'running'
                            ? const Color(0xFF34d399)
                            : theme.textTheme.bodySmall?.color),
                    const SizedBox(width: 8),
                    Expanded(
                        child: Text(s.name,
                            style: theme.textTheme.bodySmall)),
                    Text(s.moduleType.name,
                        style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.primary
                                .withValues(alpha: 0.7))),
                  ],
                ),
              )),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Models — per-station model config
// ─────────────────────────────────────────────────────────────────────────────

class _ModelsSection extends ConsumerWidget {
  const _ModelsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final stationList = ref.watch(stationsProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader('Models', Icons.psychology,
              'LLM model assignments per station. Edit station manifests to change.'),
          const SizedBox(height: 20),
          if (stationList.isEmpty)
            Text('No stations loaded', style: theme.textTheme.bodySmall)
          else
            ...stationList.map((s) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _InfoCard(
                    header: Row(
                      children: [
                        Icon(Icons.radio,
                            size: 14, color: theme.colorScheme.primary),
                        const SizedBox(width: 6),
                        Text(s.name,
                            style: theme.textTheme.labelMedium?.copyWith(
                                color: theme.colorScheme.primary)),
                      ],
                    ),
                    children: [
                      _KV('Type', s.moduleType.name),
                      _KV('Host', s.host.isEmpty ? '—' : s.host),
                      _KV('Status', s.status.name),
                    ],
                  ),
                )),
          const SizedBox(height: 8),
          Text(
            'To change model assignments, edit the station\'s manifest.yaml\n'
            '(stations/<id>/manifest.yaml → models.host_model / models.producer_model)',
            style: theme.textTheme.bodySmall
                ?.copyWith(fontStyle: FontStyle.italic),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Voices — list installed voice files
// ─────────────────────────────────────────────────────────────────────────────

class _VoicesSection extends ConsumerStatefulWidget {
  const _VoicesSection();
  @override
  ConsumerState<_VoicesSection> createState() => _VoicesSectionState();
}

class _VoicesSectionState extends ConsumerState<_VoicesSection> {
  List<String> _voices = [];
  bool _loading = true;
  bool _hasKokoro = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(shellApiProvider);
      final voices = await api.listVoices();
      if (mounted) {
        setState(() {
          _voices = voices;
          _hasKokoro = voices.any((v) =>
              v.toLowerCase().contains('kokoro') ||
              v.toLowerCase().contains('.onnx'));
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) return const Center(child: CircularProgressIndicator());

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader(
              'Voices', Icons.record_voice_over, 'Installed TTS voice models.'),
          const SizedBox(height: 16),

          // Kokoro status card
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: _hasKokoro
                  ? const Color(0xFF34d399).withValues(alpha: 0.08)
                  : const Color(0xFFfbbf24).withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: _hasKokoro
                    ? const Color(0xFF34d399)
                    : const Color(0xFFfbbf24),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  _hasKokoro ? Icons.check_circle : Icons.warning,
                  size: 18,
                  color: _hasKokoro
                      ? const Color(0xFF34d399)
                      : const Color(0xFFfbbf24),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _hasKokoro
                        ? 'Kokoro ONNX models detected'
                        : 'Kokoro not found — voices/kokoro/ missing. Run:\n'
                            'pip install kokoro-onnx  (in radioenv)\n'
                            'Then download kokoro-v1.0.onnx + voices-v1.0.bin',
                    style: theme.textTheme.bodySmall,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          if (_voices.isEmpty)
            Text(
              'No voices found via /api/voices.\n'
              'Installed: kokoro (voices/kokoro/), piper (voices/*.onnx)',
              style: theme.textTheme.bodySmall
                  ?.copyWith(fontStyle: FontStyle.italic),
            )
          else ...[
            Text('${_voices.length} voice(s) found',
                style: theme.textTheme.labelMedium),
            const SizedBox(height: 8),
            ..._voices.map((v) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    children: [
                      Icon(Icons.mic, size: 13,
                          color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                          child: Text(v,
                              style: theme.textTheme.bodySmall)),
                    ],
                  ),
                )),
          ],

          const SizedBox(height: 16),
          Text('Kokoro voices (built-in)',
              style: theme.textTheme.labelMedium),
          const SizedBox(height: 8),
          _InfoCard(children: const [
            _KV('af_alloy', 'American Female — neutral, clear'),
            _KV('af_bella', 'American Female — warm'),
            _KV('af_heart', 'American Female — expressive'),
            _KV('af_jessica', 'American Female — energetic'),
            _KV('am_adam', 'American Male — deep'),
            _KV('am_michael', 'American Male — natural'),
            _KV('bf_emma', 'British Female — polished'),
            _KV('bm_george', 'British Male — authoritative'),
          ]),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Environment — key env vars
// ─────────────────────────────────────────────────────────────────────────────

class _EnvironmentSection extends ConsumerStatefulWidget {
  const _EnvironmentSection();
  @override
  ConsumerState<_EnvironmentSection> createState() =>
      _EnvironmentSectionState();
}

class _EnvironmentSectionState extends ConsumerState<_EnvironmentSection> {
  Map<String, dynamic>? _env;
  bool _loading = true;

  static const _importantVars = [
    'OPENAI_API_KEY',
    'RADIO_OS_ROOT',
    'RADIO_OS_PLUGINS',
    'RADIO_OS_VOICES',
    'STATION_DIR',
    'CONTEXT_MODEL',
    'HOST_MODEL',
    'PYTHONPATH',
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(shellApiProvider);
      final res = await api.getEnvironmentSettings();
      if (mounted) setState(() { _env = res; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _mask(String key, String? val) {
    if (val == null || val.isEmpty) return '(not set)';
    if (key.toLowerCase().contains('key') ||
        key.toLowerCase().contains('secret') ||
        key.toLowerCase().contains('token')) {
      if (val.length > 8) {
        return '${val.substring(0, 8)}••••••••';
      }
      return '••••••••';
    }
    return val;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) return const Center(child: CircularProgressIndicator());

    final envMap = (_env?['environment'] as Map?)?.cast<String, String?>() ??
        (_env?.cast<String, String?>() ?? {});

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader('Environment', Icons.computer,
              'Runtime environment variables. Set in /etc/environment on Pi.'),
          const SizedBox(height: 16),

          Text('Key variables', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          _InfoCard(
            children: _importantVars.map((key) {
              final val = envMap[key];
              final isSet = val != null && val.isNotEmpty;
              return _KVStatus(
                label: key,
                value: _mask(key, val),
                ok: isSet,
              );
            }).toList(),
          ),

          if (envMap.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('All environment vars (${envMap.length})',
                style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            _InfoCard(
              children: envMap.entries
                  .where((e) => !_importantVars.contains(e.key))
                  .map((e) => _KV(e.key, _mask(e.key, e.value)))
                  .toList(),
            ),
          ],

          const SizedBox(height: 16),
          Text(
            'To set OPENAI_API_KEY permanently:\n'
            "  echo 'OPENAI_API_KEY=sk-...' | sudo tee -a /etc/environment\n"
            'Then add EnvironmentFile=/etc/environment to your systemd service.',
            style: theme.textTheme.bodySmall
                ?.copyWith(fontStyle: FontStyle.italic),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Appearance — theme picker
// ─────────────────────────────────────────────────────────────────────────────

class _AppearanceSection extends ConsumerWidget {
  const _AppearanceSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final current = ref.watch(themeNameProvider);
    final themes = ['dark', 'nord', 'dracula', 'monokai', 'solarized'];

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader('Appearance', Icons.palette, 'UI theme selection.'),
          const SizedBox(height: 16),
          Text('Theme', style: theme.textTheme.labelMedium),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: themes.map((name) {
              final colors = RadioColors.forName(name);
              final isActive = name == current;
              return InkWell(
                onTap: () =>
                    ref.read(themeNameProvider.notifier).state = name,
                borderRadius: BorderRadius.circular(8),
                child: Container(
                  width: 90,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: colors.bgPrimary,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: isActive ? colors.accent : colors.border,
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

  Widget _dot(Color color) => Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(shape: BoxShape.circle, color: color),
      );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sound (Puck audio nodes)
// ─────────────────────────────────────────────────────────────────────────────

class _SoundSection extends ConsumerStatefulWidget {
  const _SoundSection();
  @override
  ConsumerState<_SoundSection> createState() => _SoundSectionState();
}

class _SoundSectionState extends ConsumerState<_SoundSection> {
  // ── Audio output state ───────────────────────────────────────
  List<Map<String, dynamic>> _sinks = [];
  String _defaultSink = '';
  bool _sinksLoading = true;
  bool _sinkSetting = false;
  String? _sinksError;

  // ── Puck state ───────────────────────────────────────────────
  List<Map<String, dynamic>> _pucks = [];
  bool _pucksLoading = true;
  String? _pucksError;
  int _groupVolume = 80;

  static const _routeOptions = ['all', 'none'];

  @override
  void initState() {
    super.initState();
    _loadSinks();
    _loadPucks();
  }

  Future<void> _loadSinks() async {
    setState(() { _sinksLoading = true; _sinksError = null; });
    try {
      final api = ref.read(shellApiProvider);
      final raw = await api.listAudioSinks();
      if (!mounted) return;
      final sinks = (raw['sinks'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      setState(() {
        _sinks = sinks;
        _defaultSink = raw['default'] as String? ?? '';
        _sinksLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _sinksError = e.toString(); _sinksLoading = false; });
    }
  }

  Future<void> _setDefaultSink(String sinkName) async {
    setState(() => _sinkSetting = true);
    try {
      final api = ref.read(shellApiProvider);
      final result = await api.setDefaultAudioSink(sinkName);
      if (!mounted) return;
      if (result['ok'] == true) {
        setState(() => _defaultSink = sinkName);
        ref.read(toastsProvider.notifier).show(
          'Audio output set to ${_sinkLabel(sinkName)}',
          type: 'success',
        );
        await _loadSinks();
      }
    } catch (e) {
      if (!mounted) return;
      ref.read(toastsProvider.notifier).show('Failed: $e', type: 'error');
    } finally {
      if (mounted) setState(() => _sinkSetting = false);
    }
  }

  String _sinkLabel(String name) {
    for (final s in _sinks) {
      if (s['name'] == name) return s['description'] as String? ?? name;
    }
    return name;
  }

  Future<void> _loadPucks() async {
    setState(() { _pucksLoading = true; _pucksError = null; });
    try {
      final api = ref.read(shellApiProvider);
      final raw = await api.getPucks();
      final pucks = raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      if (pucks.isNotEmpty) {
        final sum = pucks.fold<int>(0, (s, p) => s + ((p['volume'] as num?)?.toInt() ?? 80));
        _groupVolume = (sum / pucks.length).round();
      }
      if (!mounted) return;
      setState(() { _pucks = pucks; _pucksLoading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _pucksError = e.toString(); _pucksLoading = false; });
    }
  }

  Future<void> _setGroupVolume(int v) async {
    setState(() => _groupVolume = v);
    final api = ref.read(shellApiProvider);
    await api.setGroupVolume(v);
    setState(() { for (final p in _pucks) { p['volume'] = v; } });
  }

  Future<void> _setPuckVolume(int nodeId, int v) async {
    setState(() { for (final p in _pucks) { if ((p['node_id'] as int?) == nodeId) p['volume'] = v; } });
    await ref.read(shellApiProvider).setPuckVolume(nodeId, v);
  }

  Future<void> _toggleMute(int nodeId, bool muted) async {
    setState(() { for (final p in _pucks) { if ((p['node_id'] as int?) == nodeId) p['muted'] = muted; } });
    await ref.read(shellApiProvider).setPuckMute(nodeId, muted: muted);
  }

  Future<void> _muteAll(bool muted) async {
    setState(() { for (final p in _pucks) { p['muted'] = muted; } });
    await ref.read(shellApiProvider).muteAllPucks(muted: muted);
  }

  Future<void> _setRoute(int nodeId, String route) async {
    setState(() { for (final p in _pucks) { if ((p['node_id'] as int?) == nodeId) p['route'] = route; } });
    await ref.read(shellApiProvider).setPuckRoute(nodeId, route);
  }

  Future<void> _testTone(int nodeId) async =>
      ref.read(shellApiProvider).sendPuckTestTone(nodeId);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = theme.colorScheme.primary;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader('Sound', Icons.speaker, 'Audio output device and wireless puck nodes'),
          const SizedBox(height: 20),

          // ── Audio Output ────────────────────────────────────────────────
          _InfoCard(
            header: Row(
              children: [
                Icon(Icons.speaker, size: 16, color: accent),
                const SizedBox(width: 6),
                Text('Audio Output Device', style: theme.textTheme.labelLarge),
                const Spacer(),
                if (_sinkSetting)
                  const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                else
                  IconButton(
                    icon: const Icon(Icons.refresh, size: 16),
                    tooltip: 'Refresh sinks',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    onPressed: _loadSinks,
                  ),
              ],
            ),
            children: [
              if (_sinksLoading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_sinksError != null)
                Text('Could not load audio devices: $_sinksError',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: const Color(0xFFf87171)))
              else if (_sinks.isEmpty)
                Text('No audio sinks found. Is PulseAudio or PipeWire running?',
                    style: theme.textTheme.bodySmall)
              else
                ..._sinks.map((sink) {
                  final name = sink['name'] as String;
                  final desc = sink['description'] as String? ?? name;
                  final isDefault = sink['is_default'] as bool? ?? (name == _defaultSink);
                  final isBt = sink['is_bluetooth'] as bool? ?? false;
                  final state = sink['state'] as String? ?? '';
                  return GestureDetector(
                    onTap: isDefault || _sinkSetting ? null : () => _setDefaultSink(name),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 160),
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: isDefault
                            ? accent.withValues(alpha: 0.12)
                            : theme.cardColor,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: isDefault
                              ? accent.withValues(alpha: 0.6)
                              : theme.dividerColor,
                          width: isDefault ? 1.5 : 1,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            isBt ? Icons.bluetooth_audio : Icons.speaker,
                            size: 20,
                            color: isDefault ? accent : theme.textTheme.bodySmall?.color,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(desc,
                                    style: TextStyle(
                                      fontSize: 14,
                                      fontWeight: isDefault ? FontWeight.w600 : FontWeight.normal,
                                      color: isDefault ? accent : theme.textTheme.bodyMedium?.color,
                                    )),
                                if (state.isNotEmpty)
                                  Text(state,
                                      style: theme.textTheme.labelSmall
                                          ?.copyWith(fontSize: 11)),
                              ],
                            ),
                          ),
                          if (isDefault)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: accent.withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(color: accent.withValues(alpha: 0.4)),
                              ),
                              child: Text('DEFAULT',
                                  style: TextStyle(
                                      color: accent,
                                      fontSize: 10,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: 1.5)),
                            )
                          else
                            Text('SET DEFAULT',
                                style: TextStyle(
                                    color: accent.withValues(alpha: 0.5),
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1)),
                        ],
                      ),
                    ),
                  );
                }),
            ],
          ),
          const SizedBox(height: 20),

          // ── Puck audio nodes ────────────────────────────────────────────
          if (_pucksLoading)
            const Center(child: CircularProgressIndicator())
          else if (_pucksError != null)
            _InfoCard(children: [
              Row(children: [
                const Icon(Icons.error_outline, color: Color(0xFFf87171), size: 18),
                const SizedBox(width: 8),
                Expanded(
                    child: Text('Could not load pucks: $_pucksError',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: const Color(0xFFf87171)))),
              ]),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: _loadPucks,
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('Retry'),
              ),
            ])
          else ...[
            // ── Group volume ──────────────────────────────────────────
            _InfoCard(
              header: Row(
                children: [
                  const Icon(Icons.volume_up, size: 16),
                  const SizedBox(width: 6),
                  Text('Group Volume', style: theme.textTheme.labelLarge),
                  const Spacer(),
                  OutlinedButton.icon(
                    onPressed: () => _muteAll(true),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                    icon: const Icon(Icons.volume_off, size: 14),
                    label: const Text('Mute all', style: TextStyle(fontSize: 12)),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: () => _muteAll(false),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                    icon: const Icon(Icons.volume_up, size: 14),
                    label: const Text('Unmute all', style: TextStyle(fontSize: 12)),
                  ),
                ],
              ),
              children: [
                Row(
                  children: [
                    Text('$_groupVolume',
                        style: theme.textTheme.labelMedium
                            ?.copyWith(fontFamily: 'monospace', fontSize: 16),
                        textAlign: TextAlign.right),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Slider(
                        value: _groupVolume.toDouble(),
                        min: 0,
                        max: 100,
                        divisions: 20,
                        label: '$_groupVolume',
                        onChanged: (v) => setState(() => _groupVolume = v.round()),
                        onChangeEnd: (v) => _setGroupVolume(v.round()),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),
            // ── Per-puck rows ─────────────────────────────────────────
            if (_pucks.isEmpty)
              _InfoCard(children: [
                Text('No pucks connected. Flash firmware and connect ESP32 nodes to WiFi.',
                    style: theme.textTheme.bodySmall),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: _loadPucks,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Refresh'),
                ),
              ])
            else
              ..._pucks.map((puck) {
                final nodeId = (puck['node_id'] as num?)?.toInt() ?? 0;
                final volume = (puck['volume'] as num?)?.toInt() ?? 80;
                final muted = puck['muted'] as bool? ?? false;
                final connected = puck['connected'] as bool? ?? false;
                final route = puck['route'] as String? ?? 'all';

                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _InfoCard(
                    header: Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: connected
                                ? const Color(0xFF34d399)
                                : const Color(0xFF9ca3af),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text('Puck $nodeId',
                            style: theme.textTheme.labelLarge),
                        const SizedBox(width: 6),
                        Text(connected ? 'connected' : 'offline',
                            style: theme.textTheme.bodySmall?.copyWith(
                                color: connected
                                    ? const Color(0xFF34d399)
                                    : const Color(0xFF9ca3af))),
                        const Spacer(),
                        // Mute toggle
                        IconButton(
                          tooltip: muted ? 'Unmute' : 'Mute',
                          icon: Icon(
                            muted ? Icons.volume_off : Icons.volume_up,
                            size: 18,
                            color: muted ? const Color(0xFFf87171) : null,
                          ),
                          onPressed: () => _toggleMute(nodeId, !muted),
                        ),
                        // Test tone
                        IconButton(
                          tooltip: 'Send test tone',
                          icon: const Icon(Icons.surround_sound, size: 18),
                          onPressed: connected ? () => _testTone(nodeId) : null,
                        ),
                      ],
                    ),
                    children: [
                      // Volume row
                      Row(
                        children: [
                          SizedBox(
                            width: 36,
                            child: Text('$volume',
                                style: theme.textTheme.bodySmall
                                    ?.copyWith(fontFamily: 'monospace'),
                                textAlign: TextAlign.right),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Slider(
                              value: volume.toDouble(),
                              min: 0,
                              max: 100,
                              divisions: 20,
                              label: '$volume',
                              onChanged: muted
                                  ? null
                                  : (v) => setState(() {
                                        for (final p in _pucks) {
                                          if ((p['node_id'] as int?) == nodeId) {
                                            p['volume'] = v.round();
                                          }
                                        }
                                      }),
                              onChangeEnd: muted
                                  ? null
                                  : (v) => _setPuckVolume(nodeId, v.round()),
                            ),
                          ),
                        ],
                      ),
                      // Route row
                      Row(
                        children: [
                          Text('Route:',
                              style: theme.textTheme.labelMedium),
                          const SizedBox(width: 12),
                          DropdownButton<String>(
                            value: _routeOptions.contains(route) ? route : 'all',
                            isDense: true,
                            items: _routeOptions
                                .map((r) => DropdownMenuItem(
                                    value: r,
                                    child: Text(r == 'all' ? 'All stations' : r == 'none' ? 'Silent' : r,
                                        style: theme.textTheme.bodySmall)))
                                .toList(),
                            onChanged: (v) {
                              if (v != null) _setRoute(nodeId, v);
                            },
                          ),
                        ],
                      ),
                    ],
                  ),
                );
              }),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _loadPucks,
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Refresh puck status'),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared widgets
// ─────────────────────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final String title;
  final IconData icon;
  final String subtitle;
  const _SectionHeader(this.title, this.icon, this.subtitle);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 20, color: theme.colorScheme.primary),
            const SizedBox(width: 8),
            Text(title, style: theme.textTheme.headlineMedium),
          ],
        ),
        const SizedBox(height: 4),
        Text(subtitle, style: theme.textTheme.bodySmall),
      ],
    );
  }
}

class _InfoCard extends StatelessWidget {
  final List<Widget> children;
  final Widget? header;
  const _InfoCard({required this.children, this.header});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (header != null) ...[header!, const SizedBox(height: 8)],
          ...children,
        ],
      ),
    );
  }
}

class _KV extends StatelessWidget {
  final String label;
  final String value;
  const _KV(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 200,
            child: Text(label, style: theme.textTheme.labelMedium),
          ),
          Expanded(
            child: Text(value,
                style: theme.textTheme.bodySmall
                    ?.copyWith(fontFamily: 'monospace')),
          ),
        ],
      ),
    );
  }
}

class _KVStatus extends StatelessWidget {
  final String label;
  final String value;
  final bool ok;
  const _KVStatus(
      {required this.label, required this.value, required this.ok});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            ok ? Icons.check_circle_outline : Icons.cancel_outlined,
            size: 14,
            color: ok
                ? const Color(0xFF34d399)
                : const Color(0xFFf87171),
          ),
          const SizedBox(width: 6),
          SizedBox(
            width: 194,
            child: Text(label, style: theme.textTheme.labelMedium),
          ),
          Expanded(
            child: Text(value,
                style: theme.textTheme.bodySmall?.copyWith(
                    fontFamily: 'monospace',
                    color: ok ? null : const Color(0xFF9ca3af))),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Bluetooth
// ─────────────────────────────────────────────────────────────────────────────

class _BluetoothSection extends ConsumerStatefulWidget {
  const _BluetoothSection();

  @override
  ConsumerState<_BluetoothSection> createState() => _BluetoothSectionState();
}

class _BluetoothSectionState extends ConsumerState<_BluetoothSection> {
  List<Map<String, dynamic>> _devices = [];
  bool _loading = true;
  bool _scanning = false;
  bool _powered = false;
  final Map<String, bool> _actionBusy = {};
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(shellApiProvider);
      final results = await Future.wait([
        api.getBluetoothStatus(),
        api.getBluetoothDevices(),
      ]);
      final status = results[0];
      final devResult = results[1];
      if (!mounted) return;
      setState(() {
        _powered = status['powered'] as bool? ?? false;
        _scanning = status['discovering'] as bool? ?? false;
        final raw = devResult['devices'];
        _devices = raw is List
            ? raw.map((e) => Map<String, dynamic>.from(e as Map)).toList()
            : [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _togglePower() async {
    final api = ref.read(shellApiProvider);
    setState(() => _actionBusy['power'] = true);
    try {
      await api.bluetoothPower(on: !_powered);
      await _loadAll();
    } catch (_) {
    } finally {
      if (mounted) setState(() => _actionBusy.remove('power'));
    }
  }

  Future<void> _toggleScan() async {
    final api = ref.read(shellApiProvider);
    final newScan = !_scanning;
    setState(() => _scanning = newScan);
    try {
      await api.bluetoothScan(enable: newScan);
      if (newScan) {
        await Future.delayed(const Duration(seconds: 4));
        await _loadAll();
      }
    } catch (_) {
      if (mounted) setState(() => _scanning = false);
    }
  }

  Future<void> _pair(String mac) async {
    final api = ref.read(shellApiProvider);
    setState(() => _actionBusy[mac] = true);
    try {
      await api.bluetoothPair(mac);
      await _loadAll();
    } catch (_) {
    } finally {
      if (mounted) setState(() => _actionBusy.remove(mac));
    }
  }

  Future<void> _connect(String mac) async {
    final api = ref.read(shellApiProvider);
    setState(() => _actionBusy['${mac}_c'] = true);
    try {
      await api.bluetoothConnect(mac);
      await _loadAll();
    } catch (_) {
    } finally {
      if (mounted) setState(() => _actionBusy.remove('${mac}_c'));
    }
  }

  Future<void> _disconnect(String mac) async {
    final api = ref.read(shellApiProvider);
    setState(() => _actionBusy['${mac}_d'] = true);
    try {
      await api.bluetoothDisconnect(mac);
      await _loadAll();
    } catch (_) {
    } finally {
      if (mounted) setState(() => _actionBusy.remove('${mac}_d'));
    }
  }

  Future<void> _remove(String mac) async {
    final api = ref.read(shellApiProvider);
    setState(() => _actionBusy['${mac}_r'] = true);
    try {
      await api.bluetoothRemove(mac);
      await _loadAll();
    } catch (_) {
    } finally {
      if (mounted) setState(() => _actionBusy.remove('${mac}_r'));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;
    final pad = isUltraWide ? 14.0 : 20.0;

    return SingleChildScrollView(
      padding: EdgeInsets.all(pad),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header ────────────────────────────────────────────────────
          Row(
            children: [
              Icon(Icons.bluetooth,
                  color: theme.colorScheme.primary,
                  size: isUltraWide ? 20 : 24),
              const SizedBox(width: 10),
              Text('Bluetooth',
                  style: theme.textTheme.headlineSmall
                      ?.copyWith(fontSize: isUltraWide ? 18 : 22)),
              const Spacer(),
              // Power toggle
              if (_actionBusy['power'] == true)
                const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
              else
                Row(children: [
                  Text(_powered ? 'On' : 'Off',
                      style: theme.textTheme.bodySmall),
                  const SizedBox(width: 6),
                  Switch(
                    value: _powered,
                    onChanged: (_) => _togglePower(),
                    activeColor: theme.colorScheme.primary,
                  ),
                ]),
              const SizedBox(width: 8),
              IconButton(
                onPressed: _loadAll,
                icon: const Icon(Icons.refresh),
                tooltip: 'Refresh',
                iconSize: isUltraWide ? 18 : 22,
              ),
            ],
          ),
          SizedBox(height: isUltraWide ? 8 : 12),

          // ── Error banner ──────────────────────────────────────────────
          if (_error != null) ...[
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: theme.colorScheme.error.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(children: [
                Icon(Icons.error_outline,
                    color: theme.colorScheme.error, size: 16),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(_error!,
                        style: TextStyle(
                            color: theme.colorScheme.error,
                            fontSize: 13))),
              ]),
            ),
            SizedBox(height: isUltraWide ? 8 : 12),
          ],

          // ── Scan bar ──────────────────────────────────────────────────
          Container(
            padding: EdgeInsets.all(isUltraWide ? 10 : 14),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: theme.dividerColor),
            ),
            child: Row(
              children: [
                if (_scanning)
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: theme.colorScheme.primary,
                    ),
                  )
                else
                  Icon(Icons.bluetooth_searching,
                      color: theme.colorScheme.primary,
                      size: isUltraWide ? 16 : 18),
                const SizedBox(width: 10),
                Text(
                  _scanning
                      ? 'Scanning for devices…'
                      : 'Tap Scan to discover nearby devices',
                  style: theme.textTheme.bodyMedium,
                ),
                const Spacer(),
                TextButton.icon(
                  onPressed: _powered ? _toggleScan : null,
                  icon: Icon(_scanning ? Icons.stop : Icons.search,
                      size: isUltraWide ? 15 : 17),
                  label: Text(_scanning ? 'Stop' : 'Scan'),
                ),
              ],
            ),
          ),

          SizedBox(height: isUltraWide ? 8 : 14),

          // ── Device list ───────────────────────────────────────────────
          if (_loading)
            const Center(
                child: Padding(
              padding: EdgeInsets.all(24),
              child: CircularProgressIndicator(),
            ))
          else if (_devices.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 20),
              child: Center(
                child: Text(
                  'No devices found. Enable Bluetooth and tap Scan.',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            )
          else
            ..._devices.map((dev) => _DeviceTile(
                  device: dev,
                  isUltraWide: isUltraWide,
                  actionBusy: _actionBusy,
                  onPair: () => _pair(dev['mac'] as String),
                  onConnect: () => _connect(dev['mac'] as String),
                  onDisconnect: () => _disconnect(dev['mac'] as String),
                  onRemove: () => _remove(dev['mac'] as String),
                )),
        ],
      ),
    );
  }
}

// ── Device tile ──────────────────────────────────────────────────────────────

class _DeviceTile extends StatelessWidget {
  final Map<String, dynamic> device;
  final bool isUltraWide;
  final Map<String, bool> actionBusy;
  final VoidCallback onPair;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;
  final VoidCallback onRemove;

  const _DeviceTile({
    required this.device,
    required this.isUltraWide,
    required this.actionBusy,
    required this.onPair,
    required this.onConnect,
    required this.onDisconnect,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final mac = device['mac'] as String? ?? '';
    final name = device['name'] as String? ?? mac;
    final paired = device['paired'] as bool? ?? false;
    final connected = device['connected'] as bool? ?? false;

    final isBusy = actionBusy[mac] == true ||
        actionBusy['${mac}_c'] == true ||
        actionBusy['${mac}_d'] == true ||
        actionBusy['${mac}_r'] == true;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: EdgeInsets.symmetric(
          horizontal: isUltraWide ? 12 : 16,
          vertical: isUltraWide ? 8 : 12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: connected
              ? theme.colorScheme.primary.withValues(alpha: 0.6)
              : theme.dividerColor,
          width: connected ? 1.5 : 1,
        ),
      ),
      child: Row(
        children: [
          Icon(
            connected
                ? Icons.bluetooth_connected
                : paired
                    ? Icons.bluetooth
                    : Icons.bluetooth_disabled,
            color: connected
                ? theme.colorScheme.primary
                : paired
                    ? theme.textTheme.bodyMedium?.color
                    : theme.textTheme.bodySmall?.color,
            size: isUltraWide ? 18 : 22,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Text(name,
                      style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                          fontSize: isUltraWide ? 13 : 15)),
                  if (connected) ...[
                    const SizedBox(width: 8),
                    _BtBadge('CONNECTED', const Color(0xFF2EE59D)),
                  ] else if (paired) ...[
                    const SizedBox(width: 8),
                    _BtBadge('PAIRED', const Color(0xFF4CC9F0)),
                  ],
                ]),
                Text(mac,
                    style: theme.textTheme.labelSmall?.copyWith(
                        fontFamily: 'monospace',
                        fontSize: isUltraWide ? 10 : 12,
                        color: theme.textTheme.bodySmall?.color)),
              ],
            ),
          ),
          if (isBusy)
            const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2))
          else
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!paired)
                  _BtActionButton(
                    label: 'Pair',
                    icon: Icons.link,
                    onTap: onPair,
                    isUltraWide: isUltraWide,
                  ),
                if (paired && !connected)
                  _BtActionButton(
                    label: 'Connect',
                    icon: Icons.bluetooth_connected,
                    color: theme.colorScheme.primary,
                    onTap: onConnect,
                    isUltraWide: isUltraWide,
                  ),
                if (connected)
                  _BtActionButton(
                    label: 'Disconnect',
                    icon: Icons.bluetooth_disabled,
                    onTap: onDisconnect,
                    isUltraWide: isUltraWide,
                  ),
                if (paired)
                  _BtActionButton(
                    label: 'Forget',
                    icon: Icons.delete_outline,
                    color: theme.colorScheme.error,
                    onTap: onRemove,
                    isUltraWide: isUltraWide,
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _BtBadge extends StatelessWidget {
  final String label;
  final Color color;
  const _BtBadge(this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 9,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}

class _BtActionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  final Color? color;
  final bool isUltraWide;

  const _BtActionButton({
    required this.label,
    required this.icon,
    required this.onTap,
    this.color,
    required this.isUltraWide,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final c = color ?? theme.textTheme.bodyMedium?.color ?? Colors.white;
    return Padding(
      padding: const EdgeInsets.only(left: 6),
      child: TextButton.icon(
        style: TextButton.styleFrom(
          foregroundColor: c,
          padding: EdgeInsets.symmetric(
              horizontal: isUltraWide ? 8 : 10,
              vertical: isUltraWide ? 4 : 6),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        onPressed: onTap,
        icon: Icon(icon, size: isUltraWide ? 14 : 16),
        label: Text(label,
            style: TextStyle(fontSize: isUltraWide ? 11 : 13)),
      ),
    );
  }
}

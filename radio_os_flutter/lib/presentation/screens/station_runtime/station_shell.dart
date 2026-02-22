/// Station Shell — persistent wrapper with nav bar + subtitle overlay.
/// This is the ShellRoute builder for all station/* routes.
/// Designed for 1920×480: the tab bar runs horizontally at the bottom,
/// the subtitle floats above it, and the content fills the remaining area.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../data/models/station.dart';
import '../../../domain/providers.dart';
import '../../widgets/connection_banner.dart';
import '../../widgets/now_playing_banner.dart';
import '../../widgets/subtitle_overlay.dart';
import '../../widgets/toast_overlay.dart';

class StationShell extends ConsumerStatefulWidget {
  final Widget child;
  const StationShell({super.key, required this.child});

  @override
  ConsumerState<StationShell> createState() => _StationShellState();
}

class _StationShellState extends ConsumerState<StationShell> {
  @override
  void initState() {
    super.initState();
    // Connect WebSocket streams when entering a station
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final station = ref.read(activeStationProvider);
      if (station != null) {
        final ws = ref.read(wsManagerProvider);
        ws.connectToStation(station.id);
        ws.onEventMessage = (msg) {
          dispatchWsEventFromContainer(
              ProviderScope.containerOf(context), msg);
        };
      }
    });
  }

  @override
  void dispose() {
    ref.read(wsManagerProvider).disconnect();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final station = ref.watch(activeStationProvider);
    final activeTab = ref.watch(activeTabProvider);
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;

    // Determine tabs based on station module type
    final tabs = _tabsForStation(station);

    return Scaffold(
      body: Column(
        children: [
          const ConnectionBanner(),

          // Top toolbar
          Container(
            height: isUltraWide ? 36 : 44,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              border: Border(bottom: BorderSide(color: theme.dividerColor)),
            ),
            child: Row(
              children: [
                // Back to browser
                IconButton(
                  icon: const Icon(Icons.arrow_back, size: 18),
                  onPressed: () => context.go('/'),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                      minWidth: 32, minHeight: 32),
                  tooltip: 'Back to stations',
                ),
                const SizedBox(width: 8),
                Icon(Icons.radio, color: theme.colorScheme.primary, size: 16),
                const SizedBox(width: 6),
                Text(
                  station?.name ?? 'Station',
                  style: theme.textTheme.labelLarge,
                ),
                const SizedBox(width: 8),
                if (station?.status == StationStatus.running)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(
                      color: const Color(0xFF34d399).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Text('● Connected',
                        style: TextStyle(
                            color: Color(0xFF34d399),
                            fontSize: 10,
                            fontWeight: FontWeight.w500)),
                  ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.settings, size: 18),
                  onPressed: () => context.go('/settings/general'),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                      minWidth: 32, minHeight: 32),
                ),
              ],
            ),
          ),

          // Main content
          Expanded(
            child: Stack(
              children: [
                widget.child,
                const SubtitleOverlay(),
                const ToastOverlay(),
              ],
            ),
          ),

          // Now playing
          const NowPlayingBanner(),

          // Tab bar — scrollable horizontal for ultra-wide
          Container(
            height: isUltraWide ? 40 : 48,
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              border: Border(top: BorderSide(color: theme.dividerColor)),
            ),
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 8),
              itemCount: tabs.length,
              itemBuilder: (context, index) {
                final tab = tabs[index];
                final isActive = tab.id == activeTab;
                return GestureDetector(
                  onTap: () {
                    ref.read(activeTabProvider.notifier).state = tab.id;
                    if (station != null) {
                      context.go('/station/${station.id}/${tab.id}');
                    }
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    decoration: BoxDecoration(
                      border: Border(
                        bottom: BorderSide(
                          color: isActive
                              ? theme.colorScheme.primary
                              : Colors.transparent,
                          width: 2,
                        ),
                      ),
                    ),
                    alignment: Alignment.center,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(tab.emoji,
                            style: TextStyle(
                                fontSize: isUltraWide ? 14 : 16)),
                        const SizedBox(width: 4),
                        Text(
                          tab.label,
                          style: TextStyle(
                            fontSize: isUltraWide ? 10 : 11,
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
              },
            ),
          ),
        ],
      ),
    );
  }

  List<_TabDef> _tabsForStation(Station? station) {
    if (station == null) return _ftbTabs;

    switch (station.moduleType) {
      case StationModuleType.ftb:
        return _ftbTabs;
      case StationModuleType.oracleKingdom:
        return _okTabs;
      case StationModuleType.radio:
        return _radioTabs;
      case StationModuleType.neikos:
        return _neikosTabs;
    }
  }
}

class _TabDef {
  final String id;
  final String emoji;
  final String label;
  const _TabDef(this.id, this.emoji, this.label);
}

const _ftbTabs = [
  _TabDef('dashboard', '🏠', 'Home'),
  _TabDef('team', '👥', 'Team'),
  _TabDef('car', '🏎️', 'Car'),
  _TabDef('development', '🔧', 'Dev'),
  _TabDef('raceops', '🏁', 'Race'),
  _TabDef('pbp', '📡', 'PBP'),
  _TabDef('finance', '💰', 'Finance'),
  _TabDef('sponsors', '🤝', 'Sponsors'),
  _TabDef('promotion', '📈', 'Promo'),
  _TabDef('stats', '📊', 'Stats'),
  _TabDef('analytics', '📈', 'Analytics'),
  _TabDef('career', '🏆', 'Career'),
  _TabDef('calendar', '📅', 'Calendar'),
  _TabDef('ai', '🤖', 'AI'),
  _TabDef('penalties', '⚠️', 'Penalties'),
  _TabDef('history', '📜', 'History'),
  _TabDef('help', '❓', 'Help'),
  _TabDef('data', '🗄️', 'Data'),
];

const _okTabs = [
  _TabDef('dashboard', '🏠', 'Home'),
  _TabDef('decree', '👑', 'Decree'),
  _TabDef('kingdom', '🏰', 'Kingdom'),
  _TabDef('court', '🏛️', 'Court'),
  _TabDef('narrative', '📜', 'Narrative'),
  _TabDef('ledger', '📖', 'Ledger'),
];

const _radioTabs = [
  _TabDef('dashboard', '🏠', 'Home'),
  _TabDef('feeds', '📡', 'Feeds'),
  _TabDef('events', '📋', 'Events'),
];

const _neikosTabs = [
  _TabDef('dashboard', '🏠', 'Home'),
  _TabDef('islands', '🏝️', 'Islands'),
  _TabDef('species', '🐾', 'Species'),
  _TabDef('league', '🏆', 'League'),
  _TabDef('ecology', '🌿', 'Ecology'),
];

/// Station Shell — persistent wrapper with swipeable PageView + tab bar.
/// Each tab is a full-width card. Swipe to navigate; bottom tab bar stays
/// in sync and can also be tapped. Designed for 1920×480 ultra-wide displays.
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
import 'station_tab_screen.dart';

class StationShell extends ConsumerStatefulWidget {
  // child is kept for ShellRoute compat but we drive navigation via PageView.
  final Widget child;
  const StationShell({super.key, required this.child});

  @override
  ConsumerState<StationShell> createState() => _StationShellState();
}

class _StationShellState extends ConsumerState<StationShell> {
  Object? _wsManager;
  late PageController _pageCtrl;
  String? _lastStationId;

  @override
  void initState() {
    super.initState();
    _pageCtrl = PageController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final station = ref.read(activeStationProvider);
      if (station != null) {
        final ws = ref.read(wsManagerProvider);
        _wsManager = ws;
        ws.connectToStation(station.id);
        ws.onEventMessage = (msg) {
          if (!mounted) return;
          dispatchWsEventFromContainer(
              ProviderScope.containerOf(context), msg);
        };
      }
    });
  }

  @override
  void dispose() {
    _pageCtrl.dispose();
    (_wsManager as dynamic)?.disconnect();
    super.dispose();
  }

  void _jumpToTab(int index, List<_TabDef> tabs) {
    _pageCtrl.animateToPage(
      index,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
    );
    ref.read(activeTabProvider.notifier).state = tabs[index].id;
  }

  @override
  Widget build(BuildContext context) {
    final station = ref.watch(activeStationProvider);
    final activeTab = ref.watch(activeTabProvider);
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;

    final tabs = _tabsForStation(station);

    // If station changed, rebuild page controller at page 0.
    if (station?.id != _lastStationId) {
      _lastStationId = station?.id;
      // Can't call jumpToPage during build — schedule it.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_pageCtrl.hasClients) {
          _pageCtrl.jumpToPage(0);
          if (mounted) {
            ref.read(activeTabProvider.notifier).state =
                tabs.isNotEmpty ? tabs[0].id : 'dashboard';
          }
        }
      });
    }

    final activeIndex =
        tabs.indexWhere((t) => t.id == activeTab).clamp(0, tabs.length - 1);

    return Scaffold(
      body: Column(
        children: [
          const ConnectionBanner(),

          // ── Top toolbar ───────────────────────────────────────────────
          Container(
            height: isUltraWide ? 36 : 44,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              border: Border(bottom: BorderSide(color: theme.dividerColor)),
            ),
            child: Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.arrow_back, size: 18),
                  onPressed: () => context.go('/'),
                  padding: EdgeInsets.zero,
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                  tooltip: 'Back to stations',
                ),
                const SizedBox(width: 8),
                Icon(Icons.radio,
                    color: theme.colorScheme.primary, size: 16),
                const SizedBox(width: 6),
                Text(station?.name ?? 'Station',
                    style: theme.textTheme.labelLarge),
                const SizedBox(width: 8),
                if (station?.status == StationStatus.running)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 1),
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
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                ),
              ],
            ),
          ),

          // ── Swipeable page content ────────────────────────────────────
          Expanded(
            child: Stack(
              children: [
                PageView.builder(
                  controller: _pageCtrl,
                  itemCount: tabs.length,
                  onPageChanged: (index) {
                    if (!mounted) return;
                    ref.read(activeTabProvider.notifier).state =
                        tabs[index].id;
                  },
                  itemBuilder: (context, index) {
                    final tabId = tabs[index].id;
                    return StationTabScreen(
                      stationId: station?.id ?? '',
                      tab: tabId,
                    );
                  },
                ),
                const SubtitleOverlay(),
                const ToastOverlay(),
              ],
            ),
          ),

          const NowPlayingBanner(),

          // ── Bottom tab strip — scrollable, stays in sync with PageView ─
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
                final isActive = index == activeIndex;
                return GestureDetector(
                  onTap: () => _jumpToTab(index, tabs),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12),
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
    // Default to radio tabs — never fall through to FTB for unknown stations.
    if (station == null) return _radioTabs;

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
  _TabDef('dashboard', '🏠', 'On Air'),
  _TabDef('feeds', '📡', 'Feeds'),
  _TabDef('events', '📋', 'Events'),
];

// Neikos uses the same basic radio layout until its tabs are built out.
const _neikosTabs = _radioTabs;

/// FTB Dashboard Tab — primary game overview.
/// Designed for 1920×480: uses a wide horizontal layout with metrics row,
/// event columns, and driver result banner all visible at once.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';
import '../../widgets/metric_card.dart';
import '../../widgets/stat_bar.dart';

class FTBDashboardTab extends ConsumerWidget {
  const FTBDashboardTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;

    if (!gs.hasGame) {
      return _NoGameView(gameState: gs);
    }

    final team = gs.playerTeam!;
    final budget = team['budget'] as Map<String, dynamic>? ?? {};
    final morale = (team['morale'] as num?)?.toDouble() ?? 50.0;
    final reputation = (team['reputation'] as num?)?.toDouble() ?? 50.0;
    final roster = team['roster'] as Map<String, dynamic>? ?? {};
    final drivers = roster['drivers'] as List<dynamic>? ?? [];

    if (isUltraWide) {
      return _UltraWideDashboard(
        gs: gs,
        team: team,
        budget: budget,
        morale: morale,
        reputation: reputation,
        drivers: drivers,
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PhaseHeader(gs: gs),
          const SizedBox(height: 12),
          _MetricsRow(budget: budget, morale: morale, reputation: reputation),
          const SizedBox(height: 12),
          _DriverBanner(drivers: drivers, gs: gs),
          const SizedBox(height: 12),
          _EventsSection(gs: gs),
        ],
      ),
    );
  }
}

/// Ultra-wide layout: 3-column horizontal arrangement.
class _UltraWideDashboard extends StatelessWidget {
  final dynamic gs;
  final Map<String, dynamic> team;
  final Map<String, dynamic> budget;
  final double morale;
  final double reputation;
  final List<dynamic> drivers;

  const _UltraWideDashboard({
    required this.gs,
    required this.team,
    required this.budget,
    required this.morale,
    required this.reputation,
    required this.drivers,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left column: Phase + Metrics + Drivers
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _PhaseHeader(gs: gs),
                const SizedBox(height: 8),
                _MetricsRow(
                    budget: budget,
                    morale: morale,
                    reputation: reputation),
                const SizedBox(height: 8),
                Expanded(
                  child: _DriverBanner(drivers: drivers, gs: gs),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),

          // Divider
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 12),

          // Right column: Events
          Expanded(
            flex: 3,
            child: _EventsSection(gs: gs),
          ),
        ],
      ),
    );
  }
}

class _PhaseHeader extends StatelessWidget {
  final dynamic gs;
  const _PhaseHeader({required this.gs});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final phase = (gs.phase as String?) ?? 'development';
    final dateStr = (gs.dateStr as String?) ?? '--/--';
    final tick = gs.tick as int? ?? 0;
    final season = gs.seasonNumber as int? ?? 0;

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: _phaseColor(phase).withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            humanizeToken(phase),
            style: TextStyle(
              color: _phaseColor(phase),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(width: 10),
        Text('Day $dateStr',
            style: theme.textTheme.bodySmall),
        const SizedBox(width: 10),
        Text('Tick $tick',
            style: theme.textTheme.labelSmall),
        if (season > 0) ...[
          const SizedBox(width: 10),
          Text('Season $season',
              style: theme.textTheme.labelSmall),
        ],
      ],
    );
  }

  Color _phaseColor(String phase) {
    switch (phase) {
      case 'race_weekend':
        return const Color(0xFFf87171);
      case 'offseason':
        return const Color(0xFF60a5fa);
      default:
        return const Color(0xFF34d399);
    }
  }
}

class _MetricsRow extends StatelessWidget {
  final Map<String, dynamic> budget;
  final double morale;
  final double reputation;

  const _MetricsRow({
    required this.budget,
    required this.morale,
    required this.reputation,
  });

  @override
  Widget build(BuildContext context) {
    final cash = (budget['cash'] as num?)?.toDouble() ?? 0;
    final runway = (budget['runway_days'] as num?)?.toInt();

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        SizedBox(
          width: 140,
          child: MetricCard(
            label: 'Cash',
            value: formatMoney(cash),
            icon: Icons.account_balance_wallet,
            valueColor: cash > 0
                ? const Color(0xFF34d399)
                : const Color(0xFFf87171),
          ),
        ),
        SizedBox(
          width: 120,
          child: MetricCard(
            label: 'Morale',
            value: '${morale.toStringAsFixed(0)}%',
            icon: Icons.sentiment_satisfied_alt,
          ),
        ),
        SizedBox(
          width: 120,
          child: MetricCard(
            label: 'Reputation',
            value: '${reputation.toStringAsFixed(0)}',
            icon: Icons.star_outline,
          ),
        ),
        if (runway != null)
          SizedBox(
            width: 120,
            child: MetricCard(
              label: 'Runway',
              value: '$runway days',
              icon: Icons.timeline,
              valueColor: runway < 30
                  ? const Color(0xFFf87171)
                  : null,
            ),
          ),
      ],
    );
  }
}

class _DriverBanner extends StatelessWidget {
  final List<dynamic> drivers;
  final dynamic gs;

  const _DriverBanner({required this.drivers, required this.gs});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (drivers.isEmpty) {
      return Text('No drivers signed',
          style: theme.textTheme.bodySmall);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Drivers', style: theme.textTheme.labelMedium),
        const SizedBox(height: 4),
        ...drivers.take(4).map((d) {
          final driver = d as Map<String, dynamic>;
          final name = driver['name'] as String? ?? 'Unknown';
          final skill = (driver['skill'] as num?)?.toDouble() ?? 0;
          return Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              children: [
                SizedBox(
                  width: 80,
                  child: Text(name,
                      style: theme.textTheme.bodySmall,
                      overflow: TextOverflow.ellipsis),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: StatBar(
                    label: '',
                    value: skill,
                    showLabel: false,
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}

class _EventsSection extends StatelessWidget {
  final dynamic gs;
  const _EventsSection({required this.gs});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final events = gs.recentEvents as List<dynamic>? ?? [];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Recent Events', style: theme.textTheme.labelMedium),
        const SizedBox(height: 6),
        Expanded(
          child: events.isEmpty
              ? Center(
                  child: Text('No events yet',
                      style: theme.textTheme.bodySmall))
              : ListView.builder(
                  itemCount: events.length.clamp(0, 50),
                  itemBuilder: (context, index) {
                    final evt = events[index];
                    final summary = formatEventSummary(
                        evt is Map<String, dynamic> ? evt : {});
                    final category = (evt is Map<String, dynamic>
                            ? evt['category'] as String?
                            : null) ??
                        '';

                    return Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 5),
                      decoration: BoxDecoration(
                        border: Border(
                          bottom: BorderSide(
                            color: theme.dividerColor
                                .withValues(alpha: 0.3),
                          ),
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _categoryIcon(category),
                            size: 14,
                            color: theme.textTheme.bodySmall?.color,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              summary,
                              style: theme.textTheme.bodySmall,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  IconData _categoryIcon(String category) {
    switch (category.toLowerCase()) {
      case 'race_result':
        return Icons.flag;
      case 'sponsor_payment':
        return Icons.attach_money;
      case 'staff_change':
        return Icons.person;
      case 'team_fold':
        return Icons.warning;
      case 'team_spawned':
        return Icons.group_add;
      default:
        return Icons.circle;
    }
  }
}

/// Shown when no game is loaded — offers New Game / Load Game.
class _NoGameView extends ConsumerWidget {
  final dynamic gameState;
  const _NoGameView({required this.gameState});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.sports_motorsports,
              size: 48,
              color: theme.colorScheme.primary.withValues(alpha: 0.4)),
          const SizedBox(height: 16),
          Text('No Game Loaded',
              style: theme.textTheme.headlineMedium),
          const SizedBox(height: 8),
          Text('Start a new game or load a save',
              style: theme.textTheme.bodySmall),
          const SizedBox(height: 24),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ElevatedButton.icon(
                onPressed: () {
                  // TODO: Open new game wizard
                  ref.read(toastsProvider.notifier).show(
                      'New game wizard coming soon');
                },
                icon: const Icon(Icons.add, size: 18),
                label: const Text('New Game'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                onPressed: () {
                  // TODO: Open load game screen
                  ref.read(toastsProvider.notifier).show(
                      'Load game screen coming soon');
                },
                icon: const Icon(Icons.folder_open, size: 18),
                label: const Text('Load Game'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

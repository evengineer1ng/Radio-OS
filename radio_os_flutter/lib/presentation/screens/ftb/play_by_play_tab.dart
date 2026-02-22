/// FTB Play-by-Play Tab — live race standings, lap events, telemetry.
/// Optimised for 1920×480: wide horizontal split.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';

class PlayByPlayTab extends ConsumerWidget {
  const PlayByPlayTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);
    final pbp = gs.playByPlay;

    if (!gs.hasGame) {
      return Center(
          child: Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    if (!pbp.isLive) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.live_tv,
                size: 48,
                color: theme.colorScheme.primary.withValues(alpha: 0.3)),
            const SizedBox(height: 12),
            Text('No live race', style: theme.textTheme.bodyLarge),
            const SizedBox(height: 4),
            Text('Play-by-play activates during live race events',
                style: theme.textTheme.bodySmall),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left: Standings
          Expanded(
            flex: 3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: Color(0xFFf87171),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text('LIVE', style: TextStyle(
                      color: const Color(0xFFf87171),
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1,
                    )),
                    const SizedBox(width: 12),
                    Text(
                      'Lap ${pbp.currentLap}/${pbp.totalLaps}',
                      style: theme.textTheme.headlineSmall,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                // Standings table
                Expanded(
                  child: pbp.standings.isEmpty
                      ? Center(
                          child: Text('Waiting for data...',
                              style: theme.textTheme.bodySmall))
                      : ListView.builder(
                          itemCount: pbp.standings.length,
                          itemBuilder: (context, index) {
                            return _StandingRow(
                              position: index + 1,
                              entry: pbp.standings[index],
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 12),
          // Right: Live events feed
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Race Events', style: theme.textTheme.headlineSmall),
                const SizedBox(height: 8),
                Expanded(
                  child: pbp.liveEvents.isEmpty
                      ? Center(
                          child: Text('No events yet',
                              style: theme.textTheme.bodySmall))
                      : ListView.builder(
                          reverse: true,
                          itemCount: pbp.liveEvents.length,
                          itemBuilder: (context, index) {
                            final evt = pbp.liveEvents[index];
                            final text = evt is Map
                                ? (evt['text'] as String? ??
                                    evt['description'] as String? ??
                                    evt.toString())
                                : evt.toString();
                            return Padding(
                              padding:
                                  const EdgeInsets.only(bottom: 4),
                              child: Text(text,
                                  style: theme.textTheme.bodySmall),
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StandingRow extends StatelessWidget {
  final int position;
  final dynamic entry;

  const _StandingRow({
    required this.position,
    required this.entry,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    String driver = '';
    String team = '';
    String gap = '';

    if (entry is Map) {
      driver = entry['driver'] as String? ??
          entry['name'] as String? ??
          '';
      team = entry['team'] as String? ?? '';
      gap = entry['gap'] as String? ??
          entry['gap_to_leader'] as String? ??
          '';
    } else if (entry is List && entry.length >= 2) {
      driver = entry[0].toString();
      team = entry.length > 1 ? entry[1].toString() : '';
    }

    final posColor = position <= 3
        ? const Color(0xFFfbbf24)
        : theme.textTheme.bodySmall?.color;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: theme.dividerColor.withValues(alpha: 0.3),
          ),
        ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 28,
            child: Text(
              'P$position',
              style: TextStyle(
                color: posColor,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(driver,
                style: theme.textTheme.bodySmall,
                overflow: TextOverflow.ellipsis),
          ),
          Expanded(
            flex: 2,
            child: Text(team,
                style: theme.textTheme.labelSmall,
                overflow: TextOverflow.ellipsis),
          ),
          SizedBox(
            width: 60,
            child: Text(gap,
                style: theme.textTheme.labelSmall,
                textAlign: TextAlign.right),
          ),
        ],
      ),
    );
  }
}

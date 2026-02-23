/// FTB Race Ops Tab — race day flow, qualifying, strategy.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/api/game_api_client.dart';
import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';

class RaceOpsTab extends ConsumerWidget {
  const RaceOpsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);

    if (!gs.hasGame) {
      return Center(
          child: Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    final raceDay = gs.raceDay;
    final phase = raceDay?['phase'] as String? ?? 'idle';

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Race day phase indicator
          Row(
            children: [
              Icon(Icons.flag, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: 8),
              Text('Race Day', style: theme.textTheme.headlineSmall),
              const SizedBox(width: 12),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: _phaseColor(phase).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  humanizeToken(phase),
                  style: TextStyle(
                    color: _phaseColor(phase),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Phase-specific content
          Expanded(child: _buildPhaseContent(context, ref, phase, raceDay)),
        ],
      ),
    );
  }

  Widget _buildPhaseContent(
      BuildContext context, WidgetRef ref, String phase, Map<String, dynamic>? raceDay) {
    final theme = Theme.of(context);

    switch (phase) {
      case 'idle':
        return Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.event_available,
                  size: 48,
                  color: theme.colorScheme.primary.withValues(alpha: 0.3)),
              const SizedBox(height: 12),
              Text('No active race',
                  style: theme.textTheme.bodyLarge),
              const SizedBox(height: 4),
              Text('Advance time to reach the next race weekend',
                  style: theme.textTheme.bodySmall),
            ],
          ),
        );

      case 'pre_race_prompt':
        return Center(
          child: Container(
            padding: const EdgeInsets.all(24),
            constraints: const BoxConstraints(maxWidth: 400),
            decoration: BoxDecoration(
              color: theme.cardColor,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: theme.dividerColor),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Race Weekend',
                    style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text('Watch the race live or simulate?',
                    style: theme.textTheme.bodyMedium),
                const SizedBox(height: 20),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    ElevatedButton.icon(
                      onPressed: () => _respond(ref, true),
                      icon: const Icon(Icons.visibility, size: 18),
                      label: const Text('Watch Live'),
                    ),
                    const SizedBox(width: 12),
                    OutlinedButton.icon(
                      onPressed: () => _respond(ref, false),
                      icon: const Icon(Icons.fast_forward, size: 18),
                      label: const Text('Simulate'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );

      case 'race_running':
      case 'quali_running':
        return Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 36,
                height: 36,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
              const SizedBox(height: 12),
              Text(
                phase == 'quali_running'
                    ? 'Qualifying in progress...'
                    : 'Race in progress...',
                style: theme.textTheme.bodyLarge,
              ),
              const SizedBox(height: 4),
              Text('Switch to the PBP tab for live standings',
                  style: theme.textTheme.bodySmall),
            ],
          ),
        );

      default:
        return Center(
          child: Text('Race phase: ${humanizeToken(phase)}',
              style: theme.textTheme.bodyMedium),
        );
    }
  }

  Future<void> _respond(WidgetRef ref, bool watchLive) async {
    final api = ref.read(gameApiProvider);
    final gs = ref.read(gameStateProvider.notifier);
    await api.raceDayRespond(watchLive);
    gs.refresh();
  }

  Color _phaseColor(String phase) {
    if (phase.contains('running')) return const Color(0xFFf87171);
    if (phase.contains('ready') || phase.contains('prompt')) {
      return const Color(0xFFfbbf24);
    }
    if (phase.contains('complete')) return const Color(0xFF34d399);
    return const Color(0xFF666666);
  }
}

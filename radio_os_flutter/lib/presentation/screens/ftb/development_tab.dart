/// FTB Development Tab — R&D projects, technology tree.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';
import '../../widgets/stat_bar.dart';

class DevelopmentTab extends ConsumerWidget {
  const DevelopmentTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);

    if (!gs.hasGame) {
      return Center(
          child: Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    final team = gs.playerTeam!;
    final rdProjects = team['rd_projects'] as List<dynamic>? ?? [];
    final infra = team['infrastructure'] as Map<String, dynamic>? ?? {};

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left: Active R&D projects
          Expanded(
            flex: 3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('R&D Projects', style: theme.textTheme.headlineSmall),
                const SizedBox(height: 8),
                Expanded(
                  child: rdProjects.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.science,
                                  size: 36,
                                  color: theme.colorScheme.primary
                                      .withValues(alpha: 0.3)),
                              const SizedBox(height: 8),
                              Text('No active R&D projects',
                                  style: theme.textTheme.bodySmall),
                            ],
                          ),
                        )
                      : ListView.builder(
                          itemCount: rdProjects.length,
                          itemBuilder: (context, index) {
                            final p = rdProjects[index]
                                as Map<String, dynamic>? ??
                                {};
                            final name =
                                p['name'] as String? ?? 'Project';
                            final progress =
                                (p['progress'] as num?)?.toDouble() ??
                                    0;
                            final cost = p['budget'] as num?;

                            return Container(
                              padding: const EdgeInsets.all(10),
                              margin: const EdgeInsets.only(bottom: 6),
                              decoration: BoxDecoration(
                                color: theme.cardColor,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                    color: theme.dividerColor),
                              ),
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(name,
                                            style: theme
                                                .textTheme.labelLarge),
                                      ),
                                      if (cost != null)
                                        Text(formatMoney(cost),
                                            style: theme
                                                .textTheme.labelSmall),
                                    ],
                                  ),
                                  const SizedBox(height: 6),
                                  StatBar(
                                    label: 'Progress',
                                    value: progress,
                                    color: theme.colorScheme.primary,
                                  ),
                                ],
                              ),
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
          // Right: Infrastructure
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Infrastructure', style: theme.textTheme.headlineSmall),
                const SizedBox(height: 8),
                if (infra.isEmpty)
                  Text('No infrastructure data',
                      style: theme.textTheme.bodySmall)
                else
                  Expanded(
                    child: ListView(
                      children: infra.entries.map((e) {
                        final level =
                            (e.value is num ? e.value as num : 0)
                                .toDouble();
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: StatBar(
                            label: humanizeToken(e.key),
                            value: level,
                          ),
                        );
                      }).toList(),
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

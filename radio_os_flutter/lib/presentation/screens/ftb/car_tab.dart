/// FTB Car Tab — parts inventory, car setup, performance stats.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';
import '../../widgets/stat_bar.dart';

class CarTab extends ConsumerWidget {
  const CarTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);

    if (!gs.hasGame) {
      return Center(
          child: Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    final team = gs.playerTeam!;
    final car = team['car'] as Map<String, dynamic>? ?? {};
    final parts = team['parts_inventory'] as List<dynamic>? ?? [];
    final marketplace = gs.partsMarketplace;

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left: Current car stats
          Expanded(
            flex: 2,
            child: _CarStats(car: car),
          ),
          const SizedBox(width: 12),
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 12),
          // Middle: Equipped parts
          Expanded(
            flex: 2,
            child: _PartsList(title: 'Equipped Parts', parts: parts),
          ),
          const SizedBox(width: 12),
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 12),
          // Right: Marketplace
          Expanded(
            flex: 2,
            child:
                _PartsList(title: 'Marketplace', parts: marketplace),
          ),
        ],
      ),
    );
  }
}

class _CarStats extends StatelessWidget {
  final Map<String, dynamic> car;
  const _CarStats({required this.car});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final stats = <String, double>{};

    // Extract car stat fields
    for (final key in [
      'speed',
      'downforce',
      'reliability',
      'fuel_efficiency',
      'tyre_wear'
    ]) {
      final v = car[key];
      if (v is num) stats[key] = v.toDouble();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Car Performance', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        if (stats.isEmpty)
          Text('No car data available', style: theme.textTheme.bodySmall)
        else
          ...stats.entries.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: StatBar(
                  label: humanizeToken(e.key),
                  value: e.value,
                ),
              )),
      ],
    );
  }
}

class _PartsList extends StatelessWidget {
  final String title;
  final List<dynamic> parts;
  const _PartsList({required this.title, required this.parts});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Expanded(
          child: parts.isEmpty
              ? Center(
                  child:
                      Text('No parts', style: theme.textTheme.bodySmall))
              : ListView.builder(
                  itemCount: parts.length,
                  itemBuilder: (context, index) {
                    final part = parts[index];
                    if (part is! Map<String, dynamic>) {
                      return const SizedBox.shrink();
                    }
                    final name = part['name'] as String? ??
                        part['part_type'] as String? ??
                        'Unknown';
                    final quality =
                        (part['quality'] as num?)?.toDouble() ?? 0;
                    final cost = part['cost'] as num?;

                    return Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 6),
                      margin: const EdgeInsets.only(bottom: 3),
                      decoration: BoxDecoration(
                        color: theme.cardColor,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: theme.dividerColor),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            flex: 2,
                            child: Text(humanizeToken(name),
                                style: theme.textTheme.bodySmall,
                                overflow: TextOverflow.ellipsis),
                          ),
                          Expanded(
                            flex: 2,
                            child: StatBar(
                                label: '',
                                value: quality,
                                showLabel: false),
                          ),
                          if (cost != null) ...[
                            const SizedBox(width: 8),
                            Text(formatMoney(cost),
                                style: theme.textTheme.labelSmall),
                          ],
                        ],
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}

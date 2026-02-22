/// Generic Tab — a placeholder for tabs that haven't been fully implemented yet.
/// Displays the tab name and any widget_update data for that key.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';

class GenericTab extends ConsumerWidget {
  final String tabId;
  const GenericTab({super.key, required this.tabId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final gs = ref.watch(gameStateProvider);
    final widgetData = ref.watch(widgetUpdatesProvider)[tabId];

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            humanizeToken(tabId),
            style: theme.textTheme.headlineMedium,
          ),
          const SizedBox(height: 8),
          if (widgetData != null) ...[
            Text('Widget data available',
                style: theme.textTheme.labelSmall),
            const SizedBox(height: 8),
            Expanded(
              child: SingleChildScrollView(
                child: SelectableText(
                  _prettyPrint(widgetData),
                  style: TextStyle(
                    fontFamily: 'JetBrainsMono',
                    fontSize: 11,
                    color: theme.textTheme.bodySmall?.color,
                  ),
                ),
              ),
            ),
          ] else ...[
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.construction,
                        size: 48,
                        color: theme.colorScheme.primary
                            .withValues(alpha: 0.2)),
                    const SizedBox(height: 12),
                    Text(
                      '${humanizeToken(tabId)} tab',
                      style: theme.textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      gs.hasGame
                          ? 'Detailed view coming soon'
                          : 'Load a game to see data',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _prettyPrint(dynamic data) {
    if (data is Map) {
      return data.entries
          .map((e) => '${e.key}: ${e.value}')
          .join('\n');
    }
    return data.toString();
  }
}

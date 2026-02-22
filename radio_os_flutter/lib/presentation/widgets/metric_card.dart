/// Metric card — displays a label, value, and optional trend.
/// Mirrors MetricDisplay.svelte.
library;

import 'package:flutter/material.dart';

class MetricCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData? icon;
  final Color? valueColor;
  final String? trend; // "+5%", "-12", etc.
  final bool compact;

  const MetricCard({
    super.key,
    required this.label,
    required this.value,
    this.icon,
    this.valueColor,
    this.trend,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;

    if (compact) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: theme.textTheme.labelSmall,
              overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text(value,
              style: theme.textTheme.labelLarge
                  ?.copyWith(color: valueColor ?? colors.primary),
              overflow: TextOverflow.ellipsis),
        ],
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: 14, color: colors.primary),
                const SizedBox(width: 6),
              ],
              Expanded(
                child: Text(label,
                    style: theme.textTheme.labelSmall,
                    overflow: TextOverflow.ellipsis),
              ),
              if (trend != null)
                Text(trend!,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: trend!.startsWith('+')
                          ? const Color(0xFF34d399)
                          : trend!.startsWith('-')
                              ? const Color(0xFFf87171)
                              : null,
                    )),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: theme.textTheme.headlineMedium
                ?.copyWith(color: valueColor ?? colors.primary),
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

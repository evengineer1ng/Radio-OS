/// Stat bar — horizontal progress bar with colour gradient.
/// Mirrors StatBar.svelte.
library;

import 'package:flutter/material.dart';

class StatBar extends StatelessWidget {
  final String label;
  final double value; // 0.0 – 1.0  (or 0–100, controlled by [maxValue])
  final double maxValue;
  final Color? color;
  final Color? backgroundColor;
  final bool showLabel;
  final bool showValue;

  const StatBar({
    super.key,
    required this.label,
    required this.value,
    this.maxValue = 100,
    this.color,
    this.backgroundColor,
    this.showLabel = true,
    this.showValue = true,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pct = (value / maxValue).clamp(0.0, 1.0);
    final barColor = color ?? _colorForPct(pct);

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (showLabel)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: theme.textTheme.labelSmall),
              if (showValue)
                Text('${(pct * 100).toStringAsFixed(0)}%',
                    style: theme.textTheme.labelSmall
                        ?.copyWith(color: barColor)),
            ],
          ),
        if (showLabel) const SizedBox(height: 3),
        Container(
          height: 6,
          decoration: BoxDecoration(
            color: backgroundColor ?? theme.dividerColor.withValues(alpha: 0.3),
            borderRadius: BorderRadius.circular(3),
          ),
          child: FractionallySizedBox(
            alignment: Alignment.centerLeft,
            widthFactor: pct,
            child: Container(
              decoration: BoxDecoration(
                color: barColor,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Color _colorForPct(double pct) {
    if (pct >= 0.7) return const Color(0xFF34d399);
    if (pct >= 0.4) return const Color(0xFFfbbf24);
    return const Color(0xFFf87171);
  }
}

/// Station card helpers — logo emblem builder shared across layouts.
library;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../config/constants.dart';
import '../../../data/models/station.dart';
import '../../../domain/providers.dart';

/// Stateless helper: just exposes [buildEmblem] for the cinematic carousel.
class StationCard extends ConsumerWidget {
  final Station station;
  final bool isSelected;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTap;

  const StationCard({
    super.key,
    required this.station,
    this.isSelected = false,
    this.onTap,
    this.onDoubleTap,
  });

  // ── Static emblem builder used by the carousel ───────────────────────────
  static Widget buildEmblem(Station station, Color accent, double size) {
    final logoUrl = _logoUrl(station);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size * 0.18),
        color: accent.withValues(alpha: 0.08),
        border: Border.all(color: accent.withValues(alpha: 0.25), width: 1.5),
        boxShadow: [
          BoxShadow(
              color: accent.withValues(alpha: 0.15),
              blurRadius: size * 0.3,
              spreadRadius: 1),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(size * 0.18),
        child: CachedNetworkImage(
          imageUrl: logoUrl,
          fit: BoxFit.cover,
          errorWidget: (_, __, ___) => Center(
            child: Icon(
              _iconForModule(station.moduleType),
              color: accent,
              size: size * 0.45,
            ),
          ),
          placeholder: (_, __) => Center(
            child: Icon(
              _iconForModule(station.moduleType),
              color: accent.withValues(alpha: 0.4),
              size: size * 0.45,
            ),
          ),
        ),
      ),
    );
  }

  static String _logoUrl(Station station) {
    return 'http://${ApiConstants.defaultHost}:${ApiConstants.shellPort}'
        '/api/stations/${station.id}/logo';
  }

  static IconData _iconForModule(StationModuleType type) {
    return switch (type) {
      StationModuleType.ftb => Icons.sports_motorsports,
      StationModuleType.oracleKingdom => Icons.castle,
      StationModuleType.neikos => Icons.pets,
      StationModuleType.radio => Icons.radio,
    };
  }

  // ── Widget form (kept for any non-carousel usage) ────────────────────────
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final accent = theme.colorScheme.primary;

    return GestureDetector(
      onTap: onTap,
      onDoubleTap: onDoubleTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected ? theme.cardColor : theme.scaffoldBackgroundColor,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected
                ? accent.withValues(alpha: 0.6)
                : theme.dividerColor,
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Row(
          children: [
            buildEmblem(station, accent, 56),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(station.name,
                      style: theme.textTheme.labelLarge,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  if (station.category.isNotEmpty)
                    Text(station.category,
                        style: theme.textTheme.labelSmall,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

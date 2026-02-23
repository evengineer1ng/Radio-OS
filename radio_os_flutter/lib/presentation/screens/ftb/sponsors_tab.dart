/// FTB Sponsors Tab — sponsor offers and active deals.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';

class SponsorsTab extends ConsumerWidget {
  const SponsorsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);

    if (!gs.hasGame) {
      return Center(
          child: Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    final sponsorships = gs.sponsorships;
    final active = sponsorships['active'] as List<dynamic>? ?? [];
    final offers = sponsorships['offers'] as List<dynamic>? ?? [];

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Active sponsors
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.handshake,
                        size: 16, color: theme.colorScheme.primary),
                    const SizedBox(width: 6),
                    Text('Active Sponsors',
                        style: theme.textTheme.headlineSmall),
                  ],
                ),
                const SizedBox(height: 8),
                Expanded(
                  child: active.isEmpty
                      ? Center(
                          child: Text('No active sponsors',
                              style: theme.textTheme.bodySmall))
                      : ListView.builder(
                          itemCount: active.length,
                          itemBuilder: (context, i) {
                            final s =
                                active[i] as Map<String, dynamic>? ?? {};
                            return _SponsorCard(
                                sponsor: s, isOffer: false);
                          },
                        ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 12),
          // Offers
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.local_offer,
                        size: 16, color: theme.colorScheme.primary),
                    const SizedBox(width: 6),
                    Text('Sponsor Offers',
                        style: theme.textTheme.headlineSmall),
                  ],
                ),
                const SizedBox(height: 8),
                Expanded(
                  child: offers.isEmpty
                      ? Center(
                          child: Text('No pending offers',
                              style: theme.textTheme.bodySmall))
                      : ListView.builder(
                          itemCount: offers.length,
                          itemBuilder: (context, i) {
                            final s =
                                offers[i] as Map<String, dynamic>? ?? {};
                            return _SponsorCard(
                              sponsor: s,
                              isOffer: true,
                              offerIndex: i,
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

class _SponsorCard extends ConsumerWidget {
  final Map<String, dynamic> sponsor;
  final bool isOffer;
  final int? offerIndex;

  const _SponsorCard({
    required this.sponsor,
    required this.isOffer,
    this.offerIndex,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final name = sponsor['name'] as String? ??
        sponsor['sponsor_name'] as String? ??
        'Unknown';
    final payment = sponsor['payment'] as num? ??
        sponsor['amount'] as num? ??
        0;
    final duration = sponsor['duration'] as num?;

    return Container(
      padding: const EdgeInsets.all(10),
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(name, style: theme.textTheme.labelLarge),
              ),
              Text(formatMoney(payment),
                  style: TextStyle(
                    color: theme.colorScheme.primary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  )),
            ],
          ),
          if (duration != null) ...[
            const SizedBox(height: 2),
            Text('${duration.toInt()} seasons',
                style: theme.textTheme.labelSmall),
          ],
          if (isOffer && offerIndex != null) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                SizedBox(
                  height: 28,
                  child: ElevatedButton(
                    onPressed: () async {
                      final api = ref.read(gameApiProvider);
                      final gs = ref.read(gameStateProvider.notifier);
                      await api.acceptSponsor(offerIndex!);
                      gs.refresh();
                    },
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      textStyle: const TextStyle(fontSize: 11),
                    ),
                    child: const Text('Accept'),
                  ),
                ),
                const SizedBox(width: 6),
                SizedBox(
                  height: 28,
                  child: OutlinedButton(
                    onPressed: () async {
                      final api = ref.read(gameApiProvider);
                      final gs = ref.read(gameStateProvider.notifier);
                      await api.declineSponsor(offerIndex!);
                      gs.refresh();
                    },
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      textStyle: const TextStyle(fontSize: 11),
                    ),
                    child: const Text('Decline'),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

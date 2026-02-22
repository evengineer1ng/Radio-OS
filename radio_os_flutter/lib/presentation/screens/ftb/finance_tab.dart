/// FTB Finance Tab — budget, income/expenses, prize money.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';
import '../../widgets/metric_card.dart';

class FinanceTab extends ConsumerWidget {
  const FinanceTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);

    if (!gs.hasGame) {
      return Center(
          child: Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    final team = gs.playerTeam!;
    final budget = team['budget'] as Map<String, dynamic>? ?? {};
    final cash = (budget['cash'] as num?)?.toDouble() ?? 0;
    final income = (budget['income'] as num?)?.toDouble() ?? 0;
    final expenses = (budget['expenses'] as num?)?.toDouble() ?? 0;
    final prizeMoney = (budget['prize_money'] as num?)?.toDouble() ?? 0;
    final runwayDays = (budget['runway_days'] as num?)?.toInt();

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left: Key metrics
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Financial Overview',
                    style: theme.textTheme.headlineSmall),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    SizedBox(
                      width: 160,
                      child: MetricCard(
                        label: 'Cash Balance',
                        value: formatMoney(cash),
                        icon: Icons.account_balance_wallet,
                        valueColor: cash > 0
                            ? const Color(0xFF34d399)
                            : const Color(0xFFf87171),
                      ),
                    ),
                    SizedBox(
                      width: 140,
                      child: MetricCard(
                        label: 'Income / Day',
                        value: formatMoney(income),
                        icon: Icons.trending_up,
                        valueColor: const Color(0xFF34d399),
                      ),
                    ),
                    SizedBox(
                      width: 140,
                      child: MetricCard(
                        label: 'Expenses / Day',
                        value: formatMoney(expenses),
                        icon: Icons.trending_down,
                        valueColor: const Color(0xFFf87171),
                      ),
                    ),
                    SizedBox(
                      width: 140,
                      child: MetricCard(
                        label: 'Prize Money',
                        value: formatMoney(prizeMoney),
                        icon: Icons.emoji_events,
                      ),
                    ),
                    if (runwayDays != null)
                      SizedBox(
                        width: 140,
                        child: MetricCard(
                          label: 'Runway',
                          value: '$runwayDays days',
                          icon: Icons.timeline,
                          valueColor: runwayDays < 30
                              ? const Color(0xFFf87171)
                              : null,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 12),
          // Right: Transaction history (from recent events)
          Expanded(
            flex: 3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Recent Transactions',
                    style: theme.textTheme.headlineSmall),
                const SizedBox(height: 8),
                Expanded(
                  child: _TransactionList(events: gs.recentEvents),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TransactionList extends StatelessWidget {
  final List<dynamic> events;
  const _TransactionList({required this.events});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final financialEvents = events
        .whereType<Map<String, dynamic>>()
        .where((e) {
      final cat = (e['category'] as String? ?? '').toLowerCase();
      return cat.contains('payment') ||
          cat.contains('transaction') ||
          cat.contains('prize') ||
          cat.contains('salary') ||
          cat.contains('sponsor');
    }).toList();

    if (financialEvents.isEmpty) {
      return Center(
        child: Text('No financial events',
            style: theme.textTheme.bodySmall),
      );
    }

    return ListView.builder(
      itemCount: financialEvents.length,
      itemBuilder: (context, index) {
        final evt = financialEvents[index];
        final data = evt['data'] as Map<String, dynamic>? ?? {};
        final amount = data['amount'] as num?;
        final desc = formatEventSummary(evt);

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
              Expanded(
                child: Text(desc,
                    style: theme.textTheme.bodySmall,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              ),
              if (amount != null)
                Text(
                  formatMoney(amount),
                  style: TextStyle(
                    color: amount > 0
                        ? const Color(0xFF34d399)
                        : const Color(0xFFf87171),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

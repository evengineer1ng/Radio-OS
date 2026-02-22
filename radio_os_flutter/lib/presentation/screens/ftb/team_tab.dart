/// FTB Team Tab — driver roster, engineer stats, staff contracts.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';
import '../../widgets/stat_bar.dart';

class TeamTab extends ConsumerWidget {
  const TeamTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gs = ref.watch(gameStateProvider);
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;

    if (!gs.hasGame) {
      return Center(
          child:
              Text('No game loaded', style: theme.textTheme.bodySmall));
    }

    final team = gs.playerTeam!;
    final roster = team['roster'] as Map<String, dynamic>? ?? {};
    final drivers = roster['drivers'] as List<dynamic>? ?? [];
    final engineers = roster['engineers'] as List<dynamic>? ?? [];
    final staff = [...drivers, ...engineers];

    if (isUltraWide) {
      // Horizontal split: drivers left, engineers right
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: _StaffList(
              title: 'Drivers',
              members: drivers,
              icon: Icons.sports_motorsports,
            ),
          ),
          Container(width: 1, color: theme.dividerColor),
          Expanded(
            child: _StaffList(
              title: 'Engineers',
              members: engineers,
              icon: Icons.engineering,
            ),
          ),
        ],
      );
    }

    return _StaffList(
      title: 'Team Roster',
      members: staff,
      icon: Icons.group,
    );
  }
}

class _StaffList extends StatelessWidget {
  final String title;
  final List<dynamic> members;
  final IconData icon;

  const _StaffList({
    required this.title,
    required this.members,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Text(title, style: theme.textTheme.headlineSmall),
              const SizedBox(width: 8),
              Text('(${members.length})',
                  style: theme.textTheme.labelSmall),
            ],
          ),
          const SizedBox(height: 8),
          Expanded(
            child: members.isEmpty
                ? Center(
                    child: Text('No members',
                        style: theme.textTheme.bodySmall))
                : ListView.builder(
                    itemCount: members.length,
                    itemBuilder: (context, index) {
                      final member =
                          members[index] as Map<String, dynamic>? ?? {};
                      return _MemberCard(member: member);
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _MemberCard extends StatelessWidget {
  final Map<String, dynamic> member;
  const _MemberCard({required this.member});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final name = member['name'] as String? ?? 'Unknown';
    final role = member['role'] as String? ??
        member['type'] as String? ??
        'staff';
    final skill = (member['skill'] as num?)?.toDouble() ?? 0;
    final morale = (member['morale'] as num?)?.toDouble() ?? 50;
    final salary = member['salary'] as num?;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      margin: const EdgeInsets.only(bottom: 4),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Row(
        children: [
          // Name + role
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: theme.textTheme.labelLarge,
                    overflow: TextOverflow.ellipsis),
                Text(humanizeToken(role),
                    style: theme.textTheme.labelSmall),
              ],
            ),
          ),
          // Skill bar
          Expanded(
            flex: 2,
            child: StatBar(label: 'Skill', value: skill),
          ),
          const SizedBox(width: 8),
          // Morale bar
          Expanded(
            flex: 2,
            child: StatBar(label: 'Morale', value: morale),
          ),
          // Salary
          if (salary != null) ...[
            const SizedBox(width: 8),
            Text(formatMoney(salary),
                style: theme.textTheme.labelSmall),
          ],
        ],
      ),
    );
  }
}

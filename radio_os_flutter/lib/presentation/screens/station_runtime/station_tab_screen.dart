/// Station Tab Screen — routes to the correct tab widget based on the
/// current station type and active tab ID.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/station.dart';
import '../../../domain/providers.dart';
import '../ftb/dashboard_tab.dart';
import '../ftb/team_tab.dart';
import '../ftb/car_tab.dart';
import '../ftb/development_tab.dart';
import '../ftb/race_ops_tab.dart';
import '../ftb/play_by_play_tab.dart';
import '../ftb/finance_tab.dart';
import '../ftb/sponsors_tab.dart';
import '../ftb/generic_tab.dart';
import 'radio_dashboard_tab.dart';

class StationTabScreen extends ConsumerWidget {
  final String stationId;
  final String tab;

  const StationTabScreen({
    super.key,
    required this.stationId,
    required this.tab,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Update active tab provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(activeTabProvider.notifier).state = tab;
    });

    final station = ref.watch(activeStationProvider);
    final moduleType = station?.moduleType ?? StationModuleType.radio;

    // Radio and any other non-game stations get the radio dashboard
    if (moduleType == StationModuleType.radio) {
      return _radioTab(tab);
    }

    // Game stations (FTB, Oracle Kingdom, Neikos) keep their full tab routing
    if (moduleType == StationModuleType.ftb) {
      return _ftbTab(tab);
    }

    // Oracle Kingdom and Neikos fall through to generic for now
    return GenericTab(tabId: tab);
  }

  Widget _radioTab(String tab) {
    switch (tab) {
      case 'dashboard':
        return const RadioDashboardTab();
      default:
        return GenericTab(tabId: tab);
    }
  }

  Widget _ftbTab(String tab) {
    switch (tab) {
      case 'dashboard':
        return const FTBDashboardTab();
      case 'team':
        return const TeamTab();
      case 'car':
        return const CarTab();
      case 'development':
        return const DevelopmentTab();
      case 'raceops':
        return const RaceOpsTab();
      case 'pbp':
        return const PlayByPlayTab();
      case 'finance':
        return const FinanceTab();
      case 'sponsors':
        return const SponsorsTab();
      default:
        return GenericTab(tabId: tab);
    }
  }
}

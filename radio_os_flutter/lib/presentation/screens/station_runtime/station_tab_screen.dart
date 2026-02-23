/// Station Tab Screen — resolves a tab ID to the correct widget.
/// Used as the page builder inside StationShell's PageView.
/// Tab/station-type routing lives here; navigation lives in StationShell.
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
    final station = ref.watch(activeStationProvider);
    final moduleType = station?.moduleType ?? StationModuleType.radio;

    switch (moduleType) {
      case StationModuleType.ftb:
        return _ftbTab(tab);
      case StationModuleType.oracleKingdom:
        // OK tabs not yet implemented — fall through to generic.
        return GenericTab(tabId: tab);
      case StationModuleType.radio:
      case StationModuleType.neikos:
        return _radioTab(tab);
    }
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


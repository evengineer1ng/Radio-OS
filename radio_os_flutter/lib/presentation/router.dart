/// GoRouter configuration for Radio OS.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'screens/station_browser/station_browser_screen.dart';
import 'screens/station_runtime/station_shell.dart';
import 'screens/station_runtime/station_tab_screen.dart';
import 'screens/settings/settings_screen.dart';

final radioRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const StationBrowserScreen(),
    ),
    ShellRoute(
      builder: (context, state, child) => StationShell(child: child),
      routes: [
        GoRoute(
          path: '/station/:id',
          redirect: (context, state) {
            final id = state.pathParameters['id'];
            return '/station/$id/dashboard';
          },
        ),
        GoRoute(
          path: '/station/:id/:tab',
          builder: (context, state) {
            final id = state.pathParameters['id']!;
            final tab = state.pathParameters['tab'] ?? 'dashboard';
            return StationTabScreen(stationId: id, tab: tab);
          },
        ),
      ],
    ),
    GoRoute(
      path: '/settings',
      redirect: (context, state) => '/settings/connection',
    ),
    GoRoute(
      path: '/settings/:section',
      builder: (context, state) {
        final section = state.pathParameters['section'] ?? 'general';
        return SettingsScreen(section: section);
      },
    ),
  ],
);

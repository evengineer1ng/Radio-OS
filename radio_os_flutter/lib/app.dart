/// Radio OS Flutter — Application root widget.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'config/themes.dart';
import 'presentation/router.dart';
import 'presentation/screens/settings/settings_screen.dart';
import 'presentation/widgets/audio_cli_overlay.dart';

class RadioOsApp extends ConsumerWidget {
  const RadioOsApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeName = ref.watch(themeNameProvider);
    final colors = RadioColors.forName(themeName);
    final themeData = buildRadioTheme(colors);

    return MaterialApp.router(
      title: 'Radio OS',
      debugShowCheckedModeBanner: false,
      theme: themeData,
      routerConfig: radioRouter,
      builder: (context, child) {
        return Stack(
          children: [
            child ?? const SizedBox.shrink(),
            const AudioCliOverlay(),
          ],
        );
      },
    );
  }
}

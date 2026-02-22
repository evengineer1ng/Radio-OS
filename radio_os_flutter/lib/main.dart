/// Radio OS Flutter — Application entry point.
///
/// Runs on a 1920×480 ultra-wide bar display (Raspberry Pi 5).
/// Wraps the entire app in a Riverpod [ProviderScope].
///
/// Set [_simulatePiDisplay] to true during macOS dev to force the
/// window to 1920×480 so you can preview the ultra-wide layout.
library;

import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

/// Flip to `true` on macOS to force the window to 1920×480.
const bool _simulatePiDisplay = false;

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // On Linux/Pi the window manager will give us 1920×480 automatically.
  // On macOS we can optionally force it for testing.
  if (_simulatePiDisplay && Platform.isMacOS) {
    // Request a fixed window size from the macOS embedder.
    // This uses the same channel Flutter's own window-size plugin uses.
    const channel = MethodChannel('flutter/windowManagement');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      channel.invokeMethod('setWindowFrame', {
        'x': 0.0,
        'y': 100.0,
        'width': 1920.0,
        'height': 480.0,
      }).catchError((_) {
        // Channel not available — ignore (will just use default size).
      });
    });
  }

  runApp(
    const ProviderScope(
      child: RadioOsApp(),
    ),
  );
}

/// Radio OS — Theme definitions.
///
/// Dark-first, information-dense, terminal-inspired aesthetic with accent
/// colours.  Ported from shell_bookmark.py's 6 themes and the Svelte CSS
/// custom properties.
library;

import 'package:flutter/material.dart';

// ---------------------------------------------------------------------------
// Colour palettes
// ---------------------------------------------------------------------------

class RadioColors {
  final Color bgPrimary;
  final Color bgSecondary;
  final Color bgCard;
  final Color border;
  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;
  final Color accent;
  final Color success;
  final Color warning;
  final Color danger;
  final Color info;

  const RadioColors({
    required this.bgPrimary,
    required this.bgSecondary,
    required this.bgCard,
    required this.border,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.accent,
    required this.success,
    required this.warning,
    required this.danger,
    required this.info,
  });

  // -- Built-in palettes --------------------------------------------------

  static const dark = RadioColors(
    bgPrimary: Color(0xFF0e0e0e),
    bgSecondary: Color(0xFF121212),
    bgCard: Color(0xFF1a1a1a),
    border: Color(0xFF2a2a2a),
    textPrimary: Color(0xFFe8e8e8),
    textSecondary: Color(0xFF9a9a9a),
    textMuted: Color(0xFF666666),
    accent: Color(0xFF4cc9f0),
    success: Color(0xFF34d399),
    warning: Color(0xFFfbbf24),
    danger: Color(0xFFf87171),
    info: Color(0xFF60a5fa),
  );

  static const nord = RadioColors(
    bgPrimary: Color(0xFF2e3440),
    bgSecondary: Color(0xFF3b4252),
    bgCard: Color(0xFF434c5e),
    border: Color(0xFF4c566a),
    textPrimary: Color(0xFFeceff4),
    textSecondary: Color(0xFFd8dee9),
    textMuted: Color(0xFF7b88a1),
    accent: Color(0xFF88c0d0),
    success: Color(0xFFa3be8c),
    warning: Color(0xFFebcb8b),
    danger: Color(0xFFbf616a),
    info: Color(0xFF81a1c1),
  );

  static const dracula = RadioColors(
    bgPrimary: Color(0xFF282a36),
    bgSecondary: Color(0xFF21222c),
    bgCard: Color(0xFF343746),
    border: Color(0xFF44475a),
    textPrimary: Color(0xFFf8f8f2),
    textSecondary: Color(0xFFc0c0c0),
    textMuted: Color(0xFF6272a4),
    accent: Color(0xFFbd93f9),
    success: Color(0xFF50fa7b),
    warning: Color(0xFFf1fa8c),
    danger: Color(0xFFff5555),
    info: Color(0xFF8be9fd),
  );

  static const monokai = RadioColors(
    bgPrimary: Color(0xFF272822),
    bgSecondary: Color(0xFF1e1f1c),
    bgCard: Color(0xFF3e3d32),
    border: Color(0xFF49483e),
    textPrimary: Color(0xFFf8f8f2),
    textSecondary: Color(0xFFc0c0c0),
    textMuted: Color(0xFF75715e),
    accent: Color(0xFF66d9ef),
    success: Color(0xFFa6e22e),
    warning: Color(0xFFe6db74),
    danger: Color(0xFFf92672),
    info: Color(0xFFae81ff),
  );

  static const solarized = RadioColors(
    bgPrimary: Color(0xFF002b36),
    bgSecondary: Color(0xFF073642),
    bgCard: Color(0xFF0a4050),
    border: Color(0xFF586e75),
    textPrimary: Color(0xFFfdf6e3),
    textSecondary: Color(0xFF93a1a1),
    textMuted: Color(0xFF657b83),
    accent: Color(0xFF268bd2),
    success: Color(0xFF859900),
    warning: Color(0xFFb58900),
    danger: Color(0xFFdc322f),
    info: Color(0xFF2aa198),
  );

  static RadioColors forName(String name) {
    switch (name) {
      case 'nord':
        return nord;
      case 'dracula':
        return dracula;
      case 'monokai':
        return monokai;
      case 'solarized':
        return solarized;
      case 'dark':
      default:
        return dark;
    }
  }
}

// ---------------------------------------------------------------------------
// ThemeData builder
// ---------------------------------------------------------------------------

ThemeData buildRadioTheme(RadioColors c) {
  return ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: c.bgPrimary,
    colorScheme: ColorScheme.dark(
      surface: c.bgSecondary,
      primary: c.accent,
      secondary: c.accent,
      error: c.danger,
      onSurface: c.textPrimary,
      onPrimary: c.bgPrimary,
    ),
    cardColor: c.bgCard,
    dividerColor: c.border,
    appBarTheme: AppBarTheme(
      backgroundColor: c.bgSecondary,
      foregroundColor: c.textPrimary,
      elevation: 0,
    ),
    bottomNavigationBarTheme: BottomNavigationBarThemeData(
      backgroundColor: c.bgSecondary,
      selectedItemColor: c.accent,
      unselectedItemColor: c.textMuted,
    ),
    iconTheme: IconThemeData(color: c.textSecondary, size: 28),
    textTheme: _textTheme(c),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: c.bgCard,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: c.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: c.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: c.accent, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: c.accent,
        foregroundColor: c.bgPrimary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: c.accent,
        side: BorderSide(color: c.accent.withValues(alpha: 0.5)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      ),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.border),
      ),
      textStyle: TextStyle(color: c.textPrimary, fontSize: 12),
    ),
  );
}

TextTheme _textTheme(RadioColors c) {
  return TextTheme(
    headlineLarge: TextStyle(
        fontSize: 32,
        fontWeight: FontWeight.w800,
        color: c.textPrimary,
        letterSpacing: -0.3),
    headlineMedium: TextStyle(
        fontSize: 26,
        fontWeight: FontWeight.w700,
        color: c.textPrimary,
        letterSpacing: -0.2),
    headlineSmall: TextStyle(
        fontSize: 22,
        fontWeight: FontWeight.w600,
        color: c.textPrimary),
    bodyLarge: TextStyle(fontSize: 20, color: c.textPrimary),
    bodyMedium: TextStyle(fontSize: 18, color: c.textPrimary),
    bodySmall: TextStyle(fontSize: 16, color: c.textSecondary),
    labelLarge: TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: c.textPrimary),
    labelMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w500,
        color: c.textSecondary),
    labelSmall: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w500,
        color: c.textMuted,
        letterSpacing: 0.5),
  );
}

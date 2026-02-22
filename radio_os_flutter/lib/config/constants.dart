/// Radio OS — API constants, timeouts, and default configuration values.
library;

class ApiConstants {
  ApiConstants._();

  /// Default backend host (localhost on the Pi).
  static const String defaultHost = '127.0.0.1';

  /// Shell server port (web_server.py).
  static const int shellPort = 7800;

  /// Game / plugin server port (ftb_web_server.py).
  static const int gamePort = 7555;

  /// Base URLs derived from host + port.
  static String shellBaseUrl([String host = defaultHost]) =>
      'http://$host:$shellPort';

  static String gameBaseUrl([String host = defaultHost]) =>
      'http://$host:$gamePort';

  /// WebSocket URLs.
  static String audioWsUrl(String stationId, [String host = defaultHost]) =>
      'ws://$host:$shellPort/ws/audio/$stationId';

  static String eventWsUrl(String stationId, [String host = defaultHost]) =>
      'ws://$host:$shellPort/ws/station/$stationId';

  static String directPluginWsUrl([String host = defaultHost]) =>
      'ws://$host:$gamePort/ws/live';

  /// Timeouts.
  static const Duration httpTimeout = Duration(seconds: 10);
  static const Duration wsReconnectDelay = Duration(seconds: 2);
  static const int httpMaxRetries = 3;

  /// Polling intervals.
  static const Duration gameStatePollInterval = Duration(seconds: 3);
  static const Duration audioStatePollInterval = Duration(seconds: 5);
  static const Duration stationStatusPollInterval = Duration(seconds: 10);
  static const Duration healthCheckInterval = Duration(seconds: 5);
}

/// Audio mixing defaults — mirrors webAudio.ts constants.
class AudioDefaults {
  AudioDefaults._();

  static const double masterVolume = 0.8;
  static const double voiceVolume = 1.0;
  static const double musicVolume = 0.10;
  static const double musicDuckVolume = 0.02;
  static const double engineVolume = 0.12;
  static const double crashVolume = 0.30;
  static const double crowdVolume = 0.25;
  static const double ambientVolume = 0.08;
  static const double sfxVolume = 0.30;
}

/// Layout breakpoints for the ultra-wide 1920×480 display.
class LayoutBreakpoints {
  LayoutBreakpoints._();

  /// Primary target: 1920×480 ultra-wide bar display.
  static const double ultraWideMinWidth = 1600;

  /// Standard widescreen (HDMI debug monitor).
  static const double wideMinWidth = 1280;

  /// Compact (7" 800×480 RPi touchscreen).
  static const double compactMinWidth = 640;

  /// Minimum touch target size.
  static const double minTouchTarget = 44.0;
}

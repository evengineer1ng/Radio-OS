/// Host configuration service — persists the Radio OS backend host
/// so the app can point at localhost (Pi), a Mac, or any network server.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/constants.dart';

const _kHostKey = 'radio_os_backend_host';
const _kPortOverrideKey = 'radio_os_shell_port';

class HostConfig {
  final String host;
  final int shellPort;

  const HostConfig({
    this.host = ApiConstants.defaultHost,
    this.shellPort = ApiConstants.shellPort,
  });

  /// The full shell base URL derived from current config.
  String get shellBaseUrl => 'http://$host:$shellPort';

  /// Game port is always shellPort-245 by Radio OS convention
  /// (7800 shell → 7555 game), but only matters if game server
  /// is on the same host.
  int get gamePort => ApiConstants.gamePort;
  String get gameBaseUrl => 'http://$host:$gamePort';

  HostConfig copyWith({String? host, int? shellPort}) => HostConfig(
        host: host ?? this.host,
        shellPort: shellPort ?? this.shellPort,
      );

  /// Convenience presets shown in the UI.
  static const presets = [
    _HostPreset('This Pi (localhost)', '127.0.0.1'),
    _HostPreset('Mac / PC on LAN', ''),   // user fills in
    _HostPreset('Custom', ''),
  ];
}

class _HostPreset {
  final String label;
  final String host;
  const _HostPreset(this.label, this.host);
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

final hostConfigProvider =
    StateNotifierProvider<HostConfigNotifier, HostConfig>((ref) {
  return HostConfigNotifier();
});

class HostConfigNotifier extends StateNotifier<HostConfig> {
  HostConfigNotifier() : super(const HostConfig()) {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final host = prefs.getString(_kHostKey) ?? ApiConstants.defaultHost;
    final port = prefs.getInt(_kPortOverrideKey) ?? ApiConstants.shellPort;
    state = HostConfig(host: host, shellPort: port);
  }

  Future<void> setHost(String host) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kHostKey, host.trim());
    state = state.copyWith(host: host.trim());
  }

  Future<void> setShellPort(int port) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_kPortOverrideKey, port);
    state = state.copyWith(shellPort: port);
  }

  Future<void> reset() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kHostKey);
    await prefs.remove(_kPortOverrideKey);
    state = const HostConfig();
  }
}

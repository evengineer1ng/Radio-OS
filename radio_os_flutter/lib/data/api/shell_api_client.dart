/// Shell API client — port 7800 REST endpoints from web_server.py.
library;

import '../../config/constants.dart';
import '../models/station.dart';
import 'http_client.dart';

class ShellApiClient {
  late final RadioHttpClient _http;

  ShellApiClient({
    String host = ApiConstants.defaultHost,
    int port = ApiConstants.shellPort,
  }) {
    final baseUrl = 'http://$host:$port';
    _http = RadioHttpClient(baseUrl: baseUrl);
  }

  // ── Health ──────────────────────────────────────────────────
  Future<bool> healthCheck() async {
    final res = await _http.get('/api/health');
    return res['status'] == 'ok';
  }

  // ── Stations ────────────────────────────────────────────────
  Future<List<Station>> listStations() async {
    final res = await _http.get('/api/stations');
    final items = res['items'] as List<dynamic>? ??
        res['stations'] as List<dynamic>? ??
        (res.containsKey('error') ? [] : [res]);

    // If response was a plain list, items key was injected by http_client.
    if (res.containsKey('items') && res['items'] is List) {
      return (res['items'] as List)
          .map((e) => Station.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return items
        .whereType<Map<String, dynamic>>()
        .map((e) => Station.fromJson(e))
        .toList();
  }

  Future<Map<String, dynamic>> launchStation(String id) =>
      _http.post('/api/stations/$id/launch');

  Future<Map<String, dynamic>> stopStation(String id) =>
      _http.post('/api/stations/$id/stop');

  Future<Map<String, dynamic>> getStationStatus(String id) =>
      _http.get('/api/stations/$id/status');

  Future<String> getStationLog(String id, {int lines = 100}) async {
    final res =
        await _http.get('/api/stations/$id/log', queryParams: {'lines': lines});
    return res['log'] as String? ?? res['data']?.toString() ?? '';
  }

  Future<Map<String, dynamic>> getStationManifest(String id) =>
      _http.get('/api/stations/$id/manifest');

  Future<Map<String, dynamic>> saveStationManifest(
          String id, Map<String, dynamic> manifest) =>
      _http.put('/api/stations/$id/manifest', data: manifest);

  Future<Map<String, dynamic>> createStation(
          String stationId, Map<String, dynamic> manifest) =>
      _http.post('/api/stations/create',
          data: {'station_id': stationId, 'manifest': manifest});

  Future<Map<String, dynamic>> deleteStation(String id) =>
      _http.delete('/api/stations/$id');

  // ── Settings ────────────────────────────────────────────────
  Future<Map<String, dynamic>> getSettings() => _http.get('/api/settings');
  Future<Map<String, dynamic>> saveSettings(Map<String, dynamic> data) =>
      _http.post('/api/settings', data: data);

  Future<Map<String, dynamic>> getGeneralSettings() =>
      _http.get('/api/settings/general');
  Future<Map<String, dynamic>> updateGeneralSettings(
          Map<String, dynamic> data) =>
      _http.post('/api/settings/general', data: data);

  Future<Map<String, dynamic>> getModelSettings() =>
      _http.get('/api/settings/models');
  Future<Map<String, dynamic>> updateModelSettings(
          Map<String, dynamic> data) =>
      _http.post('/api/settings/models', data: data);

  Future<Map<String, dynamic>> getVoiceSettings() =>
      _http.get('/api/settings/voices');
  Future<Map<String, dynamic>> updateVoiceSettings(
          Map<String, dynamic> data) =>
      _http.post('/api/settings/voices', data: data);

  Future<Map<String, dynamic>> getEnvironmentSettings() =>
      _http.get('/api/settings/environment');
  Future<Map<String, dynamic>> updateEnvironmentSettings(
          Map<String, dynamic> data) =>
      _http.post('/api/settings/environment', data: data);

  // ── Plugins & Voices ────────────────────────────────────────
  Future<Map<String, dynamic>> listPlugins() => _http.get('/api/plugins');

  Future<List<String>> listMetaPlugins() async {
    final res = await _http.get('/api/meta_plugins');
    final items = res['items'] as List<dynamic>? ?? [];
    return items.map((e) => e.toString()).toList();
  }

  Future<List<String>> listVoices() async {
    final res = await _http.get('/api/voices');
    final items = res['items'] as List<dynamic>? ??
        res['voices'] as List<dynamic>? ??
        [];
    return items.map((e) => e.toString()).toList();
  }

  // ── Feeds ───────────────────────────────────────────────────
  Future<Map<String, dynamic>> listFeeds(String stationId) =>
      _http.get('/api/stations/$stationId/feeds');

  Future<Map<String, dynamic>> toggleFeed(String stationId, String feed) =>
      _http.post('/api/stations/$stationId/feeds/$feed/toggle');

  Future<Map<String, dynamic>> configureFeed(
          String stationId, String feed, Map<String, dynamic> cfg) =>
      _http.put('/api/stations/$stationId/feeds/$feed/config', data: cfg);

  // ── Plugin commands ─────────────────────────────────────────
  Future<Map<String, dynamic>> pluginCommand(
          String stationId, String plugin, Map<String, dynamic> cmd) =>
      _http.post('/api/stations/$stationId/plugin/$plugin/command', data: cmd);

  // ── Storage ─────────────────────────────────────────────────
  Future<Map<String, dynamic>> getStorageInfo() =>
      _http.get('/api/storage/info');
  Future<Map<String, dynamic>> clearLogs() =>
      _http.post('/api/storage/clear_logs');
  Future<Map<String, dynamic>> vacuumDatabases() =>
      _http.post('/api/storage/vacuum_databases');

  // ── Pucks (ESP32 wireless audio nodes) ─────────────────────
  Future<List<dynamic>> getPucks() async {
    final res = await _http.get('/api/pucks');
    // HTTP client wraps lists as {'items': [...]}
    if (res.containsKey('items') && res['items'] is List) {
      return res['items'] as List<dynamic>;
    }
    // puck_manager returns {'group_volume': N, 'pucks': {'1': {...}, ...}}
    final pucksVal = res['pucks'];
    if (pucksVal is Map) {
      return pucksVal.values.toList();
    }
    if (pucksVal is List) return pucksVal;
    return [];
  }

  Future<Map<String, dynamic>> setPuckVolume(int nodeId, int volume) =>
      _http.post('/api/pucks/$nodeId/volume', data: {'volume': volume});

  Future<Map<String, dynamic>> setGroupVolume(int volume) =>
      _http.post('/api/pucks/group_volume', data: {'volume': volume});

  Future<Map<String, dynamic>> setPuckMute(int nodeId, {required bool muted}) =>
      _http.post('/api/pucks/$nodeId/mute', data: {'muted': muted});

  Future<Map<String, dynamic>> muteAllPucks({required bool muted}) =>
      _http.post('/api/pucks/mute_all', data: {'muted': muted});

  Future<Map<String, dynamic>> setPuckRoute(int nodeId, String route) =>
      _http.post('/api/pucks/$nodeId/route', data: {'route': route});

  Future<Map<String, dynamic>> sendPuckTestTone(int nodeId) =>
      _http.post('/api/pucks/$nodeId/test_tone');

  // ── Station logo URL ────────────────────────────────────────
  String stationLogoUrl(String stationId) =>
      '${_http.baseUrl}/api/stations/$stationId/logo';

  // ── Bluetooth ───────────────────────────────────────────────
  Future<Map<String, dynamic>> getBluetoothDevices() =>
      _http.get('/api/bluetooth/devices');

  Future<Map<String, dynamic>> getBluetoothStatus() =>
      _http.get('/api/bluetooth/status');

  Future<Map<String, dynamic>> bluetoothPower({required bool on}) =>
      _http.post('/api/bluetooth/power', data: {'on': on});

  Future<Map<String, dynamic>> bluetoothScan({bool enable = true}) =>
      _http.post('/api/bluetooth/scan', data: {'enable': enable});

  Future<Map<String, dynamic>> bluetoothPair(String mac) =>
      _http.post('/api/bluetooth/pair', data: {'mac': mac});

  Future<Map<String, dynamic>> bluetoothConnect(String mac) =>
      _http.post('/api/bluetooth/connect', data: {'mac': mac});

  Future<Map<String, dynamic>> bluetoothDisconnect(String mac) =>
      _http.post('/api/bluetooth/disconnect', data: {'mac': mac});

  Future<Map<String, dynamic>> bluetoothRemove(String mac) =>
      _http.post('/api/bluetooth/remove', data: {'mac': mac});

  void dispose() => _http.dispose();
}

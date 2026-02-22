/// Game API client — port 7555 REST endpoints from ftb_web_server.py.
library;

import '../../config/constants.dart';
import '../models/game_state.dart';
import 'http_client.dart';

class GameApiClient {
  late final RadioHttpClient _http;

  GameApiClient({String host = ApiConstants.defaultHost}) {
    _http = RadioHttpClient(baseUrl: ApiConstants.gameBaseUrl(host));
  }

  // ── Core state ──────────────────────────────────────────────
  Future<FTBGameState> getGameState() async {
    final res = await _http.get('/api/state');
    if (res.containsKey('error')) {
      return const FTBGameState(status: 'no_controller');
    }
    return FTBGameState.fromJson(res);
  }

  Future<FTBGameState> getFullGameState() async {
    try {
      final res = await _http.get('/api/full_state');
      if (res.containsKey('error')) return getGameState();
      return FTBGameState.fromJson(res);
    } catch (_) {
      return getGameState();
    }
  }

  Future<String> getSubtitle() async {
    final res = await _http.get('/api/subtitle');
    return res['text'] as String? ?? '';
  }

  Future<Map<String, dynamic>> getAudioState() =>
      _http.get('/api/audio_state');

  Future<Map<String, dynamic>> getUIScreen() => _http.get('/api/ui_screen');
  Future<Map<String, dynamic>> getSnapshot() => _http.get('/api/snapshot');

  // ── Commands ────────────────────────────────────────────────
  Future<Map<String, dynamic>> sendCommand(Map<String, dynamic> cmd) =>
      _http.post('/api/command', data: cmd);

  Future<Map<String, dynamic>> sendUICommand(
          String action, Map<String, dynamic> payload) =>
      _http.post('/api/ui_command',
          data: {'action': action, 'payload': payload});

  Future<Map<String, dynamic>> navigate(String screen, {int? step}) {
    final body = <String, dynamic>{'target': screen};
    if (step != null) body['step'] = step;
    return _http.post('/api/navigate', data: body);
  }

  // ── Tick / Simulation ───────────────────────────────────────
  Future<Map<String, dynamic>> tick({int n = 1, bool batch = false}) =>
      _http.post('/api/tick', data: {'n': n, 'batch': batch});

  // ── Race Day ────────────────────────────────────────────────
  Future<Map<String, dynamic>> raceDayRespond(bool watchLive) =>
      _http.post('/api/race_day/respond',
          data: {'watch_live': watchLive});

  Future<Map<String, dynamic>> raceDayStartLive({int speed = 10}) =>
      _http.post('/api/race_day/start_live', data: {'speed': speed});

  Future<Map<String, dynamic>> raceDayPause() =>
      _http.post('/api/race_day/pause', data: {'paused': true});

  Future<Map<String, dynamic>> raceDayResume() =>
      _http.post('/api/race_day/pause', data: {'paused': false});

  Future<Map<String, dynamic>> raceDayComplete() =>
      _http.post('/api/race_day/complete');

  // ── Sponsors ────────────────────────────────────────────────
  Future<Map<String, dynamic>> acceptSponsor(int offerIndex) =>
      _http.post('/api/sponsor/accept', data: {'offer_index': offerIndex});

  Future<Map<String, dynamic>> declineSponsor(int offerIndex) =>
      _http.post('/api/sponsor/decline', data: {'offer_index': offerIndex});

  // ── Parts ───────────────────────────────────────────────────
  Future<Map<String, dynamic>> buyPart(String partId, double cost) =>
      _http.post('/api/parts/buy', data: {'part_id': partId, 'cost': cost});

  Future<Map<String, dynamic>> sellPart(String partId) =>
      _http.post('/api/parts/sell', data: {'part_id': partId});

  Future<Map<String, dynamic>> equipPart(String partId) =>
      _http.post('/api/parts/equip', data: {'part_id': partId});

  // ── Staff ───────────────────────────────────────────────────
  Future<Map<String, dynamic>> hireFreeAgent(String entityName,
          {int freeAgentId = 0}) =>
      _http.post('/api/staff/hire',
          data: {'entity_name': entityName, 'free_agent_id': freeAgentId});

  Future<Map<String, dynamic>> fireStaff(String entityName) =>
      _http.post('/api/staff/fire', data: {'entity_name': entityName});

  Future<Map<String, dynamic>> applyForJob(int listingId) =>
      _http.post('/api/staff/apply_job', data: {'listing_id': listingId});

  // ── R&D ─────────────────────────────────────────────────────
  Future<Map<String, dynamic>> startRD(String projectId,
          {double budget = 0}) =>
      _http.post('/api/rd/start',
          data: {'project_id': projectId, 'budget': budget});

  Future<Map<String, dynamic>> cancelRD(String projectId) =>
      _http.post('/api/rd/cancel', data: {'project_id': projectId});

  Future<List<dynamic>> fetchRDCatalog() async {
    final res = await _http.get('/api/rd_catalog');
    return res['catalog'] as List<dynamic>? ?? [];
  }

  // ── Infrastructure ──────────────────────────────────────────
  Future<Map<String, dynamic>> upgradeInfra(String facility,
          {int amount = 10}) =>
      _http.post('/api/infrastructure/upgrade',
          data: {'facility': facility, 'amount': amount});

  Future<Map<String, dynamic>> sellInfra(String facility) =>
      _http.post('/api/infrastructure/sell', data: {'facility': facility});

  // ── Promotion ───────────────────────────────────────────────
  Future<Map<String, dynamic>> applyPromotion(String opportunityId) =>
      _http.post('/api/promotion/apply',
          data: {'opportunity_id': opportunityId});

  Future<Map<String, dynamic>> declinePromotion(String opportunityId) =>
      _http.post('/api/promotion/decline',
          data: {'opportunity_id': opportunityId});

  // ── Save / Load ─────────────────────────────────────────────
  Future<Map<String, dynamic>> newGame(Map<String, dynamic> opts) =>
      _http.post('/api/new_game', data: opts);

  Future<Map<String, dynamic>> loadGame(String path) =>
      _http.post('/api/load_game', data: {'path': path});

  Future<Map<String, dynamic>> saveGame({String name = '', String path = ''}) =>
      _http.post('/api/save_game', data: {'name': name, 'path': path});

  Future<List<dynamic>> fetchSaves() async {
    final res = await _http.get('/api/saves');
    return res['saves'] as List<dynamic>? ?? [];
  }

  Future<Map<String, dynamic>> checkAutosave() =>
      _http.get('/api/check_autosave');

  void dispose() => _http.dispose();
}

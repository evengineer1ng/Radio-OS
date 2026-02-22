/// Riverpod providers — all shared state for the Radio OS Flutter app.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/constants.dart';
import '../config/host_config.dart';
import '../data/api/game_api_client.dart';
import '../data/api/shell_api_client.dart';
import '../data/api/ws_manager.dart';
import '../data/models/event.dart';
import '../data/models/game_state.dart';
import '../data/models/station.dart';

// Re-export so other files can import from providers.dart
export '../config/host_config.dart' show HostConfig, HostConfigNotifier, hostConfigProvider;

// ═══════════════════════════════════════════════════════════════════════════
// Singleton service providers — rebuild when host changes
// ═══════════════════════════════════════════════════════════════════════════

final shellApiProvider = Provider<ShellApiClient>((ref) {
  final cfg = ref.watch(hostConfigProvider);
  final client = ShellApiClient(host: cfg.host, port: cfg.shellPort);
  ref.onDispose(client.dispose);
  return client;
});

final gameApiProvider = Provider<GameApiClient>((ref) {
  final cfg = ref.watch(hostConfigProvider);
  final client = GameApiClient(host: cfg.host);
  ref.onDispose(client.dispose);
  return client;
});

final wsManagerProvider = Provider<RadioWebSocketManager>((ref) {
  final cfg = ref.watch(hostConfigProvider);
  final mgr = RadioWebSocketManager(host: cfg.host, shellPort: cfg.shellPort);
  ref.onDispose(mgr.dispose);
  return mgr;
});

// ═══════════════════════════════════════════════════════════════════════════
// Connection state
// ═══════════════════════════════════════════════════════════════════════════

enum ConnectionState { disconnected, connecting, connected }

final connectionStateProvider =
    StateProvider<ConnectionState>((ref) => ConnectionState.disconnected);

final audioConnectedProvider = StateProvider<bool>((ref) => false);
final eventConnectedProvider = StateProvider<bool>((ref) => false);

// ═══════════════════════════════════════════════════════════════════════════
// Station list & selection
// ═══════════════════════════════════════════════════════════════════════════

final stationsProvider =
    StateNotifierProvider<StationListNotifier, List<Station>>((ref) {
  return StationListNotifier(ref);
});

class StationListNotifier extends StateNotifier<List<Station>> {
  final Ref _ref;
  Timer? _pollTimer;

  StationListNotifier(this._ref) : super([]) {
    _startPolling();
  }

  Future<void> refresh() async {
    try {
      final api = _ref.read(shellApiProvider);
      final stations = await api.listStations();

      // Merge with running status
      final runningRes = await api.getSettings(); // we just use the station list
      // For each station, check if running by querying status
      final updated = <Station>[];
      for (final s in stations) {
        try {
          final statusRes = await api.getStationStatus(s.id);
          final isRunning = statusRes['status'] == 'running';
          updated.add(s.copyWith(
            status: isRunning ? StationStatus.running : StationStatus.stopped,
            pid: (statusRes['pid'] as num?)?.toInt(),
            uptimeSec: (statusRes['uptime_sec'] as num?)?.toInt(),
            webPort: (statusRes['web_port'] as num?)?.toInt(),
          ));
        } catch (_) {
          updated.add(s);
        }
      }
      state = updated;
      _ref.read(connectionStateProvider.notifier).state =
          ConnectionState.connected;
    } catch (_) {
      _ref.read(connectionStateProvider.notifier).state =
          ConnectionState.disconnected;
    }
  }

  void _startPolling() {
    refresh();
    _pollTimer = Timer.periodic(
        ApiConstants.stationStatusPollInterval, (_) => refresh());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }
}

final activeStationProvider = StateProvider<Station?>((ref) => null);

// ═══════════════════════════════════════════════════════════════════════════
// Game state (FTB / plugin)
// ═══════════════════════════════════════════════════════════════════════════

final gameStateProvider =
    StateNotifierProvider<GameStateNotifier, FTBGameState>((ref) {
  return GameStateNotifier(ref);
});

class GameStateNotifier extends StateNotifier<FTBGameState> {
  final Ref _ref;
  Timer? _pollTimer;

  GameStateNotifier(this._ref) : super(const FTBGameState()) {
    _startPolling();
  }

  void updateFromJson(Map<String, dynamic> json) {
    final newState = FTBGameState.fromJson(json);
    if (newState.status == 'busy') return; // skip lock-contended responses
    state = newState;
  }

  Future<void> refresh() async {
    final station = _ref.read(activeStationProvider);
    if (station == null || station.status != StationStatus.running) return;

    try {
      final api = _ref.read(gameApiProvider);
      final gs = await api.getFullGameState();
      if (gs.status != 'busy') {
        state = gs;
      }
    } catch (_) {}
  }

  void _startPolling() {
    _pollTimer = Timer.periodic(
        ApiConstants.gameStatePollInterval, (_) => refresh());
  }

  void reset() {
    state = const FTBGameState();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Subtitle
// ═══════════════════════════════════════════════════════════════════════════

final subtitleProvider = StateProvider<String>((ref) => '');

// ═══════════════════════════════════════════════════════════════════════════
// Notifications
// ═══════════════════════════════════════════════════════════════════════════

final notificationsProvider =
    StateNotifierProvider<NotificationNotifier, List<NotificationItem>>((ref) {
  return NotificationNotifier();
});

class NotificationNotifier extends StateNotifier<List<NotificationItem>> {
  NotificationNotifier() : super([]);

  void add(NotificationItem item) {
    state = [item, ...state].take(200).toList();
  }

  void markRead(String id) {
    state = [
      for (final n in state)
        if (n.id == id) n.copyWith(read: true) else n,
    ];
  }

  void markAllRead() {
    state = [for (final n in state) n.copyWith(read: true)];
  }

  int get unreadCount => state.where((n) => !n.read).length;
}

// ═══════════════════════════════════════════════════════════════════════════
// Now Playing
// ═══════════════════════════════════════════════════════════════════════════

class NowPlayingInfo {
  final String speaker;
  final String voiceId;
  final String textPreview;
  final bool isPlaying;

  const NowPlayingInfo({
    required this.speaker,
    this.voiceId = '',
    this.textPreview = '',
    this.isPlaying = true,
  });
}

final nowPlayingProvider = StateProvider<NowPlayingInfo?>((ref) => null);

// ═══════════════════════════════════════════════════════════════════════════
// Active tab
// ═══════════════════════════════════════════════════════════════════════════

final activeTabProvider = StateProvider<String>((ref) => 'dashboard');

// ═══════════════════════════════════════════════════════════════════════════
// Event log
// ═══════════════════════════════════════════════════════════════════════════

final eventLogProvider =
    StateNotifierProvider<EventLogNotifier, List<StationEvent>>((ref) {
  return EventLogNotifier();
});

class EventLogNotifier extends StateNotifier<List<StationEvent>> {
  EventLogNotifier() : super([]);

  void add(StationEvent event) {
    state = [event, ...state].take(500).toList();
  }

  void clear() {
    state = [];
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Toast messages
// ═══════════════════════════════════════════════════════════════════════════

class ToastMessage {
  final int id;
  final String text;
  final String type; // info, success, warning, error
  final DateTime timestamp;

  const ToastMessage({
    required this.id,
    required this.text,
    this.type = 'info',
    required this.timestamp,
  });
}

final toastsProvider =
    StateNotifierProvider<ToastNotifier, List<ToastMessage>>((ref) {
  return ToastNotifier();
});

class ToastNotifier extends StateNotifier<List<ToastMessage>> {
  int _nextId = 0;

  ToastNotifier() : super([]);

  void show(String text, {String type = 'info'}) {
    final id = ++_nextId;
    final toast = ToastMessage(
      id: id,
      text: text,
      type: type,
      timestamp: DateTime.now(),
    );
    state = [...state, toast];

    // Auto-dismiss after 5 seconds
    Future.delayed(const Duration(seconds: 5), () {
      state = state.where((t) => t.id != id).toList();
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Widget updates (keyed per widget, from WS widget_update events)
// ═══════════════════════════════════════════════════════════════════════════

final widgetUpdatesProvider =
    StateProvider<Map<String, dynamic>>((ref) => {});

// ═══════════════════════════════════════════════════════════════════════════
// Event dispatcher — routes incoming WebSocket events to the right providers
// ═══════════════════════════════════════════════════════════════════════════

void dispatchWsEvent(WidgetRef ref, Map<String, dynamic> msg) {
  _dispatchWsEventInternal(ref, msg);
}

void dispatchWsEventFromContainer(ProviderContainer container, Map<String, dynamic> msg) {
  final type = msg['type'] as String? ?? '';
  final data = msg['data'] as Map<String, dynamic>? ?? msg;

  switch (type) {
    case 'state_update':
      container.read(gameStateProvider.notifier).updateFromJson(data);
      break;
    case 'subtitle':
      container.read(subtitleProvider.notifier).state =
          data['text'] as String? ?? msg['text'] as String? ?? '';
      break;
    case 'notification':
      container.read(notificationsProvider.notifier).add(
            NotificationItem.fromJson(data),
          );
      break;
    case 'now_playing':
      container.read(nowPlayingProvider.notifier).state = NowPlayingInfo(
        speaker: data['speaker'] as String? ?? '',
        voiceId: data['voice'] as String? ?? '',
        textPreview: data['text'] as String? ?? '',
      );
      break;
    case 'widget_update':
      final key = data['widget_key'] as String? ?? '';
      if (key.isNotEmpty) {
        final current =
            Map<String, dynamic>.from(container.read(widgetUpdatesProvider));
        current[key] = data['data'] ?? data;
        container.read(widgetUpdatesProvider.notifier).state = current;
      }
      break;
    case 'navigate':
      // Handled by the navigation layer in the UI
      break;
    case 'switch_tab':
      final tab = data['tab'] as String?;
      if (tab != null) {
        container.read(activeTabProvider.notifier).state = tab;
      }
      break;
    case 'audio_event':
      // Handled by the audio engine
      break;
    case 'pong':
      break;
  }
}

void _dispatchWsEventInternal(WidgetRef ref, Map<String, dynamic> msg) {
  final type = msg['type'] as String? ?? '';
  final data = msg['data'] as Map<String, dynamic>? ?? msg;

  switch (type) {
    case 'state_update':
      ref.read(gameStateProvider.notifier).updateFromJson(data);
      break;
    case 'subtitle':
      ref.read(subtitleProvider.notifier).state =
          data['text'] as String? ?? msg['text'] as String? ?? '';
      break;
    case 'notification':
      ref.read(notificationsProvider.notifier).add(
            NotificationItem.fromJson(data),
          );
      break;
    case 'now_playing':
      ref.read(nowPlayingProvider.notifier).state = NowPlayingInfo(
        speaker: data['speaker'] as String? ?? '',
        voiceId: data['voice'] as String? ?? '',
        textPreview: data['text'] as String? ?? '',
      );
      break;
    case 'widget_update':
      final key = data['widget_key'] as String? ?? '';
      if (key.isNotEmpty) {
        final current =
            Map<String, dynamic>.from(ref.read(widgetUpdatesProvider));
        current[key] = data['data'] ?? data;
        ref.read(widgetUpdatesProvider.notifier).state = current;
      }
      break;
    case 'switch_tab':
      final tab = data['tab'] as String?;
      if (tab != null) {
        ref.read(activeTabProvider.notifier).state = tab;
      }
      break;
    case 'pong':
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Audio segment parser — extracts metadata + WAV from binary WS payload
// ═══════════════════════════════════════════════════════════════════════════

class AudioSegment {
  final AudioSegmentMeta meta;
  final Uint8List wavBytes;

  const AudioSegment({required this.meta, required this.wavBytes});
}

AudioSegment? parseAudioPayload(Uint8List payload) {
  if (payload.length < 4) return null;

  try {
    final metaLen =
        ByteData.sublistView(payload, 0, 4).getUint32(0, Endian.big);
    if (4 + metaLen > payload.length) return null;

    final metaJson = utf8.decode(payload.sublist(4, 4 + metaLen));
    final metaMap = jsonDecode(metaJson) as Map<String, dynamic>;
    final wavBytes = payload.sublist(4 + metaLen);

    return AudioSegment(
      meta: AudioSegmentMeta.fromJson(metaMap),
      wavBytes: Uint8List.fromList(wavBytes),
    );
  } catch (_) {
    return null;
  }
}

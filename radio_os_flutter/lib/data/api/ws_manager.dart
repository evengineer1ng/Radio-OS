/// WebSocket connection manager — handles audio + event streams with
/// auto-reconnect and exponential backoff.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../../config/constants.dart';

typedef BinaryMessageHandler = void Function(Uint8List data);
typedef JsonMessageHandler = void Function(Map<String, dynamic> msg);
typedef ConnectionStateHandler = void Function(bool connected);

class RadioWebSocketManager {
  final String _host;
  final int _shellPort;

  WebSocketChannel? _audioWs;
  WebSocketChannel? _eventWs;

  StreamSubscription? _audioSub;
  StreamSubscription? _eventSub;

  Timer? _audioReconnect;
  Timer? _eventReconnect;

  String? _activeStationId;
  bool _disposed = false;

  // Callbacks
  BinaryMessageHandler? onAudioMessage;
  JsonMessageHandler? onEventMessage;
  ConnectionStateHandler? onAudioConnectionChange;
  ConnectionStateHandler? onEventConnectionChange;

  RadioWebSocketManager({
    String host = ApiConstants.defaultHost,
    int shellPort = ApiConstants.shellPort,
  })  : _host = host,
        _shellPort = shellPort;

  String? get activeStationId => _activeStationId;
  bool get isAudioConnected => _audioWs != null;
  bool get isEventConnected => _eventWs != null;

  // ── Connect to a station ────────────────────────────────────
  void connectToStation(String stationId) {
    _activeStationId = stationId;
    _connectAudioWs(stationId);
    _connectEventWs(stationId);
  }

  void disconnect() {
    _activeStationId = null;
    _disconnectAudio();
    _disconnectEvent();
  }

  // ── Audio WebSocket ─────────────────────────────────────────
  void _connectAudioWs(String stationId) {
    _disconnectAudio();
    if (_disposed) return;

    final url = 'ws://$_host:$_shellPort/ws/audio/$stationId';
    try {
      _audioWs = WebSocketChannel.connect(Uri.parse(url));
      onAudioConnectionChange?.call(true);

      _audioSub = _audioWs!.stream.listen(
        (data) {
          if (data is List<int>) {
            onAudioMessage?.call(Uint8List.fromList(data));
          }
        },
        onError: (_) => _scheduleAudioReconnect(stationId),
        onDone: () => _scheduleAudioReconnect(stationId),
      );

      // Start keepalive ping
      _startPing(_audioWs!);
    } catch (_) {
      _scheduleAudioReconnect(stationId);
    }
  }

  void _disconnectAudio() {
    _audioReconnect?.cancel();
    _audioReconnect = null;
    _audioSub?.cancel();
    _audioSub = null;
    try {
      _audioWs?.sink.close();
    } catch (_) {}
    _audioWs = null;
    onAudioConnectionChange?.call(false);
  }

  void _scheduleAudioReconnect(String stationId) {
    _audioWs = null;
    onAudioConnectionChange?.call(false);
    if (_disposed || _activeStationId != stationId) return;
    _audioReconnect?.cancel();
    _audioReconnect = Timer(ApiConstants.wsReconnectDelay, () {
      if (_activeStationId == stationId) {
        _connectAudioWs(stationId);
      }
    });
  }

  // ── Event WebSocket ─────────────────────────────────────────
  void _connectEventWs(String stationId) {
    _disconnectEvent();
    if (_disposed) return;

    final url = 'ws://$_host:$_shellPort/ws/station/$stationId';
    try {
      _eventWs = WebSocketChannel.connect(Uri.parse(url));
      onEventConnectionChange?.call(true);

      _eventSub = _eventWs!.stream.listen(
        (data) {
          if (data is String) {
            try {
              final msg = jsonDecode(data) as Map<String, dynamic>;
              onEventMessage?.call(msg);
            } catch (_) {}
          }
        },
        onError: (_) => _scheduleEventReconnect(stationId),
        onDone: () => _scheduleEventReconnect(stationId),
      );
    } catch (_) {
      _scheduleEventReconnect(stationId);
    }
  }

  void _disconnectEvent() {
    _eventReconnect?.cancel();
    _eventReconnect = null;
    _eventSub?.cancel();
    _eventSub = null;
    try {
      _eventWs?.sink.close();
    } catch (_) {}
    _eventWs = null;
    onEventConnectionChange?.call(false);
  }

  void _scheduleEventReconnect(String stationId) {
    _eventWs = null;
    onEventConnectionChange?.call(false);
    if (_disposed || _activeStationId != stationId) return;
    _eventReconnect?.cancel();
    _eventReconnect = Timer(ApiConstants.wsReconnectDelay, () {
      if (_activeStationId == stationId) {
        _connectEventWs(stationId);
      }
    });
  }

  // ── Send messages ───────────────────────────────────────────
  void sendEventMessage(Map<String, dynamic> msg) {
    if (_eventWs != null) {
      _eventWs!.sink.add(jsonEncode(msg));
    }
  }

  void sendPing() {
    try {
      _eventWs?.sink.add(jsonEncode({'type': 'ping'}));
    } catch (_) {}
  }

  // ── Keepalive ───────────────────────────────────────────────
  void _startPing(WebSocketChannel ws) {
    // Simple keepalive — send "ping" text every 30s
    Timer.periodic(const Duration(seconds: 30), (timer) {
      if (_disposed || ws != _audioWs) {
        timer.cancel();
        return;
      }
      try {
        ws.sink.add('ping');
      } catch (_) {
        timer.cancel();
      }
    });
  }

  void dispose() {
    _disposed = true;
    disconnect();
  }
}

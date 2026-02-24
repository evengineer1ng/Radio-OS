/// Audio CLI Overlay — reactive fullscreen overlay for the 1920×480 Pi display.
///
/// Activates on "hey radio" (session_start event from /ws/audio_cli),
/// shows a semi-transparent dark scrim with:
///   LEFT column  → live user transcripts (scrolling history)
///   RIGHT column → LLM thinking bubble + transcribed responses
///
/// Dismisses on "thanks radio" (session_end event).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../config/host_config.dart';

// ═══════════════════════════════════════════════════════════════════════════
// State models
// ═══════════════════════════════════════════════════════════════════════════

/// A single exchange: user says something, LLM responds.
class AudioCliTurn {
  final String userText;
  final String llmText;
  final bool isComplete; // false while LLM is still thinking

  const AudioCliTurn({
    required this.userText,
    this.llmText = '',
    this.isComplete = false,
  });

  AudioCliTurn copyWith({String? llmText, bool? isComplete}) => AudioCliTurn(
        userText: userText,
        llmText: llmText ?? this.llmText,
        isComplete: isComplete ?? this.isComplete,
      );
}

class AudioCliState {
  final bool isActive;
  final List<AudioCliTurn> turns;
  final String partialTranscript;
  final bool isThinking;

  const AudioCliState({
    this.isActive = false,
    this.turns = const [],
    this.partialTranscript = '',
    this.isThinking = false,
  });

  AudioCliState copyWith({
    bool? isActive,
    List<AudioCliTurn>? turns,
    String? partialTranscript,
    bool? isThinking,
  }) =>
      AudioCliState(
        isActive: isActive ?? this.isActive,
        turns: turns ?? this.turns,
        partialTranscript: partialTranscript ?? this.partialTranscript,
        isThinking: isThinking ?? this.isThinking,
      );
}

// ═══════════════════════════════════════════════════════════════════════════
// State notifier
// ═══════════════════════════════════════════════════════════════════════════

class AudioCliStateNotifier extends StateNotifier<AudioCliState> {
  AudioCliStateNotifier() : super(const AudioCliState());

  void handleEvent(Map<String, dynamic> event) {
    final type = event['type'] as String? ?? '';
    switch (type) {
      case 'session_start':
        state = const AudioCliState(isActive: true);
        break;

      case 'session_end':
        // Keep history visible for 1 s then hide
        state = state.copyWith(
          isActive: false,
          partialTranscript: '',
          isThinking: false,
        );
        break;

      case 'transcript_partial':
        state = state.copyWith(
          partialTranscript: event['text'] as String? ?? '',
        );
        break;

      case 'transcript_final':
        final text = event['text'] as String? ?? '';
        // Push a new turn with the user text; LLM response pending
        final newTurns = [
          ...state.turns,
          AudioCliTurn(userText: text, isComplete: false),
        ];
        state = state.copyWith(
          turns: newTurns,
          partialTranscript: '',
          isThinking: true,
        );
        break;

      case 'llm_thinking':
        state = state.copyWith(isThinking: true);
        break;

      case 'llm_response':
        final text = event['text'] as String? ?? '';
        if (state.turns.isEmpty) break;
        // Fill the most recent turn's LLM response
        final updated = List<AudioCliTurn>.from(state.turns);
        updated[updated.length - 1] =
            updated.last.copyWith(llmText: text, isComplete: true);
        state = state.copyWith(
          turns: updated,
          isThinking: false,
        );
        break;
    }
  }

  void clear() {
    state = const AudioCliState();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Riverpod providers
// ═══════════════════════════════════════════════════════════════════════════

final audioCliStateProvider =
    StateNotifierProvider<AudioCliStateNotifier, AudioCliState>(
        (ref) => AudioCliStateNotifier());

// ═══════════════════════════════════════════════════════════════════════════
// WebSocket connection manager (auto-reconnect)
// ═══════════════════════════════════════════════════════════════════════════

class _AudioCliWsManager {
  final String host;
  final int port;
  final void Function(Map<String, dynamic>) onEvent;

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  bool _disposed = false;
  Timer? _reconnectTimer;

  _AudioCliWsManager({
    required this.host,
    required this.port,
    required this.onEvent,
  }) {
    _connect();
  }

  void _connect() {
    if (_disposed) return;
    try {
      _channel = WebSocketChannel.connect(
        Uri.parse('ws://$host:$port/ws/audio_cli'),
      );
      _sub = _channel!.stream.listen(
        (raw) {
          try {
            final event = jsonDecode(raw as String) as Map<String, dynamic>;
            onEvent(event);
          } catch (_) {}
        },
        onDone: _scheduleReconnect,
        onError: (_) => _scheduleReconnect(),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _sub?.cancel();
    _channel = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), _connect);
  }

  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Root overlay widget — wrap this around MaterialApp.router in app.dart
// ═══════════════════════════════════════════════════════════════════════════

class AudioCliOverlay extends ConsumerStatefulWidget {
  const AudioCliOverlay({super.key});

  @override
  ConsumerState<AudioCliOverlay> createState() => _AudioCliOverlayState();
}

class _AudioCliOverlayState extends ConsumerState<AudioCliOverlay> {
  _AudioCliWsManager? _ws;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initWs());
  }

  void _initWs() {
    final cfg = ref.read(hostConfigProvider);
    _ws = _AudioCliWsManager(
      host: cfg.host,
      port: cfg.shellPort,
      onEvent: (event) {
        if (mounted) {
          ref.read(audioCliStateProvider.notifier).handleEvent(event);
        }
      },
    );
  }

  @override
  void dispose() {
    _ws?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(audioCliStateProvider);
    if (!state.isActive) return const SizedBox.shrink();
    return const _OverlayContent();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Overlay content (shown when session is active)
// ═══════════════════════════════════════════════════════════════════════════

class _OverlayContent extends ConsumerWidget {
  const _OverlayContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(audioCliStateProvider);
    final size = MediaQuery.of(context).size;
    // 1920×480 is our target but adapt to whatever screen is present
    final isUltraWide = size.width > 1200 && size.height < 600;

    return AnimatedOpacity(
      opacity: state.isActive ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 300),
      child: Stack(
        fit: StackFit.expand,
        children: [
          // ── Frosted glass scrim ──────────────────────────────────────
          ClipRect(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 3, sigmaY: 3),
              child: Container(
                color: Colors.black.withValues(alpha: 0.78),
              ),
            ),
          ),

          // ── Two-column transcript layout ─────────────────────────────
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: isUltraWide ? 32 : 24,
              vertical: isUltraWide ? 12 : 20,
            ),
            child: Row(
              children: [
                // LEFT: user transcripts
                Expanded(
                  child: _UserColumn(state: state, isUltraWide: isUltraWide),
                ),
                Container(
                  width: 1,
                  color: Colors.white.withValues(alpha: 0.12),
                  margin: const EdgeInsets.symmetric(horizontal: 24),
                ),
                // RIGHT: LLM responses
                Expanded(
                  child: _LlmColumn(state: state, isUltraWide: isUltraWide),
                ),
              ],
            ),
          ),

          // ── Corner label ─────────────────────────────────────────────
          Positioned(
            top: isUltraWide ? 8 : 12,
            right: isUltraWide ? 16 : 20,
            child: Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: Color(0xFF4CC9F0),
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  'AUDIO CLI',
                  style: TextStyle(
                    color: const Color(0xFF4CC9F0),
                    fontSize: isUltraWide ? 11 : 13,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// LEFT column — user speech
// ═══════════════════════════════════════════════════════════════════════════

class _UserColumn extends StatelessWidget {
  final AudioCliState state;
  final bool isUltraWide;

  const _UserColumn({required this.state, required this.isUltraWide});

  @override
  Widget build(BuildContext context) {
    final baseSize = isUltraWide ? 14.0 : 17.0;
    final completedTurns =
        state.turns.where((t) => t.userText.isNotEmpty).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ColumnHeader(
          icon: Icons.person_outline,
          label: 'YOU',
          color: const Color(0xFF4CC9F0),
          isUltraWide: isUltraWide,
        ),
        const SizedBox(height: 8),
        Expanded(
          child: ListView.builder(
            reverse: true, // newest at bottom, scrolls up
            itemCount: completedTurns.length,
            itemBuilder: (_, i) {
              // reversed list: index 0 = newest
              final turn =
                  completedTurns[completedTurns.length - 1 - i];
              final isNewest = i == 0;
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: AnimatedOpacity(
                  opacity: isNewest ? 1.0 : 0.55,
                  duration: const Duration(milliseconds: 200),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('▸ ',
                          style: TextStyle(
                              color: Color(0xFF4CC9F0), fontSize: 14)),
                      Expanded(
                        child: Text(
                          turn.userText,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: baseSize,
                            fontWeight: isNewest
                                ? FontWeight.w600
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        // Partial transcript at bottom (live dictation)
        if (state.partialTranscript.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Row(
              children: [
                const _PulsingDot(color: Color(0xFF4CC9F0)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    state.partialTranscript,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.6),
                      fontSize: baseSize - 1,
                      fontStyle: FontStyle.italic,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// RIGHT column — LLM responses
// ═══════════════════════════════════════════════════════════════════════════

class _LlmColumn extends StatelessWidget {
  final AudioCliState state;
  final bool isUltraWide;

  const _LlmColumn({required this.state, required this.isUltraWide});

  @override
  Widget build(BuildContext context) {
    final baseSize = isUltraWide ? 14.0 : 17.0;
    final completedTurns =
        state.turns.where((t) => t.isComplete && t.llmText.isNotEmpty).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ColumnHeader(
          icon: Icons.radio,
          label: 'RADIO',
          color: const Color(0xFF2EE59D),
          isUltraWide: isUltraWide,
        ),
        const SizedBox(height: 8),
        Expanded(
          child: ListView.builder(
            reverse: true,
            itemCount: completedTurns.length,
            itemBuilder: (_, i) {
              final turn =
                  completedTurns[completedTurns.length - 1 - i];
              final isNewest = i == 0;
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: AnimatedOpacity(
                  opacity: isNewest ? 1.0 : 0.55,
                  duration: const Duration(milliseconds: 200),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('▸ ',
                          style: TextStyle(
                              color: Color(0xFF2EE59D), fontSize: 14)),
                      Expanded(
                        child: Text(
                          turn.llmText,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: baseSize,
                            fontWeight: isNewest
                                ? FontWeight.w500
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        // Thinking bubble
        if (state.isThinking) const _ThinkingBubble(),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Sub-widgets
// ═══════════════════════════════════════════════════════════════════════════

class _ColumnHeader extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool isUltraWide;

  const _ColumnHeader({
    required this.icon,
    required this.label,
    required this.color,
    required this.isUltraWide,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: color, size: isUltraWide ? 16 : 18),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: isUltraWide ? 11 : 13,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
          ),
        ),
      ],
    );
  }
}

/// Animated three-dot thinking indicator
class _ThinkingBubble extends StatefulWidget {
  const _ThinkingBubble();

  @override
  State<_ThinkingBubble> createState() => _ThinkingBubbleState();
}

class _ThinkingBubbleState extends State<_ThinkingBubble>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: const Color(0xFF2EE59D).withValues(alpha: 0.4),
              ),
            ),
            child: AnimatedBuilder(
              animation: _controller,
              builder: (_, __) {
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: List.generate(3, (i) {
                    // Each dot peaks at a different phase
                    final phase = (i / 3.0);
                    final t = (_controller.value + phase) % 1.0;
                    final scale = 0.5 + 0.5 * _bounceAt(t);
                    return Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 3),
                      child: Transform.scale(
                        scale: scale,
                        child: Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: const Color(0xFF2EE59D)
                                .withValues(alpha: 0.4 + 0.6 * scale),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                    );
                  }),
                );
              },
            ),
          ),
          const SizedBox(width: 10),
          Text(
            'thinking…',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.45),
              fontSize: 13,
              fontStyle: FontStyle.italic,
            ),
          ),
        ],
      ),
    );
  }

  /// Simple bounce curve: rises to 1.0 at t=0.5, falls back to 0.0.
  double _bounceAt(double t) {
    if (t < 0.5) return t * 2.0;
    return 1.0 - (t - 0.5) * 2.0;
  }
}

/// A small pulsing dot used for the partial-transcript indicator.
class _PulsingDot extends StatefulWidget {
  final Color color;
  const _PulsingDot({required this.color});

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    )..repeat(reverse: true);
    _opacity = Tween<double>(begin: 0.3, end: 1.0).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          color: widget.color,
          shape: BoxShape.circle,
        ),
      ),
    );
  }
}

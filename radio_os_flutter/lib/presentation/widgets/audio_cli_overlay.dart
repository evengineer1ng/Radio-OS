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

    return AnimatedOpacity(
      opacity: state.isActive ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 300),
      child: Stack(
        fit: StackFit.expand,
        children: [
          // ── Dark scrim ───────────────────────────────────────────────
          ClipRect(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
              child: Container(color: Colors.black.withValues(alpha: 0.85)),
            ),
          ),

          // ── Conversation thread ──────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(48, 12, 48, 12),
            child: _ConversationThread(state: state),
          ),

          // ── AUDIO CLI badge (top-right) ───────────────────────────────
          Positioned(
            top: 10,
            right: 20,
            child: Row(
              children: [
                const _PulsingDot(color: Color(0xFF4CC9F0)),
                const SizedBox(width: 8),
                const Text(
                  'AUDIO CLI',
                  style: TextStyle(
                    color: Color(0xFF4CC9F0),
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.6,
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
// Conversation thread — iMessage-style, newest at right edge of screen
// ═══════════════════════════════════════════════════════════════════════════

class _ConversationThread extends StatelessWidget {
  final AudioCliState state;
  const _ConversationThread({required this.state});

  @override
  Widget build(BuildContext context) {
    // Show only the most recent turn prominently; fade out older ones.
    final turns = state.turns;
    final hasTurns = turns.isNotEmpty;
    final latestTurn = hasTurns ? turns.last : null;
    final olderTurns = hasTurns && turns.length > 1
        ? turns.sublist(0, turns.length - 1)
        : <AudioCliTurn>[];

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // ── Older turns — dimmed, stacked on the left ─────────────────
        if (olderTurns.isNotEmpty)
          Expanded(
            flex: 2,
            child: Opacity(
              opacity: 0.3,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Show only the most recent of the older turns
                  _OldTurnChip(turn: olderTurns.last),
                ],
              ),
            ),
          ),

        if (olderTurns.isNotEmpty) const SizedBox(width: 24),

        // ── Current / latest turn — full size ────────────────────────
        Expanded(
          flex: olderTurns.isNotEmpty ? 5 : 7,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Partial transcript (user currently speaking)
              if (state.partialTranscript.isNotEmpty && latestTurn == null)
                _PartialBubble(text: state.partialTranscript),

              // Latest user bubble (left-aligned)
              if (latestTurn != null)
                _UserBubble(
                  text: latestTurn.userText,
                  animate: true,
                ),

              if (latestTurn != null) const SizedBox(height: 10),

              // Latest Radio response (right-aligned) or thinking dots
              if (state.isThinking)
                const Align(
                  alignment: Alignment.centerRight,
                  child: _ThinkingBubble(),
                )
              else if (latestTurn != null && latestTurn.llmText.isNotEmpty)
                _RadioBubble(
                  text: latestTurn.llmText,
                  animate: latestTurn.isComplete,
                ),
            ],
          ),
        ),
      ],
    );
  }
}

// ── User speech bubble — LEFT aligned, blue ──────────────────────────────
class _UserBubble extends StatelessWidget {
  final String text;
  final bool animate;
  const _UserBubble({required this.text, this.animate = false});

  @override
  Widget build(BuildContext context) {
    const color = Color(0xFF4CC9F0);
    const bubbleColor = Color(0xFF1A3A4A);
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 900),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(20),
            bottomLeft: Radius.circular(20),
            bottomRight: Radius.circular(20),
          ),
          border: Border.all(color: color.withValues(alpha: 0.35), width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.person_outline, color: color, size: 22),
            const SizedBox(width: 10),
            Flexible(
              child: animate
                  ? _TypewriterText(
                      text: text,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.w600,
                        height: 1.25,
                      ),
                      charDelayMs: 22,
                    )
                  : Text(
                      text,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.w600,
                        height: 1.25,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Radio response bubble — RIGHT aligned, green ─────────────────────────
class _RadioBubble extends StatelessWidget {
  final String text;
  final bool animate;
  const _RadioBubble({required this.text, this.animate = false});

  @override
  Widget build(BuildContext context) {
    const color = Color(0xFF2EE59D);
    const bubbleColor = Color(0xFF0D2E22);
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 900),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(20),
            topRight: Radius.circular(4),
            bottomLeft: Radius.circular(20),
            bottomRight: Radius.circular(20),
          ),
          border: Border.all(color: color.withValues(alpha: 0.35), width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Flexible(
              child: animate
                  ? _TypewriterText(
                      text: text,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 30,
                        fontWeight: FontWeight.w400,
                        height: 1.25,
                      ),
                      charDelayMs: 14,
                    )
                  : Text(
                      text,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 30,
                        fontWeight: FontWeight.w400,
                        height: 1.25,
                      ),
                    ),
            ),
            const SizedBox(width: 10),
            const Icon(Icons.radio, color: color, size: 22),
          ],
        ),
      ),
    );
  }
}

// ── Partial transcript (live dictation, before STT finalises) ─────────────
class _PartialBubble extends StatelessWidget {
  final String text;
  const _PartialBubble({required this.text});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 900),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: const Color(0xFF4CC9F0).withValues(alpha: 0.2),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _PulsingDot(color: Color(0xFF4CC9F0)),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                text,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.5),
                  fontSize: 28,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Older turn chip — compact, dimmed history ─────────────────────────────
class _OldTurnChip extends StatelessWidget {
  final AudioCliTurn turn;
  const _OldTurnChip({required this.turn});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (turn.userText.isNotEmpty)
          Text(
            turn.userText,
            style: const TextStyle(
              color: Color(0xFF4CC9F0),
              fontSize: 18,
              fontWeight: FontWeight.w500,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        if (turn.llmText.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              turn.llmText,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 16,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Typewriter text widget — animates text character by character
// ═══════════════════════════════════════════════════════════════════════════

class _TypewriterText extends StatefulWidget {
  final String text;
  final TextStyle style;

  /// Milliseconds between each character appearing.
  final int charDelayMs;

  const _TypewriterText({
    required this.text,
    required this.style,
    this.charDelayMs = 28,
  });

  @override
  State<_TypewriterText> createState() => _TypewriterTextState();
}

class _TypewriterTextState extends State<_TypewriterText> {
  int _visibleChars = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _startTyping();
  }

  @override
  void didUpdateWidget(_TypewriterText old) {
    super.didUpdateWidget(old);
    if (old.text != widget.text) {
      _timer?.cancel();
      _visibleChars = 0;
      _startTyping();
    }
  }

  void _startTyping() {
    if (widget.text.isEmpty) return;
    _timer = Timer.periodic(
      Duration(milliseconds: widget.charDelayMs),
      (t) {
        if (!mounted) {
          t.cancel();
          return;
        }
        setState(() => _visibleChars++);
        if (_visibleChars >= widget.text.length) {
          t.cancel();
        }
      },
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final shown = widget.text.substring(
      0,
      _visibleChars.clamp(0, widget.text.length),
    );
    final isDone = _visibleChars >= widget.text.length;
    return RichText(
      text: TextSpan(
        style: widget.style,
        children: [
          TextSpan(text: shown),
          if (!isDone)
            TextSpan(
              text: '▌',
              style: widget.style.copyWith(
                color: widget.style.color?.withValues(alpha: 0.7),
              ),
            ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Sub-widgets
// ═══════════════════════════════════════════════════════════════════════════

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
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        color: const Color(0xFF0D2E22),
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(20),
          topRight: Radius.circular(4),
          bottomLeft: Radius.circular(20),
          bottomRight: Radius.circular(20),
        ),
        border: Border.all(
          color: const Color(0xFF2EE59D).withValues(alpha: 0.35),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedBuilder(
            animation: _controller,
            builder: (_, __) {
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(3, (i) {
                  final phase = (i / 3.0);
                  final t = (_controller.value + phase) % 1.0;
                  final scale = 0.5 + 0.5 * _bounceAt(t);
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 5),
                    child: Transform.scale(
                      scale: scale,
                      child: Container(
                        width: 12,
                        height: 12,
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
          const SizedBox(width: 14),
          Text(
            'thinking…',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.5),
              fontSize: 26,
              fontStyle: FontStyle.italic,
            ),
          ),
          const SizedBox(width: 10),
          const Icon(Icons.radio, color: Color(0xFF2EE59D), size: 22),
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

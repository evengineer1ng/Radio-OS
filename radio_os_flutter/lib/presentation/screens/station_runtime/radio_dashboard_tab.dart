/// Radio Dashboard Tab — default view for non-game stations.
///
/// Shows:
///   • Animated waveform for active TTS / now-playing
///   • Subtitle strip
///   • Live event log (last N events from WebSocket)
///   • Station status / uptime
///
/// This is intentionally simple — no game UI, no load/new game.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/event.dart';
import '../../../domain/providers.dart';
import '../../../utils/formatters.dart';

class RadioDashboardTab extends ConsumerWidget {
  const RadioDashboardTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final station = ref.watch(activeStationProvider);
    final np = ref.watch(nowPlayingProvider);
    final subtitle = ref.watch(subtitleProvider);
    final events = ref.watch(eventLogProvider);
    final size = MediaQuery.of(context).size;
    final isUltraWide = size.width > 1200 && size.height < 600;

    if (isUltraWide) {
      return _UltraWideLayout(
        station: station,
        np: np,
        subtitle: subtitle,
        events: events,
      );
    }

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _StationHeader(station: station),
          const SizedBox(height: 16),
          _WaveformPanel(np: np, subtitle: subtitle),
          const SizedBox(height: 16),
          Expanded(child: _EventFeed(events: events)),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Ultra-wide layout: left waveform panel | right event feed
// ─────────────────────────────────────────────────────────────────────────────

class _UltraWideLayout extends StatelessWidget {
  final dynamic station;
  final dynamic np;
  final String subtitle;
  final List<StationEvent> events;

  const _UltraWideLayout({
    required this.station,
    required this.np,
    required this.subtitle,
    required this.events,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left: waveform + subtitle
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _StationHeader(station: station),
                const SizedBox(height: 12),
                Expanded(child: _WaveformPanel(np: np, subtitle: subtitle)),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Container(width: 1, color: theme.dividerColor),
          const SizedBox(width: 16),
          // Right: event feed
          Expanded(
            flex: 3,
            child: _EventFeed(events: events),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Station header
// ─────────────────────────────────────────────────────────────────────────────

class _StationHeader extends StatelessWidget {
  final dynamic station;
  const _StationHeader({required this.station});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (station == null) return const SizedBox.shrink();

    final uptime = station.uptimeSec as int?;
    final uptimeStr = uptime != null ? _formatUptime(uptime) : null;

    return Row(
      children: [
        Icon(Icons.radio, size: 16, color: theme.colorScheme.primary),
        const SizedBox(width: 8),
        Text(
          station.name as String? ?? 'Radio',
          style: theme.textTheme.titleMedium,
        ),
        const SizedBox(width: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
          decoration: BoxDecoration(
            color: const Color(0xFF34d399).withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(4),
          ),
          child: const Text(
            '● ON AIR',
            style: TextStyle(
              color: Color(0xFF34d399),
              fontSize: 10,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
            ),
          ),
        ),
        if (uptimeStr != null) ...[
          const SizedBox(width: 10),
          Text(
            'up $uptimeStr',
            style: theme.textTheme.labelSmall,
          ),
        ],
      ],
    );
  }

  String _formatUptime(int seconds) {
    if (seconds < 60) return '${seconds}s';
    if (seconds < 3600) return '${(seconds ~/ 60)}m';
    final h = seconds ~/ 3600;
    final m = (seconds % 3600) ~/ 60;
    return '${h}h ${m}m';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Waveform panel — full animated waveform + subtitle
// ─────────────────────────────────────────────────────────────────────────────

class _WaveformPanel extends StatelessWidget {
  final dynamic np;
  final String subtitle;

  const _WaveformPanel({required this.np, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isPlaying = np != null && (np.isPlaying as bool? ?? false);
    final speaker = np != null ? (np.speaker as String? ?? '') : '';
    final preview = np != null ? (np.textPreview as String? ?? '') : '';

    return Container(
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.dividerColor),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Speaker label
          if (speaker.isNotEmpty) ...[
            Row(
              children: [
                Icon(
                  isPlaying ? Icons.mic : Icons.mic_none,
                  size: 14,
                  color: isPlaying
                      ? theme.colorScheme.primary
                      : theme.textTheme.bodySmall?.color,
                ),
                const SizedBox(width: 6),
                Text(
                  speaker,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: isPlaying ? theme.colorScheme.primary : null,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
          ],

          // Main waveform
          SizedBox(
            height: 56,
            child: isPlaying
                ? _AnimatedWaveform(color: theme.colorScheme.primary)
                : _IdleWaveform(color: theme.dividerColor),
          ),

          // Subtitle / text preview
          if (subtitle.isNotEmpty || preview.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              subtitle.isNotEmpty ? subtitle : preview,
              style: theme.textTheme.bodySmall?.copyWith(
                fontStyle: FontStyle.italic,
                color: theme.textTheme.bodySmall?.color
                    ?.withValues(alpha: 0.8),
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ] else if (!isPlaying) ...[
            const SizedBox(height: 10),
            Text(
              'Waiting for broadcast…',
              style: theme.textTheme.bodySmall?.copyWith(
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Animated waveform — smooth sine-based bars while playing
// ─────────────────────────────────────────────────────────────────────────────

class _AnimatedWaveform extends StatefulWidget {
  final Color color;
  const _AnimatedWaveform({required this.color});

  @override
  State<_AnimatedWaveform> createState() => _AnimatedWaveformState();
}

class _AnimatedWaveformState extends State<_AnimatedWaveform>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (context, _) {
        return CustomPaint(
          painter: _WaveformPainter(
            phase: _ctrl.value * math.pi * 2,
            color: widget.color,
          ),
          child: const SizedBox.expand(),
        );
      },
    );
  }
}

class _WaveformPainter extends CustomPainter {
  final double phase;
  final Color color;

  const _WaveformPainter({required this.phase, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.fill;

    const barCount = 32;
    final barWidth = (size.width / barCount) * 0.55;
    final spacing = size.width / barCount;
    final cx = size.height / 2;

    for (int i = 0; i < barCount; i++) {
      final x = i * spacing + spacing / 2;
      // Multi-frequency sine for organic look
      final t = i / barCount;
      final h = (math.sin(t * math.pi * 4 + phase) * 0.5 +
              math.sin(t * math.pi * 7 + phase * 1.3) * 0.3 +
              math.sin(t * math.pi * 2 + phase * 0.7) * 0.2)
          .abs();
      final barH = (h * size.height * 0.85).clamp(3.0, size.height);

      final rect = RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: Offset(x, cx),
          width: barWidth,
          height: barH,
        ),
        const Radius.circular(2),
      );
      canvas.drawRRect(rect, paint);
    }
  }

  @override
  bool shouldRepaint(_WaveformPainter old) =>
      old.phase != phase || old.color != color;
}

class _IdleWaveform extends StatelessWidget {
  final Color color;
  const _IdleWaveform({required this.color});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _IdleLinePainter(color: color),
      child: const SizedBox.expand(),
    );
  }
}

class _IdleLinePainter extends CustomPainter {
  final Color color;
  const _IdleLinePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withValues(alpha: 0.5)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    const barCount = 32;
    final spacing = size.width / barCount;
    final cx = size.height / 2;

    for (int i = 0; i < barCount; i++) {
      final x = i * spacing + spacing / 2;
      canvas.drawLine(
        Offset(x, cx - 2),
        Offset(x, cx + 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_IdleLinePainter old) => old.color != color;
}

// ─────────────────────────────────────────────────────────────────────────────
// Event feed — live stream of station events
// ─────────────────────────────────────────────────────────────────────────────

class _EventFeed extends StatelessWidget {
  final List<StationEvent> events;
  const _EventFeed({required this.events});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Live Feed', style: theme.textTheme.labelMedium),
        const SizedBox(height: 8),
        Expanded(
          child: events.isEmpty
              ? Center(
                  child: Text(
                    'Waiting for events…',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(fontStyle: FontStyle.italic),
                  ),
                )
              : ListView.builder(
                  reverse: true,
                  itemCount: events.length.clamp(0, 200),
                  itemBuilder: (context, i) {
                    final evt = events[i];
                    return _EventRow(event: evt);
                  },
                ),
        ),
      ],
    );
  }
}

class _EventRow extends StatelessWidget {
  final StationEvent event;
  const _EventRow({required this.event});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
          final (icon, color) = _iconForType(event.type ?? event.category);    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: theme.dividerColor.withValues(alpha: 0.25)),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 13, color: color.withValues(alpha: 0.7)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _summarise(event),
              style: theme.textTheme.bodySmall,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            _timeAgo(event.timestamp),
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.textTheme.bodySmall?.color),
          ),
        ],
      ),
    );
  }

  (IconData, Color) _iconForType(String? type) {
    switch ((type ?? '').toLowerCase()) {
      case 'subtitle':
      case 'tts_start':
        return (Icons.record_voice_over, const Color(0xFF60a5fa));
      case 'notification':
        return (Icons.notifications_none, const Color(0xFFfbbf24));
      case 'state_update':
        return (Icons.sync, const Color(0xFF34d399));
      case 'now_playing':
        return (Icons.volume_up, const Color(0xFF818cf8));
      case 'error':
        return (Icons.error_outline, const Color(0xFFf87171));
      default:
        return (Icons.circle, const Color(0xFF6b7280));
    }
  }

  String _summarise(StationEvent event) {
    final desc = event.description ?? '';
    if (desc.isNotEmpty) return desc;
    return humanizeToken(event.type ?? event.category ?? 'event');
  }

  String _timeAgo(DateTime? ts) {
    if (ts == null) return '';
    final diff = DateTime.now().difference(ts);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m';
    return '${diff.inHours}h';
  }
}

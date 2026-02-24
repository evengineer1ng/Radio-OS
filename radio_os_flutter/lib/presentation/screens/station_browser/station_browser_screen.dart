/// Station Browser — cinematic carousel for 1920×480.
/// One dominant center station, neighbours peeking, no split-panel.
library;

import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../config/constants.dart';
import '../../../data/models/station.dart';
import '../../../domain/providers.dart';
import '../../widgets/connection_banner.dart';
import '../../widgets/now_playing_banner.dart';
import 'station_card.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Root screen
// ─────────────────────────────────────────────────────────────────────────────

class StationBrowserScreen extends ConsumerWidget {
  const StationBrowserScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stations = ref.watch(stationsProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: Column(
        children: [
          const ConnectionBanner(),
          Expanded(
            child: stations.isEmpty
                ? _EmptyState(theme: theme)
                : _CinematicCarousel(stations: stations),
          ),
          const NowPlayingBanner(),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  final ThemeData theme;
  const _EmptyState({required this.theme});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.radio,
              size: 64, color: theme.colorScheme.primary.withValues(alpha: 0.2)),
          const SizedBox(height: 16),
          Text('No stations',
              style: theme.textTheme.headlineMedium
                  ?.copyWith(color: theme.disabledColor)),
          const SizedBox(height: 8),
          TextButton.icon(
            onPressed: () => context.go('/settings/connection'),
            icon: const Icon(Icons.settings),
            label: const Text('Check connection'),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Cinematic carousel
// ─────────────────────────────────────────────────────────────────────────────

class _CinematicCarousel extends ConsumerStatefulWidget {
  final List<Station> stations;
  const _CinematicCarousel({required this.stations});

  @override
  ConsumerState<_CinematicCarousel> createState() => _CinematicCarouselState();
}

class _CinematicCarouselState extends ConsumerState<_CinematicCarousel>
    with SingleTickerProviderStateMixin {
  late PageController _pageCtrl;
  int _focusedIndex = 0;
  bool _launching = false;

  @override
  void initState() {
    super.initState();
    // Start centered; viewportFraction <1 lets neighbours peek
    _pageCtrl = PageController(viewportFraction: 0.52, initialPage: 0);
  }

  @override
  void didUpdateWidget(_CinematicCarousel old) {
    super.didUpdateWidget(old);
    // Keep focused index in range if stations list shrinks
    if (_focusedIndex >= widget.stations.length) {
      _focusedIndex = widget.stations.length - 1;
    }
  }

  @override
  void dispose() {
    _pageCtrl.dispose();
    super.dispose();
  }

  Station get _focused => widget.stations[_focusedIndex];

  void _goTo(int index) {
    setState(() => _focusedIndex = index);
    _pageCtrl.animateToPage(
      index,
      duration: const Duration(milliseconds: 380),
      curve: Curves.easeOutCubic,
    );
    ref.read(activeStationProvider.notifier).state = widget.stations[index];
  }

  Future<void> _launchAndOpen() async {
    if (_launching) return;
    setState(() => _launching = true);
    final api = ref.read(shellApiProvider);
    final toasts = ref.read(toastsProvider.notifier);
    final stations = ref.read(stationsProvider.notifier);
    final id = _focused.id;
    final name = _focused.name;
    try {
      final result = await api.launchStation(id);
      if (!mounted) return;
      final ok = result['status'] == 'launched' ||
          result['status'] == 'already_running';
      if (ok) {
        stations.refresh();
        context.go('/station/$id');
      } else {
        toasts.show('Launch failed', type: 'error');
      }
    } finally {
      if (mounted) setState(() => _launching = false);
    }
  }

  Future<void> _launch() async {
    if (_launching) return;
    setState(() => _launching = true);
    // Capture ref-dependent values before the async gap so we never touch
    // ref after an await (widget may be disposed by then).
    final api = ref.read(shellApiProvider);
    final toasts = ref.read(toastsProvider.notifier);
    final stations = ref.read(stationsProvider.notifier);
    final name = _focused.name;
    try {
      final result = await api.launchStation(_focused.id);
      if (!mounted) return;
      final ok = result['status'] == 'launched' ||
          result['status'] == 'already_running';
      toasts.show(
        ok ? '$name launched' : 'Launch failed',
        type: ok ? 'success' : 'error',
      );
      if (ok) stations.refresh();
    } finally {
      if (mounted) setState(() => _launching = false);
    }
  }

  Future<void> _stop() async {
    final api = ref.read(shellApiProvider);
    final toasts = ref.read(toastsProvider.notifier);
    final stations = ref.read(stationsProvider.notifier);
    final name = _focused.name;
    await api.stopStation(_focused.id);
    if (!mounted) return;
    toasts.show('$name stopped');
    stations.refresh();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;
    final accent = theme.colorScheme.primary;
    final isRunning = _focused.status == StationStatus.running;

    return Stack(
      children: [
        // ── Settings gear (top-right corner) ──────────────────────────────
        Positioned(
          top: 0,
          right: 0,
          child: _TopBar(accent: accent),
        ),

        // ── Carousel fills full height ────────────────────────────────────
        PageView.builder(
          controller: _pageCtrl,
          itemCount: widget.stations.length,
          onPageChanged: (i) {
            setState(() => _focusedIndex = i);
            ref.read(activeStationProvider.notifier).state =
                widget.stations[i];
          },
          itemBuilder: (context, index) {
            final station = widget.stations[index];
            final isFocused = index == _focusedIndex;
            return GestureDetector(
              onTap: () => isFocused
                  ? null // already focused — hold the card to launch
                  : _goTo(index),
              child: _CarouselCard(
                station: station,
                isFocused: isFocused,
                accent: accent,
                totalHeight: size.height,
                launching: _launching,
                onHoldLaunch: isFocused ? _launchAndOpen : null,
              ),
            );
          },
        ),

        // ── Bottom action strip ───────────────────────────────────────────
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: _ActionStrip(
            station: _focused,
            isRunning: isRunning,
            stationCount: widget.stations.length,
            focusedIndex: _focusedIndex,
            onStop: _stop,
            onOpen: () => context.go('/station/${_focused.id}'),
            accent: accent,
            theme: theme,
          ),
        ),

        // ── Left / right arrows ───────────────────────────────────────────
        if (_focusedIndex > 0)
          Positioned(
            left: 12,
            top: 0,
            bottom: 72,
            child: Center(
              child: _ArrowButton(
                icon: Icons.chevron_left,
                onTap: () => _goTo(_focusedIndex - 1),
                accent: accent,
              ),
            ),
          ),
        if (_focusedIndex < widget.stations.length - 1)
          Positioned(
            right: 12,
            top: 0,
            bottom: 72,
            child: Center(
              child: _ArrowButton(
                icon: Icons.chevron_right,
                onTap: () => _goTo(_focusedIndex + 1),
                accent: accent,
              ),
            ),
          ),

      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Individual carousel card — hold to launch when focused & stopped
// ─────────────────────────────────────────────────────────────────────────────

class _CarouselCard extends StatefulWidget {
  final Station station;
  final bool isFocused;
  final Color accent;
  final double totalHeight;
  final bool launching;
  final VoidCallback? onHoldLaunch;

  const _CarouselCard({
    required this.station,
    required this.isFocused,
    required this.accent,
    required this.totalHeight,
    this.launching = false,
    this.onHoldLaunch,
  });

  @override
  State<_CarouselCard> createState() => _CarouselCardState();
}

class _CarouselCardState extends State<_CarouselCard>
    with SingleTickerProviderStateMixin {
  bool _pressing = false;
  Timer? _holdTimer;
  late AnimationController _fillCtrl;
  late Animation<double> _fillAnim;

  static const _holdMs = 700;

  @override
  void initState() {
    super.initState();
    _fillCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: _holdMs),
    );
    _fillAnim = CurvedAnimation(parent: _fillCtrl, curve: Curves.easeOut);
  }

  @override
  void dispose() {
    _holdTimer?.cancel();
    _fillCtrl.dispose();
    super.dispose();
  }

  void _onPressDown() {
    if (!widget.isFocused) return;
    if (widget.station.status == StationStatus.running) return;
    if (widget.onHoldLaunch == null) return;
    setState(() => _pressing = true);
    _fillCtrl.forward(from: 0);
    _holdTimer = Timer(const Duration(milliseconds: _holdMs), () {
      widget.onHoldLaunch?.call();
      setState(() => _pressing = false);
      _fillCtrl.reset();
    });
  }

  void _onPressUp() {
    _holdTimer?.cancel();
    _fillCtrl.reverse();
    setState(() => _pressing = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final station = widget.station;
    final isFocused = widget.isFocused;
    final accent = widget.accent;
    final isRunning = station.status == StationStatus.running;
    final isError = station.status == StationStatus.error;
    final canHold = isFocused && !isRunning && widget.onHoldLaunch != null;
    final glowColor = isRunning
        ? const Color(0xFF34d399)
        : isError
            ? const Color(0xFFf87171)
            : accent;

    final logoUrl =
        'http://${ApiConstants.defaultHost}:${ApiConstants.shellPort}'
        '/api/stations/${station.id}/logo';

    Widget card = AnimatedScale(
      scale: isFocused ? 1.0 : 0.88,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
      child: AnimatedOpacity(
        opacity: isFocused ? 1.0 : 0.45,
        duration: const Duration(milliseconds: 280),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 16, 10, 90),
          child: Container(
            decoration: BoxDecoration(
              color: theme.cardColor,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: isFocused
                    ? glowColor.withValues(alpha: 0.7)
                    : theme.dividerColor,
                width: isFocused ? 1.5 : 1,
              ),
              boxShadow: isFocused
                  ? [
                      BoxShadow(
                        color: glowColor.withValues(alpha: 0.18),
                        blurRadius: 32,
                        spreadRadius: 4,
                      ),
                    ]
                  : null,
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(19),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  // ── Faded cover art background ───────────────────────
                  Positioned.fill(
                    child: CachedNetworkImage(
                      imageUrl: logoUrl,
                      fit: BoxFit.cover,
                      errorWidget: (_, __, ___) => const SizedBox.shrink(),
                      placeholder: (_, __) => const SizedBox.shrink(),
                    ),
                  ),
                  // Dark gradient overlay — more opaque on left (text side)
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.centerRight,
                          end: Alignment.centerLeft,
                          colors: [
                            theme.cardColor.withValues(alpha: 0.15),
                            theme.cardColor.withValues(alpha: 0.82),
                            theme.cardColor.withValues(alpha: 0.95),
                          ],
                          stops: const [0.0, 0.45, 0.75],
                        ),
                      ),
                    ),
                  ),

                  // ── Foreground content ───────────────────────────────
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 28, vertical: 20),
                    child: Row(
                      children: [
                        // ── Logo emblem ──────────────────────────────
                        _StationEmblem(
                          station: station,
                          accent: glowColor,
                          isFocused: isFocused,
                        ),
                        const SizedBox(width: 28),

                        // ── Name + meta ──────────────────────────────
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                station.name,
                                style:
                                    theme.textTheme.headlineLarge?.copyWith(
                                  fontSize: isFocused ? 30 : 22,
                                  letterSpacing: -0.5,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              if (station.category.isNotEmpty) ...[
                                const SizedBox(height: 6),
                                Text(
                                  station.category.toUpperCase(),
                                  style:
                                      theme.textTheme.labelSmall?.copyWith(
                                    color: accent.withValues(alpha: 0.7),
                                    letterSpacing: 2.5,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                              const SizedBox(height: 10),
                              _StatusPill(status: station.status),
                            ],
                          ),
                        ),

                        // ── Running dot on right edge ────────────────
                        if (isRunning && isFocused)
                          Padding(
                            padding: const EdgeInsets.only(left: 16),
                            child:
                                _PulsingDot(color: const Color(0xFF34d399)),
                          ),
                      ],
                    ),
                  ),

                  // ── Hold-to-launch progress overlay ──────────────────
                  if (canHold && _pressing)
                    Positioned.fill(
                      child: AnimatedBuilder(
                        animation: _fillAnim,
                        builder: (_, __) => Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.bottomCenter,
                              end: Alignment.topCenter,
                              colors: [
                                accent.withValues(alpha: 0.55 * _fillAnim.value),
                                accent.withValues(alpha: 0.0),
                              ],
                              stops: [_fillAnim.value, 1.0],
                            ),
                          ),
                        ),
                      ),
                    ),

                  // ── Hold-to-launch hint (bottom of card) ─────────────
                  if (canHold && !widget.launching)
                    Positioned(
                      bottom: 14,
                      left: 0,
                      right: 0,
                      child: Center(
                        child: AnimatedOpacity(
                          opacity: _pressing ? 1.0 : 0.5,
                          duration: const Duration(milliseconds: 150),
                          child: Text(
                            _pressing ? 'LAUNCHING…' : 'HOLD TO LAUNCH',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 2.5,
                              color: accent,
                            ),
                          ),
                        ),
                      ),
                    ),

                  // ── Launching spinner overlay ─────────────────────────
                  if (widget.launching && isFocused)
                    Positioned.fill(
                      child: Container(
                        color: Colors.black.withValues(alpha: 0.4),
                        child: Center(
                          child: CircularProgressIndicator(
                              strokeWidth: 2.5, color: accent),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    if (!canHold) return card;

    return GestureDetector(
      onTapDown: (_) => _onPressDown(),
      onTapUp: (_) => _onPressUp(),
      onTapCancel: _onPressUp,
      child: card,
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Station emblem (logo or icon)
// ─────────────────────────────────────────────────────────────────────────────

class _StationEmblem extends StatelessWidget {
  final Station station;
  final Color accent;
  final bool isFocused;

  const _StationEmblem({
    required this.station,
    required this.accent,
    required this.isFocused,
  });

  @override
  Widget build(BuildContext context) {
    final size = isFocused ? 100.0 : 72.0;
    return StationCard.buildEmblem(station, accent, size);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Status pill — no "Stopped" text, just a subtle icon indicator
// ─────────────────────────────────────────────────────────────────────────────

class _StatusPill extends StatelessWidget {
  final StationStatus status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    if (status == StationStatus.stopped) return const SizedBox.shrink();

    final (color, label, icon) = switch (status) {
      StationStatus.running => (
          const Color(0xFF34d399),
          'LIVE',
          Icons.circle,
        ),
      StationStatus.starting => (
          const Color(0xFFfbbf24),
          'STARTING',
          Icons.hourglass_top,
        ),
      StationStatus.error => (
          const Color(0xFFf87171),
          'ERROR',
          Icons.error_outline,
        ),
      StationStatus.stopped => (
          const Color(0xFF666666),
          '',
          Icons.circle,
        ),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 5),
          Text(label,
              style: TextStyle(
                  color: color,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5)),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pulsing green dot for running state
// ─────────────────────────────────────────────────────────────────────────────

class _PulsingDot extends StatefulWidget {
  final Color color;
  const _PulsingDot({required this.color});

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat(reverse: true);
    _anim = Tween(begin: 0.3, end: 1.0).animate(
        CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _anim,
      child: Container(
        width: 14,
        height: 14,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: widget.color,
          boxShadow: [
            BoxShadow(
                color: widget.color.withValues(alpha: 0.6), blurRadius: 8)
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Bottom action strip — open / stop / settings + dot indicators
// ─────────────────────────────────────────────────────────────────────────────

class _ActionStrip extends StatelessWidget {
  final Station station;
  final bool isRunning;
  final int stationCount;
  final int focusedIndex;
  final VoidCallback onStop;
  final VoidCallback onOpen;
  final Color accent;
  final ThemeData theme;

  const _ActionStrip({
    required this.station,
    required this.isRunning,
    required this.stationCount,
    required this.focusedIndex,
    required this.onStop,
    required this.onOpen,
    required this.accent,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    final theme = this.theme;
    final accent = this.accent;
    final isRunning = this.isRunning;

    return Container(
      height: 68,
      decoration: BoxDecoration(
        color: theme.scaffoldBackgroundColor,
        border: Border(
            top: BorderSide(color: theme.dividerColor.withValues(alpha: 0.5))),
      ),
      child: Row(
        children: [
          // ── Open dashboard (running) ──────────────────────────────────────
          if (isRunning)
            Expanded(
              flex: 5,
              child: GestureDetector(
                onTap: onOpen,
                child: Container(
                  margin: const EdgeInsets.fromLTRB(16, 10, 8, 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF34d399).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                        color: const Color(0xFF34d399).withValues(alpha: 0.5),
                        width: 1.5),
                  ),
                  child: Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.dashboard,
                            size: 20, color: Color(0xFF34d399)),
                        const SizedBox(width: 8),
                        Text(
                          'OPEN DASHBOARD',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 2,
                            color: const Color(0xFF34d399),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),

          // ── Stopped: dot indicators centred in the strip ──────────────────
          if (!isRunning)
            Expanded(
              child: Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: List.generate(stationCount, (i) {
                    final active = i == focusedIndex;
                    return AnimatedContainer(
                      duration: const Duration(milliseconds: 250),
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      width: active ? 20 : 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: active
                            ? accent
                            : accent.withValues(alpha: 0.25),
                        borderRadius: BorderRadius.circular(3),
                      ),
                    );
                  }),
                ),
              ),
            ),

          // ── Stop (running) ───────────────────────────────────────────────
          if (isRunning)
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 10, 8, 10),
              child: GestureDetector(
                onTap: onStop,
                child: Container(
                  width: 52,
                  decoration: BoxDecoration(
                    color: const Color(0xFFf87171).withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                        color: const Color(0xFFf87171).withValues(alpha: 0.4)),
                  ),
                  child: const Center(
                    child: Icon(Icons.stop_rounded,
                        size: 22, color: Color(0xFFf87171)),
                  ),
                ),
              ),
            ),

          // ── Settings gear ────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(0, 10, 16, 10),
            child: GestureDetector(
              onTap: () => context.go('/settings/connection'),
              child: Container(
                width: 52,
                decoration: BoxDecoration(
                  color: theme.cardColor,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: theme.dividerColor),
                ),
                child: Center(
                  child: Icon(Icons.settings,
                      size: 22,
                      color: theme.textTheme.bodySmall?.color),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Top bar (settings shortcut, minimal)
// ─────────────────────────────────────────────────────────────────────────────

class _TopBar extends StatelessWidget {
  final Color accent;
  const _TopBar({required this.accent});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 10, right: 16),
      child: Row(
        children: [
          Icon(Icons.radio, size: 18, color: accent.withValues(alpha: 0.5)),
          const SizedBox(width: 6),
          Text(
            'RADIO OS',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 3,
              color: accent.withValues(alpha: 0.4),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arrow nav buttons
// ─────────────────────────────────────────────────────────────────────────────

class _ArrowButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final Color accent;

  const _ArrowButton(
      {required this.icon, required this.onTap, required this.accent});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.black.withValues(alpha: 0.3),
          border: Border.all(color: accent.withValues(alpha: 0.2)),
        ),
        child: Icon(icon, color: accent.withValues(alpha: 0.6), size: 26),
      ),
    );
  }
}

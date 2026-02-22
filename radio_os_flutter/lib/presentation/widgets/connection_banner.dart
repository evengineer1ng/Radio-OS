/// Connection banner — shown when backend is unreachable.
/// Mirrors the Svelte conn-banner.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/providers.dart' as p;

class ConnectionBanner extends ConsumerWidget {
  const ConnectionBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(p.connectionStateProvider);

    if (state == p.ConnectionState.connected) {
      return const SizedBox.shrink();
    }

    final isConnecting = state == p.ConnectionState.connecting;
    final color =
        isConnecting ? const Color(0xFFfbbf24) : const Color(0xFFf87171);
    final text =
        isConnecting ? 'Connecting to Radio OS...' : 'Backend unavailable — retrying...';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 16),
      color: color.withValues(alpha: 0.15),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: color,
            ),
          ),
          const SizedBox(width: 8),
          Text(text,
              style: TextStyle(
                  color: color, fontSize: 12, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

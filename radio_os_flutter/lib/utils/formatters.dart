/// Formatting helpers — currency, dates, event summaries.
/// Ported from eventFormat.ts and utils.ts in the Svelte app.
library;

import 'package:intl/intl.dart';

/// Format a number as currency: $1,234,567
String formatMoney(num? value) {
  if (value == null || !value.isFinite) return r'$0';
  return '\$${NumberFormat('#,##0').format(value.round())}';
}

/// Format a percentage: 42.1%
String formatPct(num? value) {
  if (value == null || !value.isFinite) return '0%';
  return '${value.toStringAsFixed(1)}%';
}

/// Format a multiplier: 1.25x
String formatMult(num? value) {
  if (value == null || !value.isFinite) return '1.00x';
  return '${value.toStringAsFixed(2)}x';
}

/// Format file size: 1.2 MB
String formatBytes(int bytes) {
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  if (bytes < 1024 * 1024 * 1024) {
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
  return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
}

/// Format a duration in seconds to "2h 34m" or "5m 12s".
String formatDuration(int seconds) {
  if (seconds < 60) return '${seconds}s';
  if (seconds < 3600) {
    return '${seconds ~/ 60}m ${seconds % 60}s';
  }
  return '${seconds ~/ 3600}h ${(seconds % 3600) ~/ 60}m';
}

/// Humanize a snake_case or camelCase token: "race_result" → "Race Result".
String humanizeToken(String? token, {String fallback = 'Event'}) {
  if (token == null || token.isEmpty) return fallback;
  return token
      .replaceAll('_', ' ')
      .split(' ')
      .where((s) => s.isNotEmpty)
      .map((s) => s[0].toUpperCase() + s.substring(1))
      .join(' ');
}

/// Format a station event into a single-line summary.
/// Ported from eventFormat.ts `formatEventSummary`.
String formatEventSummary(dynamic evt) {
  if (evt is String) return evt.isNotEmpty ? evt : 'Event';

  if (evt is! Map<String, dynamic>) return 'Event';

  final data = (evt['data'] as Map<String, dynamic>?) ?? {};
  final category = (evt['category'] as String? ?? '').toLowerCase();

  // Try text candidates first.
  for (final key in ['description', 'text']) {
    final v = evt[key];
    if (v is String && v.isNotEmpty && v != '[object Object]') return v;
  }
  for (final key in ['message', 'description']) {
    final v = data[key];
    if (v is String && v.isNotEmpty && v != '[object Object]') return v;
  }

  // Category-specific formatters.
  if (category == 'race_result') {
    final driver = _s(data['driver'], 'Unknown driver');
    final team = _s(data['team'] ?? data['team_name'], 'Unknown team');
    final pos = _n(data['position']);
    final pts = _n(data['points']);
    final track = _s(data['track_name']);
    final trackChunk = track.isNotEmpty ? ' at $track' : '';
    return '$driver ($team) finished P${pos > 0 ? pos : '—'}$trackChunk ($pts pts)';
  }

  if (category == 'sponsor_payment') {
    final sponsor = _s(data['sponsor_name'], 'Sponsor');
    final amount = formatMoney(data['amount'] as num?);
    return '$sponsor payment: $amount';
  }

  if (category == 'staff_change') {
    final who = _s(data['entity'] ?? data['entity_name'], 'Staff');
    final role = _s(data['type'], 'staff');
    final action = _s(data['action'], 'updated');
    final team = _s(data['team'] ?? data['team_name'], 'team');
    return '$role $who was $action by $team';
  }

  if (category == 'team_fold') {
    final team = _s(data['team'], 'Team');
    final reason = _s(data['fold_reason'], 'financial collapse');
    return '$team folded ($reason)';
  }

  if (category == 'team_spawned') {
    final team = _s(data['team_name'], 'New team');
    final tier = _n(data['tier']);
    final replaced = _s(data['replaced_team']);
    final tierLabel = tier > 0 ? 'Tier $tier' : 'new tier';
    final replacedChunk = replaced.isNotEmpty ? ' replacing $replaced' : '';
    return '$team entered $tierLabel$replacedChunk';
  }

  // Fallback: show key fields.
  final label = humanizeToken(evt['category'] as String? ?? evt['type'] as String?);
  final parts = <String>[];
  for (final key in ['team', 'driver', 'entity', 'track_name', 'position', 'points', 'amount', 'status']) {
    final v = data[key];
    if (v == null || v.toString().isEmpty) continue;
    final vStr = key == 'amount' ? formatMoney(v as num?) : v.toString();
    parts.add('${key.replaceAll('_', ' ')}: $vStr');
  }
  if (parts.isNotEmpty) return '$label • ${parts.join(' • ')}';
  return label;
}

String _s(dynamic v, [String fallback = '']) {
  if (v == null) return fallback;
  final s = v.toString().trim();
  return s.isEmpty ? fallback : s;
}

int _n(dynamic v, [int fallback = 0]) {
  if (v is num) return v.toInt();
  if (v is String) return int.tryParse(v) ?? fallback;
  return fallback;
}

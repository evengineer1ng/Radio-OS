/// Event and notification models.
library;

class StationEvent {
  final String? type;
  final String? category;
  final int? tick;
  final DateTime timestamp;
  final Map<String, dynamic> data;
  final String? description;

  const StationEvent({
    this.type,
    this.category,
    this.tick,
    required this.timestamp,
    this.data = const {},
    this.description,
  });

  factory StationEvent.fromJson(Map<String, dynamic> json) {
    return StationEvent(
      type: json['type'] as String?,
      category: json['category'] as String?,
      tick: (json['tick'] as num?)?.toInt() ?? (json['ts'] as num?)?.toInt(),
      timestamp: DateTime.now(),
      data: json['data'] as Map<String, dynamic>? ?? json,
      description: json['description'] as String? ??
          json['text'] as String? ??
          (json['data'] as Map<String, dynamic>?)?['message'] as String?,
    );
  }
}

class NotificationItem {
  final String id;
  final String title;
  final String body;
  final String category;
  final DateTime timestamp;
  final bool read;
  final Map<String, dynamic>? actionPayload;

  const NotificationItem({
    required this.id,
    required this.title,
    required this.body,
    this.category = 'system',
    required this.timestamp,
    this.read = false,
    this.actionPayload,
  });

  NotificationItem copyWith({bool? read}) {
    return NotificationItem(
      id: id,
      title: title,
      body: body,
      category: category,
      timestamp: timestamp,
      read: read ?? this.read,
      actionPayload: actionPayload,
    );
  }

  factory NotificationItem.fromJson(Map<String, dynamic> json) {
    return NotificationItem(
      id: json['id']?.toString() ??
          DateTime.now().microsecondsSinceEpoch.toString(),
      title: json['title'] as String? ?? '',
      body: json['body'] as String? ?? json['text'] as String? ?? '',
      category: json['category'] as String? ?? 'system',
      timestamp: DateTime.now(),
    );
  }
}

/// Structured audio event received over WebSocket.
class AudioEvent {
  final String audioType; // "music", "engine", "crash", "crowd", "ambient", "ui"
  final String? filePath;
  final double volume;
  final bool loop;
  final String? variant;
  final Map<String, dynamic> extra;

  const AudioEvent({
    required this.audioType,
    this.filePath,
    this.volume = 1.0,
    this.loop = false,
    this.variant,
    this.extra = const {},
  });

  factory AudioEvent.fromJson(Map<String, dynamic> json) {
    return AudioEvent(
      audioType: json['audio_type'] as String? ?? json['type'] as String? ?? 'sfx',
      filePath: json['file_path'] as String? ?? json['path'] as String?,
      volume: (json['volume'] as num?)?.toDouble() ?? 1.0,
      loop: json['loop'] as bool? ?? false,
      variant: json['variant'] as String?,
      extra: json,
    );
  }
}

/// Metadata for a voice audio segment from the WAV WebSocket stream.
class AudioSegmentMeta {
  final String voice;
  final String speaker;
  final String text;
  final double duration;
  final int sampleRate;
  final int timestamp;

  const AudioSegmentMeta({
    required this.voice,
    required this.speaker,
    required this.text,
    required this.duration,
    required this.sampleRate,
    required this.timestamp,
  });

  factory AudioSegmentMeta.fromJson(Map<String, dynamic> json) {
    return AudioSegmentMeta(
      voice: json['voice'] as String? ?? '',
      speaker: json['speaker'] as String? ?? '',
      text: json['text'] as String? ?? '',
      duration: (json['duration'] as num?)?.toDouble() ?? 0.0,
      sampleRate: (json['sr'] as num?)?.toInt() ?? 24000,
      timestamp: (json['ts'] as num?)?.toInt() ?? 0,
    );
  }
}

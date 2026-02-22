/// Station data model — mirrors the station discovery from web_server.py.
library;

enum StationStatus { stopped, starting, running, error }

class Station {
  final String id;
  final String name;
  final String category;
  final String host;
  final String metaPlugin;
  final String logoPath;
  final StationStatus status;
  final int? pid;
  final int? uptimeSec;
  final int? webPort;

  const Station({
    required this.id,
    required this.name,
    this.category = '',
    this.host = '',
    this.metaPlugin = 'radio_station',
    this.logoPath = '',
    this.status = StationStatus.stopped,
    this.pid,
    this.uptimeSec,
    this.webPort,
  });

  Station copyWith({
    StationStatus? status,
    int? pid,
    int? uptimeSec,
    int? webPort,
  }) {
    return Station(
      id: id,
      name: name,
      category: category,
      host: host,
      metaPlugin: metaPlugin,
      logoPath: logoPath,
      status: status ?? this.status,
      pid: pid ?? this.pid,
      uptimeSec: uptimeSec ?? this.uptimeSec,
      webPort: webPort ?? this.webPort,
    );
  }

  factory Station.fromJson(Map<String, dynamic> json) {
    return Station(
      id: json['station_id'] as String? ?? json['id'] as String? ?? '',
      name: json['name'] as String? ?? json['station_id'] as String? ?? '',
      category: json['category'] as String? ?? '',
      host: json['host'] as String? ?? '',
      metaPlugin: json['meta_plugin'] as String? ?? 'radio_station',
      logoPath: json['logo'] as String? ?? '',
    );
  }

  /// The UI module type derived from meta_plugin.
  StationModuleType get moduleType {
    switch (metaPlugin) {
      case 'ftb_narrator_plugin':
        return StationModuleType.ftb;
      case 'ok_narrator_plugin':
        return StationModuleType.oracleKingdom;
      case 'neikos_narrator':
        return StationModuleType.neikos;
      case 'radio_station':
      default:
        return StationModuleType.radio;
    }
  }
}

enum StationModuleType { ftb, oracleKingdom, radio, neikos }

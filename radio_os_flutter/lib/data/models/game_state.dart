/// FTB game state models — mirrors stores.ts gameState shape.
library;

class FTBGameState {
  final String status; // "no_game", "running", "busy"
  final int tick;
  final String dateStr;
  final String phase; // "development", "race_weekend", "offseason"
  final String timeMode; // "paused", "playing"
  final String controlMode; // "human", "ai"
  final int seasonNumber;
  final Map<String, dynamic>? playerTeam;
  final List<dynamic> aiTeams;
  final Map<String, dynamic> leagues;
  final List<dynamic> freeAgents;
  final List<dynamic> jobBoard;
  final List<dynamic> recentEvents;
  final List<dynamic> playerDriverRecentResults;
  final List<dynamic> promotionOpportunities;
  final List<dynamic> pendingDecisions;
  final Map<String, dynamic> sponsorships;
  final List<dynamic> penalties;
  final PlayByPlayState playByPlay;
  final Map<String, dynamic>? raceDay;
  final List<dynamic> partsMarketplace;
  final Map<String, dynamic> managerCareer;
  final Map<String, dynamic> history;
  final Map<String, dynamic> delegationSettings;
  final Map<String, dynamic> tracks;
  final String? gameId;

  const FTBGameState({
    this.status = 'no_game',
    this.tick = 0,
    this.dateStr = '',
    this.phase = 'development',
    this.timeMode = 'paused',
    this.controlMode = 'human',
    this.seasonNumber = 0,
    this.playerTeam,
    this.aiTeams = const [],
    this.leagues = const {},
    this.freeAgents = const [],
    this.jobBoard = const [],
    this.recentEvents = const [],
    this.playerDriverRecentResults = const [],
    this.promotionOpportunities = const [],
    this.pendingDecisions = const [],
    this.sponsorships = const {},
    this.penalties = const [],
    this.playByPlay = const PlayByPlayState(),
    this.raceDay,
    this.partsMarketplace = const [],
    this.managerCareer = const {},
    this.history = const {},
    this.delegationSettings = const {},
    this.tracks = const {},
    this.gameId,
  });

  bool get hasGame => status == 'running' && playerTeam != null;

  String get teamName =>
      (playerTeam?['name'] as String?)?.trim() ?? '';

  double get cash =>
      (playerTeam?['budget']?['cash'] as num?)?.toDouble() ?? 0.0;

  factory FTBGameState.fromJson(Map<String, dynamic> json) {
    return FTBGameState(
      status: json['status'] as String? ?? 'no_game',
      tick: (json['tick'] as num?)?.toInt() ?? 0,
      dateStr: json['date_str'] as String? ?? '',
      phase: json['phase'] as String? ?? 'development',
      timeMode: json['time_mode'] as String? ?? 'paused',
      controlMode: json['control_mode'] as String? ?? 'human',
      seasonNumber: (json['season_number'] as num?)?.toInt() ?? 0,
      playerTeam: json['player_team'] as Map<String, dynamic>?,
      aiTeams: json['ai_teams'] as List<dynamic>? ?? [],
      leagues: json['leagues'] as Map<String, dynamic>? ?? {},
      freeAgents: json['free_agents'] as List<dynamic>? ?? [],
      jobBoard: json['job_board'] as List<dynamic>? ?? [],
      recentEvents: json['recent_events'] as List<dynamic>? ?? [],
      playerDriverRecentResults:
          json['player_driver_recent_results'] as List<dynamic>? ?? [],
      promotionOpportunities:
          json['promotion_opportunities'] as List<dynamic>? ?? [],
      pendingDecisions:
          json['pending_decisions'] as List<dynamic>? ?? [],
      sponsorships:
          json['sponsorships'] as Map<String, dynamic>? ?? {},
      penalties: json['penalties'] as List<dynamic>? ?? [],
      playByPlay: json['play_by_play'] != null
          ? PlayByPlayState.fromJson(
              json['play_by_play'] as Map<String, dynamic>)
          : const PlayByPlayState(),
      raceDay: json['race_day'] as Map<String, dynamic>?,
      partsMarketplace:
          json['parts_marketplace'] as List<dynamic>? ?? [],
      managerCareer:
          json['manager_career'] as Map<String, dynamic>? ?? {},
      history: json['history'] as Map<String, dynamic>? ?? {},
      delegationSettings:
          json['delegation_settings'] as Map<String, dynamic>? ?? {},
      tracks: json['tracks'] as Map<String, dynamic>? ?? {},
      gameId: json['game_id'] as String?,
    );
  }
}

class PlayByPlayState {
  final bool isLive;
  final Map<String, dynamic> lapInfo;
  final List<dynamic> standings;
  final List<dynamic> liveEvents;
  final Map<String, dynamic> telemetry;
  final List<dynamic> historyEntries;

  const PlayByPlayState({
    this.isLive = false,
    this.lapInfo = const {'current': 0, 'total': 0},
    this.standings = const [],
    this.liveEvents = const [],
    this.telemetry = const {},
    this.historyEntries = const [],
  });

  int get currentLap => (lapInfo['current'] as num?)?.toInt() ?? 0;
  int get totalLaps => (lapInfo['total'] as num?)?.toInt() ?? 0;

  factory PlayByPlayState.fromJson(Map<String, dynamic> json) {
    return PlayByPlayState(
      isLive: json['is_live'] as bool? ?? false,
      lapInfo: json['lap_info'] as Map<String, dynamic>? ??
          {'current': 0, 'total': 0},
      standings: json['standings'] as List<dynamic>? ?? [],
      liveEvents: json['live_events'] as List<dynamic>? ?? [],
      telemetry: json['telemetry'] as Map<String, dynamic>? ?? {},
      historyEntries: json['history'] as List<dynamic>? ?? [],
    );
  }
}

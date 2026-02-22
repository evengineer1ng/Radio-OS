/* ═══════════════════════════════════════════════════════════
   Oracle Kingdom — Web Frontend Application
   ═══════════════════════════════════════════════════════════
   Pure JS, no build step.  Talks to FastAPI on /ok/* endpoints.
*/

const API = '';  // same origin
let gameState = null;
let courtState = null;
let paused = true;
let pollTimer = null;
let selectedDecree = null;
let currentDecrees = [];

// ── Oracle trait definitions ──────────────────────────────
const TRAITS = [
  'clarity', 'conviction', 'empathy', 'severity', 'ambition',
  'humility', 'self_belief', 'doubt', 'paranoia', 'charisma',
];
const POINT_POOL = 250;
const TRAIT_MIN = 5;
const TRAIT_MAX = 50;

// ── Location metadata ─────────────────────────────────────
const LOCATIONS = {
  COURTYARD:    { icon: '🏛', name: 'Courtyard' },
  WAR_CHAMBER:  { icon: '⚔️', name: 'War Chamber' },
  TEMPLE:       { icon: '🕯', name: 'Temple' },
  HARBOR:       { icon: '⚓', name: 'Harbor' },
  LIBRARY:      { icon: '📚', name: 'Library' },
  OBSERVATORY:  { icon: '🔭', name: 'Observatory' },
  TREASURY:     { icon: '💰', name: 'Treasury' },
  RAMPARTS:     { icon: '🏰', name: 'Ramparts' },
  THRONE_ROOM:  { icon: '👑', name: 'Throne Room' },
};

// ── Presets ────────────────────────────────────────────────
const PRESETS = {
  balanced: { clarity:25, conviction:25, empathy:25, severity:25, ambition:25,
              humility:25, self_belief:25, doubt:25, paranoia:25, charisma:25 },
  tyrant:   { clarity:15, conviction:40, empathy:8, severity:45, ambition:40,
              humility:5, self_belief:35, doubt:10, paranoia:35, charisma:17 },
  mystic:   { clarity:35, conviction:20, empathy:30, severity:10, ambition:15,
              humility:35, self_belief:30, doubt:35, paranoia:10, charisma:30 },
  diplomat: { clarity:30, conviction:20, empathy:40, severity:10, ambition:20,
              humility:30, self_belief:25, doubt:15, paranoia:15, charisma:45 },
};

// ═══════════════════════════════════════════════════════════
// SCREEN MANAGEMENT
// ═══════════════════════════════════════════════════════════

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (id === 'screen-new-game') buildTraitSliders();
  if (id === 'screen-game' && !pollTimer) startPolling();
  if (id !== 'screen-game' && pollTimer) stopPolling();
  // Close any open modals when leaving the game
  if (id !== 'screen-game') {
    document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
  }
}

// ═══════════════════════════════════════════════════════════
// CHARACTER CREATION
// ═══════════════════════════════════════════════════════════

function buildTraitSliders() {
  const container = document.getElementById('trait-sliders');
  if (container.children.length > 0) return; // already built
  TRAITS.forEach(trait => {
    const row = document.createElement('div');
    row.className = 'trait-row';
    row.innerHTML = `
      <label>${trait.replace('_',' ')}</label>
      <input type="range" min="${TRAIT_MIN}" max="${TRAIT_MAX}" value="25"
             data-trait="${trait}" oninput="updateTraitDisplay()">
      <span class="trait-val" id="val-${trait}">25</span>
    `;
    container.appendChild(row);
  });
  updateTraitDisplay();
}

function updateTraitDisplay() {
  let total = 0;
  TRAITS.forEach(t => {
    const slider = document.querySelector(`input[data-trait="${t}"]`);
    const val = parseInt(slider.value);
    document.getElementById(`val-${t}`).textContent = val;
    total += val;
  });
  const remaining = POINT_POOL - total;
  document.getElementById('points-remaining').textContent = remaining;
  const btn = document.getElementById('btn-create');
  btn.disabled = remaining !== 0;
}

function applyPreset(name) {
  if (name === 'random') {
    // Random allocation
    let vals = TRAITS.map(() => 25);
    let remaining = 0;
    for (let i = 0; i < 50; i++) {
      const a = Math.floor(Math.random() * TRAITS.length);
      const b = Math.floor(Math.random() * TRAITS.length);
      if (a === b) continue;
      const amt = Math.floor(Math.random() * 5) + 1;
      if (vals[a] + amt <= TRAIT_MAX && vals[b] - amt >= TRAIT_MIN) {
        vals[a] += amt;
        vals[b] -= amt;
      }
    }
    TRAITS.forEach((t, i) => {
      document.querySelector(`input[data-trait="${t}"]`).value = vals[i];
    });
  } else {
    const preset = PRESETS[name];
    if (!preset) return;
    TRAITS.forEach(t => {
      document.querySelector(`input[data-trait="${t}"]`).value = preset[t];
    });
  }
  updateTraitDisplay();
}

// ═══════════════════════════════════════════════════════════
// API CALLS
// ═══════════════════════════════════════════════════════════

async function apiPost(path, body) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  // FastAPI 500 errors come back as {"detail": "..."} — normalise to {error: ...}
  if (!res.ok && !data.error && data.detail) {
    data.error = data.detail;
  }
  return data;
}

async function apiGet(path) {
  const res = await fetch(API + path);
  const data = await res.json();
  if (!res.ok && !data.error && data.detail) {
    data.error = data.detail;
  }
  return data;
}

// ═══════════════════════════════════════════════════════════
// GAME LIFECYCLE
// ═══════════════════════════════════════════════════════════

async function createGame() {
  const allocation = {};
  let total = 0;
  TRAITS.forEach(t => {
    allocation[t] = parseInt(document.querySelector(`input[data-trait="${t}"]`).value);
    total += allocation[t];
  });
  if (total !== POINT_POOL) { alert(`Points must sum to ${POINT_POOL} (got ${total})`); return; }

  const timePreset = document.getElementById('time-preset').value;
  await apiPost('/ok/command', {
    action: 'new_game',
    oracle_allocation: allocation,
    time_preset: timePreset,
  });

  // Wait for the controller thread to process new_game, then init court.
  // The command is async (queued), so we poll for state readiness.
  let courtOk = false;
  for (let attempt = 0; attempt < 6; attempt++) {
    await sleep(500);
    try {
      const courtRes = await apiPost('/ok/court/init', {});
      if (courtRes && courtRes.status === 'ok') {
        courtOk = true;
        console.log('[OK] Court initialized, agents:', courtRes.agents);
        break;
      }
      if (courtRes && courtRes.error) {
        console.warn(`[OK] Court init attempt ${attempt+1}:`, courtRes.error);
        // "no game loaded" means the controller hasn't processed the command yet — retry
        if (courtRes.error !== 'no game loaded') {
          showError('Court init: ' + courtRes.error);
          break;
        }
      }
    } catch (e) {
      console.warn(`[OK] Court init attempt ${attempt+1} threw:`, e);
    }
  }
  if (!courtOk) {
    console.warn('[OK] Court init did not succeed after retries');
  }

  await sleep(300);
  await refreshState();
  showScreen('screen-game');
}

// ─── Load game screen ────────────────────────────────────

async function openLoadScreen() {
  showScreen('screen-load');
  await populateSaveList();
}

async function populateSaveList() {
  const container = document.getElementById('save-list');
  container.innerHTML = '<p class="muted">Loading save files…</p>';
  try {
    const saves = await apiGet('/ok/saves');
    if (!Array.isArray(saves) || saves.length === 0) {
      container.innerHTML = '<p class="muted">No save files found. Start a new kingdom.</p>';
      return;
    }
    let html = '';
    for (const s of saves) {
      const absText = s.absence_ticks > 0
        ? `<span class="absence-warning">⏳ ${_formatAbsence(s.absence_ticks)} of in-game time passed</span>`
        : `<span class="absence-ok">✓ Up to date</span>`;
      const savedAt = s.saved_ts > 0 ? new Date(s.saved_ts * 1000).toLocaleString() : 'Unknown';
      const healthCls = s.health > 60 ? 'health-high' : s.health > 35 ? 'health-mid' : 'health-low';
      html += `
        <div class="save-card" onclick="loadSave('${escHtml(s.filename)}')">
          <div class="save-card-top">
            <span class="save-kingdom">${escHtml(s.kingdom)}</span>
            <span class="save-health ${healthCls}">♥ ${s.health}</span>
          </div>
          <div class="save-card-mid">
            <span class="save-name">${escHtml(s.name)}</span>
            ${s.is_autosave ? '<span class="save-badge">autosave</span>' : ''}
          </div>
          <div class="save-card-bot">
            <span class="muted">Year ${s.world_year} · Tick ${s.tick}</span>
            <span class="muted">${savedAt}</span>
            ${absText}
          </div>
        </div>`;
    }
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<p class="muted" style="color:var(--danger)">⚠ Could not fetch saves: ${e.message}</p>`;
  }
}

function _formatAbsence(ticks) {
  if (ticks < 10) return `${ticks} tick${ticks !== 1 ? 's' : ''}`;
  if (ticks < 365) return `${ticks} days`;
  const years = (ticks / 365).toFixed(1);
  return `~${years} years`;
}

async function loadSave(filename) {
  // POST to the dedicated /ok/load endpoint
  const res = await apiPost('/ok/load', { filename });
  if (res && res.error) {
    showError(res.error);
    return;
  }

  // Poll until state is loaded (controller processes the queued command)
  let loaded = false;
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(400);
    try {
      const snap = await apiGet('/ok/state');
      if (snap && !snap.error) { loaded = true; break; }
    } catch(_) {}
  }
  if (!loaded) { showError('Load timed out — try again'); return; }

  // Init court for the loaded game
  for (let attempt = 0; attempt < 6; attempt++) {
    await sleep(400);
    try {
      const courtRes = await apiPost('/ok/court/init', {});
      if (courtRes && courtRes.status === 'ok') break;
      if (courtRes && courtRes.error && courtRes.error !== 'no game loaded') break;
    } catch(_) {}
  }

  await refreshState();
  showScreen('screen-game');

  // Check if reconstruction is needed and show overlay
  if (gameState && gameState._reconstruction && gameState._reconstruction.pending) {
    showReconstructionOverlay(gameState._reconstruction);
  }
}

// ─── Save dialog ─────────────────────────────────────────

function openSaveDialog() {
  const input = document.getElementById('save-name-input');
  if (input) {
    // Pre-fill with kingdom + year as a sensible default
    const pk = gameState && gameState.player_kingdom;
    if (pk) {
      input.value = `${pk.name || 'Kingdom'} — Year ${pk.world_year || 1}`;
      input.select();
    } else {
      input.value = '';
    }
  }
  document.getElementById('modal-save').style.display = 'flex';
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

async function confirmSave() {
  const name = (document.getElementById('save-name-input').value || '').trim();
  closeModal('modal-save');
  const res = await apiPost('/ok/save', { name });
  if (res && res.error) {
    showError('Save failed: ' + res.error);
  } else {
    const label = name || 'autosave';
    showError(`✓ Saved as "${label}"`);
  }
}

// ─── Legacy alias kept for any old refs ──────────────────
async function saveGame() { openSaveDialog(); }

// ─── Reconstruction overlay ──────────────────────────────

function showReconstructionOverlay(reconInfo) {
  const overlay = document.getElementById('modal-reconstruction');
  const totalTicks = reconInfo.total_ticks || 0;
  const subtitle = document.getElementById('recon-subtitle');
  subtitle.textContent = `${_formatAbsence(totalTicks)} of kingdom time must be replayed.`;
  setReconProgress(0, 'Beginning reconstruction…');
  document.getElementById('recon-event-log').innerHTML = '';
  overlay.style.display = 'flex';
}

function hideReconstructionOverlay() {
  document.getElementById('modal-reconstruction').style.display = 'none';
}

function setReconProgress(fraction, phaseLabel) {
  const pct = Math.round(fraction * 100);
  document.getElementById('recon-progress-fill').style.width = pct + '%';
  document.getElementById('recon-phase').textContent = phaseLabel;
}

function appendReconEvent(text) {
  const log = document.getElementById('recon-event-log');
  const entry = document.createElement('div');
  entry.className = 'recon-event-entry';
  entry.textContent = text;
  log.prepend(entry);
  // Keep log short
  while (log.children.length > 12) log.removeChild(log.lastChild);
}

async function reconstructNext() {
  const btn = document.getElementById('btn-recon-next');
  if (btn) btn.disabled = true;
  const res = await apiPost('/ok/reconstruct/next', {});
  if (res && res.error) { showError(res.error); if (btn) btn.disabled = false; return; }
  // Poll for the phase result
  await sleep(600);
  await pollReconstructionStatus();
  if (btn) btn.disabled = false;
}

async function reconstructAll() {
  document.getElementById('btn-recon-all').disabled = true;
  document.getElementById('btn-recon-next').disabled = true;
  const res = await apiPost('/ok/reconstruct/all', {});
  if (res && res.error) {
    showError(res.error);
    document.getElementById('btn-recon-all').disabled = false;
    document.getElementById('btn-recon-next').disabled = false;
    return;
  }
  // Poll until complete
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    const done = await pollReconstructionStatus();
    if (done) break;
  }
}

// Returns true if reconstruction is complete
async function pollReconstructionStatus() {
  try {
    const status = await apiGet('/ok/reconstruct/status');
    if (!status || status.error) return false;

    if (status.status === 'idle' || status.complete) {
      setReconProgress(1.0, 'Complete — the kingdom awaits.');
      await sleep(800);
      hideReconstructionOverlay();
      await refreshState();
      return true;
    }

    if (status.status === 'in_progress') {
      setReconProgress(status.progress || 0, _reconPhaseLabel(status));
      // Append any newly completed phases to the log
      const phases = status.phases_completed || [];
      if (phases.length > 0) {
        const last = phases[phases.length - 1];
        if (last && last.phase_name) {
          appendReconEvent(`${last.phase_name}: ${last.new_events_count || 0} events across ${last.ticks_processed || 0} ticks`);
        }
      }
    }
    return false;
  } catch(e) {
    return false;
  }
}

function _reconPhaseLabel(status) {
  const names = ['silence', 'ripples', 'thresholds', 'succession', 'compound', 'myth', 'present'];
  const idx = status.phase_index || 0;
  const name = names[idx] || `phase ${idx + 1}`;
  const pct = Math.round((status.progress || 0) * 100);
  return `${name.charAt(0).toUpperCase() + name.slice(1)} (${pct}%)`;
}

async function togglePause() {
  if (paused) {
    await apiPost('/ok/command', { action: 'resume' });
    paused = false;
    document.getElementById('btn-pause').textContent = '⏸ Pause';
  } else {
    await apiPost('/ok/command', { action: 'pause' });
    paused = true;
    document.getElementById('btn-pause').textContent = '▶ Resume';
  }
}

async function manualTick() {
  await apiPost('/ok/command', { action: 'tick' });
  // Also tick court
  try {
    let res = await apiPost('/ok/court/tick', {});
    if (res && res.error === 'court not initialized') {
      await ensureCourtInit();
      res = await apiPost('/ok/court/tick', {});
    }
    if (res && res.error) console.warn('[OK] court tick:', res.error);
  } catch(e) {}
  await sleep(200);
  await refreshState();
}

// ═══════════════════════════════════════════════════════════
// POLLING
// ═══════════════════════════════════════════════════════════

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    await refreshState();
    await refreshEvents();
    await refreshNarration();
  }, 2500);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function refreshState() {
  try {
    gameState = await apiGet('/ok/state');
    if (gameState && !gameState.error) {
      try {
        courtState = await apiGet('/ok/court/state');
      } catch(e) { courtState = null; }
      renderGame();

      // If reconstruction overlay is not visible but state says it's pending, show it
      const overlay = document.getElementById('modal-reconstruction');
      const recon = gameState._reconstruction;
      if (recon && recon.pending && !recon.complete && overlay.style.display === 'none') {
        showReconstructionOverlay(recon);
      }
    }
  } catch(e) {
    console.error('State refresh failed:', e);
  }
}

async function refreshEvents() {
  try {
    const evts = await apiGet('/ok/events');
    if (Array.isArray(evts) && evts.length > 0) {
      renderEvents(evts);
    }
  } catch(e) {}
}

// ── Narration Feed (LLM-generated content) ────────────────
let lastNarrationTs = 0;

async function refreshNarration() {
  try {
    const items = await apiGet('/ok/narration');
    if (Array.isArray(items) && items.length > 0) {
      renderNarration(items);
    }
  } catch(e) {}
}

function renderNarration(items) {
  const container = document.getElementById('narration-feed');
  if (!container) return;

  // Only render items we haven't seen yet
  const newItems = items.filter(n => n.timestamp > lastNarrationTs);
  if (newItems.length === 0 && container.querySelector('.narration-entry')) return;

  if (newItems.length > 0) {
    lastNarrationTs = Math.max(...newItems.map(n => n.timestamp));
  }

  const voiceIcons = {
    narrator: '🔮',
    court_agents: '🗣️',
    chronicler: '📖',
    oracle_inner: '💭',
    host: '🎙️',
  };
  const typeLabels = {
    awakening_atmosphere: 'The Oracle Awakens',
    ambient_atmosphere: 'Atmosphere',
    agent_dialogue: 'Court Voices',
    reconstruction_chronicle: 'Chronicle',
    decree_consequence: 'Consequence',
  };

  let html = '';
  // Show most recent first, limit to 8
  const display = items.slice(-8).reverse();
  for (const n of display) {
    const icon = voiceIcons[n.voice] || '📜';
    const label = typeLabels[n.type] || n.type || 'Narration';
    const isAwakening = n.type === 'awakening_atmosphere';
    html += `<div class="narration-entry${isAwakening ? ' narration-awakening' : ''}">
      <div class="narration-header">
        <span class="narration-icon">${icon}</span>
        <span class="narration-label">${label}</span>
      </div>
      <div class="narration-text">${escapeHtml(n.text)}</div>
    </div>`;
  }

  container.innerHTML = html || '<p class="muted">The Oracle stirs...</p>';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
// Short alias used in save list rendering
const escHtml = escapeHtml;

// ═══════════════════════════════════════════════════════════
// LOCATION
// ═══════════════════════════════════════════════════════════

async function ensureCourtInit() {
  // Lazy court initialization — if the court wasn't set up at game
  // start, try once now so the next call can proceed.
  try {
    const r = await apiPost('/ok/court/init', {});
    return r && r.status === 'ok';
  } catch(e) { return false; }
}

async function moveToLocation(locId) {
  try {
    let res = await apiPost('/ok/court/move', { location: locId });
    if (res && res.error === 'court not initialized') {
      await ensureCourtInit();
      res = await apiPost('/ok/court/move', { location: locId });
    }
    if (res.error) { console.warn('[OK] move error:', res.error); showError(res.error); return; }
  } catch (e) { console.error('[OK] move failed:', e); showError('Move failed — server error'); return; }
  // Transition ambient audio to new room
  if (AmbientEngine.running) AmbientEngine.setRoom(locId);
  await sleep(200);
  await refreshState();
}

// ═══════════════════════════════════════════════════════════
// DECREES
// ═══════════════════════════════════════════════════════════

async function generateDecrees() {
  const btn = document.querySelector('.decree-header .btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating...'; }
  try {
    let res = await apiPost('/ok/court/decrees', {});
    // Auto-init court if it wasn't initialized yet
    if (res && res.error === 'court not initialized') {
      await ensureCourtInit();
      res = await apiPost('/ok/court/decrees', {});
    }
    if (res && res.options) {
      currentDecrees = res.options;
      selectedDecree = null;
      renderDecreeOptions(currentDecrees);
    } else if (res && res.error) {
      console.warn('[OK] decrees error:', res.error);
      showError(res.error);
      document.getElementById('decree-options').innerHTML =
        `<p class="muted" style="color:var(--danger)">⚠ ${res.error}</p>`;
    }
  } catch (e) {
    console.error('[OK] decrees failed:', e);
    showError('Generate decrees failed — server error');
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Generate Options'; }
}

function selectDecree(idx) {
  selectedDecree = idx;
  renderDecreeOptions(currentDecrees);
}

async function confirmDecree() {
  if (selectedDecree === null || !currentDecrees[selectedDecree]) return;
  const option = currentDecrees[selectedDecree];
  try {
    let res = await apiPost('/ok/court/decree', { option_index: selectedDecree });
    if (res && res.error === 'court not initialized') {
      await ensureCourtInit();
      res = await apiPost('/ok/court/decree', { option_index: selectedDecree });
    }
    if (res && res.error) { showError(res.error); return; }
  } catch (e) { showError('Decree failed — server error'); return; }
  currentDecrees = [];
  selectedDecree = null;
  document.getElementById('decree-options').innerHTML =
    '<p class="muted">Decree issued. The court stirs...</p>';
  await sleep(300);
  await refreshState();
}

// ═══════════════════════════════════════════════════════════
// RENDERING
// ═══════════════════════════════════════════════════════════

function renderGame() {
  if (!gameState || !gameState.player_kingdom) return;
  const pk = gameState.player_kingdom;

  // Header
  document.getElementById('hdr-kingdom-name').textContent = pk.name || 'Kingdom';
  document.getElementById('hdr-era').textContent = pk.current_era || 'STABLE';
  document.getElementById('hdr-year').textContent = `Year ${pk.world_year || 1}`;
  document.getElementById('hdr-tick').textContent = `Tick ${pk.tick || 0}`;
  const health = pk.health ? pk.health.resource_stability : 50;
  const composite = getComposite(pk.health);
  const hEl = document.getElementById('hdr-health');
  hEl.textContent = `♥ ${Math.round(composite)}`;
  hEl.className = 'health-badge ' + (composite > 60 ? 'health-high' : composite > 35 ? 'health-mid' : 'health-low');

  // Locations
  renderLocations();

  // Layer bars
  renderLayers(pk);

  // Court agents
  if (courtState && courtState.agents) renderAgents(courtState);

  // Oracle psychology
  renderPsychology(pk);

  // Oracle identity
  if (courtState && courtState.oracle_identity) {
    document.getElementById('oracle-archetype').textContent =
      courtState.oracle_identity.archetype || 'Unknown';
  }

  // CTAs
  if (courtState) renderCTAs(courtState);

  // Inner thoughts
  if (courtState && courtState.inner_state) renderThoughts(courtState.inner_state);
}

function getComposite(h) {
  if (!h) return 50;
  return (
    (h.resource_stability || 50) * 0.20 +
    (h.social_cohesion || 50) * 0.20 +
    (h.political_legitimacy || 50) * 0.20 +
    (h.cultural_confidence || 50) * 0.15 +
    (h.institutional_strength || 50) * 0.15 +
    (100 - (h.external_threat_pressure || 10)) * 0.10
  );
}

function renderLocations() {
  const container = document.getElementById('location-list');
  const currentLoc = courtState ? courtState.current_location : 'THRONE_ROOM';

  let html = '';
  for (const [id, meta] of Object.entries(LOCATIONS)) {
    const active = id === currentLoc ? 'active' : '';
    html += `<button class="loc-btn ${active}" onclick="moveToLocation('${id}')">
      <span class="loc-icon">${meta.icon}</span>${meta.name}
    </button>`;
  }
  container.innerHTML = html;

  // Current location info
  const loc = LOCATIONS[currentLoc] || LOCATIONS.THRONE_ROOM;
  document.getElementById('loc-name').textContent = loc.name;

  const descriptions = {
    COURTYARD: 'Open air, public gaze. Merchants call, dissidents murmur, pilgrims gather.',
    WAR_CHAMBER: 'Maps and steel. Generals speak in certainties. Hesitation is weakness.',
    TEMPLE: 'Incense and whispered prayers. Faith is tested. Prophecy is contested.',
    HARBOR: 'Salt air and foreign tongues. Wealth arrives and departs on the tide.',
    LIBRARY: 'Dusty silence, sharp minds. Knowledge challenges tradition.',
    OBSERVATORY: 'Stars and long silences. Time is measured in epochs, not days.',
    TREASURY: 'Coins counted, ledgers balanced. Prosperity is arithmetic here.',
    RAMPARTS: 'Wind and watchfires. The world beyond is visible and threatening.',
    THRONE_ROOM: 'Formal silence. All factions attend. Every word is weighed.',
  };
  document.getElementById('loc-desc').textContent = descriptions[currentLoc] || '';
}

function renderLayers(pk) {
  const container = document.getElementById('layer-bars');
  const layers = [];

  if (pk.physical) {
    layers.push({ label: 'Food', val: pk.physical.food_stores || 50 });
    layers.push({ label: 'Trade', val: pk.physical.trade_volume || 40 });
    layers.push({ label: 'Infra', val: pk.physical.infrastructure || 50 });
  }
  if (pk.social) {
    layers.push({ label: 'Cohesion', val: pk.social.cohesion || 50 });
    layers.push({ label: 'Hope', val: pk.social.hope_level || 50 });
    layers.push({ label: 'Fear', val: pk.social.fear_level || 15 });
    layers.push({ label: 'Tension', val: pk.social.class_tension || 20 });
  }
  if (pk.political) {
    layers.push({ label: 'Legitimacy', val: pk.political.legitimacy || 50 });
    layers.push({ label: 'Corruption', val: pk.political.corruption || 15 });
    layers.push({ label: 'Enforce', val: pk.political.enforcement_capacity || 50 });
    layers.push({ label: 'Threat', val: pk.political.external_threat || 10 });
  }
  if (pk.belief) {
    layers.push({ label: 'Faith', val: pk.belief.public_faith || 60 });
    layers.push({ label: 'Divergence', val: pk.belief.interpretation_divergence || 5 });
  }

  let html = '';
  layers.forEach(l => {
    const pct = Math.min(100, Math.max(0, l.val));
    const cls = pct > 60 ? 'good' : pct > 30 ? 'mid' : 'bad';
    // Invert coloring for "bad-when-high" metrics
    const invert = ['Fear', 'Tension', 'Corruption', 'Threat', 'Divergence'].includes(l.label);
    const fillCls = invert ? (pct > 60 ? 'bad' : pct > 30 ? 'mid' : 'good') : cls;
    html += `<div class="layer-bar">
      <span class="bar-label">${l.label}</span>
      <div class="bar-track"><div class="bar-fill ${fillCls}" style="width:${pct}%"></div></div>
      <span class="bar-val">${Math.round(l.val)}</span>
    </div>`;
  });
  container.innerHTML = html;
}

function renderAgents(cs) {
  const container = document.getElementById('agent-list');
  const agents = Object.values(cs.agents || {});
  if (agents.length === 0) { container.innerHTML = '<p class="muted">No court agents</p>'; return; }

  let html = '';
  agents.slice(0, 8).forEach(a => {
    const disp = (
      a.trust * 0.3 + a.admiration * 0.25 - a.resentment * 0.3 - a.fear * 0.05
      + (a.perceived_consistency || 50) * 0.1 - 30
    ).toFixed(0);
    const dispCls = disp > 10 ? 'health-high' : disp < -10 ? 'health-low' : 'health-mid';

    html += `<div class="agent-card">
      <div class="agent-header">
        <span class="agent-name-label">${a.character_id || a.agent_id}</span>
        <span class="agent-disposition ${dispCls}">${disp > 0 ? '+' : ''}${disp}</span>
      </div>
      <div class="agent-bars">
        <div class="agent-mini-bar" title="Trust ${Math.round(a.trust)}">
          <div class="fill trust-fill" style="width:${a.trust}%"></div>
        </div>
        <div class="agent-mini-bar" title="Fear ${Math.round(a.fear)}">
          <div class="fill fear-fill" style="width:${a.fear}%"></div>
        </div>
        <div class="agent-mini-bar" title="Admiration ${Math.round(a.admiration)}">
          <div class="fill admiration-fill" style="width:${a.admiration}%"></div>
        </div>
        <div class="agent-mini-bar" title="Resentment ${Math.round(a.resentment)}">
          <div class="fill resentment-fill" style="width:${a.resentment}%"></div>
        </div>
      </div>
    </div>`;
  });
  container.innerHTML = html;
}

function renderPsychology(pk) {
  const container = document.getElementById('oracle-psych');
  if (!pk.oracle) return;
  const o = pk.oracle;
  const bars = [
    { label: 'Ego', val: o.ego || 0, range: [-50, 50] },
    { label: 'Stress', val: o.stress || 0, range: [0, 100] },
    { label: 'Hope', val: o.hope || 0, range: [-50, 50] },
    { label: 'Dread', val: o.dread || 0, range: [0, 100] },
  ];
  let html = '';
  bars.forEach(b => {
    const norm = ((b.val - b.range[0]) / (b.range[1] - b.range[0])) * 100;
    const pct = Math.min(100, Math.max(0, norm));
    html += `<div class="layer-bar">
      <span class="bar-label">${b.label}</span>
      <div class="bar-track"><div class="bar-fill mid" style="width:${pct}%"></div></div>
      <span class="bar-val">${b.val.toFixed(1)}</span>
    </div>`;
  });
  container.innerHTML = html;
}

function renderCTAs(cs) {
  const reqs = cs.active_requests || [];
  const signals = cs.active_signals || [];
  document.getElementById('cta-count').textContent = reqs.length + signals.length;

  const container = document.getElementById('cta-list');
  if (reqs.length === 0 && signals.length === 0) {
    container.innerHTML = '<p class="muted">No active requests</p>';
    return;
  }

  let html = '';
  reqs.forEach(r => {
    html += `<div class="cta-card" onclick="moveToLocation('${r.target_location}')">
      <span class="cta-urgency urgency-${r.urgency}"></span>
      <span class="cta-text">${r.description}</span>
      <div class="cta-location">→ ${LOCATIONS[r.target_location]?.name || r.target_location}</div>
    </div>`;
  });
  signals.forEach(s => {
    html += `<div class="cta-card" onclick="moveToLocation('${s.location}')">
      <span class="cta-urgency urgency-LOW"></span>
      <span class="cta-text">${s.description}</span>
      <div class="cta-location">→ ${LOCATIONS[s.location]?.name || s.location}</div>
    </div>`;
  });
  container.innerHTML = html;
}

function renderThoughts(inner) {
  const thoughts = inner.thought_log || [];
  const container = document.getElementById('inner-thoughts');
  if (thoughts.length === 0) {
    container.innerHTML = '<p class="muted">Silence within...</p>';
    return;
  }
  // Show last 8 thoughts, most recent first
  const recent = thoughts.slice(-8).reverse();
  let html = '';
  recent.forEach(t => {
    html += `<div class="thought-entry">
      <div class="thought-type">${t.thought_type}</div>
      ${t.text}
    </div>`;
  });
  container.innerHTML = html;
}

function renderDecreeOptions(options) {
  const container = document.getElementById('decree-options');
  if (!options || options.length === 0) {
    container.innerHTML = '<p class="muted">No decree options available.</p>';
    return;
  }

  let html = '';
  options.forEach((opt, idx) => {
    const ctx = opt.court_context || {};
    const isSilence = ctx.is_silence;
    const sel = selectedDecree === idx ? 'selected' : '';

    if (isSilence) {
      html += `<div class="decree-card silence-card ${sel}" onclick="selectDecree(${idx})">
        <div class="decree-text">... (Remain Silent)</div>
        <div class="decree-meta">Silence is never neutral</div>
      </div>`;
    } else {
      const tone = opt.tone || 'PRACTICAL';
      const agentId = ctx.proposing_agent_id || '';
      const agentTone = ctx.agent_tone || '';
      const frameText = agentId
        ? `<div class="agent-frame"><span class="agent-name">${agentId.replace('court_','')}</span> speaks ${agentTone}ly:</div>`
        : '';

      html += `<div class="decree-card ${sel}" onclick="selectDecree(${idx})">
        ${frameText}
        <div class="decree-text">${opt.text}</div>
        <div class="decree-meta">
          <span class="tone-badge tone-${tone}">${tone}</span>
          <span>${opt.mode || 'DECREE'}</span>
        </div>
      </div>`;
    }
  });

  if (selectedDecree !== null) {
    html += `<div class="decree-confirm">
      <button class="btn btn-primary" onclick="confirmDecree()">Issue Decree</button>
    </div>`;
  }

  container.innerHTML = html;
}

// Event feed (append mode)
const maxFeedEvents = 30;
let feedEvents = [];

function renderEvents(evts) {
  evts.forEach(e => {
    feedEvents.unshift(e);
  });
  feedEvents = feedEvents.slice(0, maxFeedEvents);

  const container = document.getElementById('event-feed');
  let html = '';
  feedEvents.forEach(e => {
    const sev = (e.severity || 0) > 50 ? 'severity-high' : (e.severity || 0) > 25 ? 'severity-mid' : 'severity-low';
    html += `<div class="event-entry ${sev}">
      ${e.description || e.kind || 'Event'}
    </div>`;
  });
  container.innerHTML = html || '<p class="muted">The kingdom stirs...</p>';
}

// ═══════════════════════════════════════════════════════════
// VOICE / AUDIO (WebSocket from Radio OS web server)
// ═══════════════════════════════════════════════════════════

/*
 * bookmark.py handles all TTS.  In headless mode it writes WAV files
 * to <station_dir>/.audio_pipe/.  web_server.py's AudioBridge polls
 * that directory and streams the audio over WebSocket at
 * ws://<host>:7800/ws/audio/<station_id>.
 *
 * This player connects to that same WebSocket so the Oracle Kingdom
 * web frontend gets live narration, atmosphere, and court dialogue
 * from the ok_narrator_plugin meta-plugin pipeline.
 */

const STATION_ID  = 'OracleKingdom';
const WS_PORT     = 7800;       // Radio OS web-server port (default)
let audioWs       = null;
let audioCtx      = null;
let gainNode      = null;
let audioQueue    = [];
let audioPlaying  = false;
let audioEnabled  = false;       // user must opt-in (autoplay policy)
let subtitleTimer = null;

function ensureAudioCtx() {
  if (audioCtx && audioCtx.state !== 'closed') {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    return audioCtx.state === 'running';
  }
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    gainNode = audioCtx.createGain();
    gainNode.connect(audioCtx.destination);
    return audioCtx.state === 'running';
  } catch (e) {
    console.error('[Audio] AudioContext failed:', e);
    return false;
  }
}

function connectAudioWs() {
  if (audioWs && audioWs.readyState <= 1) return; // CONNECTING or OPEN
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = location.hostname + ':' + WS_PORT;
  const url = proto + '//' + wsHost + '/ws/audio/' + STATION_ID;
  console.log('[Audio] connecting to', url);

  try {
    audioWs = new WebSocket(url);
    audioWs.binaryType = 'arraybuffer';
  } catch (e) {
    console.error('[Audio] WebSocket create failed:', e);
    setAudioIndicator('error');
    return;
  }

  audioWs.onopen = () => {
    console.log('[Audio] WebSocket connected');
    setAudioIndicator('connected');
    // keepalive
    const ka = setInterval(() => {
      if (!audioWs || audioWs.readyState !== 1) { clearInterval(ka); return; }
      audioWs.send('ping');
    }, 15000);
  };

  audioWs.onmessage = (evt) => {
    if (typeof evt.data === 'string') return; // pong or text
    try {
      const buf = evt.data;
      const view = new DataView(buf);
      const metaLen = view.getUint32(0, false);
      const metaBytes = new Uint8Array(buf, 4, metaLen);
      const meta = JSON.parse(new TextDecoder().decode(metaBytes));
      const wav = buf.slice(4 + metaLen);

      // Update subtitle
      if (meta.text) showSubtitle(meta.voice, meta.text, meta.duration);

      // Drive ambient reactions from segment metadata
      if (AmbientEngine.running) {
        if (meta.stinger) AmbientEngine.playStinger(meta.stinger);
        if (meta.reaction) AmbientEngine.playReaction(meta.reaction);
      }

      audioQueue.push(wav);
      if (audioEnabled && !audioPlaying) playNextAudio();
    } catch (e) {
      console.error('[Audio] frame parse error:', e);
    }
  };

  audioWs.onclose = () => {
    console.log('[Audio] WebSocket closed, reconnecting in 4s');
    setAudioIndicator('error');
    setTimeout(connectAudioWs, 4000);
  };

  audioWs.onerror = () => {
    setAudioIndicator('error');
  };
}

function playNextAudio() {
  if (!audioQueue.length) { audioPlaying = false; setAudioIndicator('connected'); return; }
  if (!ensureAudioCtx()) { audioPlaying = false; return; }
  audioPlaying = true;
  setAudioIndicator('playing');

  const wav = audioQueue.shift();
  try {
    audioCtx.decodeAudioData(wav.slice(0), (decoded) => {
      const src = audioCtx.createBufferSource();
      src.buffer = decoded;
      src.connect(gainNode);
      src.onended = () => playNextAudio();
      src.start(0);
    }, (err) => {
      console.error('[Audio] decode failed:', err);
      audioPlaying = false;
      setTimeout(playNextAudio, 50);
    });
  } catch (e) {
    console.error('[Audio] decodeAudioData threw:', e);
    audioPlaying = false;
    setTimeout(playNextAudio, 50);
  }
}

function toggleAudio() {
  audioEnabled = !audioEnabled;
  const btn = document.getElementById('btn-audio');
  if (audioEnabled) {
    btn.textContent = '🔊';
    btn.classList.add('active');
    ensureAudioCtx();
    connectAudioWs();
    if (audioQueue.length && !audioPlaying) playNextAudio();
    // Start ambient engine
    AmbientEngine.start().catch(e => console.warn('[Ambient] start failed:', e));
  } else {
    btn.textContent = '🔇';
    btn.classList.remove('active');
    // Mute but keep connection for subtitles
    if (gainNode) gainNode.gain.value = 0;
    // Stop ambient engine
    AmbientEngine.stop();
  }
  // Restore gain when re-enabling
  if (audioEnabled && gainNode) gainNode.gain.value = 1.0;
}

function showSubtitle(voice, text, duration) {
  const el = document.getElementById('subtitle-text');
  const prefix = voice ? voice.toUpperCase() + ': ' : '';
  el.textContent = prefix + text;
  // Auto-clear after duration + 2s, or 8s fallback
  clearTimeout(subtitleTimer);
  const clearMs = ((duration || 5) + 2) * 1000;
  subtitleTimer = setTimeout(() => { el.textContent = ''; }, clearMs);
}

function setAudioIndicator(state) {
  const el = document.getElementById('audio-indicator');
  el.className = 'subtitle-indicator ' + state;
  if (state === 'connected') el.textContent = '●';
  else if (state === 'playing') el.textContent = '♫';
  else if (state === 'error') el.textContent = '○';
  else el.textContent = '○';
}

// ═══════════════════════════════════════════════════════════
// AMBIENT AUDIO ENGINE (Web Audio API)
// ═══════════════════════════════════════════════════════════
//
// Plays room ambient beds, texture loops, crowd murmurs, whispers,
// and reaction one-shots entirely in the browser.  The server's
// ok_audio_engine.py uses pygame (server-side only).  This is the
// web counterpart — it fetches OGG files over HTTP and drives them
// via the same AudioMixState values from the narrator plugin.
//
// Architecture:
//   /ok/audio_manifest  → discover all available audio files
//   /ok/audio/{path}    → fetch individual OGG files
//   /ok/audio_mix       → poll current AudioMixState + location
//
// The engine runs on a 100ms update loop once the user enables audio.

const AmbientEngine = (() => {
  let ctx = null;         // AudioContext (shared with TTS player)
  let masterGain = null;
  let manifest = null;    // from /ok/audio_manifest
  let currentRoom = '';
  let mixState = {};
  let running = false;
  let updateTimer = null;

  // Loaded audio buffers cache: path → AudioBuffer
  const bufferCache = {};

  // Active source nodes
  let bedSource = null;
  let bedGain = null;
  let prevBedSource = null;
  let prevBedGain = null;
  const textureNodes = [];   // {source, gain, fader state}
  let murmurSource = null;
  let murmurGain = null;
  let whisperTimer = 0;
  let mixPollTimer = null;

  // ── Helpers ──

  async function loadBuffer(relPath) {
    if (bufferCache[relPath]) return bufferCache[relPath];
    try {
      const resp = await fetch(`/ok/audio/${relPath}`);
      if (!resp.ok) return null;
      const arrayBuf = await resp.arrayBuffer();
      const decoded = await ctx.decodeAudioData(arrayBuf);
      bufferCache[relPath] = decoded;
      return decoded;
    } catch (e) {
      console.warn('[Ambient] load failed:', relPath, e);
      return null;
    }
  }

  function makeLoopSource(buffer, gainNode, volume) {
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.loop = true;
    src.connect(gainNode);
    gainNode.gain.setValueAtTime(volume, ctx.currentTime);
    src.start(0);
    return src;
  }

  function stopSource(src) {
    if (!src) return;
    try { src.stop(); } catch (_) {}
    try { src.disconnect(); } catch (_) {}
  }

  // ── Init ──

  async function init() {
    if (!ctx) {
      // Reuse the TTS AudioContext if available
      if (audioCtx && audioCtx.state !== 'closed') {
        ctx = audioCtx;
      } else {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
      }
    }
    if (ctx.state === 'suspended') await ctx.resume();

    if (!masterGain) {
      masterGain = ctx.createGain();
      masterGain.gain.value = 0.7;  // master ambient volume
      masterGain.connect(ctx.destination);
    }

    // Fetch audio manifest
    try {
      const resp = await fetch('/ok/audio_manifest');
      manifest = await resp.json();
      console.log('[Ambient] manifest loaded:', Object.keys(manifest.rooms || {}).length, 'rooms');
    } catch (e) {
      console.error('[Ambient] manifest fetch failed:', e);
      manifest = { rooms: {}, crowd: { murmurs: [], whispers: [], reactions: {} }, stingers: {}, lifecycle: {} };
    }
  }

  // ── Room transition ──

  async function setRoom(locationId) {
    const loc = (locationId || '').toUpperCase();
    if (loc === currentRoom || !manifest) return;
    console.log('[Ambient] room transition:', currentRoom, '→', loc);

    const roomData = manifest.rooms[loc];
    if (!roomData || !roomData.beds || roomData.beds.length === 0) {
      console.warn('[Ambient] no beds for room:', loc);
      currentRoom = loc;
      return;
    }

    // Load the first bed
    const bedPath = roomData.beds[0];
    const bedBuf = await loadBuffer(bedPath);
    if (!bedBuf) { currentRoom = loc; return; }

    // Crossfade: old bed → fade out, new bed → fade in
    const fadeDuration = 3.0;

    // Move current bed to "previous" slot
    if (prevBedSource) stopSource(prevBedSource);
    if (prevBedGain) {
      try { prevBedGain.disconnect(); } catch(_) {}
    }
    prevBedSource = bedSource;
    prevBedGain = bedGain;

    // Fade out old bed
    if (prevBedGain) {
      prevBedGain.gain.setValueAtTime(prevBedGain.gain.value, ctx.currentTime);
      prevBedGain.gain.linearRampToValueAtTime(0, ctx.currentTime + fadeDuration);
      setTimeout(() => {
        stopSource(prevBedSource);
        prevBedSource = null;
      }, (fadeDuration + 0.5) * 1000);
    }

    // Create new bed
    bedGain = ctx.createGain();
    bedGain.connect(masterGain);
    bedGain.gain.setValueAtTime(0, ctx.currentTime);
    const bedVol = getBedVolume(loc);
    bedGain.gain.linearRampToValueAtTime(bedVol, ctx.currentTime + fadeDuration);
    bedSource = makeLoopSource(bedBuf, bedGain, 0);

    // Stop old textures
    for (const tn of textureNodes) {
      stopSource(tn.source);
      if (tn.gain) try { tn.gain.disconnect(); } catch(_) {}
    }
    textureNodes.length = 0;

    // Load & start new textures
    if (roomData.textures) {
      for (const texPath of roomData.textures) {
        const texBuf = await loadBuffer(texPath);
        if (!texBuf) continue;
        const tGain = ctx.createGain();
        tGain.connect(masterGain);
        tGain.gain.setValueAtTime(0, ctx.currentTime);
        const tSrc = makeLoopSource(texBuf, tGain, 0);
        textureNodes.push({
          source: tSrc,
          gain: tGain,
          path: texPath,
          state: 'silent',
          timer: 0,
          nextDur: 5 + Math.random() * 15,  // staggered start
          targetVol: 0.15 + Math.random() * 0.15,
        });
      }
    }

    currentRoom = loc;
  }

  function getBedVolume(loc) {
    const vols = {
      COURTYARD: 0.35, WAR_CHAMBER: 0.25, TEMPLE: 0.30,
      HARBOR: 0.30, LIBRARY: 0.15, OBSERVATORY: 0.22,
      TREASURY: 0.22, RAMPARTS: 0.25, THRONE_ROOM: 0.20,
    };
    return vols[loc] || 0.25;
  }

  // ── Crowd murmur ──

  async function startMurmur() {
    if (!manifest || !manifest.crowd || !manifest.crowd.murmurs.length) return;
    const path = manifest.crowd.murmurs[0];
    const buf = await loadBuffer(path);
    if (!buf) return;

    if (!murmurGain) {
      murmurGain = ctx.createGain();
      murmurGain.connect(masterGain);
    }
    murmurGain.gain.setValueAtTime(0, ctx.currentTime);

    if (murmurSource) stopSource(murmurSource);
    murmurSource = makeLoopSource(buf, murmurGain, 0);
  }

  async function playWhisper() {
    if (!manifest || !manifest.crowd || !manifest.crowd.whispers.length) return;
    const pool = manifest.crowd.whispers;
    const path = pool[Math.floor(Date.now() / 1000) % pool.length];
    const buf = await loadBuffer(path);
    if (!buf) return;

    const g = ctx.createGain();
    g.connect(masterGain);
    const freq = (mixState.whisper_frequency || 0.1);
    g.gain.value = Math.min(0.3, freq * 0.4 + 0.05);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(g);
    src.onended = () => { try { g.disconnect(); } catch(_) {} };
    src.start(0);
  }

  async function playReaction(category) {
    if (!manifest || !manifest.crowd || !manifest.crowd.reactions) return;
    const pool = manifest.crowd.reactions[category];
    if (!pool || !pool.length) return;
    const path = pool[Math.floor(Math.random() * pool.length)];
    const buf = await loadBuffer(path);
    if (!buf) return;

    const g = ctx.createGain();
    g.connect(masterGain);
    g.gain.value = 0.5;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(g);
    src.onended = () => { try { g.disconnect(); } catch(_) {} };
    src.start(0);
  }

  async function playStinger(id) {
    if (!manifest || !manifest.stingers || !manifest.stingers[id]) return;
    const buf = await loadBuffer(manifest.stingers[id]);
    if (!buf) return;

    const g = ctx.createGain();
    g.connect(masterGain);
    g.gain.value = 0.55;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(g);
    src.onended = () => { try { g.disconnect(); } catch(_) {} };
    src.start(0);
  }

  // ── Update loop (called every ~100ms) ──

  const UPDATE_DT = 0.1;

  function update() {
    if (!ctx || !manifest) return;

    const density = mixState.murmur_density || 0.3;
    const whisperFreq = mixState.whisper_frequency || 0.1;
    const crowdEnergy = mixState.crowd_energy || 0.3;

    // Murmur volume tracks density
    if (murmurGain) {
      const targetMurmur = Math.min(0.4, density * 0.5);
      const cur = murmurGain.gain.value;
      murmurGain.gain.setValueAtTime(cur + (targetMurmur - cur) * 0.1, ctx.currentTime);
    }

    // Texture faders — simple state machine
    const texScalar = Math.min(1.0, crowdEnergy + 0.3);
    for (const tn of textureNodes) {
      tn.timer += UPDATE_DT;

      if (tn.state === 'silent') {
        if (tn.timer >= tn.nextDur) {
          tn.state = 'fading_in';
          tn.timer = 0;
          tn.nextDur = 3 + Math.random() * 8;
        }
      } else if (tn.state === 'fading_in') {
        const progress = Math.min(1, tn.timer / tn.nextDur);
        const vol = tn.targetVol * texScalar * progress;
        tn.gain.gain.setValueAtTime(vol, ctx.currentTime);
        if (progress >= 1) {
          tn.state = 'playing';
          tn.timer = 0;
          tn.nextDur = 10 + Math.random() * 25;
        }
      } else if (tn.state === 'playing') {
        tn.gain.gain.setValueAtTime(tn.targetVol * texScalar, ctx.currentTime);
        if (tn.timer >= tn.nextDur) {
          tn.state = 'fading_out';
          tn.timer = 0;
          tn.nextDur = 4 + Math.random() * 10;
        }
      } else if (tn.state === 'fading_out') {
        const progress = Math.min(1, tn.timer / tn.nextDur);
        const vol = tn.targetVol * texScalar * (1 - progress);
        tn.gain.gain.setValueAtTime(vol, ctx.currentTime);
        if (progress >= 1) {
          tn.state = 'silent';
          tn.timer = 0;
          tn.nextDur = 8 + Math.random() * 20;
        }
      }
    }

    // Whisper scheduling
    const whisperInterval = Math.max(8, 40 - whisperFreq * 35);
    whisperTimer += UPDATE_DT;
    if (whisperTimer >= whisperInterval) {
      whisperTimer = 0;
      playWhisper();
    }
  }

  // ── Mix state polling ──

  async function pollMix() {
    try {
      const resp = await fetch('/ok/audio_mix');
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.mix) mixState = data.mix;
      if (data.location && data.location !== currentRoom) {
        await setRoom(data.location);
      }
    } catch (e) {
      // silent — server may not be ready yet
    }
  }

  // ── Public API ──

  async function start() {
    if (running) return;
    await init();
    running = true;

    // Initial room
    await pollMix();
    if (!currentRoom) await setRoom('COURTYARD');

    // Start murmur loop
    await startMurmur();

    // Update loop at ~10 Hz
    updateTimer = setInterval(update, UPDATE_DT * 1000);

    // Poll mix state every 2 seconds
    mixPollTimer = setInterval(pollMix, 2000);

    console.log('[Ambient] engine started, room:', currentRoom);
  }

  function stop() {
    running = false;
    if (updateTimer) { clearInterval(updateTimer); updateTimer = null; }
    if (mixPollTimer) { clearInterval(mixPollTimer); mixPollTimer = null; }
    stopSource(bedSource); bedSource = null;
    stopSource(prevBedSource); prevBedSource = null;
    stopSource(murmurSource); murmurSource = null;
    for (const tn of textureNodes) stopSource(tn.source);
    textureNodes.length = 0;
    console.log('[Ambient] engine stopped');
  }

  function setMasterVolume(v) {
    if (masterGain) masterGain.gain.setValueAtTime(v, ctx.currentTime);
  }

  return { start, stop, setRoom, playReaction, playStinger, setMasterVolume,
           get running() { return running; } };
})();

// ── Utility ───────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function showError(msg) {
  const bar = document.getElementById('subtitle-text');
  if (bar) {
    bar.textContent = '⚠ ' + msg;
    bar.style.color = 'var(--danger)';
    setTimeout(() => { bar.style.color = ''; }, 5000);
  }
}

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  showScreen('screen-title');
  // Pre-connect audio WebSocket for subtitle display even before user enables audio
  connectAudioWs();
});

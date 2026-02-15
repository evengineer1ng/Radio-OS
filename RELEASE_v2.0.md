# Radio OS v2.0 — FTB Web Frontend

**Release Date:** February 15, 2026  
**Tag:** `v2.0`

---

## What's New

Radio OS v2.0 ships a fully playable **browser-based frontend** for From The Backmarker (FTB), the motorsport management simulation. The entire game — team management, hiring, parts, infrastructure, sponsors, R&D, race day, and more — is now accessible from a Svelte 5 web UI served by the built-in FastAPI backend. No Tkinter window required.

---

## Highlights

### 🖥️ Full Web Frontend (Svelte 5 + Vite)
- **Dashboard** — season overview, standings, morale, budget at a glance
- **Team** — hire/fire drivers, engineers, mechanics, strategists; browse free agent market and job board
- **Car & Parts** — equip, buy, and sell parts from the marketplace; visual stat bars per component
- **Development** — launch R&D projects, upgrade infrastructure facilities
- **Sponsors** — accept or decline sponsor offers, view active contracts
- **Finance** — income/expense breakdown, transaction history
- **Race Ops** — live race day with play-by-play, qualifying grids, race results
- **Calendar** — upcoming race schedule with completion tracking
- **Data Explorer** — historical season summaries and race archives
- **Setup Wizard** — guided new-game creation with manager identity, team name, tier selection
- **Toolbar** — tick controls (single step / batch advance / stop), save/load, time mode toggle

### 🔧 Critical Engine Fixes

| Bug | Impact | Fix |
|-----|--------|-----|
| **`threading.Lock` deadlock** | Every command (hire, fire, tick, parts, infra, sponsors) permanently froze the engine thread | Changed `state_lock` to `threading.RLock()` — `_refresh_widget()` was called from inside locked blocks and tried to re-acquire the same non-reentrant lock |
| **State wipe on busy** | UI went blank after any action if the lock was contended | Added `safeRefreshState()` — only updates the store when the server returns real game data, skips `"busy"` / `"no_controller"` stubs |
| **No autosave on new game** | Creating a game then refreshing the page lost everything | Immediate `save_game()` after `start_new_game` |
| **Blocking Tkinter dialog** | `messagebox.askyesno()` froze the engine thread in web-only mode (no Tk root) | Detect missing Tk root, default to instant sim |
| **`return` instead of `continue`** | 8 error paths in `_handle_ui_cmds` exited the entire command loop, silently dropping queued commands | Changed to `continue` |
| **Async event loop blocked** | `state_lock` acquired directly inside `async def` handlers froze the uvicorn event loop | All lock access moved to `run_in_executor` with 0.5s timeout |
| **Dead code confusion** | Two app factories (`create_app` + `create_full_app`), only one used | Deleted ~250 lines: `create_full_app`, `BroadcastManager`, `_ws_broadcast_listener` |
| **Missing bridge pump** | WebSocket broadcast queue never drained in the active app factory | Added `on_event("startup")` with `bridge.set_async_context()` and background `bridge_pump` task |

### 🆕 New Components
- `EntityDetail.svelte` — expanded entity view with full stat breakdown
- `PartDetail.svelte` — part inspection modal with quality, cost, type info
- `webAudio.ts` — browser-side audio state mirroring

---

## Upgrade Notes

1. **Pull the latest code**
   ```bash
   git pull origin main
   ```

2. **Install any new Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Build the web frontend** (first time or after pulling)
   ```bash
   cd web
   npm install
   npm run build
   ```

4. **Run as usual**
   ```bash
   python shell.py
   ```
   The web UI is served at `http://localhost:8420` (or the port shown in logs).

---

## Files Changed

- `plugins/ftb_game.py` — RLock, autosave, Tk dialog guard, return→continue fixes
- `plugins/ftb_web_server.py` — dead code removal, bridge pump, busy-timeout lock, safeRefreshState
- `plugins/ftb_audio_engine.py` — web audio state endpoint support
- `web/src/**` — complete Svelte 5 frontend (all tabs, components, stores, API layer, styles)
- `bookmark.py`, `shell_bookmark.py` — launcher integration updates
- `requirements.txt` — dependency updates

**25 files changed, 2,171 insertions, 527 deletions**

---

## Known Limitations

- Race day live play-by-play defaults to instant sim when no Tkinter root is present (web-only mode). A future release will add a web-native race day prompt.
- The `web/dist/` folder is gitignored — you must run `npm run build` after cloning.
- Autosave triggers every 10 ticks during gameplay; the initial autosave fires once on game creation.

---

**Full Changelog:** [`v1.03...v2.0`](https://github.com/evengineer1ng/Radio-OS/compare/v1.03...v2.0)

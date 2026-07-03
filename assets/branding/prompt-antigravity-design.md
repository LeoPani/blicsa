# Blicsa — identity v2 ("just blink") + trilingual UI sprint

You are inside the Blicsa project folder. Visual/UX and i18n only — do not change analysis logic or feature behavior. Work fully autonomously: no confirmation questions mid-task; decide and log decisions in the final report. Only stop on unrecoverable errors.

## Brand v2 (source of truth)

The mark is the ICSA/UFOP institute abstracted as a neoplastic tower: an ink structural grid of floors and rooms in building proportion, three rooms lit in the Mondrian primaries, halo nodes at the structural intersections forming a citation network. Slogan: **just blink** — always lowercase, always in English in all three languages (it's a brand asset, never translate it), always set in muted #8A877F.

Palette (Mondrian-derived, unchanged):
- `paper` #F6F4EE · `ink` #141414 · `red` #DF3117 · `blue` #1E4DA0 · `yellow` #F5BE00 · `muted` #8A877F
- Zero rounded corners, no shadows, no gradients, 2–3px ink borders, 8px spacing grid.
- Type: Archivo (bundle TTF in `assets/fonts/`, fallback Segoe UI/Helvetica). Headers 700–800.

Assets provided — place in `assets/branding/`:
`blicsa-logo.svg`, `blicsa-logo-animated.svg`, `blicsa-logo-horizontal.svg/png`, `blicsa-icon.ico`, `blicsa-icon.icns`, `blicsa-icon-512.png`, `blicsa-icon-256.png`, `blicsa-splash.gif`, `flag-pt-br.png`, `flag-en.png`, `flag-fr.png`.

## Tasks

### 1. Replace all v1 branding
Swap any previous logo/icon/splash references for the v2 files. Window icon: `.ico` on Windows (`iconbitmap`), 256px PNG via `iconphoto` elsewhere. Wire `.ico`/`.icns` into the PyInstaller spec. Use `blicsa-logo-horizontal.png` in the README header. Use `blicsa-logo-animated.svg` in the README under the header (GitHub renders SVG animation).

### 2. Trilingual UI — pt_BR, en, fr with flag switcher
- i18n layer: `core/i18n.py` exposing `t(key)`; JSON catalogs `locales/pt_BR.json`, `locales/en.json`, `locales/fr.json`. English is the fallback: a missing key logs a warning and falls back to `en`.
- Extract EVERY user-facing string in the GUI into the catalogs (menus, buttons, dialogs, tooltips, status messages, error messages, chart titles/axis labels produced by the app UI — not user data). Write natural pt_BR and en yourself; for fr, write careful translations and mark the file header with a `"_note": "machine-assisted translation, review welcome"` key.
- Language switcher: in the top bar of the home screen and in Settings — three flat buttons, each showing the flag PNG (`flag-pt-br.png`, `flag-en.png`, `flag-fr.png`) at 32×22 with a 2px ink border; active language gets a 3px red underline bar. Do NOT use emoji flags (they don't render on Windows tkinter).
- Persist the choice in the existing settings store; on first run, auto-detect from `locale.getlocale()` (pt* → pt_BR, fr* → fr, else en).
- Live switch: changing language updates visible widgets without restart if feasible with reasonable effort (rebuild the current screen); otherwise apply on restart and say so in a small toast — decide and report.
- Tests: the three catalogs must have identical key sets (CI-failing test); `t()` fallback behavior covered.

### 3. Splash screen (v2 GIF)
Borderless centered Toplevel with 3px ink border playing `blicsa-splash.gif` (~42ms/frame) while heavy imports run in a thread; closes when the main window is ready (let one pass finish, max ~3s). Version string bottom-right, muted, 11px. The slogan is inside the GIF already — don't add it again.

### 4. Home screen (keep the tile concept, rebrand it)
Asymmetric grid of flat tiles separated by 3px ink lines: New analysis (red), Search databases (blue), Open project (paper+ink border), Recent files (paper, last 5, one-click), Sample dataset (yellow, small). Top strip: horizontal logo left; right side: the three flag buttons + GitHub link. Under the logo, the slogan `just blink` in muted 12px — the only place it appears in the app UI besides the About dialog. Hover: ink border 2→4px, label underline. All tile labels via `t()`.

### 5. Consistency pass (visual only)
Apply the token system everywhere: no rounded corners/shadows/gradients anywhere; sidebar active item = 6px red left bar + bold; dialogs with 3px ink border and right-aligned buttons (primary red, secondary paper+ink); progress bars flat yellow on paper with ink border; paddings normalized to the 8px grid. About dialog: horizontal logo, slogan, version, credits mentioning ICSA/UFOP, license, GitHub link — fully translated except the slogan.

### 6. Matplotlib house style
`core/viz/blicsa.mplstyle`: paper background, no top/right spines, Archivo/DejaVu, muted 9pt ticks. Cluster palette: `#DF3117 #1E4DA0 #F5BE00 #141414 #7A9E7E #B65CA2 #5CB0B8 #C97B2D` + desaturated extensions. Network maps: paper background, ink edges at 8% alpha, labels with paper halo (`path_effects.withStroke`).

### 7. Micro-motion — "the blink"
Exactly three animated moments, nothing else moves:
1. Splash GIF.
2. Home tiles appear in reading order, 60ms stagger.
3. **The blink**: when a map/analysis finishes rendering, the small status-bar square (make it the blue brand square) does one quick vertical squash-and-restore (~250ms via `after()` height animation) — the UI literally blinks to say "done". This replaces any bell/beep.
Settings toggle "Reduce animations" (translated) disables 2 and 3 and jumps splash to its last frame.

## Acceptance
- App launches: splash → home; every existing entry point reachable; language switch works and persists across restart in all three languages.
- Catalog-parity test passes; existing test suite passes; `--selfcheck` passes if present.
- Zero rounded corners/shadows/gradients; slogan appears only in splash (baked), home strip, and About.
- Final report: files touched, decisions, screenshots if possible, anything deferred.

# Changelog

Versioning follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
PATCH fixes bugs, MINOR adds features, MAJOR makes breaking structural changes.

## 1.3.0 — 2026-10-30

**Renamed: ToolBox → Pivot (枢).**

The name changed, not the product: icon, layout, animations and features are untouched.

| Location | 1.2.x | 1.3.0 |
| --- | --- | --- |
| Executable | `mouse_macro.exe` | `pivot.exe` |
| Entry / shared module | `mouse_macro.py` / `toolbox_kit.py` | `pivot.py` / `pivot_kit.py` |
| Settings | `HKCU\Software\MouseMacro` | `HKCU\Software\Pivot` |
| Install directory | `%LOCALAPPDATA%\Programs\MouseMacro` | `...\Programs\Pivot` |
| Installer | `MouseMacro_Setup_*` | `Pivot_Setup_*` |
| Installer AppId | `{8F3A2C1E-…}` | `{35A1B8A4-…}` |

- **Settings migrate automatically**: when a new key is empty, the whole old key is copied over
  (hotkeys, window position, wallpaper, clicker settings). The old key is kept, so rolling back
  to 1.2.x still works. The wallpaper directory is duplicated the same way, leaving originals intact.
- **Note**: the AppId changed, so upgrading from 1.2.x to 1.3.0 requires uninstalling the old
  version first — otherwise both products coexist on the system. This is a one-time break;
  the AppId is fixed from here on.
- Open-sourced from this release: MIT license, and the build scripts no longer hardcode local paths.
- **Splash screen progress bar replaced by a ring spinner**: the old horizontal light band that
  simply stopped at the end read like a download progress bar. It is now a clockwise ring spinner
  (dim track plus a conical-gradient arc), which better conveys "waiting for you". It is still
  driven by the single splash progress value — no new animation object was introduced.

## 1.2.7 — 2026-10-30

**Auto-update** (check → prompt → download → verify → replace → restart).

- The update core `updater_core.py` lives outside `apps\`, so emptying the feature directory
  doesn't break update checks.
- Driven by a `version.json` manifest; SHA256 verification; path checks against zip slip.
- **Packaging switched from `--onefile` to `--onedir`**. The old scheme unpacked the whole bundle
  into `%TEMP%\_MEIxxxxxx` on every launch; when killed by `taskkill` or a crash, the leftovers
  were never cleaned up — 112 directories, 12.5 GB in total, filling the C: drive completely.
  onedir runs in place: no unpacking, no leftovers.
- Updates no longer reinstall features the user deleted on purpose (an `_apps_state.json` file
  distinguishes "deleted by the user" from "added in the new version").

## 1.2.6 — fix — 2026-10-05

- Fix: **the key-remap recorder accepted no key at all**, only the default `4` / `T`.
  The widget emitted signals but kept no state, and the remap page never connected the signal.
  Fixed by making the widget hold its own state and connecting the signal in the page.
- Added `tests\_remap_ui_check.py`, which sends real `QKeyEvent`s through the recorder.

## 1.2.6 — 2026-10-05

**Feature modularisation**: everything moved into `apps\`, one file per feature.

- The shell shrank from 5291 lines to roughly 2300; `pivot_kit.py` now holds the shared widgets.
- Four layers of fault-tolerant loading: missing file / import error / build error / invalid
  contract — each affects only a single feature.
- Deleting any file under `apps\` removes that feature from the sidebar and home page,
  and everything else keeps working.

## 1.2.5 — 2026-10-05

- Removed the scheduled-screenshot tool.
- Added **keyboard auto-repeat**: pick keys on an on-screen keyboard, set a count per key.
- Added **key remapping**: global key-to-key mapping.

## 1.2.4 — 2026-09-26

- Enlarged the credit mark in the bottom bar.
- All icons switched to a solid black background.

---

Versions before 1.2.4 have no changelog.

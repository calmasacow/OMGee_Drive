# OMGee Drive

A Dropbox-shaped Google Drive folder for [Omarchy](https://omarchy.org/).

Not affiliated with Google. There is no official Drive for Desktop on Linux; this is a thin client on top of [rclone](https://rclone.org/).

**What you get**

- `~/GoogleDrive` — browse your Drive in Nautilus like a normal folder
- Right-click **Make available offline** — real bytes on disk, still work if you are on a plane
- Right-click **Free up space** — drop the local copy, the file stays in Drive
- Docs / Sheets / Slides / Forms are **shortcuts** (`.gdoc`, `.gsheet`, …) that open in the browser, the same idea as Drive for Desktop on Windows/Mac
- Nautilus overlay badges for sync state (see below)

**What you do not get**

- Overlay badges on every icon
- Shared drives / “Shared with me” as extra roots (My Drive only, v1)
- Google treating this as an official app

## Install (Omarchy)

```bash
git clone https://github.com/calmasacow/OMGee_Drive.git ~/Projects/OMGee_Drive
cd ~/Projects/OMGee_Drive
./install.sh
omgee-drive setup    # browser login
omgee-drive start
```

Restart Nautilus once so the right-click items appear:

```bash
nautilus -q
```

Then open `~/GoogleDrive`. If overlays are missing, restart Files (`nautilus -q`) so it reloads emblems.

## Status badges

Nautilus draws a small overlay on each item in `~/GoogleDrive`:

| Badge | Means |
|---|---|
| Cloud | Online only — listed, not kept on disk |
| Circular arrows | Syncing or queued (download / upload / pin in progress) |
| Green check | Available offline and current |
| Red ! | Last pin/sync failed |
| Blue link | Google Doc / Sheet / Slide shortcut (opens in the browser) |

Queued and actively transferring share the arrows on purpose — one glance, “not settled yet.” List view also has a **Drive** column with the same words.

Not in v1 (easy to add later): conflict vs generic error, “shared with others,” paused because the laptop is offline.

### Your own OAuth client (recommended)

rclone’s shared Google client id is being retired. Create a Google Cloud **Desktop** OAuth client, enable the **Google Drive API**, then:

```bash
omgee-drive setup --client-id YOUR_ID.apps.googleusercontent.com --client-secret YOUR_SECRET
```

## Usage

| Action | How |
|---|---|
| Browse | Nautilus → `~/GoogleDrive` |
| Open a PDF / photo / zip | Double-click (downloads on demand, then opens) |
| Keep a file/folder on disk | Right-click → **Make available offline** |
| Evict local bytes | Right-click → **Free up space** |
| Open a Doc/Sheet | Double-click the shortcut (browser) |
| CLI pin | `omgee-drive pin ~/GoogleDrive/Invoices` |
| Refresh badges | `F5` in Nautilus, or `nautilus -q` |

The systemd user unit `omgee-drive.service` remounts after login.

```bash
omgee-drive status
omgee-drive stop
omgee-drive refresh-stubs
```

## How it works

rclone mounts a **union**:

1. `omgee-gdrive` — your Drive, with Google editor files skipped so they are not fake `.docx` exports
2. `omgee-local` (`:nc`) — `~/.local/share/omgee-drive/local/` (no-create overlay so new files upload to Drive)
   - shortcut stubs for Docs/Sheets/…
   - full copies of anything you pinned

New files you drop into `~/GoogleDrive` upload to Drive. Pins live on disk and sync both ways every few minutes.

## Uninstall

```bash
omgee-drive stop
systemctl --user disable omgee-drive.service
rm -f ~/.local/bin/omgee-drive
rm -f ~/.local/share/nautilus-python/extensions/omgee-drive.py
rm -rf ~/.config/omgee-drive ~/.local/share/omgee-drive ~/.cache/omgee-drive ~/.local/lib/omgee-drive
fusermount3 -u ~/GoogleDrive 2>/dev/null || true
```

Pinned files are only under `~/.local/share/omgee-drive/local/`. Copy anything you care about out before deleting that tree.

## License

MIT

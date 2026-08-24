#!/usr/bin/env bash
# Install OMGee Drive into the current user account (no root except rclone).
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
LIB_DIR="${HOME}/.local/lib/omgee-drive"
NAUTILUS_DIR="${HOME}/.local/share/nautilus-python/extensions"
MIME_DIR="${HOME}/.local/share/mime/packages"
APPS_DIR="${HOME}/.local/share/applications"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
EMBLEM_DIR="${HOME}/.local/share/icons/hicolor/scalable/emblems"

mkdir -p "$BIN_DIR" "$NAUTILUS_DIR" "$MIME_DIR" "$APPS_DIR" "$SYSTEMD_DIR" \
  "$EMBLEM_DIR" \
  "${HOME}/.local/share/icons/hicolor/16x16/emblems" \
  "${HOME}/.config/omgee-drive" \
  "${HOME}/.local/share/omgee-drive/local" \
  "${HOME}/.cache/omgee-drive"

# ln -sfn into an existing directory nests the link. Replace a real dir with a symlink.
if [[ -d "$LIB_DIR" && ! -L "$LIB_DIR" ]]; then
  rm -rf "$LIB_DIR"
fi
mkdir -p "$(dirname "$LIB_DIR")"
ln -sfn "$REPO" "$LIB_DIR"
ln -sfn "$REPO/bin/omgee-drive" "$BIN_DIR/omgee-drive"
chmod +x "$REPO/bin/omgee-drive"

ln -sfn "$REPO/nautilus/omgee-drive.py" "$NAUTILUS_DIR/omgee-drive.py"
ln -sfn "$REPO/mime/omgee-drive.xml" "$MIME_DIR/omgee-drive.xml"
ln -sfn "$REPO/mime/omgee-drive.desktop" "$APPS_DIR/omgee-drive.desktop"
ln -sfn "$REPO/systemd/omgee-drive.service" "$SYSTEMD_DIR/omgee-drive.service"
for emblem in "$REPO"/icons/emblem-omgee-*.svg; do
  base="$(basename "$emblem")"
  ln -sfn "$emblem" "$EMBLEM_DIR/$base"
  ln -sfn "$emblem" "${HOME}/.local/share/icons/hicolor/16x16/emblems/$base"
  # Nautilus 43+ sometimes looks up the -symbolic name for overlays.
  ln -sfn "$emblem" "$EMBLEM_DIR/${base%.svg}-symbolic.svg"
done
if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

if [[ ! -f "${HOME}/.config/omgee-drive/config.json" ]]; then
  cat > "${HOME}/.config/omgee-drive/config.json" <<EOF
{
  "mount_point": "${HOME}/GoogleDrive",
  "stub_refresh_sec": 300,
  "pin_sync_sec": 300
}
EOF
fi
if [[ ! -f "${HOME}/.config/omgee-drive/ignore" ]]; then
  cat > "${HOME}/.config/omgee-drive/ignore" <<'EOF'
# One glob per line. Matches the Drive-relative path or the filename.
# Examples:
#   *.tmp
#   Desktop.ini
#   Secret/**
EOF
fi
mkdir -p "${HOME}/GoogleDrive"

if command -v update-mime-database >/dev/null; then
  update-mime-database "${HOME}/.local/share/mime" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi
if command -v xdg-mime >/dev/null; then
  for mime in \
    application/x-omgee-gdoc \
    application/x-omgee-gsheet \
    application/x-omgee-gslides \
    application/x-omgee-gform \
    application/x-omgee-gdraw \
    application/x-omgee-gshortcut
  do
    xdg-mime default omgee-drive.desktop "$mime" >/dev/null 2>&1 || true
  done
fi

if command -v systemctl >/dev/null; then
  systemctl --user daemon-reload
fi

if ! command -v rclone >/dev/null; then
  if command -v omarchy >/dev/null; then
    echo "Installing rclone …"
    omarchy pkg add rclone
  else
    echo "rclone is not installed. Install it, then re-run setup." >&2
  fi
fi

echo "OMGee Drive installed."
echo
echo "  1. Authorize Google Drive (opens a browser):"
echo "       omgee-drive setup"
echo "  2. Start the folder:"
echo "       omgee-drive start"
echo
echo "Your Drive will appear at ~/GoogleDrive"
echo "Right-click in Nautilus: Make available offline / Free up space"
echo "Overlay badges: cloud = online only, arrows = syncing, green check = offline."
echo "Restart Nautilus if icons/menu are missing:  nautilus -q"

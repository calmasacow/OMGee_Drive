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

mkdir -p "$BIN_DIR" "$LIB_DIR" "$NAUTILUS_DIR" "$MIME_DIR" "$APPS_DIR" "$SYSTEMD_DIR" \
  "${HOME}/.config/omgee-drive" \
  "${HOME}/.local/share/omgee-drive/local" \
  "${HOME}/.cache/omgee-drive"

ln -sfn "$REPO" "$LIB_DIR"
ln -sfn "$REPO/bin/omgee-drive" "$BIN_DIR/omgee-drive"
chmod +x "$REPO/bin/omgee-drive"

ln -sfn "$REPO/nautilus/omgee-drive.py" "$NAUTILUS_DIR/omgee-drive.py"
ln -sfn "$REPO/mime/omgee-drive.xml" "$MIME_DIR/omgee-drive.xml"
ln -sfn "$REPO/mime/omgee-drive.desktop" "$APPS_DIR/omgee-drive.desktop"
ln -sfn "$REPO/systemd/omgee-drive.service" "$SYSTEMD_DIR/omgee-drive.service"

if [[ ! -f "${HOME}/.config/omgee-drive/config.json" ]]; then
  cat > "${HOME}/.config/omgee-drive/config.json" <<EOF
{
  "mount_point": "${HOME}/GoogleDrive",
  "stub_refresh_sec": 300,
  "pin_sync_sec": 300
}
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
echo "Restart Nautilus if the menu is missing:  nautilus -q"

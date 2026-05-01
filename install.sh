#!/bin/bash
# install.sh — Install BMCU Klipper extra via symlink
#
# Usage: ./install.sh
#
# Creates a symlink from this repo's klippy/extras/bmcu_feeder.py into
# your Klipper installation. Survives Klipper updates (unlike a copy).

set -e

KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
EXTRAS_DIR="$KLIPPER_DIR/klippy/extras"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/klippy/extras/bmcu_feeder.py"

if [ ! -d "$EXTRAS_DIR" ]; then
    echo "ERROR: Klipper extras directory not found at $EXTRAS_DIR"
    echo "Set KLIPPER_DIR if Klipper is installed elsewhere:"
    echo "  KLIPPER_DIR=/path/to/klipper ./install.sh"
    exit 1
fi

if [ ! -f "$SOURCE" ]; then
    echo "ERROR: bmcu_feeder.py not found at $SOURCE"
    exit 1
fi

TARGET="$EXTRAS_DIR/bmcu_feeder.py"

if [ -L "$TARGET" ]; then
    echo "Updating existing symlink..."
    rm "$TARGET"
elif [ -f "$TARGET" ]; then
    echo "Replacing existing file with symlink..."
    rm "$TARGET"
fi

ln -s "$SOURCE" "$TARGET"
echo "Linked: $TARGET -> $SOURCE"

echo ""
echo "Install complete. Restart Klipper to load the extra:"
echo "  sudo systemctl restart klipper"

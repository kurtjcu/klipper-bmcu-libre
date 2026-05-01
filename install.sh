#!/bin/bash
# install.sh — Install BMCU Klipper extra via symlink
#
# Usage: ./install.sh
#
# Creates symlinks from this repo into your Klipper installation:
#   - klippy/extras/bmcu_feeder.py
#   - klippy/extras/bmcu_channel.py
#   - config/ directory into Klipper config path
#
# Survives Klipper updates (unlike a copy).

set -e

KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
KLIPPER_CONFIG="${KLIPPER_CONFIG:-$HOME/printer_data/config}"
EXTRAS_DIR="$KLIPPER_DIR/klippy/extras"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$EXTRAS_DIR" ]; then
    echo "ERROR: Klipper extras directory not found at $EXTRAS_DIR"
    echo "Set KLIPPER_DIR if Klipper is installed elsewhere:"
    echo "  KLIPPER_DIR=/path/to/klipper ./install.sh"
    exit 1
fi

# --- Symlink Klipper extras ---

link_extra() {
    local name="$1"
    local source="$SCRIPT_DIR/klippy/extras/$name"
    local target="$EXTRAS_DIR/$name"

    if [ ! -f "$source" ]; then
        echo "ERROR: $name not found at $source"
        exit 1
    fi

    if [ -L "$target" ] || [ -f "$target" ]; then
        rm "$target"
    fi

    ln -s "$source" "$target"
    echo "Linked: $target -> $source"
}

link_extra "bmcu_feeder.py"
link_extra "bmcu_channel.py"

# --- Symlink config directory ---

if [ -d "$KLIPPER_CONFIG" ]; then
    CONFIG_LINK="$KLIPPER_CONFIG/bmcu"
    if [ -L "$CONFIG_LINK" ] || [ -d "$CONFIG_LINK" ]; then
        rm -rf "$CONFIG_LINK"
    fi
    ln -s "$SCRIPT_DIR/config" "$CONFIG_LINK"
    echo "Linked: $CONFIG_LINK -> $SCRIPT_DIR/config"
else
    echo ""
    echo "NOTE: Klipper config directory not found at $KLIPPER_CONFIG"
    echo "Set KLIPPER_CONFIG to symlink config files automatically:"
    echo "  KLIPPER_CONFIG=/path/to/config ./install.sh"
    echo ""
    echo "Or copy config files manually:"
    echo "  cp -r $SCRIPT_DIR/config/ $YOUR_CONFIG_DIR/bmcu/"
fi

echo ""
echo "Install complete. Restart Klipper to load the extra:"
echo "  sudo systemctl restart klipper"

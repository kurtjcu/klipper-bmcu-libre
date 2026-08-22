#!/usr/bin/env bash
#
# Build the BMCU libre firmware.
#
# This repo does not vendor the upstream BMCU firmware. Instead it keeps a
# pinned submodule (firmware/upstream) plus a small patch set, and assembles a
# build tree from the two. The submodule itself is never modified, so
# `git status` stays clean and a stray `git submodule update` cannot silently
# discard local work.
#
#   firmware/upstream/   pinned submodule -- jarczakpawel/BMCU-C-PJARCZAK
#   firmware/patches/    our changes to upstream files (74 lines)
#   firmware/src/        our own sources (uart_protocol.*)
#   firmware/build/      assembled tree, generated -- gitignored
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="$HERE/upstream"
BUILD="$HERE/build"
PINNED_SHA="fbff4e3215bd60128446d6078ebc0be3b2a2b5e7"   # tag V10.5
PIO_ENV="bmcu_libre"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '  %s\n' "$*"; }

echo "BMCU libre firmware build"

# --- 1. upstream submodule -------------------------------------------------
if [ ! -f "$UPSTREAM/platformio.ini" ]; then
  die "firmware/upstream is empty. Initialise the submodule first:

    git submodule update --init --recursive"
fi

ACTUAL_SHA="$(git -C "$UPSTREAM" rev-parse HEAD)"
if [ "$ACTUAL_SHA" != "$PINNED_SHA" ]; then
  die "firmware/upstream is at the wrong commit.

    expected  $PINNED_SHA  (V10.5)
    actual    $ACTUAL_SHA

  The patch set in firmware/patches/ is written against V10.5 and is not
  guaranteed to apply to any other revision. To restore the pin:

    git submodule update --init --recursive

  To deliberately move to a newer upstream, re-cut the patches against it
  and update PINNED_SHA in this script."
fi
say "upstream ....... V10.5 ($(echo "$PINNED_SHA" | cut -c1-8))"

# --- 2. assemble a clean build tree ----------------------------------------
rm -rf "$BUILD"
mkdir -p "$BUILD"
# -a preserves the tree; .git is a file (submodule) so exclude it explicitly.
tar -C "$UPSTREAM" --exclude=.git -cf - . | tar -C "$BUILD" -xf -
say "build tree ..... assembled from pinned submodule"

# --- 3. our own sources ----------------------------------------------------
cp "$HERE/src/uart_protocol.cpp" "$HERE/src/uart_protocol.h" "$BUILD/src/"
say "own sources .... uart_protocol.cpp, uart_protocol.h"

# --- 4. patches ------------------------------------------------------------
shopt -s nullglob
PATCHES=("$HERE"/patches/*.patch)
[ ${#PATCHES[@]} -gt 0 ] || die "no patches found in firmware/patches/"
for p in "${PATCHES[@]}"; do
  git -C "$BUILD" apply -p1 --whitespace=nowarn "$p" \
    || die "patch failed to apply: $(basename "$p")

  This usually means firmware/upstream moved off V10.5, or a patch was
  edited by hand. The build tree is left at $BUILD for inspection."
  say "patch .......... $(basename "$p")"
done

# --- 5. build --------------------------------------------------------------
command -v pio >/dev/null 2>&1 || die "PlatformIO ('pio') is not on PATH. See docs/flashing.md."
echo
( cd "$BUILD" && pio run -e "$PIO_ENV" )

BIN="$BUILD/.pio/build/$PIO_ENV/firmware.bin"
[ -f "$BIN" ] || die "build reported success but $BIN is missing."

echo
echo "firmware built: $BIN"

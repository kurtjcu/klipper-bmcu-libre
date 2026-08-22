# BMCU libre firmware

Firmware for the BMCU 370C that replaces the BambuBus RS485 protocol with a
standard 8N1 UART on the onboard CH340, so a Klipper host can drive the unit
over a plain USB-C cable.

## This directory does not contain the upstream firmware

The BMCU firmware itself is the work of **[jarczakpawel](https://github.com/jarczakpawel)**
in [BMCU-C-PJARCZAK](https://github.com/jarczakpawel/BMCU-C-PJARCZAK). It is
**not** copied into this repository. It is referenced as a pinned git submodule
and assembled at build time.

```
firmware/
  upstream/   git submodule -> jarczakpawel/BMCU-C-PJARCZAK @ V10.5 (fbff4e32)
  patches/    our changes to upstream files -- 74 lines across 8 files
  src/        our own sources -- uart_protocol.cpp / .h
  build.sh    assembles upstream + patches + our sources, then builds
  build/      generated, gitignored
```

That split is deliberate. `BMCU-C-PJARCZAK` carries **no licence**, so it is
"all rights reserved" by default and this project has no grant to redistribute
it. Referencing it as a submodule points at the author's own repository instead
of copying his code, and keeps his commit history and authorship intact.

If you are jarczakpawel and would prefer a different arrangement — or would
like to add a licence so this can be simplified — please open an issue.

## What is actually ours

| Path | Lines | Description |
|---|---|---|
| `src/uart_protocol.cpp` | 662 | The 8N1 ASCII command/response protocol on USART1 |
| `src/uart_protocol.h` | 22 | Its public interface |
| `patches/0001-…patch` | 59 | Call sites + `DISABLE_BAMBUBUS` guards in upstream files |
| `patches/0002-…patch` | 15 | The `[env:bmcu_libre]` PlatformIO environment |

## Building

```bash
git submodule update --init --recursive
./firmware/build.sh
# -> firmware/build/.pio/build/bmcu_libre/firmware.bin
```

`build.sh` verifies the submodule sits on the pinned commit before patching. If
upstream has been moved, it stops rather than applying patches to a revision
they were not written against.

The build tree is assembled in `firmware/build/`; the submodule is never
modified, so `git status` stays clean.

See [../docs/flashing.md](../docs/flashing.md) for flashing the result.

## Moving to a newer upstream

1. Check out the new tag in `firmware/upstream/`.
2. Re-cut the patches against it and confirm they apply.
3. Update `PINNED_SHA` in `build.sh` and the version above.
4. Retest on hardware — upstream changes motion control and flash layout
   between releases.

# Third-party licences shipped with Tessera

This file ships inside the Store package so the notices travel with the game.

## Tessera

Tessera is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. The full text is in the `LICENSE` file shipped alongside this one,
and the complete source code is published at the repository linked from the
Store listing and the in-game About screen.

## Quackle engine

The computer player is powered by **Quackle**, the crossword game artificial
intelligence and analysis tool.

- Copyright (C) 2005-2019 Jason Katz-Brown, John O'Laughlin, and John Fultz.
- Licence: GNU GPL version 3 or later (Quackle 0.93 onward; earlier releases
  used the Revised BSD licence).
- Homepage: https://people.csail.mit.edu/jasonkb/quackle and
  https://github.com/quackle/quackle
- Tessera builds the engine from the unmodified Quackle 1.1.0 core
  (`engine/quackle` in the source repository) plus a small command bridge
  (`tools/build_engine.py`). Both are distributed under GPL v3 or later.

## Word list

- **ENABLE** — the Enhanced North American Benchmark Lexicon, compiled by Alan
  Beale. Released for free use; it ships with this package.
- Imported word lists (CSW24, SOWPODS, or your own) are supplied by the player
  and stay on their machine. They are not part of this package. Collins
  Scrabble Words (CSW) is copyright HarperCollins and may not be redistributed.

## Other components

- **pygame** — LGPL v2.1 or later, used unmodified from the Python Package
  Index; its source remains available from pygame.org.
- **SDL2 and libraries** (SDL2_image, SDL2_mixer, SDL2_ttf, freetype) — zlib
  licence and LGPL; used unmodified from pygame's bundled binaries.

## Trademark note

Tessera is an independent word game. It is not affiliated with, endorsed by, or
connected to Mattel, Hasbro, or the SCRABBLE brand.

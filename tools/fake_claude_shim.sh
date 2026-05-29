#!/bin/bash
# Tiny shim so the bridge can call "fake_claude" like it would call "claude".
# The bridge spawns this with extra flags (-p --input-format ... etc); we
# ignore them and just run the fake. Used for the end-to-end smoke below.
exec python3 "$(dirname "$0")/fake_claude.py"

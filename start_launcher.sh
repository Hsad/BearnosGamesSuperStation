#!/bin/bash
ARCADE_DIR="$(dirname "$(realpath "$0")")"
# .bash_profile execs this before sourcing .bashrc, so ~/.local/bin (where
# claude lives) isn't on PATH yet — add it so shelled-out tools resolve.
export PATH="$HOME/.local/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/.local/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export MESA_GL_VERSION_OVERRIDE=3.3
export MESA_GLSL_VERSION_OVERRIDE=330
# Remove ARCADE_DEV=1 when done testing — disables auto-restart on code change
ARCADE_DEV=1 exec python3 "$ARCADE_DIR/launcher/main.py"

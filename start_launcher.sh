#!/bin/bash
ARCADE_DIR="$(dirname "$(realpath "$0")")"
# Remove ARCADE_DEV=1 when done testing — disables auto-restart on code change
ARCADE_DEV=1 exec python3 "$ARCADE_DIR/launcher/main.py"

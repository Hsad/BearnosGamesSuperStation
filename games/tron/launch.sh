#!/bin/bash
SDL_VIDEODRIVER=kmsdrm MESA_GL_VERSION_OVERRIDE=3.3 \
  MESA_GLSL_VERSION_OVERRIDE=330 python3 "$(dirname "$0")/tron.py"

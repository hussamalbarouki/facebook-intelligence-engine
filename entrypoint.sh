#!/bin/sh
set -eu
# Private, internal X display (no TCP listener).
export DISPLAY=:99
Xvfb :99 -screen 0 1365x910x24 -nolisten tcp -ac >/dev/null 2>&1 &
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

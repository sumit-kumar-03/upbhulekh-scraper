#!/usr/bin/env bash
# Start a virtual display, expose it over noVNC on :6080, then run the driver browser in it.
set -e

mkdir -p "$BHULEKH_DATA/out/cmd"
rm -f /tmp/.X99-lock

Xvfb :99 -screen 0 1440x1000x24 -nolisten tcp &
sleep 1
fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -forever -shared -nopw -quiet -rfbport 5900 &
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

echo ">>> open http://localhost:6080/vnc.html to see the browser"
exec python driver.py "$@"

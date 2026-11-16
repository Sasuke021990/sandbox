#!/usr/bin/env bash
# apk-smoke.sh — Install an APK in the Android sandbox, launch it, screenshot, check for crashes.
# Usage: apk-smoke.sh <path-to.apk> [package.name]
#   package.name is optional: it is auto-detected from the newly installed app.
#
# Requires: redroid running on the host (see README-redroid.txt)
# Env:
#   ADB       path to adb binary (default: ../tools/platform-tools/adb relative to this script)
#   ANDROID_HOST  host:port of the redroid adb endpoint (default: 172.16.5.1:5555)

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ADB="${ADB:-$HERE/../tools/platform-tools/adb}"
ANDROID_HOST="${ANDROID_HOST:-172.16.5.1:5555}"
APK="${1:?Usage: apk-smoke.sh <apk> [package.name]}"
PKG="${2:-}"

[ -f "$APK" ] || { echo "FAIL: APK not found: $APK"; exit 2; }
[ -x "$ADB" ] || { echo "FAIL: adb not found at $ADB"; exit 2; }

# 1. Connect
"$ADB" connect "$ANDROID_HOST" >/dev/null 2>&1
sleep 1
"$ADB" -s "$ANDROID_HOST" wait-for-device 2>/dev/null &
WPID=$!
for i in $(seq 1 30); do kill -0 $WPID 2>/dev/null || break; sleep 1; done
kill $WPID 2>/dev/null
"$ADB" -s "$ANDROID_HOST" get-state >/dev/null 2>&1 || { echo "FAIL: no Android device at $ANDROID_HOST — is redroid running on the host?"; exit 3; }
echo "[ok] connected to $ANDROID_HOST: $("$ADB" -s "$ANDROID_HOST" shell getprop ro.build.version.release 2>/dev/null)"

# 2. Detect package (if not given): list 3rd-party packages before/after install
BEFORE="$("$ADB" -s "$ANDROID_HOST" shell pm list packages -3 2>/dev/null | sort)"

# 3. Install
if "$ADB" -s "$ANDROID_HOST" install -r "$APK" > /tmp/apk_install.log 2>&1; then
  echo "[ok] installed"
else
  echo "FAIL: install error:"; cat /tmp/apk_install.log; exit 4
fi

if [ -z "$PKG" ]; then
  AFTER="$("$ADB" -s "$ANDROID_HOST" shell pm list packages -3 2>/dev/null | sort)"
  PKG="$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") | head -1 | sed 's/package://;s/\r//')"
  [ -n "$PKG" ] || { echo "FAIL: could not detect package name (pass it as 2nd argument)"; exit 5; }
fi
echo "[ok] package: $PKG"

# 4. Clean logcat, launch via monkey (opens the default launcher activity)
"$ADB" -s "$ANDROID_HOST" logcat -c 2>/dev/null
"$ADB" -s "$ANDROID_HOST" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 6

# 5. Screenshot + process check + crash check
OUT="/tmp/apk-smoke-$(date +%s)"
"$ADB" -s "$ANDROID_HOST" exec-out screencap -p > "$OUT.png" 2>/dev/null
PID="$("$ADB" -s "$ANDROID_HOST" shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
CRASH="$("$ADB" -s "$ANDROID_HOST" logcat -d 2>/dev/null | grep -E "FATAL EXCEPTION|FATAL SIGNAL|Force finishing activity.*$PKG" | head -3)"

RESULT="PASS"
[ -z "$PID" ] && RESULT="FAIL(crashed or not running)"
[ -n "$CRASH" ] && RESULT="FAIL(crash in logcat)"
[ -s "$OUT.png" ] || RESULT="FAIL(no screenshot)"

echo "RESULT: $RESULT"
echo "package: $PKG"
echo "pid: ${PID:-none}"
echo "screenshot: $OUT.png"
[ -n "$CRASH" ] && { echo "--- crash log ---"; echo "$CRASH"; }

# 6. Cleanup: uninstall to keep the sandbox fresh for the next test
"$ADB" -s "$ANDROID_HOST" uninstall "$PKG" >/dev/null 2>&1
echo "[ok] uninstalled (sandbox clean)"
[ "$RESULT" = "PASS" ] || exit 1

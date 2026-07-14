#!/usr/bin/env bash
# Headless Android emulator verification for the Dish Passport frontend.
# No GUI window: boots -no-window, verifies via adb screenshot + logcat.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
FRONTEND="$REPO_ROOT/frontend"

export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

AVD_NAME="dishport"
IMAGE="system-images;android-35;google_apis;arm64-v8a"
PKG="com.dishport.app"
AZURE_URL="https://dishport-api.agreeablesmoke-e44a377c.eastus.azurecontainerapps.io"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m[fail] %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. Provision emulator package + system image (idempotent) ---------------
# Guard on BOTH the emulator binary AND the image's package.xml — an image dir can
# exist with only a .installer staging folder (interrupted download), which the
# emulator-binary check alone would wrongly treat as "installed".
# IMAGE already starts with "system-images", so map ; -> / against ANDROID_HOME directly.
IMG_DIR="$ANDROID_HOME/$(echo "$IMAGE" | tr ';' '/')"
if [ ! -x "$ANDROID_HOME/emulator/emulator" ]; then
  say "Installing emulator package (one-time)"
  yes | sdkmanager "emulator" >/dev/null || die "emulator install failed"
fi
if [ ! -f "$IMG_DIR/package.xml" ]; then
  say "Installing system image (one-time, ~1GB)"
  rm -rf "$IMG_DIR"   # drop any partial staging dir so the install starts clean
  yes | sdkmanager "$IMAGE" >/dev/null || die "system-image install failed"
  [ -f "$IMG_DIR/package.xml" ] || die "system image installed but package.xml missing"
fi

# --- 2. Create the AVD if absent ---------------------------------------------
if ! avdmanager list avd 2>/dev/null | grep -q "Name: $AVD_NAME"; then
  say "Creating AVD '$AVD_NAME'"
  echo "no" | avdmanager create avd -n "$AVD_NAME" -k "$IMAGE" -d pixel_7 \
    || die "avd create failed"
fi

# --- 3. Boot headless & wait for full boot -----------------------------------
if ! adb devices | grep -q "emulator-"; then
  say "Booting emulator headless"
  nohup emulator -avd "$AVD_NAME" -no-window -no-audio -no-boot-anim \
    -gpu swiftshader_indirect -no-snapshot >/tmp/dishport-emulator.log 2>&1 &
fi
say "Waiting for device"
adb wait-for-device
say "Waiting for full boot"
for _ in $(seq 1 120); do
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
  sleep 2
done
[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] \
  || die "emulator did not finish booting"
adb shell input keyevent 82 >/dev/null 2>&1  # dismiss lock screen

# --- 4. Resolve the backend URL ----------------------------------------------
probe() { curl -sS -m 4 -o /dev/null "$1" 2>/dev/null; }  # any HTTP response = up
API_URL="${1:-${EXPO_PUBLIC_API_URL:-}}"
if [ -z "$API_URL" ]; then
  if probe "$AZURE_URL"; then API_URL="$AZURE_URL"; MODE="azure"
  elif probe "http://localhost:8000"; then API_URL="http://10.0.2.2:8000"; MODE="local"
  else API_URL="http://10.0.2.2:8000"; MODE="none"
  fi
else
  MODE="explicit"
fi
case "$MODE" in
  azure)    say "Backend: live Azure API" ;;
  local)    say "Backend: local Mac backend via 10.0.2.2:8000" ;;
  explicit) say "Backend: explicit URL -> $API_URL" ;;
  none)     warn "No backend reachable (Azure down, no local :8000). Verifying app BOOT ONLY — login round-trips will fail, which is expected." ;;
esac

# --- 5. Build, install & launch ----------------------------------------------
# This is an expo-dev-client build, so `expo run:android` builds + installs +
# launches and then holds Metro in the FOREGROUND (never returns). We run it in the
# background, capture its log, and wait for the "Android Bundled" signal = JS loaded.
say "Building, installing & launching $PKG (compiles debug APK, starts Metro)"
cd "$FRONTEND"
[ -d node_modules ] || npm install
EXPO_LOG="$(mktemp -t dishport-expo.XXXXXX.log)"
adb logcat -c 2>/dev/null || true
# Exactly one emulator is attached, so no --device flag (Expo's --device wants a
# device *name*, not the adb serial emulator-5554, and passing the serial fails).
EXPO_PUBLIC_API_URL="$API_URL" npx expo run:android >"$EXPO_LOG" 2>&1 &
EXPO_PID=$!
cleanup() { kill "$EXPO_PID" 2>/dev/null; pkill -P "$EXPO_PID" 2>/dev/null; }
trap cleanup EXIT

say "Waiting for Gradle build + JS bundle (first build ~3-5 min)"
for _ in $(seq 1 150); do  # up to ~10 min
  grep -qa "Android Bundled" "$EXPO_LOG" && break
  grep -qaE "BUILD FAILED|FAILURE:|Could not|error:" "$EXPO_LOG" && { tail -30 "$EXPO_LOG"; die "build/launch failed — see log above ($EXPO_LOG)"; }
  kill -0 "$EXPO_PID" 2>/dev/null || { tail -30 "$EXPO_LOG"; die "expo run:android exited early — see log above ($EXPO_LOG)"; }
  sleep 4
done
grep -qa "Android Bundled" "$EXPO_LOG" || { tail -30 "$EXPO_LOG"; die "timed out waiting for JS bundle"; }

# --- 6. Verify ----------------------------------------------------------------
say "Verifying install + launch"
adb shell pm list packages | grep -q "$PKG" || die "$PKG not installed"
# Dev-client opens its developer-menu overlay on launch; BACK returns to the app.
if adb shell dumpsys activity activities 2>/dev/null | grep -q "$PKG/expo.modules.devmenu.DevMenuActivity"; then
  adb shell input keyevent 4   # dismiss dev menu -> MainActivity
  sleep 2
fi
TOP="$(adb shell dumpsys activity activities 2>/dev/null | grep -m1 topResumedActivity)"
CRASH="$(adb logcat -d 2>/dev/null | grep -iE "FATAL EXCEPTION|AndroidRuntime.*$PKG|ReactNativeJS.*Error" | tail -20)"
adb exec-out screencap -p > "$SKILL_DIR/screenshot.png"

say "Result"
echo "  package installed: yes ($PKG)"
echo "  foreground:        ${TOP:-unknown}"
echo "  screenshot:        $SKILL_DIR/screenshot.png"
echo "  backend mode:      $MODE ($API_URL)"
if [ -n "$CRASH" ]; then
  warn "Crash lines detected in logcat:"; echo "$CRASH"
  die "app launched but crashed — see logcat above"
fi
echo "  logcat:            clean (no FATAL/AndroidRuntime/JS errors)"
say "PASS — open screenshot.png to confirm the login screen rendered."
echo "(Metro + emulator are torn down on exit; run again to reuse a booted emulator.)"

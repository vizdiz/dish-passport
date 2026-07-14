---
name: verify-android
description: Launch the Dish Passport frontend on a headless Android emulator entirely via CLI (no GUI window) and verify it boots and renders. Use when asked to run, test, or screenshot the app on an Android emulator, or to confirm the frontend works end-to-end on Android. Handles a down/unavailable Azure API by falling back to a local backend or app-boot-only verification.
---

# Verify Dish Passport on a headless Android emulator

Runs the Expo/React Native frontend (`com.dishport.app`) on an emulated device
with **no GUI window**, then proves it came up by capturing a screenshot and
scanning logcat — all from the CLI.

## When to use
- "run / test / screenshot the app on an Android emulator"
- "verify the frontend works on Android"
- After a frontend or build-config change, to confirm it still launches.

## Prerequisites (the script provisions what's missing)
- Android cmdline-tools at `ANDROID_HOME=/opt/homebrew/share/android-commandlinetools`
- Java 17 (`java -version`), `adb`, `sdkmanager`, `avdmanager` — already present here.
- The script installs the `emulator` package + `system-images;android-35;google_apis;arm64-v8a`
  and creates the `dishport` AVD if they don't exist (idempotent).

## The API-URL gotcha (read before running)
`frontend/src/config.ts` reads `EXPO_PUBLIC_API_URL`, defaulting to `http://localhost:8000`.
Inside the emulator, `localhost` is the *emulator itself*, not your Mac. Host machine = `10.0.2.2`.
So the script resolves the backend URL in this order:
1. An explicit URL passed as `$1` (or `EXPO_PUBLIC_API_URL` in the env).
2. Live Azure API — **only if it responds** (it is often down; the script probes it).
3. A local backend on the Mac (`http://10.0.2.2:8000`) — **only if it responds**.
4. None reachable → still builds & launches to verify the app **boots and renders**
   the login screen. Register/login round-trips won't work without a backend, and
   that's expected; the screenshot + clean logcat are the pass criteria.

## Run it

```bash
bash .claude/skills/verify-android/run.sh            # auto-resolve API URL
bash .claude/skills/verify-android/run.sh https://my-api.example.com   # force a URL
```

## What counts as verified
- `pm list packages` shows `com.dishport.app` installed.
- Launch produces **no** `FATAL`/`AndroidRuntime` lines in logcat.
- `screenshot.png` (written next to the script) shows the login/register screen.

Open the screenshot to confirm the UI rendered — that single image validates the
emulator, the JS bundle, and the app all came up together.

## Cleanup
`adb emu kill` stops the headless emulator. The AVD and system image persist for next time.

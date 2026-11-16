# Sandbox Service — Android + web/browser test environment for OpenBot bots

Three containers on one Docker network: `android` (redroid, Android 14, headless),
`api` (FastAPI HTTP + MCP wrapper that drives Android via adb), and `aio`
(AIO Sandbox: sandboxed browser + shell + files + Jupyter + VS Code + MCP).

## One-time host setup (on the machine that runs OpenBot, needs sudo)

```bash
# 1. kernel modules for Android-in-Docker (Ubuntu 24.04) + docker
sudo apt install -y linux-modules-extra-$(uname -r) docker.io docker-compose-v2
sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"
echo 'binder_linux options binder_linux devices="binder,hwbinder,vndbinder"' \
  | sudo tee /etc/modules-load.d/redroid.conf

# 2. shared network + attach OpenBot's container (find its name: sudo docker ps)
sudo docker network create devteam-sandbox
sudo docker network connect devteam-sandbox <openbot-container-name>

# 3. build & start
cd sandbox-service && sudo -E docker compose up -d --build
```

First boot takes 1–3 minutes. Check: `sudo docker ps` → both `sandbox-android-1`
and `sandbox-api-1` Up; then from inside OpenBot's container: `curl http://sandbox:8000/status`.

## What the bots use

HTTP API (curl-friendly): `http://sandbox:8000`
| Endpoint | Purpose |
|---|---|
| `GET /status` | device state, Android version |
| `POST /install` (multipart `file`=<apk>) | install, returns package name |
| `POST /launch` `{"package":"..."}` | launch app |
| `GET /screenshot` | PNG of the screen |
| `POST /tap` `{"x":..,"y":..}` / `POST /swipe` / `POST /type` / `POST /key` | drive the UI |
| `POST /shell` `{"command":"..."}` | adb shell on the (sandboxed) device |
| `GET /logcat?tail=500` | logs; look for FATAL EXCEPTION |
| `POST /uninstall` `{"package":"..."}` | clean up |
| `POST /smoke` (multipart `file`=<apk>) | one-shot: install→launch→screenshot→crash-check→uninstall, returns verdict |

Example smoke test from inside OpenBot's container:
```bash
curl -s -F file=@app.apk http://sandbox:8000/smoke
```

MCP: `http://sandbox:8001/mcp` — add as a streamable-HTTP MCP server in OpenBot
(settings → MCP servers → URL). Tools: `install_apk`, `launch`, `screenshot_png_base64`,
`tap`, `swipe`, `type_text`, `press_key`, `shell_cmd`, `logcat`, `uninstall`, `status`.

## AIO Sandbox (web apps & browser testing): `http://aio:8080`

All-in-one sandbox for web/backend and Linux-side testing (image `agent-infra/sandbox`,
Apache-2.0, pinned to release 1.11.0):

| URL | Purpose |
|---|---|
| `http://aio:8080/v1/docs` | HTTP API docs (shell exec, file read/write, browser screenshot, Jupyter) |
| `http://aio:8080/mcp` | MCP server: browser, file, shell, markitdown tools |
| `http://aio:8080/vnc/index.html?autoconnect=true` | watch the sandboxed browser visually (host-only) |
| `http://aio:8080/code-server/` | VS Code in the sandbox (host-only) |

Setup: copy `.env.example` to `.env` and set `SANDBOX_API_KEY` (auth for API/Jupyter/VNC).
Bots authenticate with the `X-AIO-API-Key` header. If unset, services stay open — fine on
the internal docker network, never expose 8080 publicly.

RAM note: AIO (browser + Chrome ≈ 1.5–2 GB) + redroid (2–3 GB) together exceed the
~5 GB this host has free. Run one at a time, or add `mem_limit`/`cpus` per service in
docker-compose.yml.

## Ops

- Stop/start: `sudo docker compose stop|start` (run in sandbox-service/)
- Fresh device (wipe all apps/data): `sudo rm -rf ~/redroid-data && sudo docker compose restart android`
- Do NOT expose ports 8000/8001/5555 to the internet (adb + open shell endpoint = compromise risk).
- Parallel tests: 1 emulator ≈ 2–3 GB RAM. With ~5 GB free on the host, run 1 Android test
  at a time; queue others. For a 2nd parallel Android, add another `android` service with
  its own data volume and adb port.

## Linux GUI & web apps (already available in OpenBot's container)

- Web/backend: bots run servers directly (node/npm present).
- Linux GUI: Xvfb virtual display present; root apt is blocked in-container, so test
  apps via extracted .deb / pip / npm where possible.

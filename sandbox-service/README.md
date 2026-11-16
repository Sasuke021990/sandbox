# Sandbox Service — webapp/backend test environment for OpenBot bots

One container: `aio` — [AIO Sandbox](https://github.com/agent-infra/sandbox)
(Apache-2.0): sandboxed browser + shell + file ops + Jupyter + VS Code server + MCP,
all in one Docker container with a shared filesystem.

## One-time host setup (on the machine that runs OpenBot, needs sudo)

```bash
sudo apt install -y docker.io docker-compose-v2

# shared network + attach OpenBot's container (find its name: sudo docker ps)
sudo docker network create devteam-sandbox
sudo docker network connect devteam-sandbox <openbot-container-name>

# build & start
cd sandbox-service
# (no API key needed — auth removed by user choice)
sudo -E docker compose up -d
```

Check: `sudo docker ps` → `sandbox-aio-1` Up; from inside OpenBot's container:
`curl http://aio:8080/v1/sandbox`

## What the bots use: `http://aio:8080`

| URL | Purpose |
|---|---|
| `http://aio:8080/v1/docs` | HTTP API docs: shell exec, file read/write, browser control, Jupyter |
| `http://aio:8080/mcp` | MCP server: browser, file, shell, markitdown tools |
| `http://aio:8080/vnc/index.html?autoconnect=true` | watch the sandboxed browser visually (host-only) |
| `http://aio:8080/code-server/` | VS Code in the sandbox (host-only) |

Typical bot workflow for a webapp/backend test:
1. `POST /v1/file/write` — copy project files into the sandbox
2. `POST /v1/shell/exec` — `npm install && npm run build && npm start` (or Python)
3. Browser tools / CDP — load the app's preview URL, click through, screenshot
4. `POST /v1/file/read` — pull logs/results back out

Client SDKs (optional, nicer than curl): `pip install agent-sandbox` /
`npm install @agent-infra/sandbox`.

## Ops

- Stop/start: `sudo docker compose stop|start` (in sandbox-service/)
- Fresh workspace (wipe all files): `sudo docker compose down && sudo docker volume rm sandbox-service_aio_data`
- No API key (auth removed): the API/Jupyter/VNC are open, so port 8080 must never leave this machine — never publish it, never bind it to 0.0.0.0
- Do NOT expose port 8080 to the internet.
- RAM: browser + Chrome ≈ 1.5–2 GB peak. Add `mem_limit`/`cpus` under the `aio`
  service if the host is tight (e.g. `mem_limit: 2g`, `cpus: 2`).
- Note: `seccomp:unconfined` is required by AIO's bundled Chrome — a deliberate
  trade-off; keep 8080 private.

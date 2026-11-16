import asyncio, os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

ADB = "adb"
DEVICE = os.environ.get("ANDROID_SERIAL", "android:5555")

mcp = FastMCP("android-sandbox", instructions=(
    "Headless Android 14 test sandbox. Tools: install_apk (multipart upload), launch, "
    "screenshot, tap, swipe, type_text, press_key, shell_cmd, logcat, uninstall, status. "
    "Typical test: install_apk -> launch -> screenshot -> logcat (crash check) -> uninstall."
))

api = FastAPI(title="android-sandbox API")
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------- shared helpers ----------

async def adb(*args, timeout=180):
    try:
        p = await asyncio.create_subprocess_exec(
            ADB, "-s", DEVICE, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
        return p.returncode, out
    except asyncio.TimeoutError:
        return 124, b"adb timeout"

async def ensure_device():
    rc, out = await adb("get-state")
    if rc != 0:
        await adb("connect", DEVICE, timeout=15)
        rc, out = await adb("get-state")
        if rc != 0:
            raise HTTPException(503, f"Android device not ready: {out.decode(errors='replace').strip()}")

async def list_packages_3rd():
    _, out = await adb("shell", "pm", "list", "packages", "-3")
    return set(out.decode(errors="replace").split())

async def pid_of(pkg: str) -> str:
    _, out = await adb("shell", "pidof", pkg)
    return out.decode(errors="replace").strip() or ""

async def recent_crash(pkg: str = None) -> list[str]:
    _, out = await adb("logcat", "-d")
    lines = out.decode(errors="replace").splitlines()
    pats = ("FATAL EXCEPTION", "FATAL SIGNAL")
    hits = [l for l in lines if any(p in l for p in pats)]
    if pkg:
        hits += [l for l in lines if pkg in l and "Force finishing activity" in l]
    return hits[-10:]

# ---------- core operations (shared by API and MCP) ----------

async def op_install(apk_bytes: bytes, filename: str = "app.apk"):
    await ensure_device()
    apk = f"/tmp/{filename}"
    with open(apk, "wb") as f:
        f.write(apk_bytes)
    before = await list_packages_3rd()
    rc, out = await adb("install", "-r", apk, timeout=300)
    os.remove(apk)
    if rc != 0:
        raise HTTPException(400, "install failed: " + out.decode(errors="replace"))
    after = await list_packages_3rd()
    new = sorted(after - before)
    names = [p.removeprefix("package:").strip() for p in new]
    return {"installed": True, "package": names[0] if names else None, "new_packages": names}

async def op_launch(pkg: str, wait_s: int = 6):
    await ensure_device()
    await adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    await asyncio.sleep(wait_s)
    pid = await pid_of(pkg)
    return {"launched": bool(pid), "pid": pid or None}

async def op_screenshot():
    await ensure_device()
    rc, out = await adb("exec-out", "screencap", "-p")
    if rc != 0 or not out:
        raise HTTPException(500, "screencap failed: " + out.decode(errors="replace"))
    return out

async def op_tap(x: int, y: int):
    await ensure_device()
    await adb("shell", "input", "tap", str(x), str(y))
    return {"tapped": [x, y]}

async def op_swipe(x1: int, y1: int, x2: int, y2: int, ms: int = 300):
    await ensure_device()
    await adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))
    return {"swiped": [x1, y1, x2, y2]}

async def op_type(text: str):
    await ensure_device()
    await adb("shell", "input", "text", text.replace(" ", "%s"))
    return {"typed": text}

async def op_key(keycode: str):
    await ensure_device()
    await adb("shell", "input", "keyevent", keycode)  # e.g. KEYCODE_BACK, KEYCODE_HOME, 4, 3
    return {"key": keycode}

async def op_shell(cmd: str):
    await ensure_device()
    rc, out = await adb("shell", cmd)
    return {"code": rc, "output": out.decode(errors="replace")}

async def op_logcat(tail: int = 500):
    await ensure_device()
    _, out = await adb("logcat", "-d", "-t", str(tail))
    return out.decode(errors="replace")

async def op_uninstall(pkg: str):
    await ensure_device()
    _, out = await adb("uninstall", pkg)
    return {"uninstalled": pkg, "output": out.decode(errors="replace").strip()}

async def op_status():
    _, out = await adb("get-state")
    st = out.decode(errors="replace").strip()
    _, ver = await adb("shell", "getprop", "ro.build.version.release")
    _, boot = await adb("shell", "getprop", "sys.boot_completed")
    return {"device": DEVICE, "state": st, "android": ver.decode().strip(),
            "boot_completed": boot.decode().strip() == "1"}

# ---------- FastAPI routes ----------

@api.get("/status")
async def r_status():
    return await op_status()

@api.post("/install")
async def r_install(file: UploadFile = File(...)):
    return await op_install(await file.read(), file.filename or "app.apk")

@api.post("/launch")
async def r_launch(body: dict):
    return await op_launch(body["package"])

@api.get("/screenshot")
async def r_screenshot():
    return Response(await op_screenshot(), media_type="image/png")

@api.post("/tap")
async def r_tap(body: dict):
    return await op_tap(int(body["x"]), int(body["y"]))

@api.post("/swipe")
async def r_swipe(body: dict):
    return await op_swipe(int(body["x1"]), int(body["y1"]), int(body["x2"]), int(body["y2"]), int(body.get("ms", 300)))

@api.post("/type")
async def r_type(body: dict):
    return await op_type(body["text"])

@api.post("/key")
async def r_key(body: dict):
    return await op_key(body["keycode"])

@api.post("/shell")
async def r_shell(body: dict):
    return await op_shell(body["command"])

@api.get("/logcat", response_class=PlainTextResponse)
async def r_logcat(tail: int = 500):
    return await op_logcat(tail)

@api.post("/uninstall")
async def r_uninstall(body: dict):
    return await op_uninstall(body["package"])

@api.post("/smoke")   # one-shot: install + launch + screenshot + crash check + uninstall
async def r_smoke(file: UploadFile = File(...)):
    res = await op_install(await file.read(), file.filename or "app.apk")
    pkg = res.get("package")
    if not pkg:
        return {**res, "smoke": "PASS-install; pass 'package' to /launch manually"}
    launch = await op_launch(pkg)
    png = await op_screenshot()
    crashes = await recent_crash(pkg)
    verdict = "PASS" if launch.get("pid") and not crashes else "FAIL"
    un = await op_uninstall(pkg)
    return {"verdict": verdict, "package": pkg, "launch": launch,
            "crashes": crashes, "screenshot_bytes": len(png), "uninstall": un}

mcp_app = mcp.streamable_http_app()

# ---------- MCP tools ----------

@mcp.tool()
async def status() -> dict:
    """Check the Android sandbox: state, Android version, boot status."""
    return await op_status()

@mcp.tool()
async def install_apk(apk_base64: str, filename: str = "app.apk") -> dict:
    """Install an APK (base64-encoded) into the sandbox. Returns the package name."""
    import base64
    return await op_install(base64.b64decode(apk_base64), filename)

@mcp.tool()
async def launch(package: str) -> dict:
    """Launch an installed app by package name."""
    return await op_launch(package)

@mcp.tool()
async def screenshot_png_base64() -> str:
    """Take a screenshot, returned as base64 PNG."""
    import base64
    return base64.b64encode(await op_screenshot()).decode()

@mcp.tool()
async def tap(x: int, y: int) -> dict:
    """Tap the screen at (x, y)."""
    return await op_tap(x, y)

@mcp.tool()
async def swipe(x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> dict:
    """Swipe from (x1,y1) to (x2,y2) over ms milliseconds."""
    return await op_swipe(x1, y1, x2, y2, ms)

@mcp.tool()
async def type_text(text: str) -> dict:
    """Type text into the focused field (no spaces in text; use send via shell if needed)."""
    return await op_type(text)

@mcp.tool()
async def press_key(keycode: str) -> dict:
    """Press a key event, e.g. 'KEYCODE_BACK', 'KEYCODE_HOME', '4', '3'."""
    return await op_key(keycode)

@mcp.tool()
async def shell_cmd(command: str) -> dict:
    """Run a shell command on the Android device (sandboxed; safe to use freely)."""
    return await op_shell(command)

@mcp.tool()
async def logcat(tail: int = 500) -> str:
    """Read recent device log; look for FATAL EXCEPTION / FATAL SIGNAL for crashes."""
    return await op_logcat(tail)

@mcp.tool()
async def uninstall(package: str) -> dict:
    """Uninstall an app to keep the sandbox clean."""
    return await op_uninstall(package)

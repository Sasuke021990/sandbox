ANDROID SANDBOX (redroid) — run these ONCE on the HOST machine, as a user with sudo.
The host is the computer that runs OpenBot (this container is 172.16.5.2; host is 172.16.5.1).

1) Kernel modules for Android-in-Docker (Ubuntu 24.04, no KVM needed):
   sudo apt install -y linux-modules-extra-$(uname -r) docker.io
   sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"
   echo 'binder_linux options binder_linux devices="binder,hwbinder,vndbinder"' \
     | sudo tee /etc/modules-load.d/redroid.conf
   sudo systemctl enable --now docker

2) Start the Android sandbox:
   sudo docker run -itd --rm --privileged --name android-sandbox \
     -v ~/redroid-data:/data \
     -p 5555:5555 \
     redroid/redroid:14.0.0-latest

   Optional screen size (add to the end of the run command):
     androidboot.redroid_width=1080 androidboot.redroid_height=1920 androidboot.redroid_dpi=480

3) Verify:   sudo docker ps   →  android-sandbox should be "Up".
   From inside OpenBot, a bot runs:  sandbox/apk-smoke.sh /path/to/app.apk
   It connects to 172.16.5.1:5555 automatically.

Notes:
- Do NOT expose port 5555 to the internet (redroid docs warn: adb on a public network = compromise risk).
- Stop/restart sandbox:  sudo docker restart android-sandbox   (or  sudo docker stop android-sandbox)
- Fresh device (wipe):   sudo rm -rf ~/redroid-data && rerun step 2
- If bots fail to connect, check host firewall allows container subnet → host port 5555.

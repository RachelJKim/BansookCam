# BansookCam

Live two-camera PWA for ~10 users on iOS/Android.
Running on a Jetson Orin Nano with two USB cameras.

## Architecture

```
Cameras (V4L2)
  └─ FFmpeg (MJPEG → H.264)
       └─ MediaMTX  :8554 RTSP (localhost)
                    :8888 LL-HLS
            └─ nginx  :8080  serves PWA + proxies /hls/ + basic auth
                 └─ Cloudflare Tunnel → custom domain
```

## File Structure

```
mediamtx.yml          MediaMTX config (LL-HLS, 2 camera paths)
nginx/
  bansookcam.conf     nginx site config (proxy, auth)
pwa/
  index.html          Two-player UI (hls.js + native HLS for iOS)
  manifest.json       PWA manifest
  sw.js               Service worker
  icon-192/512.png    App icons
setup/
  install.sh          Full install script
  mediamtx.service    systemd unit — MediaMTX
  bansookcam.service  systemd unit — nginx
  bansookcam-tunnel.service  systemd unit — cloudflared
```

## Running

Services are managed via systemd:

```bash
sudo systemctl start mediamtx
sudo systemctl start bansookcam
sudo systemctl start bansookcam-tunnel
```

Check status:

```bash
sudo systemctl status mediamtx bansookcam bansookcam-tunnel
```

Verify HLS streams are up:

```bash
curl -o /dev/null -w "%{http_code}" http://localhost:8888/cam0/index.m3u8
curl -o /dev/null -w "%{http_code}" http://localhost:8888/cam1/index.m3u8
```

## First-time Setup

Run the install script, then complete these manual steps:

```bash
sudo htpasswd -c /etc/nginx/bansookcam.htpasswd bansook
cloudflared tunnel login
cloudflared tunnel create bansookcam
# create ~/.cloudflared/config.yml pointing to localhost:8080
# add CNAME in Cloudflare dashboard
sudo systemctl enable --now bansookcam-tunnel.service
```

## Cameras

| Path | Device    | Model         |
|------|-----------|---------------|
| cam0 | /dev/video0 | Arducam UC852 |
| cam1 | /dev/video2 | USB camera    |

#!/usr/bin/env bash
# BansookCam install script — MediaMTX + nginx PWA + Cloudflare Tunnel
# Run as: sudo bash setup/install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)

# Normalize arch for MediaMTX release naming
case "$ARCH" in
  aarch64|arm64) MTX_ARCH="arm64v8" ;;
  armv7l|armhf)  MTX_ARCH="armv7"   ;;
  x86_64|amd64)  MTX_ARCH="amd64"   ;;
  *)             MTX_ARCH="$ARCH"   ;;
esac

# --- 1. MediaMTX ---
if ! command -v mediamtx &>/dev/null; then
    echo "Installing MediaMTX..."
    MTX_VERSION="v1.9.1"
    MTX_URL="https://github.com/bluenviron/mediamtx/releases/download/${MTX_VERSION}/mediamtx_${MTX_VERSION}_linux_${MTX_ARCH}.tar.gz"
    curl -fsSL "$MTX_URL" -o /tmp/mediamtx.tar.gz
    tar -xzf /tmp/mediamtx.tar.gz -C /tmp mediamtx
    mv /tmp/mediamtx /usr/local/bin/mediamtx
    chmod +x /usr/local/bin/mediamtx
    rm /tmp/mediamtx.tar.gz
    echo "MediaMTX installed: $(mediamtx --version 2>&1 | head -1)"
else
    echo "MediaMTX already installed: $(mediamtx --version 2>&1 | head -1)"
fi

# --- 2. FFmpeg (needed for V4L2 camera capture) ---
if ! command -v ffmpeg &>/dev/null; then
    echo "Installing FFmpeg..."
    apt-get install -y ffmpeg
else
    echo "FFmpeg already installed: $(ffmpeg -version 2>&1 | head -1)"
fi

# --- 3. nginx ---
if ! command -v nginx &>/dev/null; then
    echo "Installing nginx..."
    apt-get install -y nginx apache2-utils
else
    echo "nginx already installed: $(nginx -v 2>&1)"
fi

# --- 4. cloudflared ---
if ! command -v cloudflared &>/dev/null; then
    echo "Installing cloudflared..."
    # Use dpkg arch for .deb
    DEB_ARCH=$(dpkg --print-architecture 2>/dev/null || echo "$ARCH")
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${DEB_ARCH}.deb" \
        -o /tmp/cloudflared.deb
    dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
else
    echo "cloudflared already installed: $(cloudflared --version)"
fi

# --- 4. nginx site config ---
echo "Configuring nginx..."
cp "$REPO_DIR/nginx/bansookcam.conf" /etc/nginx/sites-available/bansookcam
ln -sf /etc/nginx/sites-available/bansookcam /etc/nginx/sites-enabled/bansookcam
rm -f /etc/nginx/sites-enabled/default

nginx -t

# --- 5. Generate PWA icons (simple colored squares) ---
if [ ! -f "$REPO_DIR/pwa/icon-192.png" ]; then
    echo "Generating placeholder icons..."
    if command -v python3 &>/dev/null; then
        python3 - "$REPO_DIR/pwa" <<'PYEOF'
import struct, zlib, sys, os

def make_png(size, color):
    def chunk(tag, data):
        c = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)
    r, g, b = color
    raw = b''
    for _ in range(size):
        row = b'\x00' + bytes([r, g, b] * size)
        raw += row
    compressed = zlib.compress(raw, 9)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', compressed)
            + chunk(b'IEND', b''))

base = sys.argv[1]
for sz in [192, 512]:
    with open(os.path.join(base, f'icon-{sz}.png'), 'wb') as f:
        f.write(make_png(sz, (30, 120, 200)))
print("Icons generated.")
PYEOF
    else
        echo "python3 not found — skipping icon generation. Add icon-192.png and icon-512.png to pwa/ manually."
    fi
fi

# --- 6. systemd service files ---
echo "Installing systemd service files..."
cp "$SCRIPT_DIR/mediamtx.service"         /etc/systemd/system/mediamtx.service
cp "$SCRIPT_DIR/bansookcam.service"        /etc/systemd/system/bansookcam.service
cp "$SCRIPT_DIR/bansookcam-tunnel.service" /etc/systemd/system/bansookcam-tunnel.service

systemctl daemon-reload

# --- 7. Enable and start MediaMTX + nginx ---
echo "Enabling mediamtx.service and bansookcam.service..."
systemctl enable --now mediamtx.service
systemctl enable --now bansookcam.service

echo ""
echo "============================================================"
echo "  Install complete. Manual steps remaining:"
echo "============================================================"
echo ""
echo "  A. Set nginx basic-auth password:"
echo "     sudo htpasswd -c /etc/nginx/bansookcam.htpasswd bansook"
echo "     sudo systemctl reload bansookcam"
echo ""
echo "  B. Authenticate with Cloudflare (one-time, as your user):"
echo "     cloudflared tunnel login"
echo ""
echo "  C. Create the tunnel (one-time):"
echo "     cloudflared tunnel create bansookcam"
echo ""
echo "  D. Create ~/.cloudflared/config.yml:"
echo "     tunnel: bansookcam"
echo "     credentials-file: /home/rachel/.cloudflared/<TUNNEL-ID>.json"
echo "     ingress:"
echo "       - hostname: cam.yourdomain.com"
echo "         service: http://localhost:8080"
echo "       - service: http_status:404"
echo ""
echo "  E. Add DNS CNAME in Cloudflare dashboard:"
echo "     cam.yourdomain.com  CNAME  <TUNNEL-ID>.cfargotunnel.com"
echo ""
echo "  F. Enable the tunnel service:"
echo "     sudo systemctl enable --now bansookcam-tunnel.service"
echo ""
echo "  G. Verify:"
echo "     sudo systemctl status mediamtx bansookcam bansookcam-tunnel"
echo "     curl http://localhost:8888/cam0/index.m3u8"
echo ""

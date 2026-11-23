#!/bin/sh
# Usage: sh scripts/install.sh [user@router] [management-url]

set -e

NETBIRD_VERSION="0.83.2"
ROUTER="${1:-root@192.168.8.1}"
MGMT_URL="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/gl-sdk4-netbird/root"

push() {
	ssh "$ROUTER" "cat > '$2' && chmod $3 '$2'" < "$1"
	echo "  OK  $2"
}

echo ">> Installing NetBird v${NETBIRD_VERSION} on ${ROUTER}"

ssh "$ROUTER" NETBIRD_VERSION="$NETBIRD_VERSION" sh -s <<'EOF'
set -e
case "$(uname -m)" in
	aarch64) arch=arm64 ;;
	x86_64) arch=amd64 ;;
	armv6l | armv7l) arch=armv6 ;;
	*) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

if [ "$(/usr/bin/netbird version 2>/dev/null)" = "$NETBIRD_VERSION" ]; then
	echo "   netbird $NETBIRD_VERSION already installed"
	exit 0
fi

base="https://github.com/netbirdio/netbird/releases/download/v${NETBIRD_VERSION}"
tarball="netbird_${NETBIRD_VERSION}_linux_${arch}.tar.gz"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fsSL -o "$tmp/$tarball" "$base/$tarball"
curl -fsSL -o "$tmp/checksums.txt" "$base/netbird_${NETBIRD_VERSION}_checksums.txt"
(cd "$tmp" && grep "  $tarball\$" checksums.txt | sha256sum -c -)
tar -xzf "$tmp/$tarball" -C "$tmp" netbird
chmod 755 "$tmp/netbird"
mv "$tmp/netbird" /usr/bin/netbird
echo "   installed netbird $(/usr/bin/netbird version)"
EOF

ssh "$ROUTER" "mkdir -p /usr/libexec /lib/upgrade/keep.d"
push "$PKG/etc/init.d/netbird" /etc/init.d/netbird 755
push "$PKG/usr/libexec/netbird-login.sh" /usr/libexec/netbird-login.sh 755
push "$PKG/usr/libexec/netbird-exit-rules.sh" /usr/libexec/netbird-exit-rules.sh 755
push "$ROOT/scripts/netbird-cleanup.sh" /usr/libexec/netbird-cleanup.sh 755
push "$PKG/lib/upgrade/keep.d/netbird" /lib/upgrade/keep.d/netbird 644

if ! ssh "$ROUTER" "test -f /etc/config/netbird"; then
	push "$PKG/etc/config/netbird" /etc/config/netbird 644
fi

ssh "$ROUTER" MGMT_URL="$MGMT_URL" sh -s <<'EOF'
set -e

uci -q get netbird.settings >/dev/null || uci -q rename netbird.@settings[0]=settings || true
uci -q get netbird.connection >/dev/null || uci -q rename netbird.@connection[0]=connection || true
[ -n "$MGMT_URL" ] && uci set netbird.connection.management_url="$MGMT_URL"
uci commit netbird

if grep -q 'netbird service run' /etc/rc.local 2>/dev/null; then
	sed -i '/^# ── NetBird/,/netbird-watchdog\.sh ) &$/d' /etc/rc.local
	echo "   removed the old NetBird start block from /etc/rc.local"
fi

if crontab -l 2>/dev/null | grep -q netbird-watchdog; then
	crontab -l 2>/dev/null | grep -v netbird-watchdog | crontab -
	/etc/init.d/cron restart >/dev/null 2>&1 || true
	echo "   removed the netbird-watchdog cron job"
fi
rm -f /usr/libexec/netbird-watchdog.sh

/etc/init.d/netbird stop >/dev/null 2>&1 || true
killall -q netbird 2>/dev/null || true
/etc/init.d/netbird enable
/etc/init.d/netbird start
echo "   procd service enabled and started"
EOF

echo ""
echo ">> Done. Sign the router in once:"
echo "   ssh ${ROUTER} /usr/libexec/netbird-login.sh"
echo "   (or use the NetBird page in the GL.iNet admin panel)"

#!/bin/sh
# Deploy the NetBird web UI. Run scripts/install.sh first.
# Usage: sh nginx-app-netbird/deploy.sh [user@router]

set -e

ROUTER="${1:-root@192.168.8.1}"
DIR="$(cd "$(dirname "$0")" && pwd)"

push() {
	ssh "$ROUTER" "cat > '$2' && chmod $3 '$2'" < "$1"
	echo "  OK  $2"
}

echo ">> Deploying the NetBird web UI to ${ROUTER}..."

ssh "$ROUTER" "mkdir -p /www/netbird /www/cgi-bin /usr/libexec /usr/share/gl-ngx /etc/nginx/gl-conf.d"
push "$DIR/index.html"             /www/netbird/index.html 644
push "$DIR/netbird-api.cgi"        /www/cgi-bin/netbird-api 755
push "$DIR/netbird-access.lua"     /usr/share/gl-ngx/netbird-access.lua 644
push "$DIR/netbird.conf"           /etc/nginx/gl-conf.d/netbird.conf 644
push "$DIR/netbird-toggle-exit.sh" /usr/libexec/netbird-toggle-exit.sh 755
push "$DIR/netbird-setup-api.sh"   /usr/libexec/netbird-setup-api.sh 755

ssh "$ROUTER" "rm -rf /var/run/netbird-cgi.lock && nginx -t && nginx -s reload"

echo ""
echo ">> Done. Open the GL.iNet admin panel → Applications → NetBird"
echo "   (or http://192.168.8.1/netbird/ while signed in to the panel)"

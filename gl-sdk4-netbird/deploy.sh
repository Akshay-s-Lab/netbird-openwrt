#!/bin/sh
# Add NetBird to the GL.iNet admin panel sidebar. Run scripts/install.sh and nginx-app-netbird/deploy.sh first.
# Usage: sh gl-sdk4-netbird/deploy.sh [user@router]

set -e

ROUTER="${1:-root@192.168.8.1}"
DIR="$(cd "$(dirname "$0")" && pwd)"

push() {
	ssh "$ROUTER" "cat > '$2' && chmod $3 '$2'" < "$DIR/$1"
	echo "  OK  $2"
}

echo ">> Deploying the GL.iNet panel entry to ${ROUTER}..."

ssh "$ROUTER" "mkdir -p /usr/share/oui/menu.d /www/i18n /www/views"
push root/usr/share/oui/menu.d/netbirdview.json /usr/share/oui/menu.d/netbirdview.json 644
push root/www/i18n/gl-sdk4-ui-netbirdview.en.json /www/i18n/gl-sdk4-ui-netbirdview.en.json 644
push root/www/views/gl-sdk4-ui-netbirdview.common.js.gz /www/views/gl-sdk4-ui-netbirdview.common.js.gz 644

echo ""
echo ">> Done. Reload the GL.iNet panel to see NetBird under Applications."

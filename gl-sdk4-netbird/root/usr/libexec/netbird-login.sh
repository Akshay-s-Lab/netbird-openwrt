#!/bin/sh
# Usage: netbird-login.sh [setup-key-file]
# Without a setup key file, NetBird prints a device-code sign-in link to open from any browser.

. /lib/functions.sh

key_file="$1"

config_load netbird
config_get mgmt_url connection management_url
config_get_bool no_client_routes connection disable_client_routes 1
config_get_bool no_dns connection disable_dns 1

if [ -z "$mgmt_url" ]; then
	echo "netbird.connection.management_url is not set" >&2
	exit 1
fi

if [ ! -S /var/run/netbird.sock ]; then
	/etc/init.d/netbird start
	i=0
	while [ ! -S /var/run/netbird.sock ] && [ "$i" -lt 15 ]; do
		sleep 1
		i=$((i + 1))
	done
fi

set -- up --management-url "$mgmt_url" --no-browser
[ "$no_client_routes" -eq 1 ] && set -- "$@" --disable-client-routes
[ "$no_dns" -eq 1 ] && set -- "$@" --disable-dns
[ -n "$key_file" ] && set -- "$@" --setup-key-file "$key_file"

exec /usr/bin/netbird "$@"

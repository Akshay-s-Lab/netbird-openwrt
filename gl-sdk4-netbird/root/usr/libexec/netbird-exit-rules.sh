#!/bin/sh
# NetBird adds one nb* ipset per access policy but may forward only the first; accept every non-empty set.

while true; do
	if iptables -n -L NETBIRD-RT-FWD-IN >/dev/null 2>&1; then
		for set_name in $(ipset list -n 2>/dev/null | grep '^nb'); do
			ipset list "$set_name" 2>/dev/null | grep -q '^[0-9]' || continue
			iptables -C NETBIRD-RT-FWD-IN -m set --match-set "$set_name" src -j ACCEPT 2>/dev/null ||
				iptables -I NETBIRD-RT-FWD-IN 1 -m set --match-set "$set_name" src -j ACCEPT 2>/dev/null
		done
	fi
	sleep 60
done

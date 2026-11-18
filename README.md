# netbird-openwrt

> NetBird WireGuard overlay for GL.iNet / OpenWrt routers — procd service, browser sign-in, web UI in the GL.iNet admin panel, survives firmware upgrades.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OpenWrt](https://img.shields.io/badge/OpenWrt-21.02+-green.svg)](https://openwrt.org)
[![NetBird](https://img.shields.io/badge/NetBird-0.82+-orange.svg)](https://netbird.io)

Runs the official NetBird client as a proper OpenWrt service on GL.iNet routers (and other OpenWrt 21.02+ devices), with a management page inside the GL.iNet admin panel.

## Features

- **procd service** — starts at boot, respawns on crash, logs to `logread`; no `rc.local` code and no cron jobs
- **Sign in from any browser** — device-code SSO prints a link (and code) to approve; reusable setup keys still work
- **Persistent enrollment** — WireGuard keys and login state live in `/etc/netbird/` on the overlay, not tmpfs `/var`
- **Survives firmware upgrades** — `/lib/upgrade/keep.d/netbird` makes GL.iNet's *Keep Settings* upgrade keep every installed file
- **Verified binary** — `install.sh` checks the release checksum before installing
- **Admin-only web UI** — status, peers, connect/disconnect/restart and sign-in inside the GL.iNet panel; nginx requires a signed-in GL.iNet admin session
- **Leaves router DNS alone** — `--disable-dns` by default, so dnsmasq / AdGuard Home keep handling DNS
- **Weekly version bumps** — a GitHub Actions workflow opens a pull request when NetBird releases a new version
- **Exit node (optional)** — API token integration for the exit node toggle, plus an opt-in procd helper that keeps forwarding rules for every peer set

## Supported hardware

| Device | Firmware | Architecture | Status |
|--------|----------|--------------|--------|
| GL.iNet GL-BE9300 (Flint 3) | GL.iNet 4.11 (OpenWrt 23.05) | `aarch64` | ✅ Tested |
| GL.iNet GL-MT3000 | GL.iNet 4.8.1 (OpenWrt 21.02) | `aarch64_cortex-a53` | ✅ Tested upstream (older layout) |
| Other OpenWrt 21.02+ | — | `aarch64`, `x86_64`, `armv6`/`armv7` | ⚠️ Untested |

The GL.iNet admin panel entry and the admin-session check need GL.iNet firmware 4.x (SDK4, nginx + fcgiwrap).

## Prerequisites

- A NetBird management server — self-hosted or [netbird.io](https://netbird.io). Give the URL with an explicit port: `https://your-server.example.com:443`
- SSH access to the router as root
- `curl`, `sha256sum` and `tar` on the router (present on GL.iNet 4.x)

## Installation

Run these from a clone of this repo on your workstation.

```bash
git clone https://github.com/Akshay-s-Lab/netbird-openwrt.git
cd netbird-openwrt

sh scripts/install.sh root@192.168.8.1 https://your-server.example.com:443
sh nginx-app-netbird/deploy.sh root@192.168.8.1
sh gl-sdk4-netbird/deploy.sh root@192.168.8.1
```

1. `scripts/install.sh` downloads the pinned NetBird release for the router's architecture, checks it against the release checksums, installs the procd service, helpers, UCI config and upgrade keep list, removes old `rc.local` / cron installs from earlier versions of this repo, and starts the service.
2. `nginx-app-netbird/deploy.sh` installs the web UI at `/netbird/` and its API, then reloads nginx after `nginx -t` passes.
3. `gl-sdk4-netbird/deploy.sh` adds **Applications → NetBird** to the GL.iNet panel sidebar.

### Sign in

Either open **Applications → NetBird** in the GL.iNet panel, leave **Setup Key** empty and click **Apply**, or over SSH:

```bash
ssh root@192.168.8.1 /usr/libexec/netbird-login.sh
```

NetBird prints a link (and sometimes a code). Open it on any device, sign in, and the router joins. You only do this once; the service reconnects with the saved login after reboots, crashes and firmware upgrades.

To enroll with a reusable setup key instead, paste it into **Setup Key**, or run `netbird-login.sh /path/to/file-containing-the-key`.

## Configuration

UCI config at `/etc/config/netbird`:

```uci
config settings 'settings'
	option enabled '1'
	option log_level 'info'
	option exit_node_rules '0'          # 1 = run the exit-node forwarding helper under procd

config connection 'connection'
	option management_url 'https://your-server.example.com:443'
	option disable_client_routes '1'    # keep peer routes (e.g. 0.0.0.0/0 exit nodes) off the router's routing table
	option disable_dns '1'              # leave /etc/resolv.conf and the router's DNS alone
	option api_token ''                 # optional: enables the exit node toggle
	option peer_id ''                   # discovered automatically from api_token
	option route_id ''                  # discovered automatically from api_token
```

`disable_client_routes` and `disable_dns` apply when the router signs in. After changing them, sign in again with `netbird-login.sh`. After changing `settings`, run `/etc/init.d/netbird restart`.

## Exit node

1. Run `scripts/setup-exit-node.sh` on the router to enable forwarding and NAT for the NetBird interface.
2. In the NetBird dashboard, add a `0.0.0.0/0` network route through the router.
3. Create an API token (dashboard avatar → **API Tokens**), paste it in the web UI under **Advanced Settings**, and save. The UI then shows an **Exit Node** toggle.
4. If peers' traffic isn't forwarded, set `option exit_node_rules '1'` and restart the service. A procd-managed helper then adds a `NETBIRD-RT-FWD-IN` accept rule for every non-empty NetBird peer set each minute.

## Architecture

```
Boot / crash
  procd → /etc/init.d/netbird (START=90, respawn)
    ├── /var/lib/netbird → /etc/netbird   (overlay, survives reboots)
    ├── netbird service run --log-file console   (logs → logread -e netbird)
    └── netbird-exit-rules.sh                    (only when exit_node_rules=1)

Sign-in (once)
  /usr/libexec/netbird-login.sh → netbird up --no-browser --disable-client-routes --disable-dns
    └── device-code link, or --setup-key-file

Web UI
  GL.iNet panel → nginx /netbird/       → /www/netbird/index.html
                  nginx /netbird/api    → fcgiwrap → /usr/libexec/netbird-api.cgi
  Both locations require a valid GL.iNet Admin-Token session (netbird-access.lua).

Firmware upgrade (Keep Settings)
  /lib/upgrade/keep.d/netbird lists every installed file, /etc/netbird/ and the rc.d links.
```

## Project structure

```
netbird-openwrt/
├── .github/workflows/update-netbird.yml   # Weekly PR when NetBird releases a new version
├── gl-sdk4-netbird/
│   ├── deploy.sh                          # Installs the GL.iNet panel sidebar entry
│   └── root/
│       ├── etc/config/netbird             # UCI config template
│       ├── etc/init.d/netbird             # procd service
│       ├── lib/upgrade/keep.d/netbird     # Files kept across firmware upgrades
│       ├── usr/libexec/netbird-login.sh   # One-time sign-in (device code or setup key)
│       ├── usr/libexec/netbird-exit-rules.sh  # Optional exit-node forwarding helper
│       └── usr/share/oui/menu.d/, www/    # GL.iNet panel entry and view bundle
├── nginx-app-netbird/
│   ├── deploy.sh                          # Installs the web UI and reloads nginx
│   ├── index.html                         # Management page
│   ├── netbird-api.cgi                    # JSON API: GET status, POST actions
│   ├── netbird-access.lua                 # GL.iNet admin-session check for nginx
│   ├── netbird.conf                       # nginx locations
│   ├── netbird-setup-api.sh               # Discovers peer_id + route_id from the API token
│   ├── netbird-toggle-exit.sh             # Toggles the exit node route via the API
│   └── setup-api.sh                       # Same discovery, run by hand on the router
└── scripts/
    ├── install.sh                         # Installs NetBird, the service and helpers
    ├── netbird-cleanup.sh                 # Full teardown (processes + NETBIRD-* iptables chains)
    ├── setup-exit-node.sh                 # One-shot exit node forwarding/NAT setup
    └── status.sh                          # Quick status overview
```

## Troubleshooting

**Check status and logs**
```bash
netbird status --detail
logread -e netbird | tail -50
ubus call service list '{"name":"netbird"}'
```

**`missing port in address` in the log**  
The management URL needs an explicit port:
```bash
uci set netbird.connection.management_url='https://your-server.example.com:443'
uci commit netbird
/usr/libexec/netbird-login.sh
```

**Sign-in fails with `user pending approval cannot add peers`**  
The account that approved the link is new to NetBird and waiting for approval. Approve it under **Team → Users** in the dashboard, or sign in with an already-approved account (a private browser window helps pick the right one).

**`LoginFailed` / `NeedsLogin` after a firmware upgrade**  
The upgrade was done without *Keep Settings*, or by a firmware that ignores `/lib/upgrade/keep.d`. Re-run `scripts/install.sh` and both deploy scripts, then sign in again.

**The NetBird page returns 401**  
Sign in to the GL.iNet admin panel first; the page and its API only answer signed-in admin sessions.

**`create firewall manager: ... Chain already exists`**  
Leftover `NETBIRD-*` chains from a daemon that didn't shut down cleanly. Tear down and let procd start it again:
```bash
/etc/init.d/netbird stop
sh /usr/libexec/netbird-cleanup.sh
/etc/init.d/netbird start
```

**Router can't resolve public hostnames after enabling NetBird DNS**  
With `disable_dns '0'`, NetBird manages `/etc/resolv.conf` and backs up the original to `/etc/resolv.conf.original.netbird`. If that backup goes missing, the router's own lookups (not LAN clients') fail. Recreate it pointing at the router's local resolver (`echo 'nameserver 127.0.0.1' > /etc/resolv.conf.original.netbird`) and restart the service, or set `disable_dns '1'` and sign in again.

**Porting to another BusyBox build**  
Some builds (GL-MT3000) lack the `pkill` applet; it then silently does nothing. Scripts here use `killall` and `pgrep`. Run `which pkill pgrep killall` on a new device before relying on process management.

## Uninstall

```bash
/etc/init.d/netbird stop
/etc/init.d/netbird disable
rm -rf /etc/netbird /etc/config/netbird /etc/init.d/netbird /lib/upgrade/keep.d/netbird \
  /usr/bin/netbird /usr/libexec/netbird-* /usr/share/gl-ngx/netbird-access.lua \
  /etc/nginx/gl-conf.d/netbird.conf /www/netbird /usr/share/oui/menu.d/netbirdview.json \
  /www/i18n/gl-sdk4-ui-netbirdview.en.json /www/views/gl-sdk4-ui-netbirdview.common.js.gz
nginx -s reload
```

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Most useful: testing on other GL.iNet models and on vanilla OpenWrt.

## License

MIT — see [LICENSE](LICENSE).

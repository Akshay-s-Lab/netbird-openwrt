#!/bin/sh
# NetBird JSON API CGI
# Deploy to: /usr/libexec/netbird-api.cgi (served at /netbird/api by nginx + fcgiwrap)
# GET  → status JSON
# POST → action JSON (action= in url-encoded body)

LOCK="/var/run/netbird-cgi.lock"
LOGIN_LOG="/var/run/netbird-login.log"
LOGIN_PID="/var/run/netbird-login.pid"
LOGIN="/usr/libexec/netbird-login.sh"

MGMT_URL=$(uci -q get netbird.connection.management_url || echo "https://your-netbird-server.example.com:443")
API_TOKEN=$(uci -q get netbird.connection.api_token || true)
ROUTE_ID=$(uci -q get netbird.connection.route_id || true)

urldecode() { printf '%b' "$(echo "$1" | sed 's/+/ /g;s/%/\\x/g')" 2>/dev/null || echo "$1"; }
get_field()  { echo "$2" | grep -o "${1}=[^&]*" | head -1 | cut -d= -f2-; }

# Escape a value for embedding in a JSON string (single line only).
json_str() {
    printf '%s' "$1" | tr -cd '\11\12\40-\176' | awk '{
        gsub(/\\/, "\\\\")
        gsub(/"/, "\\\"")
        printf "%s", $0
    }'
}

json_ok()  { printf 'Content-Type: application/json\r\n\r\n{"ok":true,"action":"%s"}' "$1"; exit 0; }
json_err() { printf 'Content-Type: application/json\r\n\r\n{"ok":false,"error":"%s"}' "$1"; exit 0; }

login_running() {
    local pid
    pid=$(cat "$LOGIN_PID" 2>/dev/null)
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

stop_login() {
    login_running && kill "$(cat "$LOGIN_PID")" 2>/dev/null
    rm -f "$LOGIN_PID"
}

start_login() {
    local key="$1" key_file=""
    stop_login
    if [ -n "$key" ]; then
        key_file=$(mktemp)
        chmod 600 "$key_file"
        printf '%s' "$key" > "$key_file"
    fi
    (
        trap - EXIT
        "$LOGIN" $key_file > "$LOGIN_LOG" 2>&1
        [ -n "$key_file" ] && rm -f "$key_file"
        rm -f "$LOGIN_PID"
        [ -n "$API_TOKEN" ] && /usr/libexec/netbird-setup-api.sh
    ) </dev/null >/dev/null 2>&1 &
    echo $! > "$LOGIN_PID"
}

# Lock helpers (directory for atomicity, file inside for PID)
lock_acquire() {
    if mkdir "$LOCK" 2>/dev/null; then
        echo $$ > "$LOCK/pid"
        return 0
    fi
    local pid
    pid=$(cat "$LOCK/pid" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 1
    fi
    rm -rf "$LOCK"
    mkdir "$LOCK" 2>/dev/null && echo $$ > "$LOCK/pid"
}

# ── POST: actions ─────────────────────────────────────────────────────────────
if [ "$REQUEST_METHOD" = "POST" ]; then
    if ! lock_acquire; then
        json_err "busy"
    fi
    trap 'rm -rf "$LOCK"' EXIT
    read -r -n "${CONTENT_LENGTH:-0}" POST_DATA
    ACTION=$(get_field "action" "$POST_DATA")

    case "$ACTION" in

        quick_setup)
            NEW_URL=$(urldecode "$(get_field "mgmt_url" "$POST_DATA")")
            NEW_KEY=$(urldecode "$(get_field "setup_key" "$POST_DATA")")
            if [ -n "$NEW_URL" ]; then
                uci set "netbird.connection.management_url=$NEW_URL"
                uci commit netbird
            fi
            start_login "$NEW_KEY"
            json_ok "quick_setup"
            ;;

        connect)
            start_login ""
            json_ok "connect"
            ;;

        cancel_login)
            stop_login
            json_ok "cancel_login"
            ;;

        disconnect)
            stop_login
            /usr/bin/netbird down >/dev/null 2>&1
            json_ok "disconnect"
            ;;

        restart)
            /etc/init.d/netbird restart >/dev/null 2>&1
            json_ok "restart"
            ;;

        toggle_exit)
            if [ -n "$API_TOKEN" ] && [ -n "$ROUTE_ID" ]; then
                ( trap - EXIT; /usr/libexec/netbird-toggle-exit.sh ) </dev/null >/dev/null 2>&1 &
            fi
            json_ok "toggle_exit"
            ;;

        save_token)
            NEW_TOKEN=$(urldecode "$(get_field "api_token" "$POST_DATA")")
            if [ -n "$NEW_TOKEN" ] && [ "$NEW_TOKEN" != "KEEP" ]; then
                uci set "netbird.connection.api_token=$NEW_TOKEN"
                uci commit netbird
                ( trap - EXIT; sleep 3; /usr/libexec/netbird-setup-api.sh ) </dev/null >/dev/null 2>&1 &
            fi
            json_ok "save_token"
            ;;

        *)
            json_err "unknown action"
            ;;
    esac
fi

# ── GET: status JSON ──────────────────────────────────────────────────────────
DAEMON=$([ -S /var/run/netbird.sock ] && echo "running" || echo "stopped")

# Timeout prevents hang when daemon is unresponsive; 2>&1 captures error msgs
STATUS_RAW=$(timeout 10 /usr/bin/netbird status --detail 2>&1) || STATUS_RAW=""

NB_IP=$(echo "$STATUS_RAW"     | grep '^NetBird IP:'   | head -1 | awk '{print $3}' | cut -d/ -f1)
FQDN=$(echo "$STATUS_RAW"      | grep '^FQDN:'         | head -1 | awk '{print $2}')
MGMT_S=$(echo "$STATUS_RAW"    | grep '^Management:'   | head -1 | cut -d: -f2- | xargs)
PEERS_CNT=$(echo "$STATUS_RAW" | grep '^Peers count:'  | head -1 | awk '{print $3}')
DAEMON_VER=$(echo "$STATUS_RAW" | grep '^Daemon version:' | head -1 | awk '{print $3}')
DAEMON_STATE=$(echo "$STATUS_RAW" | grep '^Daemon status:' | head -1 | awk '{print $3}')
NETWORKS=$(echo "$STATUS_RAW"  | grep '^Networks:'     | head -1 | awk '{$1=""; sub(/^ /,""); print}' | tr -cd '\40-\176')

LOGIN_ACTIVE=false
LOGIN_URL=""
LOGIN_CODE=""
if login_running; then
    LOGIN_ACTIVE=true
    LOGIN_URL=$(grep -o 'https://[^ ]*' "$LOGIN_LOG" 2>/dev/null | head -1)
    LOGIN_CODE=$(grep -o 'enter the code [^ ]*' "$LOGIN_LOG" 2>/dev/null | head -1 | awk '{print $4}')
fi

EXIT_ACTIVE=false
echo "$STATUS_RAW" | grep -q '0\.0\.0\.0/0' && EXIT_ACTIVE=true
TOKEN_SET=false;  [ -n "$API_TOKEN" ] && TOKEN_SET=true
ROUTE_SET=false;  [ -n "$ROUTE_ID" ]  && ROUTE_SET=true

PROCD_JSON=$(timeout 5 ubus call service list '{"name":"netbird"}' 2>/dev/null)
PROCD_MANAGED=false
echo "$PROCD_JSON" | grep -q '"running":[[:space:]]*true' && PROCD_MANAGED=true

MGMT_ESC=$(json_str "${MGMT_S:-$DAEMON_STATE}")
URL_ESC=$(json_str "$MGMT_URL")
FQDN_ESC=$(json_str "$FQDN")
NB_IP_ESC=$(json_str "$NB_IP")
NET_ESC=$(json_str "${NETWORKS:---}")
CNT_ESC=$(json_str "${PEERS_CNT:-0/0}")
VER_ESC=$(json_str "${DAEMON_VER:---}")
STATE_ESC=$(json_str "$DAEMON_STATE")
LOGIN_URL_ESC=$(json_str "$LOGIN_URL")
LOGIN_CODE_ESC=$(json_str "$LOGIN_CODE")

# Log tail: strip ALL control chars (incl. ESC/ANSI sequences) before escaping.
LOG_ESC=$(logread -e netbird 2>/dev/null | tail -20 | \
    tr -cd '\11\12\40-\176' | \
    awk '{
        gsub(/\\/, "\\\\")
        gsub(/"/, "\\\"")
        printf "%s\\n", $0
    }' | sed '$ s/\\n$//')

# Peer blocks start with " <fqdn>:" (one leading space); their fields are indented further.
PEERS_JSON=$(printf '%s\n' "$STATUS_RAW" | awk '
BEGIN { first=1; printf "["; name="" }
function emit() {
    if (name == "") return
    gsub(/["\\]/, "", name)
    if (!first) printf ","
    printf "{\"name\":\"%s\",\"ip\":\"%s\",\"status\":\"%s\",\"conn_type\":\"%s\",\"latency\":\"%s\"}",
        name, ip, status, ctype, lat
    first = 0
}
/^Peers detail:/   { in_peers = 1; next }
in_peers && /^ [^ ][^ ]*:$/ {
    emit()
    name = $1; gsub(/:$/, "", name)
    ip = ""; status = "Idle"; ctype = "-"; lat = "0s"
    next
}
in_peers && /^[^ ]/ { in_peers = 0 }
/^  NetBird IP:/   { ip = $3; gsub(/\/[0-9]+$/, "", ip) }
/^  Status:/       { status = $2 }
/Connection type:/ { ctype = $3 }
/Latency:/         { lat = $2 }
END { emit(); printf "]" }')

printf 'Content-Type: application/json\r\nCache-Control: no-cache\r\n\r\n'
printf '{"daemon":"%s","daemon_state":"%s","nb_ip":"%s","fqdn":"%s","mgmt_url":"%s","mgmt_status":"%s",' \
    "$DAEMON" "$STATE_ESC" "$NB_IP_ESC" "$FQDN_ESC" "$URL_ESC" "$MGMT_ESC"
printf '"peers_count":"%s","exit_active":%s,"networks":"%s",' \
    "$CNT_ESC" "$EXIT_ACTIVE" "$NET_ESC"
printf '"token_set":%s,"route_id_set":%s,' "$TOKEN_SET" "$ROUTE_SET"
printf '"version":"%s","procd_managed":%s,' "$VER_ESC" "$PROCD_MANAGED"
printf '"login_active":%s,"login_url":"%s","login_code":"%s",' \
    "$LOGIN_ACTIVE" "$LOGIN_URL_ESC" "$LOGIN_CODE_ESC"
printf '"log_tail":"%s",' "$LOG_ESC"
printf '"peers":%s}' "$PEERS_JSON"

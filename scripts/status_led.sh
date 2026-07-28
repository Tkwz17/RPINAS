#!/usr/bin/env bash
set -euo pipefail

if [[ -f /etc/default/rpinas ]]; then
    # shellcheck disable=SC1091
    source /etc/default/rpinas
fi

RPINAS_LED_ENABLED="${RPINAS_LED_ENABLED:-1}"
RPINAS_LED_NAME="${RPINAS_LED_NAME:-rpinas-status}"
RPINAS_LED_GPIO="${RPINAS_LED_GPIO:-17}"
RPINAS_LED_ACTIVE_LOW="${RPINAS_LED_ACTIVE_LOW:-0}"
LED_PATH="/sys/class/leds/${RPINAS_LED_NAME}"
ERROR_MARKER="/run/rpinas/status-led-error"

log() {
    printf 'rpinas-status-led: %s\n' "$*"
}

led_enabled() {
    [[ "${RPINAS_LED_ENABLED}" != "0" && "${RPINAS_LED_ENABLED,,}" != "false" && "${RPINAS_LED_ENABLED,,}" != "no" ]]
}

require_led_class() {
    if [[ ! -d "${LED_PATH}" ]]; then
        log "LED class ${LED_PATH} not found. Ensure config.txt has dtoverlay=gpio-led,gpio=${RPINAS_LED_GPIO},label=${RPINAS_LED_NAME},active_low=${RPINAS_LED_ACTIVE_LOW}."
        return 1
    fi
}

set_led_class() {
    local state="$1"

    if [[ "${state}" == "error" ]]; then
        mkdir -p "$(dirname "${ERROR_MARKER}")"
        touch "${ERROR_MARKER}"
    fi

    require_led_class || return 1

    case "${state}" in
        booting)
            printf 'timer' >"${LED_PATH}/trigger"
            printf '1000' >"${LED_PATH}/delay_on"
            printf '1000' >"${LED_PATH}/delay_off"
            ;;
        ready)
            printf 'none' >"${LED_PATH}/trigger"
            printf '1' >"${LED_PATH}/brightness"
            ;;
        error)
            printf 'timer' >"${LED_PATH}/trigger"
            printf '150' >"${LED_PATH}/delay_on"
            printf '150' >"${LED_PATH}/delay_off"
            ;;
        off)
            printf 'none' >"${LED_PATH}/trigger"
            printf '0' >"${LED_PATH}/brightness"
            ;;
        *)
            log "unknown LED state: ${state}"
            return 2
            ;;
    esac
}

service_active() {
    systemctl is-active --quiet "$1"
}

backend_accepting_connections() {
    python3 - <<'PY'
import socket
import sys

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(1)
    try:
        sock.connect(("127.0.0.1", 80))
    except OSError:
        sys.exit(1)
PY
}

ready_check() {
    local required_services=(hostapd.service dnsmasq.service smbd.service nmbd.service rpinas-backend.service)
    local svc

    for _ in {1..60}; do
        if [[ -e "${ERROR_MARKER}" ]]; then
            log "startup error marker exists; keeping fast blink error state."
            set_led_class error || true
            return 1
        fi

        local all_active=1
        for svc in "${required_services[@]}"; do
            if ! service_active "${svc}"; then
                all_active=0
                break
            fi
        done

        if [[ "${all_active}" -eq 1 ]] && backend_accepting_connections; then
            if [[ -e "${ERROR_MARKER}" ]]; then
                log "startup error marker exists; not overriding error LED state."
                set_led_class error || true
                return 1
            fi
            set_led_class ready
            log "RPINAS is ready; LED set solid on."
            return 0
        fi

        sleep 2
    done

    log "RPINAS readiness check timed out; setting fast blink error state."
    set_led_class error || true
    return 1
}

main() {
    local command="${1:-}"

    if ! led_enabled; then
        log "LED support disabled by RPINAS_LED_ENABLED=${RPINAS_LED_ENABLED}."
        return 0
    fi

    case "${command}" in
        booting|ready|error|off)
            set_led_class "${command}"
            ;;
        ready-check)
            ready_check
            ;;
        *)
            printf 'Usage: %s {booting|ready|error|off|ready-check}\n' "$0" >&2
            return 2
            ;;
    esac
}

main "$@"

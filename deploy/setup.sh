#!/usr/bin/env bash
# Initial provisioning script for an Ubuntu 24.04 VPS.
# Run as root on a freshly created instance.
#
# Usage:
#   sudo bash deploy/setup.sh
#
# Expects the repository to be cloned at /opt/kindle2notion beforehand.

set -euo pipefail

APP_DIR="/opt/kindle2notion"
APP_USER="kindle2notion"
DUCKDNS_DIR="/etc/duckdns"
SERVICE_NAME="kindle2notion-web"

if [[ "$(id -u)" -ne 0 ]]; then
	echo "This script must be run as root (use sudo)." >&2
	exit 1
fi

if [[ ! -d "${APP_DIR}" ]]; then
	echo "Repository is not present at ${APP_DIR}." >&2
	echo "Clone it first, e.g.:  sudo git clone <repo-url> ${APP_DIR}" >&2
	exit 1
fi

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
	ca-certificates \
	curl \
	debian-keyring \
	debian-archive-keyring \
	apt-transport-https \
	git \
	ufw \
	fail2ban \
	python3 \
	python3-venv \
	python3-pip \
	cron

echo "==> Installing Caddy"
if ! command -v caddy >/dev/null 2>&1; then
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
		| gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
		| tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
	apt-get update
	apt-get install -y caddy
fi

echo "==> Creating application user"
if ! id "${APP_USER}" >/dev/null 2>&1; then
	useradd --system --create-home --home-dir "/home/${APP_USER}" --shell /usr/sbin/nologin "${APP_USER}"
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> Creating Python virtualenv"
sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements/requirements.txt"

echo "==> Installing Playwright system dependencies"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m playwright install-deps chromium || \
	"${APP_DIR}/.venv/bin/python" -m playwright install-deps chromium

echo "==> Installing Playwright Chromium for the app user"
sudo -u "${APP_USER}" \
	PLAYWRIGHT_BROWSERS_PATH="${APP_DIR}/.cache/ms-playwright" \
	"${APP_DIR}/.venv/bin/python" -m playwright install chromium

echo "==> Installing systemd service"
install -m 0644 "${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service" \
	"/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo "==> Installing Caddyfile"
install -m 0644 "${APP_DIR}/deploy/Caddyfile" /etc/caddy/Caddyfile
mkdir -p /var/log/caddy
chown -R caddy:caddy /var/log/caddy
echo "Remember to edit /etc/caddy/Caddyfile and replace the placeholder domain."

echo "==> Configuring ufw firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Configuring fail2ban"
systemctl enable --now fail2ban

echo "==> Setting up DuckDNS updater (token must be placed at ${DUCKDNS_DIR}/token)"
mkdir -p "${DUCKDNS_DIR}"
chmod 700 "${DUCKDNS_DIR}"
cat >/usr/local/bin/duckdns-update <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
TOKEN_FILE="/etc/duckdns/token"
DOMAIN_FILE="/etc/duckdns/domain"
if [[ ! -f "${TOKEN_FILE}" || ! -f "${DOMAIN_FILE}" ]]; then
	echo "DuckDNS token or domain file missing." >&2
	exit 1
fi
TOKEN="$(cat "${TOKEN_FILE}")"
DOMAIN="$(cat "${DOMAIN_FILE}")"
curl -fsS "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" \
	>/var/log/duckdns.log
SCRIPT
chmod 700 /usr/local/bin/duckdns-update

cat >/etc/cron.d/duckdns <<'CRON'
*/5 * * * * root /usr/local/bin/duckdns-update >/dev/null 2>&1
CRON
chmod 644 /etc/cron.d/duckdns

echo "==> Allowing the kindle2notion user to restart the service without a password"
cat >/etc/sudoers.d/kindle2notion <<SUDO
${APP_USER} ALL=(root) NOPASSWD: /bin/systemctl restart ${SERVICE_NAME}.service, /bin/systemctl status ${SERVICE_NAME}.service
SUDO
chmod 440 /etc/sudoers.d/kindle2notion

echo ""
echo "Setup finished. Remaining manual steps:"
echo "  1. Write your DuckDNS token to ${DUCKDNS_DIR}/token (chmod 600)"
echo "  2. Write your DuckDNS subdomain (without .duckdns.org) to ${DUCKDNS_DIR}/domain"
echo "  3. Edit /etc/caddy/Caddyfile and replace kindle2notion-xxx.duckdns.org"
echo "  4. Create ${APP_DIR}/config/KEYS.env with the required secrets"
echo "  5. systemctl start caddy && systemctl start ${SERVICE_NAME}"

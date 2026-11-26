# Gebaut wird am Desktop (npm run build), nie auf dem VPS. Das Image enthält nur Caddy und den Ordner dist/.
FROM caddy:2.11-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY dist/ /srv/
ENV XDG_CONFIG_HOME=/tmp XDG_DATA_HOME=/tmp
USER 65534:65534
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO /dev/null http://127.0.0.1:${PORT:-8080}/robots.txt || exit 1

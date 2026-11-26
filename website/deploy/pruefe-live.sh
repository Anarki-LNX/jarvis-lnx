#!/usr/bin/env bash
# Prüft die öffentliche Seite nach dem Ausrollen: Status, Weiterleitungen, Sicherheits-Header, HTTP/3.
set -uo pipefail
B=https://nuorb.loopout.tech
ok=0; bad=0
t() { if eval "$2" >/dev/null 2>&1; then echo "✓ $1"; ok=$((ok+1)); else echo "✗ $1"; bad=$((bad+1)); fi; }
H=$(curl -sSI "$B/en/")
t "/en/ 200"                    '[[ "$(curl -s -o /dev/null -w %{http_code} $B/en/)" == 200 ]]'
t "/de/ 200"                    '[[ "$(curl -s -o /dev/null -w %{http_code} $B/de/)" == 200 ]]'
t "/ 200 (Sprachwahl)"          '[[ "$(curl -s -o /dev/null -w %{http_code} $B/)" == 200 ]]'
t "404-Seite"                   '[[ "$(curl -s -o /dev/null -w %{http_code} $B/gibt-es-nicht)" == 404 ]]'
t "http → https"                '[[ "$(curl -s -o /dev/null -w %{redirect_url} http://nuorb.loopout.tech/)" == https://* ]]'
t "HSTS"                        'grep -qi "^strict-transport-security" <<<"$H"'
t "CSP"                         'grep -qi "^content-security-policy: default-src .none." <<<"$H"'
t "nosniff"                     'grep -qi "^x-content-type-options: nosniff" <<<"$H"'
t "kein Server-Header"          '! grep -qi "^server:" <<<"$H"'
t "Video mit Range (206)"       '[[ "$(curl -s -o /dev/null -r 0-99 -w %{http_code} $B$(curl -s $B/en/ | grep -o "/media/video/[^\"]*" | head -1))" == 206 ]]'
t "sitemap"                     '[[ "$(curl -s -o /dev/null -w %{http_code} $B/sitemap-index.xml)" == 200 ]]'
t "HTTP/3"                      'curl -s --http3-only -o /dev/null $B/en/'
echo "$ok ok, $bad Fehler"; [[ $bad == 0 ]]

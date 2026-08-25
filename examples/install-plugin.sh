#!/bin/bash
# Install the prometheus datasource plugin into brew's shared plugin dir. Run once.
#
# The Homebrew grafana bottle does not ship this plugin (official tarball/deb do).
# Without it Grafana starts fine but every panel is blank and the log says
# plugin.notRegistered. It goes to /opt/homebrew/var/lib/grafana/plugins rather than
# the project's build/ dir: that is what brew's own service uses, it survives
# `brew upgrade`, and clean.sh cannot touch it.
set -euo pipefail

PLUGINS="${GF_PLUGINS:-$(brew --prefix)/var/lib/grafana/plugins}"
VERSION="${1:-$(grafana --version | awk '{print $3}')}"
URL="https://storage.googleapis.com/plugins-cdn/prometheus/$VERSION/prometheus-$VERSION.zip"

[ -d "$PLUGINS/prometheus" ] && { echo "already installed: $PLUGINS/prometheus"; exit 0; }

mkdir -p "$PLUGINS"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo "downloading prometheus plugin $VERSION ..."
curl -fL --progress-bar "$URL" -o "$TMP/p.zip" || {
  echo "download failed. Fetch it manually and unzip into $PLUGINS/prometheus:" >&2
  echo "  $URL" >&2
  exit 1
}
unzip -q "$TMP/p.zip" -d "$TMP"
mv "$TMP/prometheus" "$PLUGINS/prometheus"
echo "installed: $PLUGINS/prometheus"

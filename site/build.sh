#!/bin/sh
# Builds the static site into site/www:
#   demo.html            the demo replay, copied from demo/
#   cartographer.tar.gz  the current checkout (bin, package, skills), which install.sh downloads
#   cartographer.zip     the same, for install.ps1 on Windows
#
# Cloudflare Pages settings: build command `sh site/build.sh`, output directory `site/www`.
# Locally: `sh site/build.sh && python3 -m http.server -d site/www 8080`, then open http://localhost:8080/.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/site/www"
mkdir -p "$OUT"
cp "$ROOT/demo/cartographer-replay.html" "$OUT/demo.html"
git -C "$ROOT" archive --format=tar.gz --prefix=cartographer/ -o "$OUT/cartographer.tar.gz" HEAD -- bin cartographer skills pyproject.toml README.md
git -C "$ROOT" archive --format=zip --prefix=cartographer/ -o "$OUT/cartographer.zip" HEAD -- bin cartographer skills pyproject.toml README.md
echo "site built in $OUT ($(du -h "$OUT/cartographer.tar.gz" | cut -f1) tarball, $(du -h "$OUT/cartographer.zip" | cut -f1) zip)"

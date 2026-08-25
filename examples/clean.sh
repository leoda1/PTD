#!/bin/bash
# Delete every generated artifact. Run once before replaying a new batch of logs.
set -euo pipefail
BUILD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/build"
rm -rf "$BUILD"
echo "removed $BUILD"

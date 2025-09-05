#!/bin/bash
# Simple release script for Schulmanager Integration
# Usage: ./scripts/release.sh <version_type> "<change_description>"
# Example: ./scripts/release.sh patch "Fixed bug in calendar sync"

set -e

# Check if we have the required arguments
if [ $# -ne 2 ]; then
    echo "Usage: $0 <version_type> <change_description>"
    echo "Version types: major, minor, patch"
    echo "Example: $0 patch 'Fixed bug in calendar sync'"
    exit 1
fi

VERSION_TYPE=$1
CHANGES=$2

# Get current directory (should be repo root)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "🚀 Starting release process..."
echo "Version type: $VERSION_TYPE"
echo "Changes: $CHANGES"
echo ""

# Run the Python deployment script
python3 scripts/deploy.py "$VERSION_TYPE" "$CHANGES"

echo ""
echo "✅ Release process completed!"
echo "🏷️  New version tagged and ready for HACS"
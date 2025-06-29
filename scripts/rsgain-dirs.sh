#!/usr/bin/bash

RSGAIN_BINARY="rsgain"

if ! command -v "$RSGAIN_BINARY" >/dev/null 2>&1; then
    echo "Error: '$RSGAIN_BINARY' not found."
    exit 1
fi

ROOT="/mnt/data/Videos/YouTube Symlinks"

DIRS=(
    "Bobby/Various Music Videos"
    "Diversity"
    "Nightblue Music"
    "Syrex"
    "xKito Music"
)

for dirname in "${DIRS[@]}";
do
    fullpath="$ROOT/$dirname"
    echo "$fullpath"
    $RSGAIN_BINARY easy -S -m MAX "$fullpath"
done

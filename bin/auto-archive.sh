#!/bin/bash
# auto-archive.sh — Weekly cleanup: session archive + log rotation
# Cron example: 0 3 * * 0  (Sunday 03:00 local)

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh" || exit 1
PURE="$CBP_CLI_HOME"
ARCHIVE_DIR="$PURE/sessions/archive"
mkdir -p "$ARCHIVE_DIR"

MONTH=$(date +%Y-%m)

# 1. Sessions > 15 days → tar.gz (MERGE into existing monthly archive, never overwrite)
FILES=$(find "$PURE/sessions/cli" -maxdepth 1 \( -name "*.jsonl" -o -name "*.json" \) -mtime +15 2>/dev/null)
if [ -n "$FILES" ]; then
    COUNT=$(echo "$FILES" | wc -l)
    ARCHIVE="$ARCHIVE_DIR/sessions-$MONTH.tar.gz"
    STAGE=$(mktemp -d "$ARCHIVE_DIR/.merge-XXXXXX")
    # 1a. If a monthly archive already exists, unpack it into the staging dir
    #     so this run APPENDS rather than overwrites (previous bug: tar -czf
    #     create-mode clobbered the month's prior archive + --remove-files had
    #     already deleted the sources = permanent data loss).
    if [ -f "$ARCHIVE" ]; then
        tar -xzf "$ARCHIVE" -C "$STAGE" 2>/dev/null
    fi
    # 1b. Copy the newly-aged session files into staging (flat, basename only)
    echo "$FILES" | while IFS= read -r f; do
        [ -n "$f" ] && cp -p "$f" "$STAGE/" 2>/dev/null
    done
    # 1c. Repack the union (old + new). Only on success do we remove sources.
    if tar -czf "$ARCHIVE.tmp" -C "$STAGE" . 2>/dev/null && mv "$ARCHIVE.tmp" "$ARCHIVE"; then
        echo "$FILES" | while IFS= read -r f; do
            [ -n "$f" ] && rm -f "$f"
        done
        TOTAL=$(tar -tzf "$ARCHIVE" 2>/dev/null | grep -cE '\.(jsonl|json)$')
        echo "$(date +%Y-%m-%d) Archived $COUNT session files → sessions-$MONTH.tar.gz (now holds $TOTAL)"
    else
        echo "$(date +%Y-%m-%d) ERROR: archive repack failed, sources kept (sessions-$MONTH.tar.gz unchanged)"
    fi
    rm -rf "$STAGE"
fi

# 2. Log rotation (> 10MB) for any *.jsonl under $CBP_LOGS
for LOG in "$CBP_LOGS"/*.jsonl; do
    [ -f "$LOG" ] || continue
    SIZE=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 10485760 ]; then
        mv "$LOG" "$LOG.$(date +%Y%m%d).bak"
        echo "$(date +%Y-%m-%d) Rotated $(basename "$LOG") ($SIZE bytes)"
    fi
done

# 3. Clean repo-local tmp > 7 days
find "$CBP_TMP" -type f -mtime +7 -delete 2>/dev/null

# 4. Site-specific cleanup (optional, gitignored): config/auto-archive.local.sh
if [ -f "$CBP_ROOT/config/auto-archive.local.sh" ]; then . "$CBP_ROOT/config/auto-archive.local.sh"; fi
exit 0

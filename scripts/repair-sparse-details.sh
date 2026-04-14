#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-coffee.db}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

SPARSE_WHERE="
COALESCE(city, '') = ''
AND COALESCE(address, '') = ''
AND COALESCE(website, '') = ''
AND COALESCE(instagram, '') = ''
AND COALESCE(description, '') = ''
AND (
  image_urls IS NULL
  OR image_urls = ''
  OR image_urls = '[]'
)
"

before=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM shop_details WHERE $SPARSE_WHERE;")
sqlite3 "$DB_PATH" "DELETE FROM shop_details WHERE $SPARSE_WHERE;"
after=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM shop_details WHERE $SPARSE_WHERE;")
deleted=$((before - after))

echo "Deleted $deleted sparse shop_details row(s) (before=$before, after=$after)."
echo "Next step: rerun historical scrape to repopulate these details from cache."

#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-coffee.db}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

WHERE_CLAUSE="
COALESCE(name, '') = ''
AND COALESCE(city, '') = ''
AND COALESCE(country, '') = ''
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

before=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM shop_details WHERE $WHERE_CLAUSE;")
sqlite3 "$DB_PATH" "DELETE FROM shop_details WHERE $WHERE_CLAUSE;"
after=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM shop_details WHERE $WHERE_CLAUSE;")
deleted=$((before - after))

echo "Deleted $deleted empty shop_details row(s) (before=$before, after=$after)."

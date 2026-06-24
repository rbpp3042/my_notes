#!/usr/bin/env bash
# publish-tmp-upload.sh — stage a file into assets/tmp-uploads/ with a timestamp prefix.
#
# Usage:
#   publish-tmp-upload.sh <source-file> [dest-basename]
#
# - <source-file>   : path to an existing file to publish.
# - [dest-basename] : optional output basename (without the timestamp prefix).
#                     Defaults to the source basename. A non-ASCII / unsafe name is
#                     slugified to keep the public URL clean.
#
# Copies the file to:   <repo>/assets/tmp-uploads/YYYYMMDD-HHMMSS_<basename>
# Prints the output filename (the part under assets/tmp-uploads/) on success.
#
# Exit codes: 0 success, 1 bad arguments or missing file.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="$REPO_DIR/assets/tmp-uploads"

err() { printf 'error: %s\n' "$*" >&2; }

if [[ $# -lt 1 || $# -gt 2 ]]; then
  err "usage: publish-tmp-upload.sh <source-file> [dest-basename]"
  exit 1
fi

SRC="$1"
if [[ ! -f "$SRC" ]]; then
  err "source file not found: $SRC"
  exit 1
fi

# Resolve desired basename (ext kept from the chosen base).
if [[ $# -eq 2 && -n "$2" ]]; then
  RAW_BASE="$2"
else
  RAW_BASE="$(basename "$SRC")"
fi

EXT=""
NAME="$RAW_BASE"
if [[ "$RAW_BASE" == *.* ]]; then
  EXT=".${RAW_BASE##*.}"
  NAME="${RAW_BASE%.*}"
fi

# Slugify: lowercase, transliterate non-ASCII, keep [a-z0-9._-], collapse dashes.
slugify() {
  python3 - "$1" <<'PY'
import sys, re, unicodedata
RU = {
 'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
 'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
 'у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y',
 'ь':'','э':'e','ю':'yu','я':'ya'}
s = sys.argv[1].lower()
out = []
for ch in s:
    out.append(RU.get(ch, ch))
s = ''.join(out)
s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
s = re.sub(r'[^a-z0-9._-]+', '-', s)
s = re.sub(r'-{2,}', '-', s).strip('-._')
print(s or 'file')
PY
}

SLUG="$(slugify "$NAME")"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="${TS}_${SLUG}${EXT}"

mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST_DIR/$OUT"

# Stdout: just the filename (callers parse this). Hints go to stderr.
echo "$OUT"
{
  echo "staged: assets/tmp-uploads/$OUT"
  echo "url:    https://rbpp3042.github.io/my_notes/assets/tmp-uploads/$OUT"
  echo "next:   git add + commit + push (URL is live only after push)"
} >&2

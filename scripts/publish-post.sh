#!/usr/bin/env bash
# publish-post.sh — turn a Markdown/HTML file into a real Jekyll blog post under _posts/.
#
# Unlike publish-tmp-upload.sh (raw static hosting under assets/tmp-uploads/), this
# creates a themed post that appears in the blog index and gets a clean permalink:
#   https://rbpp3042.github.io/my_notes/post/<slug>/
#
# Usage:
#   publish-post.sh <source.md|.html> [options]
#
# Options:
#   --title  "..."        Post title. Default: first "# H1" / "<h1>" in the file, else slug.
#   --slug   <slug>       URL slug (ASCII). Default: transliterated title.
#   --date   YYYY-MM-DD    Post date. Default: today.
#   --author "..."        Author. Default: "Егор Колосов".
#   --draft               Set published: false (won't show on the live blog).
#
# If the source already begins with YAML front matter (---), it is kept verbatim and
# only copied into _posts/ with the dated filename.
#
# Output: writes <repo>/_posts/YYYY-MM-DD-<slug>.md and prints its path + permalink.
# Exit codes: 0 success, 1 bad arguments or missing file.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POSTS_DIR="$REPO_DIR/_posts"

err() { printf 'error: %s\n' "$*" >&2; }

if [[ $# -lt 1 ]]; then
  err "usage: publish-post.sh <source.md|.html> [--title ..] [--slug ..] [--date ..] [--author ..] [--draft]"
  exit 1
fi

SRC="$1"; shift
if [[ ! -f "$SRC" ]]; then
  err "source file not found: $SRC"
  exit 1
fi

TITLE=""; SLUG=""; DATE=""; AUTHOR="Егор Колосов"; DRAFT="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)  TITLE="${2:-}"; shift 2 ;;
    --slug)   SLUG="${2:-}"; shift 2 ;;
    --date)   DATE="${2:-}"; shift 2 ;;
    --author) AUTHOR="${2:-}"; shift 2 ;;
    --draft)  DRAFT="1"; shift ;;
    *) err "unknown option: $1"; exit 1 ;;
  esac
done

[[ -n "$DATE" ]] || DATE="$(date +%Y-%m-%d)"

# NOTE: heredoc is redirected to a temp file (NOT nested inside $(...)) because
# macOS ships bash 3.2, which mis-parses a heredoc placed inside command substitution.
TMP_OUT="$(mktemp "${TMPDIR:-/tmp}/publish-post.XXXXXX")"
trap 'rm -f "$TMP_OUT"' EXIT
SRC="$SRC" TITLE="$TITLE" SLUG="$SLUG" DATE="$DATE" AUTHOR="$AUTHOR" \
DRAFT="$DRAFT" POSTS_DIR="$POSTS_DIR" python3 > "$TMP_OUT" <<'PY'
import os, re, sys, unicodedata

src   = os.environ["SRC"]
title = os.environ["TITLE"].strip()
slug  = os.environ["SLUG"].strip()
date  = os.environ["DATE"].strip()
author= os.environ["AUTHOR"]
draft = os.environ["DRAFT"] == "1"
posts = os.environ["POSTS_DIR"]

with open(src, encoding="utf-8") as f:
    body = f.read()

RU = {
 'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
 'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
 'у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y',
 'ь':'','э':'e','ю':'yu','я':'ya'}
def slugify(s):
    s = s.lower()
    s = ''.join(RU.get(ch, ch) for ch in s)
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return s

# If the source already has YAML front matter, keep it verbatim.
has_fm = body.lstrip().startswith('---')

if not has_fm:
    # Derive title from first H1 if not given; strip that heading from the body.
    if not title:
        m = re.search(r'^\s*#\s+(.+?)\s*$', body, re.M)
        if m:
            title = m.group(1).strip()
            body = body[:m.start()] + body[m.end():]
        else:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', body, re.I|re.S)
            if m:
                title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                body = body[:m.start()] + body[m.end():]
    if not slug:
        slug = slugify(title) if title else slugify(os.path.splitext(os.path.basename(src))[0])
    if not title:
        title = slug.replace('-', ' ').capitalize()

    body = body.lstrip('\n')
    esc = title.replace('"', '\\"')
    fm = ["---", "layout: post", f'author: "{author}"', f'title: "{esc}"', f"date: {date}"]
    if draft:
        fm.append("published: false")
    fm.append("---")
    content = "\n".join(fm) + "\n\n" + body
    if not content.endswith("\n"):
        content += "\n"
else:
    # Has front matter already: derive slug for the filename only.
    if not slug:
        m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', body, re.M)
        slug = slugify(m.group(1)) if m else slugify(os.path.splitext(os.path.basename(src))[0])
    content = body

if not slug:
    slug = "post"

os.makedirs(posts, exist_ok=True)
out = os.path.join(posts, f"{date}-{slug}.md")
with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print(out)
PY

OUT_PATH="$(cat "$TMP_OUT")"

SLUG_FINAL="$(basename "$OUT_PATH" .md)"
SLUG_FINAL="${SLUG_FINAL#????-??-??-}"

echo "$OUT_PATH"
{
  echo "created: _posts/$(basename "$OUT_PATH")"
  echo "permalink: https://rbpp3042.github.io/my_notes/post/${SLUG_FINAL}/"
  echo "next: git add + commit + push (live only after push; theme rebuild ~1-3 min)"
  if [[ "$DRAFT" == "1" ]]; then
    echo "note: published:false — will NOT appear on the live blog"
  fi
} >&2

exit 0

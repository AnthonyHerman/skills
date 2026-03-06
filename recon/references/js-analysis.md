# JavaScript Analysis

Use this phase to extract endpoints, secrets, API routes, and architectural insights from JavaScript files. This is a dedicated phase — not lumped into content discovery. Runs in Wave 4 alongside content-discovery and browser-mapping.

## Inputs

- `live-hosts.txt`
- optional `technologies.json` (to prioritize SPA/React/Angular targets)

## Procedure

### 1. Collect JavaScript Files

```bash
# From crawling
if command -v katana >/dev/null 2>&1; then
  katana -list live-hosts.txt -d 3 -jc -ef css,png,jpg,gif,svg,woff,ttf -silent 2>/dev/null | grep -iE "\.js(\?|$)" | sort -u > js-files-crawl.txt
fi

# From historical archives
if command -v gau >/dev/null 2>&1; then
  cat live-hosts.txt | gau --threads 5 2>/dev/null | grep -iE "\.js(\?|$)" | sort -u > js-files-archive.txt
fi

if command -v waybackurls >/dev/null 2>&1; then
  cat live-hosts.txt | waybackurls 2>/dev/null | grep -iE "\.js(\?|$)" | sort -u >> js-files-archive.txt
fi

# Merge and deduplicate
cat js-files-crawl.txt js-files-archive.txt 2>/dev/null | sort -u > js-files.txt
```

Fallback:

```bash
while read url; do
  curl -s --connect-timeout 5 "$url" 2>/dev/null | grep -oE 'src="[^"]*\.js[^"]*"' | sed 's/src="//;s/"//' | while read js; do
    case "$js" in
      http*) echo "$js" ;;
      //*) echo "https:${js}" ;;
      /*) echo "${url}${js}" ;;
    esac
  done
done < live-hosts.txt | sort -u > js-files.txt
```

### 2. Extract Endpoints and API Routes

```bash
# LinkFinder or similar
if command -v linkfinder >/dev/null 2>&1; then
  while read jsurl; do
    linkfinder -i "$jsurl" -o cli 2>/dev/null
  done < js-files.txt | sort -u > js-endpoints.txt
fi
```

Fallback — regex extraction:

```bash
while read jsurl; do
  content=$(curl -s --connect-timeout 10 "$jsurl" 2>/dev/null)
  # API paths
  echo "$content" | grep -oP '["'"'"'](\/api\/[^"'"'"'\s]+)["'"'"']' | tr -d "\"'" | sort -u
  # Absolute URLs
  echo "$content" | grep -oE 'https?://[^"'"'"'\s<>]+' | sort -u
  # Relative paths starting with /
  echo "$content" | grep -oP '["'"'"'](\/[a-zA-Z][^"'"'"'\s]{2,})["'"'"']' | tr -d "\"'" | grep -v '\.css\|\.png\|\.jpg\|\.svg\|\.gif\|\.woff' | sort -u
done < js-files.txt | sort -u > js-endpoints.txt
```

### 3. Search for Secrets and Sensitive Data

```bash
# trufflehog for verified secrets
if command -v trufflehog >/dev/null 2>&1; then
  while read jsurl; do
    curl -s "$jsurl" 2>/dev/null | trufflehog filesystem --stdin --only-verified 2>/dev/null
  done < js-files.txt > js-secrets-verified.txt
fi

# Pattern-based secret detection (always run)
while read jsurl; do
  content=$(curl -s --connect-timeout 10 "$jsurl" 2>/dev/null)
  echo "$content" | grep -oiE "(api[_-]?key|apikey|api[_-]?secret|token|secret|password|auth[_-]?token|access[_-]?key|aws[_-]?access|private[_-]?key|client[_-]?secret)['"'"'":\s=]+['"'"'"][a-zA-Z0-9/+=_\-]{16,}['"'"'"]" | while read match; do
    echo "${jsurl}:${match}"
  done
done < js-files.txt | sort -u > js-secrets.txt

# Merge verified and pattern-based
cat js-secrets-verified.txt js-secrets.txt 2>/dev/null | sort -u > js-secrets-all.txt
mv js-secrets-all.txt js-secrets.txt
```

### 4. Detect Configuration and Feature Flags

```bash
while read jsurl; do
  content=$(curl -s --connect-timeout 10 "$jsurl" 2>/dev/null)
  # Config objects
  echo "$content" | grep -oiE '(config|settings|env|feature[_-]?flags?)\s*[:=]\s*\{[^}]{10,}\}' | while read match; do
    echo "${jsurl}:CONFIG:${match}"
  done
  # Environment indicators
  echo "$content" | grep -oiE '(NODE_ENV|REACT_APP_|NEXT_PUBLIC_|VUE_APP_)[A-Z_]*\s*[:=]\s*['"'"'"][^'"'"'"]+['"'"'"]' | while read match; do
    echo "${jsurl}:ENV:${match}"
  done
done < js-files.txt | sort -u > js-configs.txt
```

### 5. Webpack and Source Map Analysis

```bash
while read jsurl; do
  # Check for source maps
  mapurl="${jsurl}.map"
  status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$mapurl" 2>/dev/null)
  [ "$status" = "200" ] && echo "SOURCEMAP:${mapurl}"

  # Check for webpack manifest or chunk references
  content=$(curl -s --connect-timeout 10 "$jsurl" 2>/dev/null)
  echo "$content" | grep -oE 'webpackChunk[a-zA-Z_]+' | head -5 | while read chunk; do
    echo "WEBPACK:${jsurl}:${chunk}"
  done
done < js-files.txt | sort -u > js-sourcemaps.txt
```

## Output

- `js-files.txt`: one JavaScript URL per line
- `js-endpoints.txt`: API paths and URLs extracted from JS source
- `js-secrets.txt`: potential secrets with source file reference (redacted values where possible)
- optional `js-configs.txt`: configuration objects and environment variables
- optional `js-sourcemaps.txt`: discovered source maps and webpack manifests

## Rules

- Download each JS file only once — cache content if checking multiple patterns.
- Do not store full secret values — store the source URL, the key name, and a truncated value.
- Prioritize SPA frameworks (React, Angular, Vue, Next.js) from `technologies.json` when present.
- Source maps are high-value — they expose original source code. Flag them prominently.
- `js-endpoints.txt` feeds directly into the api-discovery phase (Wave 5).

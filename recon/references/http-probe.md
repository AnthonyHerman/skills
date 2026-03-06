# HTTP Probing

Use this phase to identify live HTTP(S) services from `subdomains.txt` and fingerprint them.

## Inputs

- `subdomains.txt`
- optional `ports.txt`

## Procedure

### 1. Probe Hosts

```bash
cat subdomains.txt | httpx -silent -status-code -title -tech-detect -content-length -follow-redirects -json -o httpx-output.json 2>/dev/null
cat subdomains.txt | httpx -silent -o live-hosts.txt 2>/dev/null
```

Fallback:

```bash
while read sub; do
  for scheme in https http; do
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${scheme}://${sub}" 2>/dev/null)
    if [ "$status" != "000" ]; then
      echo "${scheme}://${sub}"
    fi
  done
done < subdomains.txt
```

### 2. Extract Technology Metadata

```bash
cat httpx-output.json | jq -r 'select(.tech != null) | {url: .url, status: .status_code, title: .title, tech: .tech, content_length: .content_length}' 2>/dev/null
```

Fallback:

```bash
while read url; do
  headers=$(curl -sI --connect-timeout 5 "$url" 2>/dev/null)
  server=$(echo "$headers" | grep -i "^server:" | cut -d: -f2- | xargs)
  powered=$(echo "$headers" | grep -i "^x-powered-by:" | cut -d: -f2- | xargs)
  echo "{\"url\":\"$url\",\"server\":\"$server\",\"powered_by\":\"$powered\"}"
done < live-hosts.txt
```

### 3. Flag Interesting Headers

```bash
while read url; do
  headers=$(curl -sI --connect-timeout 5 "$url" 2>/dev/null)
  echo "$headers" | grep -qi "strict-transport-security" || echo "MISSING HSTS: $url"
  echo "$headers" | grep -qi "x-frame-options\\|content-security-policy" || echo "MISSING XFO/CSP: $url"
  echo "$headers" | grep -qi "x-debug\\|x-backend\\|x-server\\|x-amz\\|x-goog\\|x-azure" && echo "INTERESTING HEADERS: $url"
done < live-hosts.txt
```

### 4. Capture Screenshots

```bash
if command -v gowitness >/dev/null 2>&1; then
  mkdir -p screenshots
  gowitness file -f live-hosts.txt -P screenshots/ --timeout 10 2>/dev/null
fi
```

## Output

- `live-hosts.txt`
- `technologies.json`

## Rules

- Always try both HTTP and HTTPS.
- Follow redirects, but note them.
- Prefer 5 to 10 second timeouts.
- Probe non-standard web ports from `ports.txt` when present.

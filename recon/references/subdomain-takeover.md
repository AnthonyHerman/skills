# Subdomain Takeover

Use this phase to check for dangling DNS records that could allow subdomain takeover. Runs in Wave 3 alongside http-probe and port-scan.

## Inputs

- `subdomains.txt`

## Procedure

### 1. Nuclei Takeover Templates (Preferred)

```bash
if command -v nuclei >/dev/null 2>&1; then
  nuclei -l subdomains.txt -t takeovers/ -silent -o takeover-nuclei.txt 2>/dev/null
fi
```

### 2. CNAME Fingerprint Check (Fallback)

Check for dangling CNAMEs pointing to deprovisioned services:

```bash
while read sub; do
  cname=$(dig +short CNAME "$sub" 2>/dev/null | head -1)
  [ -z "$cname" ] && continue

  # Check if the CNAME target resolves
  resolved=$(dig +short A "$cname" 2>/dev/null | head -1)

  if [ -z "$resolved" ]; then
    echo "DANGLING:${sub}:${cname}"
    continue
  fi

  # Check for known takeover fingerprints
  body=$(curl -s --connect-timeout 5 "http://${sub}" 2>/dev/null)
  case "$cname" in
    *.github.io*)
      echo "$body" | grep -qi "There isn't a GitHub Pages site here" && echo "GITHUB-PAGES:${sub}:${cname}" ;;
    *.herokuapp.com*)
      echo "$body" | grep -qi "no such app" && echo "HEROKU:${sub}:${cname}" ;;
    *.s3.amazonaws.com*|*.s3-*.amazonaws.com*)
      echo "$body" | grep -qi "NoSuchBucket" && echo "S3:${sub}:${cname}" ;;
    *.azurewebsites.net*)
      echo "$body" | grep -qi "404 Web Site not found" && echo "AZURE:${sub}:${cname}" ;;
    *.cloudfront.net*)
      echo "$body" | grep -qi "Bad request" && echo "CLOUDFRONT:${sub}:${cname}" ;;
    *.shopify.com*)
      echo "$body" | grep -qi "Sorry, this shop is currently unavailable" && echo "SHOPIFY:${sub}:${cname}" ;;
    *.fastly.net*)
      echo "$body" | grep -qi "Fastly error: unknown domain" && echo "FASTLY:${sub}:${cname}" ;;
    *.ghost.io*)
      echo "$body" | grep -qi "The thing you were looking for is no longer here" && echo "GHOST:${sub}:${cname}" ;;
    *.pantheon.io*)
      echo "$body" | grep -qi "404 error unknown site" && echo "PANTHEON:${sub}:${cname}" ;;
  esac
done < subdomains.txt
```

### 3. NS Delegation Check

```bash
while read sub; do
  ns=$(dig +short NS "$sub" 2>/dev/null)
  [ -z "$ns" ] && continue
  for nameserver in $ns; do
    resolved=$(dig +short A "$nameserver" 2>/dev/null | head -1)
    [ -z "$resolved" ] && echo "DANGLING-NS:${sub}:${nameserver}"
  done
done < subdomains.txt
```

## Output

- `takeovers.txt`: one potential takeover per line:
  ```
  GITHUB-PAGES:blog.example.com:example.github.io
  S3:assets.example.com:assets.example.com.s3.amazonaws.com
  DANGLING:old.example.com:old-service.provider.com
  ```

## Rules

- Verify before reporting — a CNAME to a third-party service is not a takeover unless the service confirms the resource is unclaimed.
- Prioritize dangling CNAMEs (NXDOMAIN targets) as highest confidence.
- Do not attempt to actually register or claim any resources.
- Report the service type, subdomain, and CNAME target for each finding.

# Cloud Enumeration

Use this phase to discover cloud-hosted assets: S3 buckets, GCS buckets, Azure blobs, CDN origins, and cloud service fingerprints. Runs in parallel with subdomain-enum (Wave 2).

## Inputs

- `seeds.txt` (domain names for permutation)

## Procedure

### 1. Bucket and Blob Permutation

```bash
# cloud_enum covers S3, GCS, and Azure in one pass
if command -v cloud_enum >/dev/null 2>&1; then
  cloud_enum -k <target-keyword> -l cloud-enum-output.txt 2>/dev/null
fi

# S3-specific scanning
if command -v s3scanner >/dev/null 2>&1; then
  # Generate permutations from the target domain
  for word in "" "-dev" "-staging" "-prod" "-backup" "-assets" "-media" "-static" "-logs" "-data" "-internal" "-test" "-cdn" "-uploads" "-public" "-private"; do
    echo "<target-keyword>${word}"
  done > bucket-permutations.txt
  s3scanner --bucket-file bucket-permutations.txt 2>/dev/null
fi
```

Fallback — check buckets with curl:

```bash
while read name; do
  # S3
  status=$(curl -s -o /dev/null -w "%{http_code}" "https://${name}.s3.amazonaws.com" 2>/dev/null)
  [ "$status" != "000" ] && [ "$status" != "404" ] && echo "s3:${name}:${status}"

  # GCS
  status=$(curl -s -o /dev/null -w "%{http_code}" "https://storage.googleapis.com/${name}" 2>/dev/null)
  [ "$status" != "000" ] && [ "$status" != "404" ] && echo "gcs:${name}:${status}"

  # Azure
  status=$(curl -s -o /dev/null -w "%{http_code}" "https://${name}.blob.core.windows.net" 2>/dev/null)
  [ "$status" != "000" ] && [ "$status" != "404" ] && echo "azure:${name}:${status}"
done < bucket-permutations.txt
```

### 2. CNAME-Based Cloud Service Detection

```bash
# Check subdomains for cloud CNAMEs (run after subdomains.txt exists, or use seeds)
while read domain; do
  cname=$(dig +short CNAME "$domain" 2>/dev/null | head -1)
  [ -z "$cname" ] && continue
  case "$cname" in
    *.amazonaws.com*) echo "aws-cname:${domain}:${cname}" ;;
    *.cloudfront.net*) echo "cloudfront:${domain}:${cname}" ;;
    *.azurewebsites.net*|*.azure-api.net*|*.blob.core.windows.net*) echo "azure-cname:${domain}:${cname}" ;;
    *.googleapis.com*|*.appspot.com*) echo "gcp-cname:${domain}:${cname}" ;;
    *.herokuapp.com*) echo "heroku-cname:${domain}:${cname}" ;;
    *.firebaseapp.com*) echo "firebase-cname:${domain}:${cname}" ;;
  esac
done < subdomains-or-seeds.txt
```

### 3. CDN Origin Discovery

```bash
# Check for origin headers that reveal backend infrastructure
while read url; do
  headers=$(curl -sI --connect-timeout 5 "$url" 2>/dev/null)
  echo "$headers" | grep -iE "^(x-amz-|x-goog-|x-azure-|x-cache|x-cdn|cf-ray|x-served-by|x-backend)" | while read line; do
    echo "cdn-header:${url}:${line}"
  done
done < live-hosts-or-seeds.txt
```

## Output

- `cloud-assets.txt`: one asset per line in `type:identifier:detail` format:
  ```
  s3:company-assets:200
  s3:company-backup:403
  gcs:company-data:public
  azure:company-storage:403
  cloudfront:cdn.example.com:d123.cloudfront.net
  aws-cname:api.example.com:elb-123.us-east-1.elb.amazonaws.com
  ```

## Rules

- Generate permutations from the target keyword, not just the domain (e.g., `acme` not `acme.com`).
- Include common suffixes: `-dev`, `-staging`, `-prod`, `-backup`, `-assets`, `-media`, `-static`, `-logs`, `-data`, `-internal`, `-test`.
- Report HTTP status codes — 403 is interesting (exists but restricted), 200 is potentially open.
- Rate-limit requests to avoid triggering WAF blocks.
- Deduplicate across tools.

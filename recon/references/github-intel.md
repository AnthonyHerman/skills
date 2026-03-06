# GitHub Intelligence

Use this phase to discover leaked secrets, internal URLs, configuration files, and developer information from GitHub. Runs in parallel with seed-discovery (Wave 1).

## Inputs

- target domain or organization name

## Procedure

### 1. Find Organization and Developer Accounts

```bash
# Search for GitHub orgs matching the target
gh search repos "<target>" --limit 50 --json fullName,description,url 2>/dev/null

# Search for code mentioning the target domain
gh search code "<target>" --limit 100 --json repository,path,textMatches 2>/dev/null
```

Fallback with curl:

```bash
curl -s "https://api.github.com/search/repositories?q=<target>" | jq -r '.items[].full_name'
curl -s "https://api.github.com/search/code?q=<target>" | jq -r '.items[] | "\(.repository.full_name) \(.path)"'
```

### 2. Search for Secrets and Credentials

```bash
# If trufflehog is available, scan discovered repos
trufflehog github --org=<target-org> --only-verified 2>/dev/null

# Manual secret patterns via GitHub search
gh search code "password <target>" --limit 50 2>/dev/null
gh search code "api_key <target>" --limit 50 2>/dev/null
gh search code "apikey <target>" --limit 50 2>/dev/null
gh search code "secret <target>" --limit 50 2>/dev/null
gh search code "token <target>" --limit 50 2>/dev/null
gh search code "AWS_ACCESS_KEY <target>" --limit 50 2>/dev/null
```

### 3. Search for Configuration and Internal URLs

```bash
gh search code "filename:.env <target>" --limit 50 2>/dev/null
gh search code "filename:config <target>" --limit 50 2>/dev/null
gh search code "filename:.yml <target>" --limit 50 2>/dev/null
gh search code "internal.<target>" --limit 50 2>/dev/null
gh search code "staging.<target>" --limit 50 2>/dev/null
gh search code "dev.<target>" --limit 50 2>/dev/null
```

### 4. Search for CI/CD and Infrastructure

```bash
gh search code "filename:.github/workflows <target>" --limit 50 2>/dev/null
gh search code "filename:Dockerfile <target>" --limit 50 2>/dev/null
gh search code "filename:docker-compose <target>" --limit 50 2>/dev/null
gh search code "filename:terraform <target>" --limit 50 2>/dev/null
```

### 5. Extract Postman Collections

```bash
# Search for leaked Postman collections referencing the target
gh search code "postman <target>" --limit 50 2>/dev/null
curl -s "https://www.postman.com/_api/ws/proxy" -d '{"service":"search","method":"POST","path":"/search-all","body":{"queryIndices":["runtime~collection"],"queryText":"'"<target>"'"}}' 2>/dev/null | jq -r '.data[].document.name' 2>/dev/null
```

## Output

- `github-intel.txt`: one finding per line — `type:detail` format:
  ```
  repo:org/repo-name
  internal-url:https://internal.example.com/admin
  config-file:org/repo/.env
  ci-workflow:org/repo/.github/workflows/deploy.yml
  postman:collection-name
  ```
- `github-secrets.txt`: one potential secret per line (redacted values, include source repo and file path)

## Rules

- Rate-limit GitHub API calls. Use `--limit` flags and add delays between searches.
- Never store actual secret values in output — store the source location and type only.
- Deduplicate results across search queries.
- Flag but do not dismiss unverified findings — they may still indicate useful surface.

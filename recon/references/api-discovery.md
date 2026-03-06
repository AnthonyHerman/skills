# API Discovery

Use this phase to discover and enumerate API endpoints, GraphQL schemas, and OpenAPI/Swagger definitions. Runs in Wave 5 after js-analysis and content-discovery complete, because their outputs inform targeting.

## Inputs

- `live-hosts.txt`
- `technologies.json` (to identify API-heavy targets)
- `js-endpoints.txt` (API routes extracted from JavaScript)
- optional `urls.txt` (discovered URLs from content-discovery)
- optional `api-routes.txt` (from browser-mapping)

## Procedure

### 1. Identify API Targets

Build a focused target list from technology fingerprints and JS analysis:

```bash
# Hosts with API-related tech stacks
cat technologies.json | jq -r 'select(.tech | any(test("express|django|flask|spring|rails|fastapi|laravel|graphql|swagger|openapi"; "i"))) | .url' 2>/dev/null > api-targets.txt

# Hosts with /api/ paths from JS analysis
cat js-endpoints.txt 2>/dev/null | grep -iE '/api/|/graphql|/v[0-9]+/' | unfurl -u domains 2>/dev/null | sort -u >> api-targets.txt

# Hosts with API paths from content discovery
cat urls.txt 2>/dev/null | grep -iE '/api/|/graphql|/v[0-9]+/' | unfurl -u domains 2>/dev/null | sort -u >> api-targets.txt

# Hosts with API routes from browser mapping
cat api-routes.txt 2>/dev/null | unfurl -u domains 2>/dev/null | sort -u >> api-targets.txt

# Deduplicate
sort -u api-targets.txt -o api-targets.txt

# Fall back to all live hosts if no specific API targets found
[ ! -s api-targets.txt ] && cp live-hosts.txt api-targets.txt
```

### 2. Swagger/OpenAPI File Discovery

```bash
SWAGGER_PATHS=(
  "/swagger.json" "/swagger/v1/swagger.json" "/swagger-ui.html"
  "/openapi.json" "/openapi.yaml" "/openapi/v1"
  "/api-docs" "/api-docs.json" "/api/docs"
  "/v1/api-docs" "/v2/api-docs" "/v3/api-docs"
  "/docs" "/redoc" "/.well-known/openapi"
  "/api/swagger" "/api/openapi" "/api/schema"
)

while read url; do
  for path in "${SWAGGER_PATHS[@]}"; do
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${url}${path}" 2>/dev/null)
    if [ "$status" = "200" ] || [ "$status" = "301" ] || [ "$status" = "302" ]; then
      echo "${url}${path}:${status}"
    fi
  done
done < api-targets.txt | sort -u > swagger-files.txt

# Download discovered swagger files
mkdir -p swagger-files
while IFS=: read -r scheme host path status; do
  url="${scheme}:${host}${path}"
  filename=$(echo "${host}${path}" | sed 's/[^a-zA-Z0-9]/_/g')
  curl -s --connect-timeout 5 "$url" -o "swagger-files/${filename}.json" 2>/dev/null
done < swagger-files.txt
```

### 3. GraphQL Introspection

```bash
GRAPHQL_PATHS=(
  "/graphql" "/graphiql" "/v1/graphql" "/api/graphql"
  "/query" "/gql" "/graphql/console"
)

INTROSPECTION_QUERY='{"query":"{ __schema { types { name fields { name } } } }"}'

while read url; do
  for path in "${GRAPHQL_PATHS[@]}"; do
    # Test introspection
    response=$(curl -s --connect-timeout 5 -X POST -H "Content-Type: application/json" -d "$INTROSPECTION_QUERY" "${url}${path}" 2>/dev/null)
    if echo "$response" | jq -e '.__data.__schema // .data.__schema' >/dev/null 2>&1; then
      echo "INTROSPECTION-ENABLED:${url}${path}"
      mkdir -p graphql-schemas
      echo "$response" | jq '.' > "graphql-schemas/$(echo "${url}${path}" | sed 's/[^a-zA-Z0-9]/_/g').json"
    elif echo "$response" | grep -qi "graphql\|query"; then
      echo "GRAPHQL-DETECTED:${url}${path}"
    fi
  done
done < api-targets.txt | sort -u > graphql-results.txt
```

### 4. Kiterunner API Route Bruteforce

```bash
if command -v kr >/dev/null 2>&1; then
  # Use Kiterunner's built-in API wordlists (67k+ Swagger signatures)
  kr brute api-targets.txt -w routes-large.kite --fail-status-codes 400,404,500 -o json 2>/dev/null | \
    jq -r '.results[] | "\(.url) \(.status) \(.length)"' 2>/dev/null > kiterunner-results.txt
fi
```

Fallback — manual API path brute-force:

```bash
API_PATHS=(
  "/api" "/api/v1" "/api/v2" "/api/v3"
  "/api/users" "/api/user" "/api/me" "/api/profile"
  "/api/admin" "/api/config" "/api/settings"
  "/api/health" "/api/status" "/api/version" "/api/info"
  "/api/login" "/api/auth" "/api/token" "/api/oauth"
  "/api/search" "/api/query" "/api/data" "/api/export"
  "/actuator" "/actuator/health" "/actuator/env" "/actuator/beans"
  "/_debug" "/_status" "/_health" "/_config"
)

while read url; do
  for path in "${API_PATHS[@]}"; do
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${url}${path}" 2>/dev/null)
    case "$status" in
      200|201|204|301|302|307|401|403|405) echo "${url}${path}:${status}" ;;
    esac
  done
done < api-targets.txt | sort -u > api-bruteforce-results.txt
```

### 5. Merge JS-Discovered Routes with Brute-Force Results

```bash
# Combine all discovered API endpoints
cat js-endpoints.txt kiterunner-results.txt api-bruteforce-results.txt swagger-files.txt graphql-results.txt 2>/dev/null | sort -u > api-endpoints.txt
```

## Output

- `api-endpoints.txt`: all discovered API endpoints, merged from all sources
- `swagger-files/`: downloaded OpenAPI/Swagger definition files
- `graphql-schemas/`: downloaded GraphQL introspection results

## Rules

- Target smartly — use `technologies.json` and `js-endpoints.txt` to focus, not brute-force everything.
- GraphQL introspection is a finding in itself — always flag it.
- Swagger/OpenAPI exposure is a finding — flag it.
- 401/403 responses on API paths are interesting — the endpoint exists but is protected.
- Spring Boot actuator endpoints (`/actuator/*`) are high-value targets.
- Merge all sources into `api-endpoints.txt` so the vault and report have one consolidated view.

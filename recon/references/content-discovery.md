# Content Discovery

Use this phase to collect URLs, parameters, and interesting patterns from `live-hosts.txt`. Runs in Wave 4 alongside js-analysis and browser-mapping.

**JavaScript analysis is handled by the dedicated js-analysis phase.** This phase focuses on URL collection, directory brute-force, parameter extraction, and pattern matching.

## Inputs

- `live-hosts.txt`
- `technologies.json` (used for tech-routed wordlist selection)

## Procedure

### 1. Technology-Routed Target Selection

Before brute-forcing, read `technologies.json` and categorize hosts by stack. This determines which wordlists and extensions to use.

```bash
# Extract tech stacks and build per-tech host lists
cat technologies.json | jq -r '
  . as $entry |
  if (.tech | any(test("wordpress|wp-"; "i"))) then "wordpress:\(.url)"
  elif (.tech | any(test("drupal"; "i"))) then "drupal:\(.url)"
  elif (.tech | any(test("joomla"; "i"))) then "joomla:\(.url)"
  elif (.tech | any(test("spring|java|tomcat"; "i"))) then "java:\(.url)"
  elif (.tech | any(test("django|flask|python"; "i"))) then "python:\(.url)"
  elif (.tech | any(test("express|node|next|nuxt"; "i"))) then "node:\(.url)"
  elif (.tech | any(test("laravel|php|symfony"; "i"))) then "php:\(.url)"
  elif (.tech | any(test("ruby|rails"; "i"))) then "ruby:\(.url)"
  elif (.tech | any(test("asp|\.net|iis"; "i"))) then "dotnet:\(.url)"
  else "general:\(.url)"
  end
' 2>/dev/null > tech-routed-hosts.txt
```

Wordlist selection per stack:

| Stack | Wordlist | Extensions |
|-------|----------|------------|
| WordPress | `SecLists/Discovery/Web-Content/CMS/wordpress.fuzz.txt` | `.php` |
| Drupal | `SecLists/Discovery/Web-Content/CMS/drupal.txt` | `.php` |
| Java/Spring | `SecLists/Discovery/Web-Content/spring-boot.txt` + actuator paths | `.jsp, .do, .action` |
| Python | `SecLists/Discovery/Web-Content/django.txt` | `.py` |
| Node | General + API-focused lists | `.js, .json` |
| PHP | `SecLists/Discovery/Web-Content/Common-PHP-Filenames.txt` | `.php, .inc` |
| .NET | `SecLists/Discovery/Web-Content/IIS.fuzz.txt` | `.aspx, .ashx, .asmx` |
| General | `SecLists/Discovery/Web-Content/raft-medium-directories.txt` | — |

### 2. Historical URL Discovery

```bash
cat live-hosts.txt | waybackurls 2>/dev/null | anew urls-raw.txt
cat live-hosts.txt | gau --threads 5 2>/dev/null | anew urls-raw.txt
```

### 3. Active Crawling

```bash
katana -list live-hosts.txt -d 3 -jc -silent -o katana-output.txt 2>/dev/null
cat katana-output.txt | anew urls-raw.txt
```

### 4. Directory and File Brute Force (Tech-Routed)

```bash
if command -v feroxbuster >/dev/null 2>&1; then
  while IFS=: read -r stack url; do
    # Select wordlist based on tech stack
    case "$stack" in
      wordpress)
        WORDLIST="${HOME}/.recon-wordlists/SecLists/Discovery/Web-Content/CMS/wordpress.fuzz.txt"
        EXTENSIONS=".php"
        ;;
      java)
        WORDLIST="${HOME}/.recon-wordlists/SecLists/Discovery/Web-Content/spring-boot.txt"
        EXTENSIONS=".jsp,.do,.action"
        ;;
      php)
        WORDLIST="${HOME}/.recon-wordlists/SecLists/Discovery/Web-Content/Common-PHP-Filenames.txt"
        EXTENSIONS=".php,.inc"
        ;;
      *)
        WORDLIST="${HOME}/.recon-wordlists/SecLists/Discovery/Web-Content/raft-medium-directories.txt"
        EXTENSIONS=""
        ;;
    esac

    [ ! -f "$WORDLIST" ] && WORDLIST="${HOME}/.recon-wordlists/SecLists/Discovery/Web-Content/raft-medium-directories.txt"

    EXTRA_FLAGS=""
    [ -n "$EXTENSIONS" ] && EXTRA_FLAGS="-x ${EXTENSIONS}"

    if [ -f "$WORDLIST" ]; then
      feroxbuster -u "$url" -w "$WORDLIST" $EXTRA_FLAGS --silent --no-state -t 20 --timeout 10 -s 200,301,302,307,401,403,405 -o "ferox-$(echo $url | sed 's/[^a-zA-Z0-9]/_/g').txt" 2>/dev/null
    fi
  done < tech-routed-hosts.txt
fi
```

### 5. Extract Parameters

```bash
cat urls-raw.txt | unfurl -u keys 2>/dev/null | sort -u > params.txt
cat urls-raw.txt | unfurl -u keypairs 2>/dev/null | sort -u > param-values.txt
```

### 6. Match Interesting Patterns

```bash
mkdir -p interesting
if command -v gf >/dev/null 2>&1; then
  cat urls-raw.txt | gf xss 2>/dev/null | sort -u > interesting/xss.txt
  cat urls-raw.txt | gf ssrf 2>/dev/null | sort -u > interesting/ssrf.txt
  cat urls-raw.txt | gf redirect 2>/dev/null | sort -u > interesting/redirect.txt
  cat urls-raw.txt | gf idor 2>/dev/null | sort -u > interesting/idor.txt
  cat urls-raw.txt | gf lfi 2>/dev/null | sort -u > interesting/lfi.txt
  cat urls-raw.txt | gf sqli 2>/dev/null | sort -u > interesting/sqli.txt
  cat urls-raw.txt | gf debug_logic 2>/dev/null | sort -u > interesting/debug.txt
fi
```

Fallback to manual `grep` patterns if `gf` is unavailable.

## Output

- `urls.txt`
- `params.txt`
- `interesting/*.txt`

Note: `js-files.txt` is now produced by the js-analysis phase, not this one.

## Rules

- Consume `technologies.json` to route wordlist and extension selection — do not use one-size-fits-all.
- Normalize URLs and drop fragments before final output.
- Exclude obvious static assets from `urls.txt` unless they are relevant.
- Focus brute force on high-interest hosts rather than every host.
- Remove empty output files.

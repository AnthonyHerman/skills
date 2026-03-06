# Subdomain Enumeration

Use this phase to enumerate subdomains from `domain:` entries in `seeds.txt`.

## Inputs

- `seeds.txt`

## Procedure

Extract all root domains from `seeds.txt`, then collect results into temporary files and merge at the end.

### 1. Passive Enumeration

```bash
subfinder -d <domain> -all -silent 2>/dev/null
assetfinder --subs-only <domain> 2>/dev/null
amass enum -passive -d <domain> -timeout 5 2>/dev/null
curl -s "https://crt.sh/?q=%25.<domain>&output=json" | jq -r '.[].name_value' 2>/dev/null | sed 's/\\*\\.//g' | sort -u
gau --subs <domain> 2>/dev/null | unfurl -u domains 2>/dev/null | sort -u
echo <domain> | waybackurls 2>/dev/null | unfurl -u domains 2>/dev/null | sort -u
```

### 2. Resolve and Filter

```bash
cat all-passive-results.txt | dnsx -silent -a -resp 2>/dev/null > resolved.txt
```

Fallback:

```bash
cat all-passive-results.txt | while read sub; do
  host "$sub" 2>/dev/null | grep -q "has address" && echo "$sub"
done
```

### 3. Active Brute Force

Run only when active enumeration is allowed.

```bash
WORDLIST="${HOME}/.recon-wordlists/assetnote/httparchive_subdomains.txt"
if [ ! -f "$WORDLIST" ]; then
  WORDLIST="${HOME}/.recon-wordlists/SecLists/Discovery/DNS/subdomains-top1million-5000.txt"
fi

if [ -f "$WORDLIST" ]; then
  cat "$WORDLIST" | sed "s/$/.${domain}/" | dnsx -silent -a 2>/dev/null
fi
```

### 4. Mutations

```bash
cat subdomains-so-far.txt | alterx -silent 2>/dev/null | dnsx -silent 2>/dev/null
```

## Output

Write `subdomains.txt` as one deduplicated subdomain per line.

## Rules

- Merge every source before deduplication.
- Remove wildcard entries and obvious out-of-scope hosts.
- Report source coverage and the final count.

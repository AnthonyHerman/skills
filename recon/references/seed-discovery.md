# Seed Discovery

Use this phase to discover root domains, ASNs, and CIDR ranges tied to the target organization.

## Inputs

- target domain

## Procedure

### 1. Identify the Organization

```bash
whois <target> | grep -i "org\\|registrant\\|organization"
whois <target> | grep -iE "registrant (organization|email|name)"
```

### 2. Find ASNs

```bash
asnmap -d <target> -json 2>/dev/null
whois -h whois.radb.net -- "-i origin $(whois <target> | grep -i origin | awk '{print $NF}')" 2>/dev/null
amass intel -d <target> -asn 2>/dev/null
```

### 3. Find Related Domains

```bash
amass intel -d <target> -whois 2>/dev/null
curl -s "https://crt.sh/?q=%25.<target>&output=json" | jq -r '.[].name_value' | sort -u | sed 's/\\*\\.//g' | rev | cut -d. -f1-2 | rev | sort -u
```

### 4. Expand CIDRs

```bash
asnmap -a <ASN> 2>/dev/null
whois -h whois.radb.net -- "-i origin <ASN>" | grep -i route | awk '{print $NF}' | sort -u
```

## Output

Write `seeds.txt` with one item per line:

```text
domain:example.com
asn:AS12345
cidr:203.0.113.0/24
```

## Rules

- Use multiple sources before trusting ownership.
- Be conservative with related-domain attribution.
- Deduplicate before writing.
- If WHOIS is redacted, rely more on certificate transparency and ASN data.

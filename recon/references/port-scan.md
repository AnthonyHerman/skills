# Port Scanning

Use this phase to identify open ports from `subdomains.txt`.

## Inputs

- `subdomains.txt`

## Procedure

### 1. Pick a Strategy

```bash
wc -l < subdomains.txt
```

- fewer than 50 targets: full `nmap` is fine
- 50 to 500 targets: use `masscan` for discovery, then `nmap` for service checks
- more than 500 targets: scan common web ports only unless the caller asks for more

### 2. Scan Common Ports

```bash
PORTS="80,443,8080,8443,8000,8888,3000,5000,9090,9443,4443,2087,2083,10000,7443,8009"
sudo masscan -iL subdomains.txt -p${PORTS} --rate 1000 -oG masscan-output.txt 2>/dev/null
nmap -iL subdomains.txt -p${PORTS} -T4 --open -oG nmap-output.txt 2>/dev/null
```

### 3. Extend the Scan for Smaller Targets

```bash
nmap -iL subdomains.txt --top-ports 1000 -T4 --open -oG nmap-extended.txt 2>/dev/null
nmap -iL subdomains.txt -p 1-10000 -T4 --open -oG nmap-range.txt 2>/dev/null
```

### 4. Detect Services

```bash
nmap -iL targets-with-ports.txt -sV --version-intensity 5 -oG nmap-services.txt 2>/dev/null
```

### 5. Parse Open Ports

```bash
grep "Ports:" nmap-output.txt | while read line; do
  host=$(echo "$line" | awk '{print $2}')
  ports=$(echo "$line" | grep -oP '\\d+/open' | cut -d/ -f1)
  for port in $ports; do
    echo "${host}:${port}"
  done
done
```

## Output

- `ports.txt`
- optional `services.txt`

## Rules

- Report only open ports.
- Deduplicate results from every scan pass.
- Prefer `nmap` if `masscan` or root access is unavailable.
- Respect program rules before port scanning.

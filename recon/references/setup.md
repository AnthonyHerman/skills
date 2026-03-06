# Recon Setup

Use this reference when the environment is missing tools or wordlists and the caller wants setup help.

## Detect the Environment

Check:

```bash
uname -s
cat /etc/os-release 2>/dev/null
which apt brew pacman dnf yum 2>/dev/null
which go python3 pip3 git curl wget 2>/dev/null
```

Report what you detected before installing anything.

## Install Prerequisites

Most recon tools require Go. If `go` is missing:

- Linux with `apt`: `sudo apt-get update && sudo apt-get install -y golang`
- Linux with `pacman`: `sudo pacman -S go`
- macOS with Homebrew: `brew install go`

Ensure `~/go/bin` is on `PATH`.

## Install Recon Tools

Check each tool with `which` first and only install what is missing.

### Subdomain Enumeration

```bash
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/tomnomnom/assetfinder@latest
go install -v github.com/owasp-amass/amass/v4/...@master
```

### DNS and Infrastructure

```bash
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/projectdiscovery/asnmap/cmd/asnmap@latest
```

### HTTP Probing and Screenshots

```bash
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/sensepost/gowitness@latest
```

### Content Discovery

```bash
curl -sL https://raw.githubusercontent.com/epi052/feroxbuster/main/install-nix.sh | bash -s ~/go/bin
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
go install -v github.com/tomnomnom/waybackurls@latest
go install -v github.com/lc/gau/v2/cmd/gau@latest
```

### URL Analysis

```bash
go install -v github.com/tomnomnom/unfurl@latest
go install -v github.com/tomnomnom/gf@latest
go install -v github.com/tomnomnom/qsreplace@latest
go install -v github.com/tomnomnom/anew@latest
```

### Ports

Install from system packages when available:

- `nmap`
- `masscan`

### Vulnerability Scanning and Subdomain Takeover

```bash
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
```

### JavaScript Analysis

```bash
pip3 install linkfinder 2>/dev/null || pip install linkfinder 2>/dev/null
# trufflehog (secret detection)
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b ~/go/bin
```

### API Discovery

```bash
# Kiterunner (API route brute-force with Swagger signatures)
# Download latest release from https://github.com/assetnote/kiterunner/releases
# or build from source:
go install github.com/assetnote/kiterunner/cmd/kr@latest 2>/dev/null
```

### Cloud Enumeration

```bash
pip3 install cloud_enum 2>/dev/null || pip install cloud_enum 2>/dev/null
pip3 install s3scanner 2>/dev/null || pip install s3scanner 2>/dev/null
```

### Note Mapping

For headless note-vault creation:

- macOS: `brew tap yakitrak/yakitrak && brew install yakitrak/yakitrak/notesmd-cli`
- from source: `go install github.com/Yakitrak/notesmd-cli@latest`

## Install Wordlists

```bash
mkdir -p ~/.recon-wordlists
```

### SecLists

```bash
git clone --depth 1 https://github.com/danielmiessler/SecLists.git ~/.recon-wordlists/SecLists
```

### Assetnote DNS Wordlist

```bash
mkdir -p ~/.recon-wordlists/assetnote
wget -q -O ~/.recon-wordlists/assetnote/httparchive_subdomains.txt https://wordlists-cdn.assetnote.io/data/manual/best-dns-wordlist.txt
```

### `gf` Patterns

```bash
git clone --depth 1 https://github.com/1ndianl33t/Gf-Patterns.git /tmp/gf-patterns
mkdir -p ~/.gf
cp /tmp/gf-patterns/*.json ~/.gf/
rm -rf /tmp/gf-patterns
```

## Verify Installation

```bash
for tool in subfinder assetfinder amass dnsx asnmap httpx gowitness feroxbuster katana waybackurls gau unfurl gf qsreplace anew nmap masscan nuclei notesmd-cli linkfinder trufflehog kr cloud_enum s3scanner gh; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "OK   $tool"
  else
    echo "FAIL $tool"
  fi
done
```

Also verify:

```bash
[ -d ~/.recon-wordlists/SecLists ] && echo "OK   SecLists" || echo "FAIL SecLists"
[ -f ~/.recon-wordlists/assetnote/httparchive_subdomains.txt ] && echo "OK   Assetnote wordlists" || echo "FAIL Assetnote wordlists"
[ -d ~/.gf ] && echo "OK   gf patterns" || echo "FAIL gf patterns"
```

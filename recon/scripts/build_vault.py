#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


API_HINTS = ("api", "gateway", "service", "graphql", "auth", "login", "oauth")
APP_HINTS = ("app", "portal", "dashboard", "admin", "citrix", "bank", "rewards")


def slug(value: str) -> str:
    value = value.replace("://", "-").replace(":", "-")
    value = value.replace("/", "-")
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return value.strip("-")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n")


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_httpx(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def note_link(section: str, name: str) -> str:
    return f"[[{section}/{name}]]"


def host_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def origin_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def load_interesting(interesting_dir: Path) -> dict[str, list[str]]:
    results = {}
    if not interesting_dir.exists():
        return results
    for file in sorted(interesting_dir.glob("*.txt")):
        results[file.stem] = load_lines(file)
    return results


def classify_role(host: str) -> list[str]:
    roles = []
    lower = host.lower()
    if any(token in lower for token in API_HINTS):
        roles.append("api")
    if any(token in lower for token in APP_HINTS):
        roles.append("app")
    if any(token in lower for token in ("dev", "test", "stage", "cert", "prod", "dr")):
        roles.append("environment-tagged")
    return sorted(set(roles))


def empty_host(host: str) -> dict:
    return {
        "host": host,
        "urls": set(),
        "api_routes": set(),
        "status_codes": set(),
        "titles": set(),
        "tech": set(),
        "ports": set(),
        "findings": set(),
        "connections": defaultdict(set),
        "browser_edges": defaultdict(set),
        "ips": set(),
        "cnames": set(),
        "roles": set(classify_role(host)),
    }


def build_host_model(base: Path) -> tuple[dict, set[str], dict[str, list[str]]]:
    httpx_records = load_httpx(base / "httpx-output.json")
    urls = load_lines(base / "urls.txt")
    ports = load_lines(base / "ports.txt")
    interesting = load_interesting(base / "interesting")

    hosts: dict[str, dict] = {}
    techs: set[str] = set()
    by_ip: dict[str, list[str]] = defaultdict(list)
    by_cname: dict[str, list[str]] = defaultdict(list)

    for record in httpx_records:
        input_host = str(record.get("input", "")).lower()
        if not input_host:
            continue
        host = hosts.setdefault(input_host, empty_host(input_host))
        if record.get("url"):
            host["urls"].add(record["url"])
        if record.get("status_code") is not None:
            host["status_codes"].add(str(record["status_code"]))
        if record.get("title"):
            host["titles"].add(str(record["title"]))
        for tech in record.get("tech") or []:
            host["tech"].add(str(tech))
            techs.add(str(tech))
        if record.get("host"):
            host["ips"].add(str(record["host"]))
            by_ip[str(record["host"])].append(input_host)
        for cname in record.get("cname") or []:
            cname = str(cname).lower()
            host["cnames"].add(cname)
            by_cname[cname].append(input_host)
        final_url = record.get("final_url")
        if final_url:
            final_host = host_from_url(final_url)
            if final_host and final_host != input_host:
                host["connections"]["redirects_to"].add(final_host)

    for line in ports:
        if ":" not in line:
            continue
        host_name, port = line.rsplit(":", 1)
        host_name = host_name.lower()
        if host_name in hosts:
            hosts[host_name]["ports"].add(port)

    for url in urls:
        src_host = host_from_url(url)
        if not src_host:
            continue
        host = hosts.setdefault(src_host, empty_host(src_host))
        host["urls"].add(url)
        parsed = urlparse(url)
        path = parsed.path.lower()
        if "/api/" in path or path.endswith("/api") or "api." in parsed.netloc.lower():
            host["roles"].add("api")

    network_payload = load_json(base / "network-requests.json") or {}
    for item in network_payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        request_url = str(item.get("request_url") or "").strip()
        page_host = str(item.get("page_host") or "").lower()
        request_host = str(item.get("request_host") or host_from_url(request_url)).lower()
        resource_type = str(item.get("resource_type") or "").lower()
        if not request_url:
            continue
        if page_host:
            host = hosts.setdefault(page_host, empty_host(page_host))
            if request_url:
                host["api_routes"].add(request_url)
            if request_host and request_host != page_host:
                host["connections"]["runtime_calls"].add(request_host)
        if request_host and request_host in hosts:
            hosts[request_host]["api_routes"].add(request_url)
            if resource_type in {"fetch", "xmlhttprequest", "websocket", "eventsource"}:
                hosts[request_host]["roles"].add("api")

    for category, hits in interesting.items():
        for hit in hits:
            hit_host = host_from_url(hit)
            if hit_host in hosts:
                hosts[hit_host]["findings"].add(category)

    for current_host, host in hosts.items():
        for url in list(host["urls"]):
            other_host = host_from_url(url)
            if other_host and other_host != current_host:
                host["connections"]["references"].add(other_host)
        if "api" in host["roles"]:
            for other_host in hosts:
                if other_host == current_host:
                    continue
                if other_host.endswith("." + current_host) or current_host.endswith("." + other_host):
                    host["connections"]["naming_family"].add(other_host)

    for _, members in by_ip.items():
        uniq = sorted(set(members))
        if len(uniq) < 2:
            continue
        for host_name in uniq:
            hosts[host_name]["connections"]["shared_ip"].update(x for x in uniq if x != host_name)

    for _, members in by_cname.items():
        uniq = sorted(set(members))
        if len(uniq) < 2:
            continue
        for host_name in uniq:
            hosts[host_name]["connections"]["shared_cname"].update(x for x in uniq if x != host_name)

    return hosts, techs, interesting


def format_target(value: str) -> str:
    if value.startswith("host:"):
        return note_link("hosts", slug(value.split(":", 1)[1]))
    if value.startswith("origin:"):
        return note_link("origins", slug(value.split(":", 1)[1]))
    if value.startswith("scope:"):
        return f"`{value.split(':', 1)[1]}`"
    return f"`{value}`"


def add_browser_edge(hosts: dict[str, dict], host_name: str, edge_type: str, target_type: str, target_value: str) -> None:
    if not host_name:
        return
    host = hosts.setdefault(host_name, empty_host(host_name))
    host["browser_edges"][edge_type].add(f"{target_type}:{target_value}")


def build_browser_model(base: Path, hosts: dict[str, dict]) -> tuple[dict[str, dict], dict, dict[str, int]]:
    payload = load_json(base / "browser-relationships.json") or {}
    origins: dict[str, dict] = {}
    relationship_counts: dict[str, int] = defaultdict(int)

    def origin_entry(origin: str) -> dict:
        entry = origins.get(origin)
        if entry is None:
            entry = {
                "origin": origin,
                "host": host_from_url(origin),
                "incoming": defaultdict(set),
                "outgoing": defaultdict(set),
            }
            origins[origin] = entry
        return entry

    for edge in payload.get("edges") or []:
        edge_type = str(edge.get("type") or "")
        if not edge_type:
            continue
        relationship_counts[edge_type] += 1
        source = edge.get("source") or {}
        target = edge.get("target") or {}
        source_kind = str(source.get("kind") or "")
        source_value = str(source.get("value") or "")
        target_kind = str(target.get("kind") or "")
        target_value = str(target.get("value") or "")

        if source_kind == "host":
            add_browser_edge(hosts, source_value, edge_type, target_kind, target_value)
        if target_kind == "host":
            add_browser_edge(hosts, target_value, f"incoming-{edge_type}", source_kind, source_value)
        if source_kind == "origin":
            origin_entry(source_value)["outgoing"][edge_type].add(f"{target_kind}:{target_value}")
        if target_kind == "origin":
            origin_entry(target_value)["incoming"][edge_type].add(f"{source_kind}:{source_value}")

    return origins, payload, relationship_counts


def render_host_note(host: dict) -> str:
    lines = [f"# {host['host']}", ""]
    roles = sorted(host["roles"])
    if roles:
        lines.extend(["## Roles", "", ", ".join(roles), ""])
    if host["status_codes"] or host["titles"]:
        lines.extend(["## HTTP", ""])
        if host["status_codes"]:
            lines.append(f"- Statuses: {', '.join(sorted(host['status_codes']))}")
        if host["titles"]:
            lines.append(f"- Titles: {' | '.join(sorted(host['titles'])[:5])}")
        lines.append("")
    if host["tech"]:
        lines.extend(["## Technologies", ""])
        for tech in sorted(host["tech"]):
            lines.append(f"- {note_link('tech', slug(tech))}")
        lines.append("")
    if host["ips"] or host["cnames"] or host["ports"]:
        lines.extend(["## Infrastructure", ""])
        if host["ips"]:
            lines.append(f"- IPs: {', '.join(sorted(host['ips']))}")
        if host["cnames"]:
            lines.append(f"- CNAMEs: {', '.join(sorted(host['cnames'])[:8])}")
        if host["ports"]:
            lines.append(f"- Open Ports: {', '.join(sorted(host['ports']))}")
        lines.append("")
    if host["findings"]:
        lines.extend(["## Findings", ""])
        for finding in sorted(host["findings"]):
            lines.append(f"- {note_link('findings', finding)}")
        lines.append("")
    if host["connections"]:
        lines.extend(["## Recon Connections", ""])
        for kind in sorted(host["connections"]):
            targets = sorted(host["connections"][kind])
            if not targets:
                continue
            lines.append(f"### {kind.replace('_', ' ').title()}")
            lines.append("")
            for target in targets[:25]:
                lines.append(f"- {note_link('hosts', slug(target))}")
            lines.append("")
    if host["browser_edges"]:
        lines.extend(["## Browser Relationships", ""])
        for kind in sorted(host["browser_edges"]):
            targets = sorted(host["browser_edges"][kind])
            if not targets:
                continue
            lines.append(f"### {kind.replace('_', ' ').title()}")
            lines.append("")
            for target in targets[:25]:
                lines.append(f"- {format_target(target)}")
            lines.append("")
    if host["api_routes"]:
        lines.extend(["## Runtime API Routes", ""])
        for url in sorted(host["api_routes"])[:25]:
            lines.append(f"- `{url}`")
        lines.append("")
    endpoints = sorted(host["urls"])
    if endpoints:
        lines.extend(["## Endpoints", ""])
        for url in endpoints[:25]:
            lines.append(f"- `{url}`")
        lines.append("")
    return "\n".join(lines)


def render_tech_note(tech: str, hosts: dict[str, dict]) -> str:
    consumers = sorted(host["host"] for host in hosts.values() if tech in host["tech"])
    lines = [f"# {tech}", "", "## Hosts", ""]
    for host_name in consumers:
        lines.append(f"- {note_link('hosts', slug(host_name))}")
    lines.append("")
    return "\n".join(lines)


def render_finding_note(name: str, hits: list[str]) -> str:
    severity = "medium"
    if name in {"xss", "sqli", "ssrf", "lfi"}:
        severity = "high"
    elif name == "debug":
        severity = "low"
    lines = [f"# {name}", "", f"Severity: {severity}", "", "## Matches", ""]
    for hit in hits[:200]:
        lines.append(f"- `{hit}`")
    lines.append("")
    return "\n".join(lines)


def render_origin_note(origin: dict) -> str:
    lines = [f"# {origin['origin']}", ""]
    if origin["host"]:
        lines.extend(["## Host", "", f"- {note_link('hosts', slug(origin['host']))}", ""])
    if origin["incoming"]:
        lines.extend(["## Incoming", ""])
        for kind in sorted(origin["incoming"]):
            lines.append(f"### {kind.replace('_', ' ').title()}")
            lines.append("")
            for target in sorted(origin["incoming"][kind])[:25]:
                lines.append(f"- {format_target(target)}")
            lines.append("")
    if origin["outgoing"]:
        lines.extend(["## Outgoing", ""])
        for kind in sorted(origin["outgoing"]):
            lines.append(f"### {kind.replace('_', ' ').title()}")
            lines.append("")
            for target in sorted(origin["outgoing"][kind])[:25]:
                lines.append(f"- {format_target(target)}")
            lines.append("")
    return "\n".join(lines)


def render_browser_relationships(payload: dict, relationship_counts: dict[str, int]) -> str:
    meta = payload.get("meta") or {}
    collector = meta.get("collector") or {}
    lines = [
        "# Browser Relationships",
        "",
        f"Generated: {meta.get('generated_at', datetime.now(timezone.utc).isoformat())}",
        "",
        f"- Collector: `{collector.get('name', 'chrome-devtools-mcp')}`",
        f"- Status: `{collector.get('status', 'unknown')}`",
    ]
    if collector.get("reason"):
        lines.append(f"- Note: {collector['reason']}")
    lines.extend(["", "## Edge Counts", ""])
    for edge_type in sorted(relationship_counts):
        lines.append(f"- `{edge_type}`: {relationship_counts[edge_type]}")
    lines.extend(["", "## Captures", ""])
    for capture in payload.get("captures") or []:
        url = capture.get("page_url") or capture.get("capture_file")
        lines.append(f"- `{url}`")
    lines.append("")
    return "\n".join(lines)


def render_browser_captures(payload: dict) -> str:
    lines = ["# Browser Captures", "", "## Pages", ""]
    for capture in payload.get("captures") or []:
        frames = capture.get("frames")
        if frames is None:
            frames = capture.get("frame_count", 0)
        lines.append(
            f"- `{capture.get('page_url', capture.get('capture_file', 'unknown'))}`"
            f" | requests={capture.get('network_requests', 0)}"
            f" runtime={capture.get('runtime_requests', 0)}"
            f" cookies={capture.get('cookies', 0)}"
            f" forms={capture.get('forms', 0)}"
            f" frames={frames}"
        )
    lines.append("")
    return "\n".join(lines)


def render_browser_security_review(base: Path) -> str | None:
    review_path = base / "browser-security-review.md"
    if not review_path.exists():
        return None
    return review_path.read_text().rstrip() + "\n"


def render_index(target: str, hosts: dict[str, dict], techs: set[str], interesting: dict[str, list[str]], url_count: int, origins: dict[str, dict], browser_payload: dict, relationship_counts: dict[str, int]) -> str:
    lines = [
        f"# Recon Vault Index: {target}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Counts",
        "",
        f"- Hosts: {len(hosts)}",
        f"- Technologies: {len(techs)}",
        f"- Finding Notes: {len([k for k, v in interesting.items() if v])}",
        f"- URLs: {url_count}",
        f"- Origins: {len(origins)}",
        f"- Browser Edges: {sum(relationship_counts.values())}",
        "",
        "## Hosts",
        "",
    ]
    for host_name in sorted(hosts):
        lines.append(f"- {note_link('hosts', slug(host_name))}")
    lines.extend(["", "## Technologies", ""])
    for tech in sorted(techs):
        lines.append(f"- {note_link('tech', slug(tech))}")
    lines.extend(["", "## Findings", ""])
    for finding, hits in sorted(interesting.items()):
        if hits:
            lines.append(f"- {note_link('findings', finding)}")
    if origins:
        lines.extend(["", "## Origins", ""])
        for origin in sorted(origins):
            lines.append(f"- {note_link('origins', slug(origin))}")
    if browser_payload:
        lines.extend(["", "## Browser Notes", ""])
        lines.append(f"- {note_link('browser', 'relationships')}")
        lines.append(f"- {note_link('browser', 'captures')}")
        lines.append(f"- {note_link('browser', 'security-review')}")
    lines.append("")
    return "\n".join(lines)


def notesmd_create(vault: str, note: str, content: str) -> None:
    subprocess.run(
        ["notesmd-cli", "create", note, "--vault", vault, "--content", content, "--overwrite"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an Obsidian-style mapping vault from recon output.")
    parser.add_argument("target", help="Recon target folder name, e.g. example.com")
    parser.add_argument("--recon-root", default="results", help="Root directory containing target recon outputs")
    parser.add_argument("--vault-dir", help="Directory to write the vault into. Defaults to results/<target>/vault")
    parser.add_argument("--vault-name", help="Optional notesmd-cli vault name to mirror notes into")
    args = parser.parse_args()

    base = Path(args.recon_root) / args.target
    if not base.exists():
        raise SystemExit(f"recon target directory not found: {base}")

    vault_dir = Path(args.vault_dir) if args.vault_dir else base / "vault"
    ensure_dir(vault_dir / "hosts")
    ensure_dir(vault_dir / "tech")
    ensure_dir(vault_dir / "findings")
    ensure_dir(vault_dir / "origins")
    ensure_dir(vault_dir / "browser")

    hosts, techs, interesting = build_host_model(base)
    origins, browser_payload, relationship_counts = build_browser_model(base, hosts)
    url_count = len(load_lines(base / "urls.txt"))

    for host_name, host in sorted(hosts.items()):
        content = render_host_note(host)
        note_name = slug(host_name)
        write_file(vault_dir / "hosts" / f"{note_name}.md", content)
        if args.vault_name:
            notesmd_create(args.vault_name, f"hosts/{note_name}", content)

    for tech in sorted(techs):
        content = render_tech_note(tech, hosts)
        note_name = slug(tech)
        write_file(vault_dir / "tech" / f"{note_name}.md", content)
        if args.vault_name:
            notesmd_create(args.vault_name, f"tech/{note_name}", content)

    for finding, hits in sorted(interesting.items()):
        if not hits:
            continue
        content = render_finding_note(finding, hits)
        write_file(vault_dir / "findings" / f"{finding}.md", content)
        if args.vault_name:
            notesmd_create(args.vault_name, f"findings/{finding}", content)

    for origin_name, origin in sorted(origins.items()):
        content = render_origin_note(origin)
        note_name = slug(origin_name)
        write_file(vault_dir / "origins" / f"{note_name}.md", content)
        if args.vault_name:
            notesmd_create(args.vault_name, f"origins/{note_name}", content)

    if browser_payload:
        relationships_note = render_browser_relationships(browser_payload, relationship_counts)
        captures_note = render_browser_captures(browser_payload)
        write_file(vault_dir / "browser" / "relationships.md", relationships_note)
        write_file(vault_dir / "browser" / "captures.md", captures_note)
        if args.vault_name:
            notesmd_create(args.vault_name, "browser/relationships", relationships_note)
            notesmd_create(args.vault_name, "browser/captures", captures_note)
    security_review = render_browser_security_review(base)
    if security_review:
        write_file(vault_dir / "browser" / "security-review.md", security_review)
        if args.vault_name:
            notesmd_create(args.vault_name, "browser/security-review", security_review)

    index = render_index(args.target, hosts, techs, interesting, url_count, origins, browser_payload, relationship_counts)
    write_file(vault_dir / "_index.md", index)
    if args.vault_name:
        notesmd_create(args.vault_name, "_index", index)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

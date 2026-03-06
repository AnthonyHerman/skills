#!/usr/bin/env python3

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


APP_HINTS = ("app", "portal", "dashboard", "admin", "auth", "login", "graphql", "api", "gateway")
LOW_VALUE_HINTS = ("static", "cdn", "img", "images", "fonts", "assets", "media")
API_ROUTE_HINTS = ("/api", "/graphql", "/rest/", "/v1/", "/v2/", "/v3/")
RUNTIME_TYPES = {"xhr", "fetch", "websocket", "eventsource"}
RESOURCE_TYPES = {"script", "image", "font", "stylesheet", "iframe", "frame", "media"}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    value = value.replace("://", "-").replace(":", "-").replace("/", "-")
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return value.strip("-")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
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


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_text(path: Path, lines: list[str]) -> None:
    uniq = sorted({line for line in lines if line})
    path.write_text("\n".join(uniq) + ("\n" if uniq else ""))


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


def normalize_headers(headers) -> dict[str, str]:
    if not headers:
        return {}
    if isinstance(headers, dict):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    if isinstance(headers, list):
        normalized = {}
        for item in headers:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if name is None or value is None:
                continue
            normalized[str(name).lower()] = str(value)
        return normalized
    return {}


def header_value(headers: dict[str, str], name: str) -> str:
    return headers.get(name.lower(), "").strip()


def looks_like_api(url: str, resource_type: str, headers: dict[str, str]) -> bool:
    lowered = url.lower()
    if resource_type in RUNTIME_TYPES:
        return True
    if any(hint in lowered for hint in API_ROUTE_HINTS):
        return True
    content_type = header_value(headers, "content-type").lower()
    return "json" in content_type or "graphql" in content_type


def looks_like_graphql(url: str, headers: dict[str, str], body) -> bool:
    lowered = url.lower()
    if "graphql" in lowered:
        return True
    content_type = header_value(headers, "content-type").lower()
    if "graphql" in content_type:
        return True
    if isinstance(body, str) and ("query" in body or "mutation" in body):
        return True
    return False


def raw_capture_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(path for path in raw_dir.glob("*.json") if path.is_file())


def score_browser_target(record: dict, live_host: str) -> int:
    score = 0
    url = str(record.get("url") or live_host)
    host = host_from_url(url)
    title = str(record.get("title") or "").lower()
    status = int(record.get("status_code") or 0)
    tech = [str(item).lower() for item in (record.get("tech") or [])]
    if status in {200, 201, 204, 401, 403}:
        score += 5
    if any(token in host for token in APP_HINTS):
        score += 6
    if any(token in title for token in ("login", "sign in", "dashboard", "portal", "admin")):
        score += 4
    if any(token in tech for token in ("graphql", "next.js", "react", "vue", "angular")):
        score += 2
    if any(token in host for token in LOW_VALUE_HINTS):
        score -= 4
    if "/api" in url.lower():
        score -= 2
    return score


def select_browser_targets(base: Path, limit: int) -> list[str]:
    live_hosts = load_lines(base / "live-hosts.txt")
    httpx_records = load_jsonl(base / "httpx-output.json")
    by_url = {str(record.get("url")): record for record in httpx_records if record.get("url")}
    scored = []
    seen = set()
    for host in live_hosts:
        record = by_url.get(host, {})
        score = score_browser_target(record, host)
        scored.append((score, host))
        seen.add(host)
    for record in httpx_records:
        url = str(record.get("url") or "").strip()
        if not url or url in seen:
            continue
        scored.append((score_browser_target(record, url), url))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:limit]]


def edge_key(edge_type: str, source_kind: str, source_value: str, target_kind: str, target_value: str) -> tuple[str, str, str, str, str]:
    return (edge_type, source_kind, source_value, target_kind, target_value)


def add_edge(edge_map: dict, edge_type: str, source_kind: str, source_value: str, target_kind: str, target_value: str, evidence: dict) -> None:
    if not source_value or not target_value:
        return
    key = edge_key(edge_type, source_kind, source_value, target_kind, target_value)
    existing = edge_map.setdefault(
        key,
        {
            "type": edge_type,
            "source": {"kind": source_kind, "value": source_value},
            "target": {"kind": target_kind, "value": target_value},
            "evidence": [],
        },
    )
    if evidence and len(existing["evidence"]) < 10:
        existing["evidence"].append(evidence)


def cookie_scope(domain: str, path: str) -> str:
    return f"{domain or ''}{path or '/'}"


def normalize_capture(path: Path) -> dict:
    raw = load_json(path) or {}
    page = raw.get("page") or {}
    target_url = str(raw.get("final_url") or raw.get("page_url") or page.get("url") or raw.get("target_url") or "")
    page_host = host_from_url(target_url)
    page_origin = origin_from_url(target_url)
    network_requests = raw.get("network_requests") or raw.get("networkRequests") or []
    cookies = raw.get("cookies") or page.get("cookies") or []
    forms = raw.get("forms") or page.get("forms") or []
    frames = raw.get("frames") or page.get("frames") or []
    resources = raw.get("resources") or page.get("resources") or []
    return {
        "capture_file": path.name,
        "target_url": target_url,
        "page_host": page_host,
        "page_origin": page_origin,
        "network_requests": network_requests,
        "cookies": cookies,
        "forms": forms,
        "frames": frames,
        "resources": resources,
        "page_title": str(page.get("title") or raw.get("title") or ""),
    }


def ensure_report_section(report_path: Path, section_title: str, section_body: str) -> None:
    heading = f"## {section_title}"
    content = report_path.read_text() if report_path.exists() else "# Recon Report\n\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(section_title)}\n.*?(?=^## |\Z)")
    replacement = f"{heading}\n{section_body.strip()}\n"
    if pattern.search(content):
        updated = pattern.sub(replacement, content).rstrip() + "\n"
    else:
        updated = content.rstrip() + "\n\n" + replacement
    report_path.write_text(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize browser/runtime relationship captures under results/<target>/ using Chrome DevTools MCP-derived data.")
    parser.add_argument("target", help="Recon target folder name, e.g. example.com")
    parser.add_argument("--recon-root", default="results", help="Root directory containing target recon outputs")
    parser.add_argument("--raw-dir", help="Directory containing per-page browser capture JSON files")
    parser.add_argument("--max-hosts", type=int, default=10, help="How many live hosts to prioritize for browser mapping")
    parser.add_argument("--collector-status", choices=["captured", "partial", "skipped", "unavailable"], help="Override collector status in output metadata")
    parser.add_argument("--collector-reason", help="Reason to record when capture data is partial or unavailable")
    args = parser.parse_args()

    base = Path(args.recon_root) / args.target
    if not base.exists():
        raise SystemExit(f"recon target directory not found: {base}")

    raw_dir = Path(args.raw_dir) if args.raw_dir else base / "browser" / "raw"
    ensure_dir(raw_dir)

    selected_targets = select_browser_targets(base, max(args.max_hosts, 1))
    write_text(base / "browser-targets.txt", selected_targets)

    origins = set()
    forms_out = set()
    api_routes = set()
    network_out = []
    cookies_out = []
    frames_out = []
    cors_out = []
    edge_map: dict[tuple[str, str, str, str, str], dict] = {}
    capture_summaries = []
    nodes = {"host": set(), "origin": set(), "cookie-scope": set()}

    files = raw_capture_files(raw_dir)
    for capture_path in files:
        capture = normalize_capture(capture_path)
        page_host = capture["page_host"]
        page_origin = capture["page_origin"]
        if page_host:
            nodes["host"].add(page_host)
        if page_origin:
            origins.add(page_origin)
            nodes["origin"].add(page_origin)

        forms_count = 0
        frame_count = 0
        runtime_count = 0

        for form in capture["forms"]:
            if not isinstance(form, dict):
                continue
            action = str(form.get("action") or capture["target_url"] or "").strip()
            if not action:
                continue
            method = str(form.get("method") or "GET").upper()
            form_record = {
                "capture_file": capture["capture_file"],
                "page_url": capture["target_url"],
                "page_host": page_host,
                "action": action,
                "action_host": host_from_url(action),
                "action_origin": origin_from_url(action),
                "method": method,
            }
            forms_out.add(f"{method} {action}")
            forms_count += 1
            if form_record["action_origin"]:
                origins.add(form_record["action_origin"])
                nodes["origin"].add(form_record["action_origin"])
            add_edge(
                edge_map,
                "posts-form-to",
                "host",
                page_host,
                "origin",
                form_record["action_origin"] or form_record["action_host"],
                {"page_url": capture["target_url"], "method": method, "action": action},
            )

        for frame in capture["frames"]:
            if not isinstance(frame, dict):
                continue
            frame_url = str(frame.get("url") or "")
            if not frame_url:
                continue
            parent_url = str(frame.get("parent_url") or capture["target_url"] or "")
            frame_record = {
                "capture_file": capture["capture_file"],
                "page_url": capture["target_url"],
                "page_host": page_host,
                "frame_url": frame_url,
                "frame_host": host_from_url(frame_url),
                "frame_origin": origin_from_url(frame_url),
                "parent_url": parent_url,
                "parent_host": host_from_url(parent_url) or page_host,
                "parent_origin": origin_from_url(parent_url) or page_origin,
            }
            frames_out.append(frame_record)
            frame_count += 1
            if frame_record["frame_origin"]:
                origins.add(frame_record["frame_origin"])
                nodes["origin"].add(frame_record["frame_origin"])
            if frame_record["frame_host"]:
                nodes["host"].add(frame_record["frame_host"])
            add_edge(
                edge_map,
                "embeds",
                "host",
                frame_record["parent_host"],
                "origin",
                frame_record["frame_origin"] or frame_record["frame_host"],
                {"page_url": capture["target_url"], "frame_url": frame_url},
            )
            add_edge(
                edge_map,
                "embedded-by",
                "origin",
                frame_record["frame_origin"] or frame_record["frame_host"],
                "host",
                frame_record["parent_host"],
                {"page_url": capture["target_url"], "frame_url": frame_url},
            )

        for resource in capture["resources"]:
            if not isinstance(resource, dict):
                continue
            resource_url = str(resource.get("url") or "")
            if not resource_url:
                continue
            resource_type = str(resource.get("type") or resource.get("resource_type") or "").lower()
            resource_origin = origin_from_url(resource_url)
            if resource_origin:
                origins.add(resource_origin)
                nodes["origin"].add(resource_origin)
            if resource_type in RESOURCE_TYPES:
                add_edge(
                    edge_map,
                    "loads-from",
                    "host",
                    page_host,
                    "origin",
                    resource_origin or host_from_url(resource_url),
                    {"page_url": capture["target_url"], "resource_url": resource_url, "resource_type": resource_type},
                )

        for item in capture["network_requests"]:
            if not isinstance(item, dict):
                continue
            request_url = str(item.get("url") or item.get("request_url") or "")
            if not request_url:
                continue
            response_headers = normalize_headers(item.get("response_headers") or item.get("responseHeaders"))
            request_headers = normalize_headers(item.get("request_headers") or item.get("requestHeaders"))
            resource_type = str(item.get("resource_type") or item.get("type") or "").lower()
            request_record = {
                "capture_file": capture["capture_file"],
                "page_url": capture["target_url"],
                "page_host": page_host,
                "page_origin": page_origin,
                "request_url": request_url,
                "request_host": host_from_url(request_url),
                "request_origin": origin_from_url(request_url),
                "method": str(item.get("method") or "GET").upper(),
                "resource_type": resource_type,
                "status": item.get("status"),
                "initiator_url": str(item.get("initiator_url") or item.get("document_url") or ""),
                "request_headers": request_headers,
                "response_headers": response_headers,
                "is_graphql": looks_like_graphql(request_url, request_headers, item.get("post_data") or item.get("body")),
                "is_websocket": resource_type == "websocket" or request_url.lower().startswith(("ws://", "wss://")),
            }
            network_out.append(request_record)
            if request_record["request_origin"]:
                origins.add(request_record["request_origin"])
                nodes["origin"].add(request_record["request_origin"])
            if request_record["request_host"]:
                nodes["host"].add(request_record["request_host"])

            if looks_like_api(request_url, resource_type, response_headers):
                api_routes.add(request_url)
            if request_record["is_graphql"] and request_url:
                api_routes.add(request_url)

            if resource_type in RUNTIME_TYPES or request_record["is_graphql"]:
                runtime_count += 1
                add_edge(
                    edge_map,
                    "calls-api",
                    "host",
                    page_host,
                    "origin",
                    request_record["request_origin"] or request_record["request_host"],
                    {
                        "page_url": capture["target_url"],
                        "request_url": request_url,
                        "resource_type": resource_type,
                        "is_graphql": request_record["is_graphql"],
                        "is_websocket": request_record["is_websocket"],
                    },
                )
            elif resource_type in RESOURCE_TYPES:
                add_edge(
                    edge_map,
                    "loads-from",
                    "host",
                    page_host,
                    "origin",
                    request_record["request_origin"] or request_record["request_host"],
                    {"page_url": capture["target_url"], "request_url": request_url, "resource_type": resource_type},
                )

            acao = header_value(response_headers, "access-control-allow-origin")
            acac = header_value(response_headers, "access-control-allow-credentials").lower()
            if acao:
                cors_record = {
                    "capture_file": capture["capture_file"],
                    "page_url": capture["target_url"],
                    "responder_origin": request_record["request_origin"],
                    "request_url": request_url,
                    "allowed_origin": acao,
                    "allows_credentials": acac == "true",
                }
                cors_out.append(cors_record)
                add_edge(
                    edge_map,
                    "allows-origin",
                    "origin",
                    request_record["request_origin"] or request_record["request_host"],
                    "origin",
                    acao,
                    {"request_url": request_url, "page_url": capture["target_url"]},
                )
                if acac == "true" and acao:
                    add_edge(
                        edge_map,
                        "allows-credentials-for",
                        "origin",
                        request_record["request_origin"] or request_record["request_host"],
                        "origin",
                        acao,
                        {"request_url": request_url, "page_url": capture["target_url"]},
                    )

            csp = header_value(response_headers, "content-security-policy")
            xfo = header_value(response_headers, "x-frame-options")
            if csp or xfo:
                add_edge(
                    edge_map,
                    "embedded-by",
                    "origin",
                    request_record["request_origin"] or request_record["request_host"],
                    "origin",
                    page_origin,
                    {
                        "request_url": request_url,
                        "content_security_policy": csp,
                        "x_frame_options": xfo,
                    },
                )

            redirects = item.get("redirect_chain") or item.get("redirects") or []
            if isinstance(redirects, list):
                prior = request_url
                for redirect in redirects:
                    target = ""
                    if isinstance(redirect, dict):
                        target = str(redirect.get("url") or redirect.get("location") or "")
                    elif isinstance(redirect, str):
                        target = redirect
                    if not target:
                        continue
                    add_edge(
                        edge_map,
                        "redirects-to",
                        "origin",
                        origin_from_url(prior) or host_from_url(prior),
                        "origin",
                        origin_from_url(target) or host_from_url(target),
                        {"from_url": prior, "to_url": target, "page_url": capture["target_url"]},
                    )
                    prior = target

        for cookie in capture["cookies"]:
            if not isinstance(cookie, dict):
                continue
            domain = str(cookie.get("domain") or "").lower()
            path = str(cookie.get("path") or "/")
            scope = cookie_scope(domain, path)
            cookie_record = {
                "capture_file": capture["capture_file"],
                "page_url": capture["target_url"],
                "page_host": page_host,
                "name": str(cookie.get("name") or ""),
                "domain": domain,
                "path": path,
                "secure": bool(cookie.get("secure")),
                "http_only": bool(cookie.get("httpOnly") or cookie.get("http_only")),
                "same_site": str(cookie.get("sameSite") or cookie.get("same_site") or ""),
                "expires": cookie.get("expires"),
                "source_scheme": str(cookie.get("sourceScheme") or ""),
            }
            cookies_out.append(cookie_record)
            if scope:
                nodes["cookie-scope"].add(scope)
            add_edge(
                edge_map,
                "sets-cookie-for",
                "host",
                page_host,
                "cookie-scope",
                scope,
                {
                    "page_url": capture["target_url"],
                    "cookie_name": cookie_record["name"],
                    "secure": cookie_record["secure"],
                    "http_only": cookie_record["http_only"],
                    "same_site": cookie_record["same_site"],
                },
            )

        capture_summaries.append(
            {
                "capture_file": capture["capture_file"],
                "page_url": capture["target_url"],
                "page_host": page_host,
                "page_origin": page_origin,
                "page_title": capture["page_title"],
                "network_requests": len(capture["network_requests"]),
                "runtime_requests": runtime_count,
                "cookies": len(capture["cookies"]),
                "forms": forms_count,
                "frames": frame_count,
            }
        )

    observed_hosts = sorted(nodes["host"])
    scoped_hosts = defaultdict(set)
    for cookie in cookies_out:
        domain = cookie["domain"].lstrip(".")
        if not domain:
            continue
        for host in observed_hosts:
            if host == domain or host.endswith(f".{domain}"):
                scoped_hosts[cookie_scope(cookie["domain"], cookie["path"])].add(host)
    for scope, members in scoped_hosts.items():
        members = sorted(members)
        for index, source_host in enumerate(members):
            for target_host in members[index + 1 :]:
                add_edge(
                    edge_map,
                    "shares-session-scope-with",
                    "host",
                    source_host,
                    "host",
                    target_host,
                    {"cookie_scope": scope},
                )
                add_edge(
                    edge_map,
                    "shares-session-scope-with",
                    "host",
                    target_host,
                    "host",
                    source_host,
                    {"cookie_scope": scope},
                )

    status = args.collector_status or ("captured" if files else "skipped")
    reason = args.collector_reason or ("No raw browser capture files were found" if not files else "")
    meta = {
        "generated_at": iso_now(),
        "target": args.target,
        "selected_targets_file": "browser-targets.txt",
        "raw_capture_dir": str(raw_dir),
        "capture_count": len(files),
        "collector": {
            "name": "chrome-devtools-mcp",
            "status": status,
            "reason": reason,
        },
    }

    relationship_payload = {
        "meta": meta,
        "captures": capture_summaries,
        "nodes": {kind: sorted(values) for kind, values in nodes.items()},
        "edges": sorted(edge_map.values(), key=lambda item: (item["type"], item["source"]["value"], item["target"]["value"])),
    }
    write_json(base / "browser-relationships.json", relationship_payload)
    write_json(base / "network-requests.json", {"meta": meta, "items": network_out})
    write_json(base / "cookies.json", {"meta": meta, "items": cookies_out})
    write_json(base / "frames.json", {"meta": meta, "items": frames_out})
    write_json(base / "cors-results.json", {"meta": meta, "items": cors_out})
    write_text(base / "api-routes.txt", sorted(api_routes))

    if forms_out:
        write_text(base / "forms.txt", sorted(forms_out))
    if origins:
        write_text(base / "origins.txt", sorted(origins))

    report_lines = [
        "",
        f"- Collector: `{meta['collector']['name']}`",
        f"- Status: `{status}`",
        f"- Selected browser targets: `{len(selected_targets)}`",
        f"- Captures normalized: `{len(files)}`",
        f"- Runtime/API requests: `{len([item for item in network_out if item['resource_type'] in RUNTIME_TYPES or item['is_graphql']])}`",
        f"- Cookie records: `{len(cookies_out)}`",
        f"- Frame records: `{len(frames_out)}`",
        f"- Relationship edges: `{len(relationship_payload['edges'])}`",
    ]
    if reason:
        report_lines.append(f"- Note: {reason}")
    ensure_report_section(base / "report.md", "Browser Relationship Mapping", "\n".join(report_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

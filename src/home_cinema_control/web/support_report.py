from __future__ import annotations

import json
import re
from dataclasses import dataclass

_IPV4_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
_MIN_REDACTION_LENGTH = 4

DEFAULT_LOG_LINES = 200
MIN_LOG_LINES = 20
MAX_LOG_LINES = 1000


@dataclass(frozen=True)
class DiagnosticReport:
    report: str
    redaction_count: int
    log_lines_included: int


def clamp_log_lines(requested: int | None) -> int:
    if requested is None:
        return DEFAULT_LOG_LINES
    return max(MIN_LOG_LINES, min(MAX_LOG_LINES, requested))


def collect_redaction_targets(config: dict) -> dict[str, str]:
    """Harvest real (secret-merged) values from config that must never reach
    a public GitHub issue: device IPs/MACs, credentials, and filesystem paths
    that can reveal a user's personal folder structure.
    """
    targets: dict[str, str] = {}

    def add(value: object, category: str) -> None:
        text = str(value or "").strip()
        if len(text) >= _MIN_REDACTION_LENGTH:
            targets[text] = category

    add(config.get("oppo", {}).get("ip"), "IP")
    add(config.get("av", {}).get("ip"), "IP")
    add(config.get("tv", {}).get("ip"), "IP")
    add(config.get("tv", {}).get("mac"), "MAC")
    add(config.get("av", {}).get("trinnov_mac"), "MAC")

    add(config.get("smb", {}).get("username"), "CREDENTIAL")
    add(config.get("smb", {}).get("password"), "CREDENTIAL")
    add(config.get("tv", {}).get("sony_psk"), "CREDENTIAL")
    add(config.get("lighting", {}).get("home_assistant_token"), "CREDENTIAL")

    add(config.get("app", {}).get("update_webhook_url"), "URL")
    add(config.get("lighting", {}).get("home_assistant_url"), "URL")

    providers = config.get("media_servers", {}).get("providers", {}) or {}
    for provider in providers.values():
        add(provider.get("server_url"), "URL")
        add(provider.get("access_token"), "CREDENTIAL")
        add(provider.get("user_id"), "CREDENTIAL")
        path_mappings = provider.get("playback", {}).get("path_mappings", []) or []
        for mapping in path_mappings:
            add(mapping.get("source_path"), "PATH")
            add(mapping.get("player_path"), "PATH")

    return targets


def redact_text(text: str, targets: dict[str, str]) -> tuple[str, int]:
    """Replace every known sensitive value with a `[REDACTED:CATEGORY]` token,
    longest value first so a full URL is redacted as one token before its
    embedded IP could independently match and fragment it. A regex safety
    net then catches bare IPv4 addresses not present in config (e.g. other
    LAN devices mentioned in an error message).
    """
    count = 0

    for value in sorted(targets, key=len, reverse=True):
        occurrences = text.count(value)
        if occurrences:
            text = text.replace(value, f"[REDACTED:{targets[value]}]")
            count += occurrences

    def _replace_ip(match: re.Match) -> str:
        nonlocal count
        count += 1
        return "[REDACTED:IP]"

    text = _IPV4_PATTERN.sub(_replace_ip, text)

    return text, count


def _render_log_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    try:
        record = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return line
    return f"{record.get('timestamp', '')} {record.get('level', '')} {record.get('logger', '')}: {record.get('message', '')}"


def build_redacted_log(
    raw_log_text: str, targets: dict[str, str], *, max_lines: int
) -> tuple[str, int, int]:
    lines = [line for line in raw_log_text.splitlines() if line.strip()]
    selected = lines[-max_lines:]
    rendered = "\n".join(_render_log_line(line) for line in selected)
    redacted, count = redact_text(rendered, targets)
    return redacted, count, len(selected)


def build_diagnostic_report(
    *,
    config: dict,
    sanitized_summary: dict,
    raw_log_text: str,
    max_lines: int,
) -> DiagnosticReport:
    targets = collect_redaction_targets(config)

    summary_json = json.dumps(sanitized_summary, indent=2, ensure_ascii=False, default=str)
    redacted_summary, summary_count = redact_text(summary_json, targets)

    redacted_log, log_count, log_lines_included = build_redacted_log(
        raw_log_text, targets, max_lines=max_lines
    )

    report = (
        "## Support summary (sanitized)\n"
        "```json\n"
        f"{redacted_summary}\n"
        "```\n\n"
        f"## Recent log (last {log_lines_included} lines, redacted)\n"
        "```\n"
        f"{redacted_log}\n"
        "```"
    )

    return DiagnosticReport(
        report=report,
        redaction_count=summary_count + log_count,
        log_lines_included=log_lines_included,
    )

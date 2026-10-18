"""Validate review-only market research bundles, without network or CRM access."""
from __future__ import annotations

import ipaddress
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit


ALLOWED_PRODUCTS = {"odoo", "blue_ai_fabric", "blueconnect", "blue_voice", "blue_interop"}
MIN_CONFIDENCE = 0.70
MAX_EVIDENCE_AGE_DAYS = 180
REJECT_KEYS = {"email", "phone", "telefone", "whatsapp", "cpf", "contact", "recipient", "send_to", "message", "raw_html"}
ALLOWED_ROOT = {"schema_version", "company_id", "correlation_id", "records"}
ALLOWED_RECORD = {
    "external_ref", "company_name", "icp_vertical", "confidence",
    "enrichment_state", "source", "observed_at", "evidence",
    "proposed_products", "requires_human_approval", "can_send", "can_write_odoo",
}
ALLOWED_EVIDENCE = {"url", "source_type", "observed_at"}


def is_public_https_syntax(url: object) -> bool:
    """Reject suspicious URL text. Does NOT validate DNS, redirect or SSRF."""
    if not isinstance(url, str) or len(url) > 600:
        return False
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme != "https" or not host or not p.netloc:
            return False
        if p.username or p.password or p.port not in (None, 443):
            return False
        if "%" in p.netloc or re.search(r"[\\x00-\\x1f\\x7f]", url):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        if "." not in host or ".." in host or host in {"localhost", "metadata.google.internal"}:
            return False
        if host.endswith((".internal", ".local", ".localhost", ".onion", ".test")):
            return False
        return bool(re.fullmatch(r"[a-z0-9.-]+", host))
    except (ValueError, TypeError):
        return False


def recent_iso(day: object, today: date) -> bool:
    if not isinstance(day, str):
        return False
    try:
        when = date.fromisoformat(day)
    except ValueError:
        return False
    return today - timedelta(days=MAX_EVIDENCE_AGE_DAYS) <= when <= today


def scan_disallowed_keys(payload: object) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in REJECT_KEYS or scan_disallowed_keys(value):
                return True
    elif isinstance(payload, list):
        return any(scan_disallowed_keys(x) for x in payload)
    return False


def validate_report(report: object, *, today: date | None = None) -> list[str]:
    now = today or date.today()
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report:expected_object"]
    if scan_disallowed_keys(report):
        errors.append("report:personal_contact_fields_forbidden")
    if set(report) != ALLOWED_ROOT or report.get("schema_version") != "blue-market-scout-v1":
        errors.append("report:invalid_schema")
    company_id = report.get("company_id")
    if isinstance(company_id, bool) or not isinstance(company_id, int) or company_id <= 0:
        errors.append("report:invalid_company_id")
    correlation_id = report.get("correlation_id")
    if not isinstance(correlation_id, str) or not re.fullmatch(r"[a-zA-Z0-9._:-]{6,120}", correlation_id):
        errors.append("report:invalid_correlation_id")
    records = report.get("records")
    if not isinstance(records, list) or len(records) == 0 or len(records) > 100:
        return errors + ["report:invalid_records"]
    seen: set[tuple[int, str]] = set()
    for index, row in enumerate(records):
        prefix = f"record[{index}]"
        if not isinstance(row, dict) or set(row) != ALLOWED_RECORD:
            errors.append(f"{prefix}:invalid_schema")
            continue
        if row["can_send"] is not False or row["can_write_odoo"] is not False or row["requires_human_approval"] is not True:
            errors.append(f"{prefix}:must_be_review_only")
        if row["source"] != "hermes_market_research" or row["enrichment_state"] != "validated":
            errors.append(f"{prefix}:not_verified_enrichment")
        if not isinstance(row["confidence"], (int, float)) or isinstance(row["confidence"], bool) or not MIN_CONFIDENCE <= row["confidence"] <= 1:
            errors.append(f"{prefix}:confidence")
        if not isinstance(row["company_name"], str) or not 4 <= len(row["company_name"]) <= 160:
            errors.append(f"{prefix}:company_name")
        if not isinstance(row["icp_vertical"], str) or not re.fullmatch(r"[a-z0-9_-]{3,60}", row["icp_vertical"]):
            errors.append(f"{prefix}:vertical")
        key = row["external_ref"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{4,100}", key):
            errors.append(f"{prefix}:external_ref")
        else:
            item = (company_id if isinstance(company_id, int) else -1, key)
            if item in seen:
                errors.append(f"{prefix}:duplicate_in_tenant")
            seen.add(item)
        if not recent_iso(row["observed_at"], now):
            errors.append(f"{prefix}:stale_signal")
        products = row["proposed_products"]
        if not isinstance(products, list) or len(products) > 5 or any(p not in ALLOWED_PRODUCTS for p in products):
            errors.append(f"{prefix}:products")
        ev = row["evidence"]
        if not isinstance(ev, list) or not 1 <= len(ev) <= 10:
            errors.append(f"{prefix}:evidence_missing")
            continue
        for j, e in enumerate(ev):
            if not isinstance(e, dict) or set(e) != ALLOWED_EVIDENCE:
                errors.append(f"{prefix}:evidence[{j}]:invalid_schema")
                continue
            if not is_public_https_syntax(e["url"]) or not recent_iso(e["observed_at"], now):
                errors.append(f"{prefix}:evidence[{j}]:invalid_url_or_age")
            if e["source_type"] not in {"company_website", "pncp_public", "public_news", "public_registry"}:
                errors.append(f"{prefix}:evidence[{j}]:unsupported_source")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "INVALID_ARGS"}))
        return 2
    try:
        obj = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        errors = validate_report(obj)
        print(json.dumps({
            "status": "REVIEW_ONLY" if not errors else "REJECTED",
            "count": len(obj.get("records", [])) if isinstance(obj, dict) and isinstance(obj.get("records"), list) else 0,
            "error_count": len(errors),
            "errors": errors,
            "can_send": False,
            "can_write_odoo": False,
            "validated_url_network_access": False,
        }))
        return 0 if not errors else 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "REJECTED", "errors": ["report:read_or_parse_failed"], "can_send": False, "can_write_odoo": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

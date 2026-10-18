"""Harvey ↔ Hermes ↔ Odoo Company 360: deterministic REVIEW-ONLY envelopes.

Offline only: no requests, model calls, SMTP, Odoo ORM, credentials or filesystem.
Inputs may be adversarial AI output; returned "verified_source" is ALWAYS false.
"""
from __future__ import annotations
import re
from typing import Any

CODE = re.compile(r"^[A-Za-z0-9_.:-]{6,120}$")
REF = re.compile(r"^[A-Za-z0-9_.:-]{4,100}$")
BANNED = {"email", "phone", "mobile", "cpf", "cnpj", "whatsapp",
          "recipient", "message", "send_to", "authorization", "password",
          "api_key", "token", "raw_html", "stakeholder_ids", "personal_name"}
PRODUCTS = {"odoo", "blue_ai_fabric", "blueconnect", "blue_voice", "blue_interop"}
ALLOWED_HARVEY = {"company_id", "correlation_id", "external_ref",
                  "company_name", "signal_url", "observed_at",
                  "confidence", "origin", "enrichment_state",
                  "verified_source", "can_send", "can_write_odoo"}
ALLOWED_REPORT = {"schema_version", "company_id", "correlation_id", "records"}
ALLOWED_RECORD = {"external_ref", "company_name", "icp_vertical", "confidence",
                  "enrichment_state", "source", "observed_at", "evidence",
                  "proposed_products", "requires_human_approval",
                  "can_send", "can_write_odoo"}
ALLOWED_EVIDENCE = {"url", "source_type", "observed_at"}


def _dict_keys(obj: Any, allowed: set[str]) -> None:
    if not isinstance(obj, dict) or not set(obj).issubset(allowed):
        raise ValueError("INVALID_OR_EXTRA_FIELDS")
    if BANNED.intersection(map(str.lower, obj)):
        raise ValueError("PERSONAL_FIELDS_PROHIBITED")


def _tenant(tenant: Any) -> int:
    if isinstance(tenant, bool) or not isinstance(tenant, int) or tenant <= 0:
        raise ValueError("INVALID_TENANT")
    return tenant


def _id(value: Any, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("INVALID_ID")
    return value


def _safe_public_url(value: Any) -> bool:
    # Syntax-only check; networking MUST use independently governed SSRF egress.
    from urllib.parse import urlsplit
    if not isinstance(value, str) or not 1 <= len(value) <= 600:
        return False
    try:
        p = urlsplit(value)
        host = p.hostname or ""
        if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
            return False
        if not host or "." not in host or "%" in p.netloc or "[" in p.netloc:
            return False
        if re.fullmatch(r"[\d.]+", host) or not re.fullmatch(r"[A-Za-z0-9.-]+", host):
            return False
        if host.endswith((".internal", ".local", ".localhost", ".test", ".onion")):
            return False
        return not any(ord(c) < 32 or ord(c) == 127 for c in value)
    except ValueError:
        return False


def harvey_company_to_research_request(
    harvey_company: dict[str, Any], *, odoo_company_id: int, correlation_id: str
) -> dict[str, Any]:
    """Adapt REAL upstream harvey.models.company.Company to a safe research-only request.

    Upstream Harvey's "company_id" is a SQLite TEXT foreign key, NOT an Odoo
    tenant ID. The Odoo owning tenant must be supplied separately by the
    authenticated orchestration layer. Company.phone/notes/description and
    contact/prospect CSV records are NEVER exported to this bridge.
    """
    import hashlib
    known = {
        "id", "name", "domain", "website", "description", "industry",
        "company_size", "location", "phone", "source", "source_url",
        "external_id", "notes", "tech_stack", "signals",
        "created_at", "updated_at",
    }
    if not isinstance(harvey_company, dict) or set(harvey_company) - known:
        raise ValueError("NOT_AN_UPSTREAM_HARVEY_COMPANY_RECORD")
    tenant = _tenant(odoo_company_id)
    correlation = _id(correlation_id, CODE)
    name = harvey_company.get("name")
    if not isinstance(name, str) or not 4 <= len(name) <= 160:
        raise ValueError("INVALID_COMPANY_NAME")
    url = harvey_company.get("source_url") or harvey_company.get("website")
    if not _safe_public_url(url):
        raise ValueError("UNSAFE_UPSTREAM_HARVEY_SOURCE_URL")
    basis = (
        harvey_company.get("external_id") or harvey_company.get("domain")
        or harvey_company.get("id")
    )
    if not isinstance(basis, str) or not 4 <= len(basis) <= 300:
        raise ValueError("MISSING_STABLE_HARVEY_IDENTITY")
    # Stable per-tenant provider identity. No name, phone or person data in ID.
    stable = hashlib.sha256((str(tenant) + ":" + basis).encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": "blue-harvey-hermes-request-v1",
        "direction": "harvey_to_hermes",
        "company_id": tenant,
        "correlation_id": correlation,
        "external_ref": "harvey-" + stable,
        "company_name": name,
        "evidence_url": url,
        "requested_operation": "research_public_company_only",
        "evidence_verified_for_dispatch": False,
        "source_verification_state": "UNVERIFIED_UPSTREAM_HARVEY_COMPANY",
        "requires_human_approval": True,
        "can_send": False,
        "can_write_odoo": False,
    }


def to_hermes_research_request(harvey: dict[str, Any]) -> dict[str, Any]:
    """A trusted n8n operator still has to authorize the *source* outside this code."""
    _dict_keys(harvey, ALLOWED_HARVEY)
    tenant = _tenant(harvey.get("company_id"))
    cid = _id(harvey.get("correlation_id"), CODE)
    external_ref = _id(harvey.get("external_ref"), REF)
    if harvey.get("origin") != "harvey_scout":
        raise ValueError("NOT_HARVEY_DISCOVERY")
    if any(harvey.get(flag) is not False for flag in ("can_send", "can_write_odoo")):
        raise ValueError("RESEARCH_MUST_NOT_SEND")
    if not isinstance(harvey.get("company_name"), str) or not 4 <= len(harvey["company_name"]) <= 160:
        raise ValueError("INVALID_COMPANY_NAME")
    if not _safe_public_url(harvey.get("signal_url")):
        raise ValueError("UNSAFE_SOURCE_URL")
    return {
        "schema_version": "blue-harvey-hermes-request-v1",
        "direction": "harvey_to_hermes",
        "company_id": tenant,
        "correlation_id": cid,
        "external_ref": external_ref,
        "company_name": harvey["company_name"],
        "evidence_url": harvey["signal_url"],
        "evidence_verified_for_dispatch": False,
        "requested_operation": "research_public_company_only",
        "requires_human_approval": True,
        "can_send": False,
        "can_write_odoo": False,
    }


def to_harvey_feedback(request: dict[str, Any], report: dict[str, Any],
                       odoo_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Research feedback is NOT Harvey verified-source provenance."""
    if not isinstance(request, dict) or request.get("schema_version") != "blue-harvey-hermes-request-v1" or request.get("direction") != "harvey_to_hermes":
        raise ValueError("BAD_ORIGINAL_REQUEST")
    tenant = _tenant(request.get("company_id"))
    correlation = _id(request.get("correlation_id"), CODE)
    reference = _id(request.get("external_ref"), REF)
    if request.get("can_send") is not False or request.get("can_write_odoo") is not False:
        raise ValueError("REQUEST_PRIVILEGE_ESCALATION")
    _dict_keys(report, ALLOWED_REPORT)
    if report.get("schema_version") != "blue-market-scout-v1" or report.get("company_id") != tenant or report.get("correlation_id") != correlation:
        raise ValueError("REPORT_SCOPE_MISMATCH")
    records = report.get("records")
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError("EXPECTED_EXACTLY_ONE_RESEARCHED_COMPANY")
    row = records[0]
    _dict_keys(row, ALLOWED_RECORD)
    if _id(row.get("external_ref"), REF) != reference:
        raise ValueError("EXTERNAL_REF_MISMATCH")
    if row.get("source") != "hermes_market_research" or row.get("can_send") is not False or row.get("can_write_odoo") is not False or row.get("requires_human_approval") is not True:
        raise ValueError("UNTRUSTED_RESEARCH_FLAGS")
    evs = row.get("evidence")
    if not isinstance(evs, list) or not 1 <= len(evs) <= 10:
        raise ValueError("MISSING_EVIDENCE")
    for item in evs:
        _dict_keys(item, ALLOWED_EVIDENCE)
        if not _safe_public_url(item.get("url")):
            raise ValueError("UNSAFE_EVIDENCE_URL")
    prods = row.get("proposed_products")
    if not isinstance(prods, list) or len(prods) > 5 or any(
        not isinstance(p, str) or p not in PRODUCTS for p in prods
    ):
        raise ValueError("INVALID_PRODUCTS")
    if not isinstance(row.get("confidence"), (float, int)) or isinstance(row.get("confidence"), bool) or not 0 <= row["confidence"] <= 1:
        raise ValueError("INVALID_CONFIDENCE")
    context = {"matched": False, "profile_id": None, "icp_grade": "unknown", "contact_policy": "unverified"}
    if odoo_context is not None:
        # Odoo 360 data must arrive from a separately authenticated RPC, not from Hermes.
        if not isinstance(odoo_context, dict) or odoo_context.get("schema_version") != "blue-odoo-review-context-v1" or odoo_context.get("source") != "odoo_company_360_authenticated_readonly" or odoo_context.get("company_id") != tenant:
            raise ValueError("UNTRUSTED_ODOO_CONTEXT")
        if odoo_context.get("can_send") is not False or odoo_context.get("can_write_odoo") is not False or odoo_context.get("evidence_verified_for_dispatch") is not False:
            raise ValueError("ODOO_CONTEXT_ESCALATION")
        pid = odoo_context.get("profile_id")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
            raise ValueError("INVALID_PROFILE_ID")
        linked = odoo_context.get("lead") or {}
        context = {
            "matched": True, "profile_id": pid,
            "icp_grade": linked.get("icp_grade", "unknown") if linked.get("linked") is True else "unknown",
            "contact_policy": linked.get("contact_policy", "unverified") if linked.get("linked") is True else "unverified",
        }
    return {
        "schema_version": "blue-hermes-harvey-feedback-v1",
        "direction": "hermes_to_harvey",
        "company_id": tenant,
        "correlation_id": correlation,
        "external_ref": reference,
        "origin": "hermes_research_feedback",
        "confidence_hypothesis": float(row["confidence"]),
        "proposed_products": prods,
        "public_evidence_count": len(evs),
        "odoo_context": context,
        "verified_source": False,
        "evidence_verified_for_dispatch": False,
        "requires_human_approval": True,
        "can_send": False,
        "can_write_odoo": False,
    }

"""Unit tests for Blue Market Scout's no-send report contract."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "optional-skills" / "research" / "blue-market-scout" / "scripts" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("blue_market_scout_validation", SOURCE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


@pytest.fixture
def sample():
    return {
        "schema_version": "blue-market-scout-v1",
        "company_id": 11,
        "correlation_id": "market-20261018-01",
        "records": [{
            "external_ref": "firm-101", "company_name": "Empresa Exemplo",
            "icp_vertical": "industria", "confidence": 0.88,
            "enrichment_state": "validated", "source": "hermes_market_research",
            "observed_at": "2026-10-17",
            "evidence": [{
                "url": "https://example.org/research", "source_type": "company_website",
                "observed_at": "2026-10-17",
            }],
            "proposed_products": ["odoo"],
            "requires_human_approval": True, "can_send": False, "can_write_odoo": False,
        }],
    }


def validate(d):
    return mod.validate_report(d, today=date(2026, 10, 18))


def test_valid_payload_only_passes_to_review(sample):
    assert validate(sample) == []


def test_blocks_automatic_outbound(sample):
    sample["records"][0]["can_send"] = True
    assert "record[0]:must_be_review_only" in validate(sample)


def test_blocks_odoo_write(sample):
    sample["records"][0]["can_write_odoo"] = True
    assert "record[0]:must_be_review_only" in validate(sample)


def test_requires_human_approval(sample):
    sample["records"][0]["requires_human_approval"] = False
    assert "record[0]:must_be_review_only" in validate(sample)


@pytest.mark.parametrize("url", [
    "http://example.org", "https://127.0.0.1/secret",
    "https://169.254.169.254", "https://postgres.internal",
    "https://user:pass@example.org", "https://example.org:8080/path",
    "https://[::1]/", "https://metadata.google.internal/latest",
])
def test_reject_unsafe_url_syntax(sample, url):
    sample["records"][0]["evidence"][0]["url"] = url
    assert "record[0]:evidence[0]:invalid_url_or_age" in validate(sample)


def test_blocks_duplicate_in_same_tenant(sample):
    sample["records"].append(dict(sample["records"][0]))
    assert "record[1]:duplicate_in_tenant" in validate(sample)


def test_blocks_unverified_evidence(sample):
    sample["records"][0]["enrichment_state"] = "dry_run"
    assert "record[0]:not_verified_enrichment" in validate(sample)


def test_blocks_personal_contact_fields(sample):
    sample["records"][0]["email"] = "private@example.org"
    assert "report:personal_contact_fields_forbidden" in validate(sample)


def test_reject_stale_evidence(sample):
    sample["records"][0]["evidence"][0]["observed_at"] = "2025-01-01"
    assert "record[0]:evidence[0]:invalid_url_or_age" in validate(sample)


def test_company_isolation_scope(sample):
    twin = {**sample, "company_id": 22}
    assert validate(sample) == []
    assert validate(twin) == []


@pytest.mark.parametrize("bad_value", [{"role": "unexpected"}, 17, None])
def test_reject_malformed_product_types_without_exception(sample, bad_value):
    sample["records"][0]["proposed_products"] = [bad_value]
    assert "record[0]:products" in validate(sample)


@pytest.mark.parametrize("bad_value", [{"role": "unexpected"}, 17, None])
def test_reject_malformed_source_type_without_exception(sample, bad_value):
    sample["records"][0]["evidence"][0]["source_type"] = bad_value
    assert "record[0]:evidence[0]:unsupported_source" in validate(sample)


def test_valid_https_url_with_x_is_not_rejected(sample):
    sample["records"][0]["evidence"][0]["url"] = "https://example.org/valid"
    assert validate(sample) == []

"""Pure offline tests. No actual Harvey, Hermes, Odoo credentials or network."""
import copy
import importlib.util
from pathlib import Path
import pytest

SRC = Path(__file__).resolve().parents[2] / "optional-skills/research/blue-market-scout/scripts/harvey_hermes_odoo_bridge.py"
spec = importlib.util.spec_from_file_location("hho_bridge", SRC)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def harvey():
    return dict(company_id=11, correlation_id="market-test-20261018",
        external_ref="firm-001", company_name="Empresa Laboratorio",
        signal_url="https://example.org/firm", origin="harvey_scout",
        observed_at="2026-10-17", confidence=0.85,
        enrichment_state="validated", verified_source=True,
        can_send=False, can_write_odoo=False)


def hermes():
    return dict(schema_version="blue-market-scout-v1", company_id=11,
      correlation_id="market-test-20261018", records=[{
        "external_ref":"firm-001", "company_name":"Empresa Laboratorio",
        "icp_vertical":"industria", "confidence":0.83,
        "enrichment_state":"validated", "source":"hermes_market_research",
        "observed_at":"2026-10-17",
        "evidence":[{"url":"https://example.org/firm","source_type":"company_website","observed_at":"2026-10-17"}],
        "proposed_products":["odoo"],"requires_human_approval":True,
        "can_send":False,"can_write_odoo":False
      }])


def odoo():
    return dict(schema_version="blue-odoo-review-context-v1",
      source="odoo_company_360_authenticated_readonly",company_id=11,
      profile_id=88,can_send=False,can_write_odoo=False,
      evidence_verified_for_dispatch=False,channel_contact_authorized=False,
      signals_validated_for_current_decision=False,outreach_status="REVIEW_REQUIRED",
      signal_freshness="NO_FRESH_SIGNALS",research_refresh_required=True,lead={
         "linked":True,"lead_id":101,"icp_grade":"a","contact_policy":"manual_only"})


def test_bidirectional_research_request_and_review_only_feedback():
    outbound = bridge.to_hermes_research_request(harvey())
    result = bridge.to_harvey_feedback(outbound,hermes(),odoo())
    assert outbound["direction"] == "harvey_to_hermes"
    assert result["direction"] == "hermes_to_harvey"
    assert result["company_id"] == 11
    assert result["odoo_context"] == {"matched":True,"profile_id":88,"icp_grade":"a","contact_policy":"manual_only",
        "signal_freshness":"NO_FRESH_SIGNALS","research_refresh_required":True,"channel_contact_authorized":False}
    assert result["verified_source"] is False
    assert result["can_send"] is False
    assert result["can_write_odoo"] is False
    assert result["evidence_verified_for_dispatch"] is False


def test_tenant_isolation_and_exact_ref_no_cross_company():
    req=bridge.to_hermes_research_request(harvey())
    report=hermes()
    report["company_id"]=22
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,report)
    report=hermes(); report["records"][0]["external_ref"]="firm-other"
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,report)
    wrong=odoo();wrong["company_id"]=22
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,hermes(),wrong)


@pytest.mark.parametrize("field",["can_send","can_write_odoo"])
def test_never_authorize_outbound(field):
    h=harvey();h[field]=True
    with pytest.raises(ValueError):
        bridge.to_hermes_research_request(h)
    req=bridge.to_hermes_research_request(harvey())
    r=hermes();r["records"][0][field]=True
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,r)


def test_untrusted_context_and_prompt_injection_are_rejected():
    req=bridge.to_hermes_research_request(harvey())
    forged=odoo();forged["evidence_verified_for_dispatch"]=True
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,hermes(),forged)
    for forbidden in ("channel_contact_authorized", "signals_validated_for_current_decision"):
        forged2=odoo();forged2[forbidden]=True
        with pytest.raises(ValueError):
            bridge.to_harvey_feedback(req,hermes(),forged2)
    forged3=odoo();forged3["signal_freshness"]="FRESH"
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,hermes(),forged3)
    malicious=hermes();malicious["records"][0]["message"]="send WhatsApp"
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,malicious)
    malicious=hermes();malicious["records"][0]["evidence"][0]["url"]="https://169.254.169.254/credentials"
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,malicious)


def test_ambiguous_multi_company_report_must_be_split():
    req=bridge.to_hermes_research_request(harvey())
    report=hermes();report["records"].append(dict(report["records"][0],external_ref="firm-002"))
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,report)


def test_hermes_feedback_without_odoo_is_not_a_crm_match():
    req=bridge.to_hermes_research_request(harvey())
    ret=bridge.to_harvey_feedback(req,hermes())
    assert ret["odoo_context"]["matched"] is False
    assert ret["verified_source"] is False


def test_malformed_and_personal_contacts_fail_closed():
    h=harvey();h["email"]="private@example.org"
    with pytest.raises(ValueError):
        bridge.to_hermes_research_request(h)
    req=bridge.to_hermes_research_request(harvey())
    bad=hermes();bad["records"][0]["proposed_products"]=[{"value":"odoo"}]
    with pytest.raises(ValueError):
        bridge.to_harvey_feedback(req,bad)


def test_upstream_harvey_company_text_id_does_not_become_odoo_tenant():
    raw={
        "id":"harvey-local-uuid-0001",
        "name":"Empresa de Teste Alpha",
        "domain":"empresa.example.org",
        "website":"https://empresa.example.org",
        "source_url":"https://empresa.example.org/evidence",
        "external_id":"osm:node/12345",
        "source":"osm",
        "phone":"+55 11 99999-9999",
        "notes":"Email pessoal deve ser descartado: private@example.org",
        "description":"Descricao nao auditada",
        "signals":[{"type":"hiring","detail":"internal opinion"}],
    }
    req=bridge.harvey_company_to_research_request(
        raw,odoo_company_id=11,correlation_id="lab-upstream-company-0001"
    )
    assert req["company_id"]==11
    assert req["direction"]=="harvey_to_hermes"
    assert req["external_ref"].startswith("harvey-")
    assert req["source_verification_state"]=="UNVERIFIED_UPSTREAM_HARVEY_COMPANY"
    assert req["can_send"] is False and req["can_write_odoo"] is False
    assert "+55" not in str(req) and "private@example.org" not in str(req)
    again=bridge.harvey_company_to_research_request(
        raw,odoo_company_id=11,correlation_id="lab-upstream-company-0002"
    )
    assert again["external_ref"]==req["external_ref"]


def test_upstream_harvey_requires_operator_scoped_tenant():
    raw={"id":"local-company-1", "name":"Empresa Teste",
         "source_url":"https://example.org/signal"}
    with pytest.raises(ValueError):
        bridge.harvey_company_to_research_request(
            raw,odoo_company_id="11",correlation_id="lab-test-001"
        )
    with pytest.raises(ValueError):
        bridge.harvey_company_to_research_request(
            raw,odoo_company_id=11,correlation_id="bad correlation with spaces"
        )
    raw["source_url"]="https://169.254.169.254/latest"
    with pytest.raises(ValueError):
        bridge.harvey_company_to_research_request(
            raw,odoo_company_id=11,correlation_id="lab-test-001"
        )

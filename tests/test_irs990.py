"""Tests for IRS 990-PF XML parser."""

from grant_intel.sources.irs990 import filter_relevant_grants, parse_990pf_grants


def test_parse_990pf_grants(sample_990pf_xml):
    """Test parsing grants from 990-PF XML."""
    grants = parse_990pf_grants(sample_990pf_xml, foundation_ein="999888777")

    assert len(grants) == 3
    assert grants[0]["recipient_name"] == "Youth Ministry International"
    assert grants[0]["recipient_ein"] == "987654321"
    assert grants[0]["amount"] == 50000
    assert grants[0]["purpose"] == "Youth ministry leadership training"
    assert grants[0]["foundation_ein"] == "999888777"

    assert grants[1]["recipient_name"] == "Local Community Center"
    assert grants[1]["amount"] == 25000

    assert grants[2]["recipient_name"] == "Arizona Christian University"
    assert grants[2]["amount"] == 75000


def test_parse_990pf_grants_invalid_xml():
    """Test handling of invalid XML."""
    grants = parse_990pf_grants(b"not xml", foundation_ein="123")
    assert grants == []


def test_parse_990pf_grants_empty_xml():
    """Test handling of XML with no grants."""
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile">
  <ReturnData>
    <IRS990PF></IRS990PF>
  </ReturnData>
</Return>"""
    grants = parse_990pf_grants(xml)
    assert grants == []


def test_filter_relevant_grants(sample_990pf_xml):
    """Test filtering grants by YLM-relevant keywords."""
    grants = parse_990pf_grants(sample_990pf_xml)
    relevant = filter_relevant_grants(grants)

    # "Youth Ministry International" matches "youth ministry"
    # "Arizona Christian University" matches "arizona" and "christian"
    # "Local Community Center" does NOT match any keywords
    assert len(relevant) == 2
    names = [g["recipient_name"] for g in relevant]
    assert "Youth Ministry International" in names
    assert "Arizona Christian University" in names
    assert "Local Community Center" not in names

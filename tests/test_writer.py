"""Tests for the grant writer agent module."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from grant_intel.config import OrgProfile
from grant_intel.db import get_draft, get_drafts_by_opportunity, init_db, insert_draft
from grant_intel.writer.extractor import (
    _empty_requirements,
    extract_requirements_from_text,
)
from grant_intel.writer.prompts import (
    BANNED_WORDS,
    SECTION_PROMPTS,
    build_loi_prompt,
    build_section_prompt,
    build_system_prompt,
)
from grant_intel.writer.sections import (
    DEFAULT_SECTIONS,
    determine_sections,
    generate_section,
    post_process_section,
)


# ---------------------------------------------------------------------------
# Prompt construction tests
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_system_prompt_includes_org_profile(self, sample_org_profile):
        """System prompt should contain all org profile fields."""
        prompt = build_system_prompt(sample_org_profile)

        assert "Youth Link Ministries" in prompt
        assert "501(c)(3)" in prompt
        assert "Chandler" in prompt
        assert "AZ" in prompt
        assert "youth pastors" in prompt.lower()
        assert "NOT youth directly" in prompt
        assert "19" in prompt  # years_active
        assert "X20" in prompt
        assert "Local Youth Leader Networks" in prompt
        assert "Coaching" in prompt
        assert "Resources & Speaking" in prompt
        assert "under_250k" in prompt

    def test_system_prompt_contains_banned_words_warning(self, sample_org_profile):
        """System prompt should warn against using AI-sounding words."""
        prompt = build_system_prompt(sample_org_profile)
        assert "transformative" in prompt.lower()
        assert "leverage" in prompt.lower()
        assert "synergy" in prompt.lower()

    def test_system_prompt_has_critical_distinction(self, sample_org_profile):
        """System prompt must emphasize the adults-not-youth distinction."""
        prompt = build_system_prompt(sample_org_profile)
        assert "CRITICAL DISTINCTION" in prompt
        assert "ADULTS who lead youth ministry" in prompt

    def test_section_prompt_includes_requirements(self, sample_requirements):
        """Section prompt should include funder context."""
        prompt = build_section_prompt(
            "Statement of Need",
            sample_requirements,
            previous_sections={},
        )
        assert "U.S. Department of Health and Human Services" in prompt
        assert "Community-Based Nonprofit Capacity Building" in prompt
        assert "Professional development" in prompt

    def test_section_prompt_includes_prior_sections(self, sample_requirements):
        """Section prompt should thread prior section content."""
        prior = {"Statement of Need": "Youth pastors in Arizona face burnout."}
        prompt = build_section_prompt(
            "Project Description",
            sample_requirements,
            previous_sections=prior,
        )
        assert "SECTIONS ALREADY WRITTEN" in prompt
        assert "Statement of Need" in prompt
        assert "Youth pastors in Arizona face burnout" in prompt

    def test_loi_prompt_includes_funder_and_amount(self, sample_org_profile):
        """LOI prompt should include funder name, amount, and project name."""
        prompt = build_loi_prompt(
            org=sample_org_profile,
            funder_name="Smith Family Foundation",
            amount=25000,
            project_name="AZ Youth Pastor Network",
        )
        assert "Smith Family Foundation" in prompt
        assert "$25,000" in prompt
        assert "AZ Youth Pastor Network" in prompt

    def test_loi_prompt_includes_funder_context(self, sample_org_profile):
        """LOI prompt should include funder guidelines context when provided."""
        prompt = build_loi_prompt(
            org=sample_org_profile,
            funder_name="Test Foundation",
            amount=10000,
            project_name="Test Project",
            funder_context="Focus on Arizona nonprofits serving religious leaders.",
        )
        assert "FUNDER CONTEXT" in prompt
        assert "Arizona nonprofits" in prompt

    def test_all_default_sections_have_prompts(self):
        """Every default section should have a corresponding prompt."""
        for section in DEFAULT_SECTIONS:
            assert section in SECTION_PROMPTS, f"Missing prompt for section: {section}"

    def test_banned_words_list_is_nonempty(self):
        """Banned words list should have entries."""
        assert len(BANNED_WORDS) > 20


# ---------------------------------------------------------------------------
# Post-processing tests
# ---------------------------------------------------------------------------


class TestPostProcessing:
    def test_post_process_strips_markdown_headers(self):
        """Post-processor should remove leading markdown headers."""
        text = "## Statement of Need\n\nThe problem is real."
        result = post_process_section(text)
        assert not result.startswith("#")
        assert "The problem is real" in result

    def test_post_process_flags_banned_words(self):
        """Post-processor should flag banned words with a warning."""
        text = "This program is truly transformative and leverages synergy."
        result = post_process_section(text)
        assert "[REVIEW:" in result
        assert "transformative" in result
        assert "synergy" in result

    def test_post_process_clean_text_no_warning(self):
        """Clean text should not get a warning appended."""
        text = "Youth pastors in Maricopa County face high burnout rates."
        result = post_process_section(text)
        assert "[REVIEW:" not in result
        assert text == result


# ---------------------------------------------------------------------------
# Section determination tests
# ---------------------------------------------------------------------------


class TestDetermineSections:
    def test_default_sections_when_none_specified(self):
        """Should return all default sections when NOFA doesn't specify."""
        requirements = {"required_sections": []}
        sections = determine_sections(requirements)
        assert sections == DEFAULT_SECTIONS

    def test_maps_funder_section_names(self):
        """Should map funder section names to standard names."""
        requirements = {
            "required_sections": [
                "Needs Assessment",
                "Program Design",
                "Goals",
                "Budget Narrative",
            ]
        }
        sections = determine_sections(requirements)
        assert "Statement of Need" in sections
        assert "Project Description" in sections
        assert "Goals and Objectives" in sections
        assert "Budget Justification" in sections

    def test_ensures_core_sections_present(self):
        """Should ensure Statement of Need, Project Description, Goals are always present."""
        requirements = {"required_sections": ["Budget", "Sustainability"]}
        sections = determine_sections(requirements)
        assert "Statement of Need" in sections
        assert "Project Description" in sections
        assert "Goals and Objectives" in sections
        assert "Budget Justification" in sections
        assert "Sustainability" in sections

    def test_full_nofa_sections(self, sample_requirements):
        """Should handle the full NOFA requirements."""
        sections = determine_sections(sample_requirements)
        assert len(sections) >= 7
        assert "Statement of Need" in sections
        assert "Sustainability" in sections


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------


class TestExtractor:
    def test_empty_requirements_structure(self):
        """Empty requirements should have all expected keys."""
        reqs = _empty_requirements()
        assert "funder_name" in reqs
        assert "program_name" in reqs
        assert "required_sections" in reqs
        assert isinstance(reqs["focus_areas"], list)
        assert isinstance(reqs["award_range"], dict)

    @patch("grant_intel.writer.extractor.anthropic.Anthropic")
    def test_extract_requirements_from_text(self, mock_anthropic, sample_nofa_text):
        """Should parse NOFA text via Claude and return structured dict."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "funder_name": "U.S. Department of Health and Human Services",
            "program_name": "Community-Based Nonprofit Capacity Building",
            "deadline": "2026-06-30",
            "award_range": {"min": 50000, "max": 150000},
            "eligible_applicants": "501(c)(3) nonprofit organizations",
            "required_sections": ["Statement of Need", "Project Description"],
            "page_limits": {"narrative": 17},
            "evaluation_criteria": ["Mission alignment (25 points)"],
            "focus_areas": ["Professional development"],
            "restrictions": ["No religious proselytization"],
            "questions_to_answer": [],
        })

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        result = extract_requirements_from_text(sample_nofa_text, "fake-key")

        assert result["funder_name"] == "U.S. Department of Health and Human Services"
        assert result["award_range"]["min"] == 50000
        assert "raw_text" in result
        mock_client.messages.create.assert_called_once()

    @patch("grant_intel.writer.extractor.anthropic.Anthropic")
    def test_extract_empty_input(self, mock_anthropic):
        """Should handle empty input gracefully."""
        result = extract_requirements_from_text("", "fake-key")
        assert result["funder_name"] == ""
        mock_anthropic.return_value.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Section generation tests (mocked Claude calls)
# ---------------------------------------------------------------------------


class TestSectionGeneration:
    @patch("grant_intel.writer.sections.anthropic.Anthropic")
    def test_generate_section(
        self,
        mock_anthropic,
        sample_org_profile,
        sample_requirements,
        mock_claude_section_response,
    ):
        """Should generate a single section via Claude API."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = mock_claude_section_response

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        result = generate_section(
            api_key="fake-key",
            org=sample_org_profile,
            requirements=sample_requirements,
            section_name="Statement of Need",
            previous_sections={},
        )

        assert "Maricopa County" in result
        assert "youth pastors" in result
        assert "[INSERT:" in result
        mock_client.messages.create.assert_called_once()

    @patch("grant_intel.writer.sections.anthropic.Anthropic")
    def test_generate_section_with_prior_context(
        self,
        mock_anthropic,
        sample_org_profile,
        sample_requirements,
    ):
        """Prior sections should be included in the Claude API call."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "The project will train 50 youth pastors."

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        prior = {"Statement of Need": "Burnout is a real problem."}

        generate_section(
            api_key="fake-key",
            org=sample_org_profile,
            requirements=sample_requirements,
            section_name="Project Description",
            previous_sections=prior,
        )

        # Verify the call included prior sections in messages
        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        # Should have 3 messages: user (prior), assistant (ack), user (new section)
        assert len(messages) == 3
        assert "Burnout is a real problem" in messages[0]["content"]


# ---------------------------------------------------------------------------
# Database tests for grant_drafts
# ---------------------------------------------------------------------------


class TestDraftDB:
    def test_insert_and_get_draft(self, test_db):
        """Should insert a draft and retrieve it by ID."""
        draft = {
            "opportunity_id": None,
            "foundation_id": None,
            "draft_type": "federal_narrative",
            "funder_name": "HHS",
            "project_name": "Capacity Building",
            "requirements_json": "{}",
            "sections_json": json.dumps({"Statement of Need": "Test content"}),
            "full_draft": "# Full draft text",
            "model_used": "claude-sonnet-4-6",
            "status": "draft",
        }

        draft_id = insert_draft(test_db, draft)
        assert draft_id is not None
        assert draft_id > 0

        retrieved = get_draft(test_db, draft_id)
        assert retrieved is not None
        assert retrieved["funder_name"] == "HHS"
        assert retrieved["draft_type"] == "federal_narrative"
        assert retrieved["status"] == "draft"

    def test_get_draft_not_found(self, test_db):
        """Should return None for nonexistent draft ID."""
        result = get_draft(test_db, 99999)
        assert result is None

    def test_get_drafts_by_opportunity(self, test_db):
        """Should return drafts linked to a specific opportunity."""
        # Insert an opportunity first
        test_db.execute(
            """INSERT INTO opportunities
            (source, opportunity_id, title, status)
            VALUES ('test', 'OPP-1', 'Test Opportunity', 'posted')"""
        )
        test_db.commit()
        opp_row = test_db.execute(
            "SELECT id FROM opportunities WHERE opportunity_id = 'OPP-1'"
        ).fetchone()
        opp_id = opp_row[0]

        # Insert two drafts for this opportunity
        for i in range(2):
            insert_draft(test_db, {
                "opportunity_id": opp_id,
                "draft_type": "federal_narrative",
                "funder_name": "HHS",
                "project_name": f"Project {i}",
            })

        drafts = get_drafts_by_opportunity(test_db, opp_id)
        assert len(drafts) == 2

    def test_update_draft_status(self, test_db):
        """Should update draft status."""
        from grant_intel.db import update_draft_status

        draft_id = insert_draft(test_db, {
            "draft_type": "foundation_loi",
            "funder_name": "Test Foundation",
            "status": "draft",
        })

        update_draft_status(test_db, draft_id, "review")
        updated = get_draft(test_db, draft_id)
        assert updated["status"] == "review"

    def test_pipeline_stats_includes_drafts(self, test_db):
        """Pipeline stats should include draft count."""
        from grant_intel.db import get_pipeline_stats

        insert_draft(test_db, {
            "draft_type": "federal_narrative",
            "funder_name": "Test",
        })
        insert_draft(test_db, {
            "draft_type": "foundation_loi",
            "funder_name": "Test 2",
        })

        stats = get_pipeline_stats(test_db)
        assert stats["total_drafts"] == 2


# ---------------------------------------------------------------------------
# Agent orchestrator tests (mocked)
# ---------------------------------------------------------------------------


class TestAgent:
    @patch("grant_intel.writer.agent.generate_section")
    def test_draft_federal_narrative(
        self,
        mock_gen_section,
        sample_org_profile,
        sample_requirements,
    ):
        """Should generate all sections and save to file."""
        from grant_intel.writer.agent import draft_federal_narrative

        mock_gen_section.return_value = "Section content here."

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath, sections = draft_federal_narrative(
                api_key="fake-key",
                org=sample_org_profile,
                requirements=sample_requirements,
                output_dir=tmpdir,
            )

            assert os.path.exists(filepath)
            assert filepath.endswith(".md")
            assert len(sections) >= 7  # All standard sections

            content = open(filepath).read()
            assert "Federal Grant Narrative" in content
            assert "Section content here" in content

    @patch("grant_intel.writer.agent.anthropic.Anthropic")
    def test_draft_foundation_loi(
        self,
        mock_anthropic,
        sample_org_profile,
        mock_claude_loi_response,
    ):
        """Should generate an LOI and save to file."""
        from grant_intel.writer.agent import draft_foundation_loi

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = mock_claude_loi_response

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath, loi_text = draft_foundation_loi(
                api_key="fake-key",
                org=sample_org_profile,
                requirements={},
                funder_name="Smith Family Foundation",
                amount=25000,
                project_name="AZ Youth Pastor Network",
                output_dir=tmpdir,
            )

            assert os.path.exists(filepath)
            assert "Smith Family Foundation" in loi_text
            assert "$25,000" in loi_text or "25,000" in loi_text
            assert "[INSERT:" in loi_text

    @patch("grant_intel.writer.agent.generate_section")
    def test_build_draft_record(
        self,
        mock_gen_section,
        sample_org_profile,
        sample_requirements,
    ):
        """Should produce a dict suitable for DB insertion."""
        from grant_intel.writer.agent import build_draft_record, draft_federal_narrative

        mock_gen_section.return_value = "Content."

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath, sections = draft_federal_narrative(
                api_key="fake-key",
                org=sample_org_profile,
                requirements=sample_requirements,
                output_dir=tmpdir,
            )

            record = build_draft_record(
                opportunity_id=1,
                foundation_id=None,
                draft_type="federal_narrative",
                funder_name="HHS",
                project_name="Capacity Building",
                requirements=sample_requirements,
                sections=sections,
                full_draft_path=filepath,
            )

            assert record["opportunity_id"] == 1
            assert record["draft_type"] == "federal_narrative"
            assert record["model_used"] == "claude-sonnet-4-6"
            assert "Content." in record["full_draft"]
            # requirements_json should be valid JSON
            parsed = json.loads(record["requirements_json"])
            assert parsed["funder_name"] == "U.S. Department of Health and Human Services"

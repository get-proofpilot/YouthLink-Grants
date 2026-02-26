"""Voice persona, section prompts, LOI prompt, and banned-words list."""

from grant_intel.config import OrgProfile

# ---------------------------------------------------------------------------
# Banned words — these scream "AI wrote this."  The post-processor flags them.
# ---------------------------------------------------------------------------

BANNED_WORDS = [
    "transformative",
    "leverage",
    "synergy",
    "holistic",
    "robust",
    "innovative",
    "cutting-edge",
    "paradigm",
    "empower",
    "stakeholder",
    "ecosystem",
    "game-changer",
    "best-in-class",
    "world-class",
    "next-generation",
    "state-of-the-art",
    "disruptive",
    "scalable",
    "impactful",
    "utilize",
    "facilitate",
    "implement a framework",
    "in today's rapidly changing",
    "now more than ever",
    "at the end of the day",
    "move the needle",
    "deep dive",
    "circle back",
    "low-hanging fruit",
    "synergize",
    "paradigm shift",
    "thought leader",
    "value-add",
    "operationalize",
]

# ---------------------------------------------------------------------------
# Master system prompt — the grant writer persona
# ---------------------------------------------------------------------------

GRANT_WRITER_SYSTEM = """You are writing a grant application for {org_name}. You are \
a veteran grant writer with 22 years of experience. You've written over 400 successful \
proposals for small nonprofits, faith-based organizations, and community development \
programs. You've secured over $35 million in funding across your career.

YOUR WRITING STYLE:
- You write the way a thoughtful person talks to a colleague they respect. Not formal. \
Not casual. Just clear, direct, and warm.
- You never use the word "transformative." You don't say "leverage," "synergy," \
"holistic," "robust," "innovative," "cutting-edge," "paradigm," "empower," \
"stakeholder," or "ecosystem." Those words make reviewers' eyes glaze over.
- You open with the specific problem, not a grand statement. "In Maricopa County, \
43% of youth pastors leave ministry within five years" — not "In today's rapidly \
changing landscape..."
- You use concrete numbers over adjectives. "Served 127 youth pastors across \
14 Arizona counties" — not "served many youth leaders across the state."
- You write short paragraphs. Two to four sentences. You know reviewers read \
50 proposals in a weekend. They skim. You make it easy.
- You mirror the funder's language. If they say "capacity building," you say \
"capacity building." If they say "professional development," you match that.
- You connect the org's work to real people. Not "enhanced leadership competencies" \
— instead, "a youth pastor in Mesa told us the coaching helped her keep going \
when she was ready to quit."
- Every claim has a number or a name behind it. You never say "significant impact" \
without proof.
- You address the faith-based question directly when relevant. If the funder has \
restrictions on religious content, you show exactly how the project serves the \
broader community. You don't dodge it.
- You vary sentence length. Some short. Some longer, connecting ideas with a natural \
rhythm that sounds like someone who actually cares about the work.
- You never start two paragraphs the same way.

ABOUT THE ORGANIZATION:
Name: {org_name}
Status: {tax_status}
Location: {city}, {state}
Mission: {mission}
Who they serve: {serves}
Programs:
{programs}
Budget: {budget_range} annual revenue
Years active: {years_active}
NTEE Codes: {ntee_codes}

CRITICAL DISTINCTION: {org_name} serves the ADULTS who lead youth ministry — the \
pastors, the volunteers, the coordinators. Not the young people directly. Every \
sentence you write must reflect this. When a reviewer reads your proposal, they \
should understand within the first paragraph that this organization supports \
the people who support kids.

WRITING RULES:
1. First draft only. Insert [BRACKETS] for data, stories, or numbers the org \
must fill in. Example: "[INSERT: number of youth pastors served in 2025]" \
or "[INSERT: story of a pastor whose coaching changed their ministry]"
2. Match the funder's tone. Government grants = structured prose. Foundation \
LOIs = conversational warmth.
3. Never open a section with "This proposal seeks to..." or "We are writing to \
request..." — lead with the problem or the people.
4. Budget numbers must add up. If you cite a figure, keep it consistent.
5. End sections with forward momentum, not summaries.
6. Never use the words: transformative, leverage, synergy, holistic, robust, \
innovative, cutting-edge, paradigm, empower, stakeholder, ecosystem, \
impactful, utilize, facilitate.
7. Write in third person when referencing the organization ("Youth Link Ministries \
provides...") unless the funder's guidelines explicitly request first person.
8. Do not include section headers in your output — the template handles those. \
Just write the content."""

# ---------------------------------------------------------------------------
# Section-specific writing prompts
# ---------------------------------------------------------------------------

SECTION_PROMPTS = {
    "Statement of Need": (
        "Write the Statement of Need section.\n\n"
        "Open with a specific, local data point about the problem — not a national "
        "statistic. Show the gap: who are the people affected, what is happening to "
        "them, and why existing resources fall short.\n\n"
        "Build the case in 3-4 short paragraphs:\n"
        "1. The specific problem with local data (Maricopa County, Arizona, etc.)\n"
        "2. The consequences of the problem — what happens when youth pastors burn out, "
        "leave ministry, or lack training\n"
        "3. Why existing solutions don't reach this population\n"
        "4. What the funder's investment can change\n\n"
        "Use [INSERT: ...] brackets for any statistics or stories the org needs to "
        "verify or provide."
    ),
    "Project Description": (
        "Write the Project Description / Project Design section.\n\n"
        "Describe the specific activities, who will carry them out, and the timeline. "
        "Be concrete: 'Monthly peer-learning cohorts of 8-12 youth pastors, facilitated "
        "by a trained coach' — not 'regular professional development opportunities.'\n\n"
        "Cover:\n"
        "1. What activities will happen (be specific about format, frequency, duration)\n"
        "2. Who will do the work (staff roles, qualifications)\n"
        "3. Who benefits and how they're recruited/selected\n"
        "4. Timeline of major activities by quarter\n"
        "5. How this connects to the need described earlier\n\n"
        "Use [INSERT: ...] for specific staff names, exact dates, and detailed timelines "
        "the org needs to fill in."
    ),
    "Goals and Objectives": (
        "Write the Goals and Objectives section.\n\n"
        "Structure as 2-3 broad goals, each with 2-3 SMART objectives beneath them.\n\n"
        "Goals should be the big picture: 'Strengthen the retention and effectiveness "
        "of youth ministry leaders in Maricopa County.'\n\n"
        "Objectives must be measurable and time-bound: 'By Month 12, at least "
        "[INSERT: number] youth pastors will complete the full coaching cohort "
        "and report improved ministry confidence on a validated survey instrument.'\n\n"
        "Include realistic targets based on the organization's size and history."
    ),
    "Evaluation Plan": (
        "Write the Evaluation Plan section.\n\n"
        "Describe both process evaluation (are activities happening as planned?) "
        "and outcome evaluation (are they making a difference?).\n\n"
        "Cover:\n"
        "1. What data will be collected (surveys, attendance, retention rates)\n"
        "2. When and how data is collected\n"
        "3. Who analyzes the data\n"
        "4. How results inform program adjustments\n"
        "5. Reporting schedule\n\n"
        "Be practical. A small nonprofit isn't hiring an external evaluator for a "
        "$50K grant. Match the evaluation design to the budget and org capacity."
    ),
    "Organizational Capacity": (
        "Write the Organizational Capacity section.\n\n"
        "Show why this organization can deliver. Focus on:\n"
        "1. Track record — 19+ years of connecting youth ministry leaders in Arizona\n"
        "2. Specific accomplishments with numbers\n"
        "3. Key staff and their relevant experience\n"
        "4. Partnerships and networks already in place\n"
        "5. Financial management (clean audits, board governance)\n\n"
        "This is the section where the org's history and relationships matter most. "
        "Use [INSERT: ...] for specific staff bios, board details, and partnership names."
    ),
    "Budget Justification": (
        "Write the Budget Justification / Budget Narrative section.\n\n"
        "For each major line item, explain:\n"
        "1. What the cost covers\n"
        "2. How it was calculated\n"
        "3. Why it's necessary for the project\n\n"
        "Typical categories for a small nonprofit program grant:\n"
        "- Personnel (portion of salary/benefits for project staff)\n"
        "- Consultants/Coaches (if using external facilitators)\n"
        "- Travel (mileage for site visits, cohort meetings)\n"
        "- Supplies and materials\n"
        "- Meeting/venue costs\n"
        "- Indirect costs (if allowable)\n\n"
        "Use [INSERT: ...] for specific dollar amounts, salary rates, and FTE "
        "percentages. Make sure references to activities match the Project Description."
    ),
    "Sustainability": (
        "Write the Sustainability Plan section.\n\n"
        "Reviewers are skeptical of sustainability sections. Don't promise the "
        "program will magically self-fund. Instead:\n"
        "1. Identify which components can continue at low cost (peer networks, "
        "for example, mostly need coordination, not cash)\n"
        "2. Name 1-2 realistic additional funding sources being pursued\n"
        "3. Describe how lessons learned will be captured and shared\n"
        "4. Show the org's history of sustaining programs beyond initial funding\n\n"
        "Be honest. A small org sustains programs through relationships and "
        "low overhead, not endowments."
    ),
}

# ---------------------------------------------------------------------------
# Foundation Letter of Inquiry prompt
# ---------------------------------------------------------------------------

LOI_PROMPT = """Write a Letter of Inquiry to {funder_name} requesting ${amount:,} \
for the project "{project_name}."

FORMAT — a 2-3 page letter with these elements:
1. Opening hook — one sentence with a specific problem or person (not "Dear Sir/Madam, \
we are writing to request..."). Address it to {funder_name}.
2. The Need — 2-3 paragraphs with local data and real consequences. Why does this \
matter to the funder specifically?
3. The Solution — what {org_name} will do, concretely. Activities, who benefits, \
timeline.
4. Why Us — track record, relationships, positioning. Why {org_name} is the right \
org for this work.
5. The Ask — specific dollar amount, what it covers, project timeline.
6. Closing — warm, professional. Include contact info placeholder.

TONE: Conversational but professional. Like you're writing to someone who cares \
about the same things you do and has the resources to help. Not stiff. Not salesy. \
Just genuine.

{funder_context}

Write the complete letter now. Use [INSERT: ...] brackets for any specific data, \
stories, or contact details the org needs to fill in."""


def build_system_prompt(org: OrgProfile) -> str:
    """Build the master system prompt from org profile."""
    programs_text = "\n".join(
        f"- {p['name']}: {p['description']}" for p in org.programs
    )
    return GRANT_WRITER_SYSTEM.format(
        org_name=org.name,
        tax_status=org.tax_status,
        city=org.city,
        state=org.state,
        mission=org.mission,
        serves=org.serves,
        programs=programs_text,
        budget_range=org.budget_range,
        years_active=org.years_active,
        ntee_codes=", ".join(org.ntee_codes),
    )


def build_section_prompt(
    section_name: str,
    requirements: dict,
    previous_sections: dict[str, str],
) -> str:
    """Build the user prompt for a specific section."""
    section_instruction = SECTION_PROMPTS.get(section_name, "")

    parts = [section_instruction]

    # Funder requirements context
    parts.append(f"\n\nFUNDER: {requirements.get('funder_name', 'Unknown')}")
    parts.append(f"PROGRAM: {requirements.get('program_name', 'Unknown')}")

    if requirements.get("award_range"):
        ar = requirements["award_range"]
        parts.append(f"AWARD RANGE: ${ar.get('min', 0):,} – ${ar.get('max', 0):,}")

    if requirements.get("focus_areas"):
        parts.append(f"FOCUS AREAS: {', '.join(requirements['focus_areas'])}")

    if requirements.get("restrictions"):
        parts.append(f"RESTRICTIONS: {', '.join(requirements['restrictions'])}")

    if requirements.get("evaluation_criteria"):
        parts.append(
            "EVALUATION CRITERIA:\n"
            + "\n".join(f"- {c}" for c in requirements["evaluation_criteria"])
        )

    if requirements.get("questions_to_answer"):
        parts.append(
            "SPECIFIC QUESTIONS TO ADDRESS:\n"
            + "\n".join(f"- {q}" for q in requirements["questions_to_answer"])
        )

    if requirements.get("page_limits"):
        parts.append(f"PAGE LIMITS: {requirements['page_limits']}")

    # Cross-section context
    if previous_sections:
        parts.append("\n\nSECTIONS ALREADY WRITTEN (maintain consistency):")
        for name, content in previous_sections.items():
            parts.append(f"\n--- {name} ---\n{content}")

    return "\n".join(parts)


def build_loi_prompt(
    org: OrgProfile,
    funder_name: str,
    amount: int,
    project_name: str,
    funder_context: str = "",
) -> str:
    """Build the user prompt for a foundation Letter of Inquiry."""
    ctx = ""
    if funder_context:
        ctx = f"FUNDER CONTEXT / GUIDELINES:\n{funder_context}"

    return LOI_PROMPT.format(
        funder_name=funder_name,
        amount=amount,
        project_name=project_name,
        org_name=org.name,
        funder_context=ctx,
    )

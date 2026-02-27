"""Jinja2 template filters for the dashboard."""

import re
from datetime import date, datetime


def register_filters(app):
    """Register custom Jinja2 template filters on the Flask app."""

    @app.template_filter("currency")
    def currency_filter(value):
        if value is None:
            return "N/A"
        try:
            return f"${int(value):,}"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter("score_class")
    def score_class_filter(score):
        if score is None:
            return "text-muted"
        if score >= 7:
            return "text-success"
        if score >= 4:
            return "text-warning"
        return "text-danger"

    @app.template_filter("score_bg")
    def score_bg_filter(score):
        if score is None:
            return "bg-secondary"
        if score >= 7:
            return "bg-success"
        if score >= 4:
            return "bg-warning"
        return "bg-danger"

    @app.template_filter("priority_class")
    def priority_class_filter(score):
        if score is None:
            return "text-muted"
        if score >= 7.0:
            return "text-success fw-bold"
        if score >= 4.0:
            return "text-warning fw-bold"
        return "text-danger fw-bold"

    @app.template_filter("urgency_badge")
    def urgency_badge_filter(urgency):
        mapping = {
            "30_day": '<span class="badge bg-danger">URGENT</span>',
            "60_day": '<span class="badge bg-warning text-dark">UPCOMING</span>',
            "90_day": '<span class="badge bg-info text-dark">90 Days</span>',
        }
        return mapping.get(urgency, "")

    @app.template_filter("stage_badge")
    def stage_badge_filter(stage):
        mapping = {
            "discovered": '<span class="badge bg-secondary">Discovered</span>',
            "drafting": '<span class="badge bg-primary">Drafting</span>',
            "submitted": '<span class="badge bg-info">Submitted</span>',
            "awarded": '<span class="badge bg-success">Awarded</span>',
            "declined": '<span class="badge bg-danger">Declined</span>',
        }
        return mapping.get(stage, f'<span class="badge bg-secondary">{stage}</span>')

    @app.template_filter("draft_status_badge")
    def draft_status_badge_filter(status):
        mapping = {
            "draft": '<span class="badge bg-secondary">Draft</span>',
            "review": '<span class="badge bg-warning text-dark">Review</span>',
            "submitted": '<span class="badge bg-success">Submitted</span>',
        }
        return mapping.get(status, f'<span class="badge bg-secondary">{status}</span>')

    @app.template_filter("match_icon")
    def match_icon_filter(status):
        mapping = {
            "pass": '<span class="text-success">&#10004;</span>',
            "fail": '<span class="text-danger">&#10008;</span>',
            "warn": '<span class="text-warning">&#9888;</span>',
            "unknown": '<span class="text-muted">?</span>',
        }
        return mapping.get(status, "")

    @app.template_filter("match_class")
    def match_class_filter(status):
        return {"pass": "table-success", "fail": "table-danger",
                "warn": "table-warning", "unknown": ""}.get(status, "")

    @app.template_filter("highlight_inserts")
    def highlight_inserts_filter(text):
        if not text:
            return ""
        return re.sub(
            r"\[INSERT:[^\]]*\]",
            lambda m: f'<mark class="bg-warning">{m.group(0)}</mark>',
            text,
        )

    @app.template_filter("relative_date")
    def relative_date_filter(date_str):
        if not date_str:
            return ""
        try:
            d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            delta = (d - date.today()).days
            if delta < 0:
                return f"{abs(delta)} days ago"
            if delta == 0:
                return "today"
            if delta == 1:
                return "tomorrow"
            return f"in {delta} days"
        except (ValueError, TypeError):
            return date_str

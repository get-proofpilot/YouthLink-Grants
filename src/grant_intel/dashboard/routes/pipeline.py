"""Pipeline tracking page."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from grant_intel.db import (
    get_connection,
    get_pipeline_by_stage,
    get_pipeline_entry,
    update_pipeline_notes,
    update_pipeline_stage,
    upsert_pipeline_entry,
)

pipeline_bp = Blueprint("pipeline", __name__)

STAGES = ["discovered", "drafting", "submitted", "awarded", "declined"]


@pipeline_bp.route("/")
@login_required
def index():
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        pipeline = get_pipeline_by_stage(conn)
        return render_template("pipeline.html", pipeline=pipeline, stages=STAGES)
    finally:
        conn.close()


@pipeline_bp.route("/<int:entry_id>/stage", methods=["POST"])
@login_required
def change_stage(entry_id):
    new_stage = request.form.get("stage", "")
    if new_stage not in STAGES:
        flash("Invalid stage.", "danger")
        return redirect(url_for("pipeline.index"))

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        update_pipeline_stage(conn, entry_id, new_stage)
        flash(f"Pipeline entry moved to '{new_stage}'.", "success")
    finally:
        conn.close()

    return redirect(url_for("pipeline.index"))


@pipeline_bp.route("/<int:entry_id>/notes", methods=["POST"])
@login_required
def edit_notes(entry_id):
    notes = request.form.get("notes", "")
    conn = get_connection(current_app.config["DB_PATH"])
    try:
        update_pipeline_notes(conn, entry_id, notes)
        flash("Notes updated.", "success")
    finally:
        conn.close()

    return redirect(url_for("pipeline.index"))


@pipeline_bp.route("/add", methods=["POST"])
@login_required
def add_entry():
    opp_id = request.form.get("opportunity_id", type=int)
    foundation_id = request.form.get("foundation_id", type=int)

    conn = get_connection(current_app.config["DB_PATH"])
    try:
        upsert_pipeline_entry(conn, opportunity_id=opp_id, foundation_id=foundation_id)
        flash("Added to pipeline.", "success")
    finally:
        conn.close()

    if opp_id:
        return redirect(url_for("opportunities.detail", opp_id=opp_id))
    if foundation_id:
        return redirect(url_for("foundations.detail", foundation_id=foundation_id))
    return redirect(url_for("pipeline.index"))

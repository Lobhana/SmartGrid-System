import logging
from flask import Blueprint, jsonify, render_template, request
from renewable_service import (
    get_renewable_summary,
    get_renewable_trends,
    get_regional_renewable,
    get_source_detail,
)

logger = logging.getLogger(__name__)
renewable_bp = Blueprint("renewable", __name__)


@renewable_bp.route("/renewable-sources")
def renewable_sources():
    try:
        summary = get_renewable_summary()
    except Exception as exc:
        logger.error(f"Could not load renewable summary: {exc}")
        summary = None
    return render_template("renewable_sources.html", summary=summary)


@renewable_bp.route("/api/renewable/summary")
def api_renewable_summary():
    try:
        data = get_renewable_summary()
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        logger.error(f"Error in /api/renewable/summary: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@renewable_bp.route("/api/renewable/trends")
def api_renewable_trends():
    try:
        days   = min(int(request.args.get("days", 7)), 90)
        source = request.args.get("source", "all").lower().strip()
        data   = get_renewable_trends(days=days, source=source)
        return jsonify({"success": True, "data": data})
    except ValueError:
        return jsonify({"success": False, "error": "Invalid days parameter"}), 400
    except Exception as exc:
        logger.error(f"Error in /api/renewable/trends: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@renewable_bp.route("/api/renewable/regional")
def api_renewable_regional():
    try:
        region = request.args.get("region", "all").lower().strip()
        data   = get_regional_renewable(region=region)
        if "error" in data:
            return jsonify({"success": False, **data}), 404
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        logger.error(f"Error in /api/renewable/regional: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@renewable_bp.route("/api/renewable/source/<string:source>")
def api_renewable_source_detail(source: str):
    try:
        source = source.lower().strip()
        data   = get_source_detail(source)
        if "error" in data:
            return jsonify({"success": False, **data}), 404
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        logger.error(f"Error in /api/renewable/source/{source}: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@renewable_bp.route("/api/renewable/sources")
def api_renewable_all_sources():
    try:
        sources = ["solar", "wind", "hydro", "biomass", "others"]
        result  = {src: get_source_detail(src) for src in sources}
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        logger.error(f"Error in /api/renewable/sources: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500
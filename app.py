"""
6-71 Parts Desk: Flask app serving the parts page and its API.

  python app.py            # http://localhost:5001
"""

import os

from flask import Flask, jsonify, render_template, request

import parts_desk

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Static files live in public/ so Vercel serves them from its CDN at /static/...
app = Flask(__name__, static_folder="public/static", static_url_path="/static")


def _string_error(what: str, e: Exception):
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status == 402:
        return jsonify({"error": "String credits are used up for this demo key."}), 502
    return jsonify({"error": f"String {what} failed ({status or type(e).__name__})"}), 502


@app.route("/")
def parts_page():
    return render_template("parts.html", string_enabled=bool(parts_desk.api_key()))


@app.route("/api/parts", methods=["GET"])
def parts_catalog():
    return jsonify(parts_desk.CATALOG)


@app.route("/api/parts/<part_id>/sources", methods=["GET"])
def parts_sources(part_id):
    if part_id not in parts_desk.PART_IDS:
        return jsonify({"error": "unknown part"}), 404
    if not parts_desk.api_key():
        return jsonify({"error": "STRING_API_KEY is not set"}), 400
    try:
        return jsonify(parts_desk.sources(part_id, refresh=request.args.get("refresh") == "1"))
    except Exception as e:
        return _string_error("search", e)


@app.route("/api/parts/check", methods=["POST"])
def parts_check():
    url = (request.json or {}).get("url", "").strip()
    # Only vendor pages the desk has listed, so the public site isn't an open String proxy.
    if url not in parts_desk.listed_urls():
        return jsonify({"error": "not a listed source"}), 400
    if not parts_desk.api_key():
        return jsonify({"error": "STRING_API_KEY is not set"}), 400
    try:
        return jsonify(parts_desk.check_listing(url))
    except Exception as e:
        return _string_error("fetch", e)


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5001)), debug=True)

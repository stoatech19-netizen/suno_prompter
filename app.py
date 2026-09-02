import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from analyzer import (
    VARIATION_BATCH_SIZE,
    analyze_category,
    analyze_with_gemini,
    build_lyrics_structure,
    build_suno_prompt,
    extract_local_features,
    regenerate_variations,
)

load_dotenv()

if not (os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY")):
    raise RuntimeError(
        "GEMINI_API_KEY (or GEMINI_API_KEYS) is not set. Copy .env.example to .env in the "
        "suno_prompter folder and fill in your Gemini API key(s) before starting the app."
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {".mp3", ".wav"}
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB, matches Gemini inline data limit

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # dev only: always serve fresh static files


def _variation_result(analysis, fallback_bpm=None):
    bpm = analysis.get("bpm") or fallback_bpm
    return {
        "analysis": analysis,
        "suno_prompt": build_suno_prompt(analysis, bpm),
        "title": analysis.get("title"),
        "lyrics_structure": build_lyrics_structure(analysis),
        "bpm": bpm,
    }


def _gemini_error_response(e):
    if isinstance(e, RuntimeError):
        return jsonify({"error": str(e)}), 500
    message = str(e)
    upper = message.upper()
    if "429" in message or "RESOURCE_EXHAUSTED" in upper:
        return jsonify({"error": "Gemini API 무료 한도를 초과했습니다. 잠시 후 다시 시도해주세요."}), 429
    if "403" in message or "PERMISSION_DENIED" in upper:
        return jsonify({"error": "Gemini API 키(프로젝트)가 접근이 거부된 상태입니다. API 키 상태를 확인해주세요."}), 403
    return jsonify({"error": "분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}), 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "파일이 첨부되지 않았습니다."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "파일이 첨부되지 않았습니다."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "mp3 또는 wav 파일만 업로드할 수 있습니다."}), 400

    temp_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    try:
        file.save(temp_path)

        local_features = extract_local_features(temp_path)

        try:
            analysis = analyze_with_gemini(temp_path, local_features)
        except Exception as e:
            return _gemini_error_response(e)

        # Seed the browsable batch with the audio-grounded base analysis,
        # then round it out to VARIATION_BATCH_SIZE with cheap text-only
        # variations so left/right browsing works from the very first
        # analysis, not just after a manual "regenerate" click. If the
        # follow-up call fails (e.g. quota), degrade to just the base result
        # rather than failing the whole upload.
        try:
            extra = regenerate_variations(
                analysis, local_features.get("bpm"), count=VARIATION_BATCH_SIZE - 1
            )
        except Exception:
            extra = []

        variations = [_variation_result(analysis, local_features.get("bpm"))]
        variations += [_variation_result(v) for v in extra]

        return jsonify({
            "local_features": local_features,
            "analysis": analysis,
            "variations": variations,
        })
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route("/api/analyze-category", methods=["POST"])
def analyze_category_route():
    body = request.get_json(silent=True) or {}
    category = (body.get("category") or "").strip()

    if not category:
        return jsonify({"error": "카테고리를 입력해주세요."}), 400

    try:
        variations = analyze_category(category)
    except Exception as e:
        return _gemini_error_response(e)

    return jsonify({"variations": [_variation_result(v) for v in variations]})


@app.route("/api/regenerate", methods=["POST"])
def regenerate():
    body = request.get_json(silent=True) or {}
    previous_analysis = body.get("analysis")
    reference_bpm = body.get("bpm")

    if not isinstance(previous_analysis, dict):
        return jsonify({"error": "이전 분석 결과가 없습니다. 먼저 곡을 분석해주세요."}), 400

    try:
        variations = regenerate_variations(previous_analysis, reference_bpm)
    except Exception as e:
        return _gemini_error_response(e)

    return jsonify({"variations": [_variation_result(v) for v in variations]})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)

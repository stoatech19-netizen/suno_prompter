import os
import subprocess
import threading
import time
import traceback
import uuid

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from analyzer import (
    CATEGORY_TEMPO_HINTS,
    CTA_LANGUAGE_NAMES,
    CTA_TEMPO_HINTS,
    VARIATION_BATCH_SIZE,
    analyze_category,
    analyze_with_gemini,
    build_cta_lyrics,
    build_cta_suno_prompt,
    build_lyrics_structure,
    build_suno_prompt,
    extract_local_features,
    generate_cta,
    regenerate_cta,
    regenerate_variations,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {".mp3", ".wav"}
# Only the first 90s gets re-encoded and sent to Gemini (see
# _trim_audio_bytes), so this just needs to comfortably fit a full-length
# uncompressed WAV of a single song, not Gemini's own inline data limit.
MAX_CONTENT_LENGTH = 150 * 1024 * 1024  # 150MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # dev only: always serve fresh static files


def _get_app_version():
    """Short git commit hash + commit date, shown in the settings dialog so
    the user (and support) can tell which auto-updated revision is running
    (run.bat pulls on every launch -- there's no separate app version to
    bump). Falls back to "dev" if this isn't a git checkout or git isn't on
    PATH, so it never breaks the page."""
    try:
        output = subprocess.check_output(
            ["git", "-C", BASE_DIR, "log", "-1", "--format=%h (%cd)", "--date=format:%Y-%m-%d"],
            stderr=subprocess.DEVNULL, timeout=3,
        )
        return output.decode("utf-8", "replace").strip() or "dev"
    except Exception:
        return "dev"


APP_VERSION = _get_app_version()

# The desktop shortcut runs this server with its console window hidden (see
# launch.vbs), so there's no window for the user to close to stop it. Instead
# the page itself pings /api/heartbeat while open; if no ping arrives for a
# while (tab/browser closed, or the PC put the page to sleep for good), this
# watcher thread shuts the process down so it doesn't linger invisibly.
_HEARTBEAT_TIMEOUT_SECONDS = 15
_last_heartbeat_at = None
_heartbeat_lock = threading.Lock()


def _watch_heartbeat():
    while True:
        time.sleep(3)
        with _heartbeat_lock:
            last = _last_heartbeat_at
        if last is not None and time.time() - last > _HEARTBEAT_TIMEOUT_SECONDS:
            print("[server] No browser heartbeat received - shutting down.", flush=True)
            os._exit(0)


def _variation_result(analysis, fallback_bpm=None, fixed_tags=None):
    bpm = analysis.get("bpm") or fallback_bpm
    return {
        "analysis": analysis,
        "suno_prompt": build_suno_prompt(analysis, bpm, fixed_tags=fixed_tags),
        "title": analysis.get("title"),
        "lyrics_structure": build_lyrics_structure(analysis),
        "bpm": bpm,
    }


def _cta_variation_result(analysis, fixed_tags=None):
    bpm = analysis.get("bpm")
    return {
        "analysis": analysis,
        "suno_prompt": build_cta_suno_prompt(analysis, bpm, fixed_tags=fixed_tags),
        "title": analysis.get("title"),
        "lyrics_structure": build_cta_lyrics(analysis),
        "bpm": bpm,
    }


def _cta_language_from(value):
    language = (value or "ko").strip().lower()
    return language if language in CTA_LANGUAGE_NAMES else "ko"


def _cta_tempo_from(value):
    tempo = (value or "medium").strip().lower()
    return tempo if tempo in CTA_TEMPO_HINTS else "medium"


def _category_tempo_from(value):
    tempo = (value or "medium").strip().lower()
    return tempo if tempo in CATEGORY_TEMPO_HINTS else "medium"


def _fixed_tags_from_list(value):
    if not isinstance(value, list):
        return None
    tags = [str(v).strip() for v in value if str(v).strip()]
    return tags or None


def _api_keys_from_list(value):
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _missing_api_keys_response():
    return jsonify({"error": "Gemini API 키가 설정되지 않았습니다. 설정(⋮) 메뉴에서 키를 추가해주세요."}), 400


def _gemini_error_response(e):
    print("[analyze error]", flush=True)
    traceback.print_exc()
    if isinstance(e, RuntimeError):
        return jsonify({"error": str(e)}), 500
    message = str(e)
    upper = message.upper()
    if "429" in message or "RESOURCE_EXHAUSTED" in upper:
        return jsonify({"error": "Gemini API 무료 한도를 초과했습니다. 잠시 후 다시 시도해주세요."}), 429
    if "403" in message or "PERMISSION_DENIED" in upper:
        return jsonify({"error": "Gemini API 키(프로젝트)가 접근이 거부된 상태입니다. API 키 상태를 확인해주세요."}), 403
    if "503" in message or "UNAVAILABLE" in upper:
        return jsonify({"error": "Gemini 서버가 일시적으로 혼잡합니다 (503). 잠시 후 다시 시도해주세요."}), 503
    if "500" in message or ("INTERNAL" in upper and "PERMISSION" not in upper):
        return jsonify({"error": "Gemini 서버에 일시적인 오류가 발생했습니다 (500). 잠시 후 다시 시도해주세요."}), 502
    return jsonify({"error": f"분석 중 오류가 발생했습니다 ({message[:120]}). 잠시 후 다시 시도해주세요."}), 500


@app.errorhandler(RequestEntityTooLarge)
def _handle_too_large(e):
    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({"error": f"파일이 너무 큽니다. {max_mb}MB 이하의 mp3/wav 파일만 업로드할 수 있습니다."}), 413


@app.route("/")
def index():
    return render_template("index.html", app_version=APP_VERSION)


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    global _last_heartbeat_at
    with _heartbeat_lock:
        _last_heartbeat_at = time.time()
    return "", 204


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

    api_keys = _api_keys_from_list(request.form.getlist("api_keys"))
    if not api_keys:
        return _missing_api_keys_response()

    fixed_tags = _fixed_tags_from_list(request.form.getlist("fixed_tags"))

    temp_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    try:
        file.save(temp_path)

        local_features = extract_local_features(temp_path)

        try:
            analysis = analyze_with_gemini(temp_path, local_features, api_keys)
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
                analysis, local_features.get("bpm"), api_keys, count=VARIATION_BATCH_SIZE - 1
            )
        except Exception:
            extra = []

        variations = [_variation_result(analysis, local_features.get("bpm"), fixed_tags)]
        variations += [_variation_result(v, fixed_tags=fixed_tags) for v in extra]

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
    tempo = _category_tempo_from(body.get("tempo"))
    fixed_tags = _fixed_tags_from_list(body.get("fixed_tags"))
    api_keys = _api_keys_from_list(body.get("api_keys"))
    # The browser's own toggle, not a Gemini-decided guess -- whether to
    # append the user's fixed style tags (written for generic high-energy
    # retail BGM, which can fight a calm/mellow request) is now entirely
    # up to the user.
    apply_fixed_tags = bool(body.get("apply_fixed_tags", True))

    if not category:
        return jsonify({"error": "카테고리를 입력해주세요."}), 400
    if not api_keys:
        return _missing_api_keys_response()

    try:
        variations = analyze_category(category, api_keys, tempo=tempo)
    except Exception as e:
        return _gemini_error_response(e)

    effective_fixed_tags = fixed_tags if apply_fixed_tags else []
    return jsonify({
        "variations": [_variation_result(v, fixed_tags=effective_fixed_tags) for v in variations],
    })


@app.route("/api/generate-cta", methods=["POST"])
def generate_cta_route():
    body = request.get_json(silent=True) or {}
    keyword = (body.get("keyword") or "").strip()
    language = _cta_language_from(body.get("language"))
    tempo = _cta_tempo_from(body.get("tempo"))
    fixed_tags = _fixed_tags_from_list(body.get("fixed_tags"))
    api_keys = _api_keys_from_list(body.get("api_keys"))
    apply_fixed_tags = bool(body.get("apply_fixed_tags", True))

    if not keyword:
        return jsonify({"error": "키워드를 입력해주세요."}), 400
    if not api_keys:
        return _missing_api_keys_response()

    try:
        variations = generate_cta(keyword, language, tempo, api_keys)
    except Exception as e:
        return _gemini_error_response(e)

    effective_fixed_tags = fixed_tags if apply_fixed_tags else []
    return jsonify({
        "variations": [_cta_variation_result(v, effective_fixed_tags) for v in variations],
    })


@app.route("/api/regenerate-cta", methods=["POST"])
def regenerate_cta_route():
    body = request.get_json(silent=True) or {}
    previous_analysis = body.get("analysis")
    language = _cta_language_from(body.get("language"))
    tempo = _cta_tempo_from(body.get("tempo"))
    fixed_tags = _fixed_tags_from_list(body.get("fixed_tags"))
    api_keys = _api_keys_from_list(body.get("api_keys"))
    # Carried over from the batch's original generate-cta response (the
    # browser resends the toggle's last value on every regenerate).
    apply_fixed_tags = bool(body.get("apply_fixed_tags", True))

    if not isinstance(previous_analysis, dict):
        return jsonify({"error": "이전 분석 결과가 없습니다. 먼저 생성해주세요."}), 400
    if not api_keys:
        return _missing_api_keys_response()

    try:
        variations = regenerate_cta(previous_analysis, language, tempo, api_keys)
    except Exception as e:
        return _gemini_error_response(e)

    effective_fixed_tags = fixed_tags if apply_fixed_tags else []
    return jsonify({
        "variations": [_cta_variation_result(v, effective_fixed_tags) for v in variations],
    })


@app.route("/api/regenerate", methods=["POST"])
def regenerate():
    body = request.get_json(silent=True) or {}
    previous_analysis = body.get("analysis")
    reference_bpm = body.get("bpm")
    fixed_tags = _fixed_tags_from_list(body.get("fixed_tags"))
    api_keys = _api_keys_from_list(body.get("api_keys"))
    # See regenerate_cta_route: carried over from the category batch's
    # original /api/analyze-category response. The file upload tab never
    # sends this (it has no toggle), so it defaults to True -- always
    # applies the fixed tags, as before.
    apply_fixed_tags = bool(body.get("apply_fixed_tags", True))
    # Only the BGM keyword tab sends this (it has a tempo selector); the
    # file upload tab sends nothing, so it keeps the old per-variation
    # diverse-bpm behavior (see regenerate_variations).
    raw_tempo = body.get("tempo")
    tempo = _category_tempo_from(raw_tempo) if raw_tempo else None

    if not isinstance(previous_analysis, dict):
        return jsonify({"error": "이전 분석 결과가 없습니다. 먼저 곡을 분석해주세요."}), 400
    if not api_keys:
        return _missing_api_keys_response()

    try:
        variations = regenerate_variations(previous_analysis, reference_bpm, api_keys, tempo=tempo)
    except Exception as e:
        return _gemini_error_response(e)

    effective_fixed_tags = fixed_tags if apply_fixed_tags else []
    return jsonify({
        "variations": [_variation_result(v, fixed_tags=effective_fixed_tags) for v in variations],
    })


if __name__ == "__main__":
    threading.Thread(target=_watch_heartbeat, daemon=True).start()
    app.run(host="127.0.0.1", port=5001, debug=True)

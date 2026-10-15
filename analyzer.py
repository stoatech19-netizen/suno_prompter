"""Audio feature extraction + Gemini-based style analysis for Suno prompt generation."""
import json
import time

import numpy as np
import librosa
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-3.6-flash"

# Tags that always get appended to the generated Suno Style prompt (e.g.
# intro feel, loop behavior) unless the caller (the browser, which persists
# its own copy in localStorage) supplies its own list — see build_suno_prompt.
# Phrased positively (no "no build-up"/"intro") since negative instructions
# are less reliable for Suno to follow than stating what should happen instead.
DEFAULT_FIXED_STYLE_TAGS = [
    "full-energy hook hits from the very first second",
    "relentless driving rhythm with unbroken momentum",
    "wall-of-sound density at uniform peak intensity throughout",
    "seamless repeating loop with identical energy at every point",
    "punchy analog-saturated mix with tight, warm low end",
]

# Same idea as DEFAULT_FIXED_STYLE_TAGS, but for CTA (complete, vocal) songs
# — deliberately NOT loop/no-sag tags, since a CTA track has normal song
# structure. See build_cta_suno_prompt.
DEFAULT_CTA_FIXED_STYLE_TAGS = [
    "catchy, singable chorus hook that's easy to repeat after one listen",
    "polished mix with a clear, present lead vocal",
]

# API keys are supplied by the caller per request (entered in the browser's
# settings dialog, never read from an environment variable or a file), so
# that when one hits its free-tier quota, requests roll over to the next
# one instead of failing. `_key_index` just remembers the last-known-good
# key across calls so a later request doesn't re-try broken keys from
# scratch; it's reset implicitly by the modulo below if the key list
# shrinks or grows between calls.
_key_index = 0


# Errors worth retrying on the *next* key: quota exhaustion (429), a
# project being denied/suspended (403 — e.g. "Your project has been denied
# access"), and transient server-side failures (500/503). A 400-class error
# is about the request itself and would fail identically on every key, so
# it is deliberately NOT included here and is re-raised immediately.
_RETRYABLE_STATUS_CODES = {"429", "403", "500", "503"}
_RETRYABLE_MARKERS = (
    "RESOURCE_EXHAUSTED", "PERMISSION_DENIED", "UNAVAILABLE", "INTERNAL",
)


def _is_retryable_key_error(e):
    message = str(e)
    if message[:3] in _RETRYABLE_STATUS_CODES:
        return True
    upper = message.upper()
    return any(marker in upper for marker in _RETRYABLE_MARKERS)


def _generate_with_rotation(contents, config, api_keys):
    """Call Gemini, rotating through the given API keys whenever the
    current one fails with a key/project-level error (quota, permission
    denial, transient server error). Starts from the last-known-good key
    index so subsequent calls don't re-try broken keys from scratch."""
    keys = [k.strip() for k in (api_keys or []) if k and k.strip()]
    if not keys:
        raise RuntimeError(
            "Gemini API 키가 설정되지 않았습니다. 설정(⋮) 메뉴에서 키를 추가해주세요."
        )

    global _key_index
    last_err = None
    # Even with a single key, retry at least once on a retryable error:
    # Gemini's 503 "high demand" spikes are usually gone within a couple
    # seconds, and without this a lone key would fail on the first blip
    # with nothing left to rotate to.
    attempts = max(len(keys), 2)
    for i in range(attempts):
        idx = (_key_index + i) % len(keys)
        try:
            client = genai.Client(api_key=keys[idx])
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=contents, config=config
            )
            _key_index = idx
            return response
        except Exception as e:
            last_err = e
            if _is_retryable_key_error(e):
                if i < attempts - 1:
                    time.sleep(1.5)
                continue
            raise
    raise last_err


# finish_reason values that mean Gemini deliberately withheld the response
# rather than something going wrong on our end; worth telling the user about
# specifically instead of a generic "something went wrong".
_BLOCKED_FINISH_REASONS = {
    "SAFETY": "Gemini의 안전 정책으로 인해 이번 요청이 차단되었습니다. 다른 키워드나 표현으로 다시 시도해주세요.",
    "PROHIBITED_CONTENT": "Gemini의 안전 정책으로 인해 이번 요청이 차단되었습니다. 다른 키워드나 표현으로 다시 시도해주세요.",
    "BLOCKLIST": "Gemini의 안전 정책으로 인해 이번 요청이 차단되었습니다. 다른 키워드나 표현으로 다시 시도해주세요.",
    "SPII": "Gemini의 안전 정책으로 인해 이번 요청이 차단되었습니다. 다른 키워드나 표현으로 다시 시도해주세요.",
    "RECITATION": "Gemini가 저작권 보호 콘텐츠와 유사하다고 판단해 응답을 거부했습니다. 다시 시도해주세요.",
    "MAX_TOKENS": "응답이 길이 제한을 초과해 잘렸습니다. 잠시 후 다시 시도해주세요.",
}


def _response_finish_reason_name(response):
    candidates = response.candidates or []
    finish_reason = candidates[0].finish_reason if candidates else None
    return getattr(finish_reason, "name", None) or (str(finish_reason) if finish_reason else None)


def _response_json(response):
    """Parse a Gemini JSON response, raising a clear RuntimeError instead of
    a bare TypeError/JSONDecodeError when Gemini didn't actually return a
    complete, well-formed JSON payload: either no usable candidate at all
    (response.text is None -- blocked by safety filters, blocked by
    copyright/recitation matching) or a candidate that got cut off
    mid-response by the token limit (text is present but truncated, so it's
    not valid JSON). Without this, json.loads() blows up with a message
    that tells the user nothing, surfacing as a generic 500 with no
    indication of why."""
    text = response.text
    if text:
        try:
            return json.loads(text)
        except ValueError:
            reason_name = _response_finish_reason_name(response)
            raise RuntimeError(
                _BLOCKED_FINISH_REASONS.get(
                    reason_name,
                    "Gemini 응답을 해석할 수 없습니다 (형식 오류). 잠시 후 다시 시도해주세요.",
                )
            )

    reason_name = _response_finish_reason_name(response)
    raise RuntimeError(
        _BLOCKED_FINISH_REASONS.get(
            reason_name,
            "Gemini로부터 빈 응답을 받았습니다. 잠시 후 다시 시도해주세요.",
        )
    )

# Krumhansl-Schmuckler key profiles
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

GEMINI_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string"},
        "sub_genre": {"type": "string"},
        "mood": {"type": "array", "items": {"type": "string"}},
        "instruments": {"type": "array", "items": {"type": "string"}},
        "vocal_style": {"type": "string"},
        "era_influence": {"type": "string"},
        "energy_level": {"type": "string"},
        "production_quality": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
        "lyrics_structure": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "genre", "mood", "instruments", "vocal_style", "energy_level",
        "production_quality", "title", "lyrics_structure",
    ],
}

# A batch of variations is requested per regenerate click (numbered,
# browsable with prev/next) instead of one at a time, since the shared
# reference-analysis text only needs to be sent once per batch either way.
VARIATION_BATCH_SIZE = 4

# Same shape as the initial analysis, plus a suggested bpm for the variation
# (the initial analysis instead relies on librosa's measured bpm).
GEMINI_VARIATION_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        **GEMINI_ANALYSIS_SCHEMA["properties"],
        "bpm": {"type": "integer"},
    },
    "required": GEMINI_ANALYSIS_SCHEMA["required"] + ["bpm"],
}

def _variations_schema(count, with_input_style=False):
    schema = {
        "type": "object",
        "properties": {
            "variations": {
                "type": "array",
                "items": GEMINI_VARIATION_ITEM_SCHEMA,
                "minItems": count,
                "maxItems": count,
            },
        },
        "required": ["variations"],
    }
    if with_input_style:
        # Lets the caller (app.py) know whether the free-text request was a
        # product/category keyword or a literal music description, so it can
        # skip appending the user's "고정 스타일 태그" fixed tags for the
        # latter -- those tags assume generic high-energy retail BGM and
        # would otherwise clash with e.g. a request for calm cafe music.
        schema["properties"]["input_style"] = {
            "type": "string",
            "enum": ["category", "literal"],
        }
        schema["required"].append("input_style")
    return schema


def extract_local_features(file_path):
    """Return objective audio features via librosa: duration, bpm, key, mode.

    Any single measurement that fails is set to None rather than aborting the
    whole extraction, since the Gemini analysis can still proceed without it.
    """
    features = {"duration_sec": None, "bpm": None, "key": None, "mode": None}
    try:
        y, sr = librosa.load(file_path, sr=None, mono=True)
    except Exception:
        return features

    features["duration_sec"] = round(len(y) / sr, 1)

    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        features["bpm"] = round(float(np.asarray(tempo).item()))
    except Exception:
        pass

    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = chroma.mean(axis=1)
        best_score, best_key, best_mode = -np.inf, None, None
        for shift in range(12):
            major_score = np.corrcoef(np.roll(_MAJOR_PROFILE, shift), chroma_mean)[0, 1]
            minor_score = np.corrcoef(np.roll(_MINOR_PROFILE, shift), chroma_mean)[0, 1]
            if major_score > best_score:
                best_score, best_key, best_mode = major_score, _PITCH_CLASSES[shift], "major"
            if minor_score > best_score:
                best_score, best_key, best_mode = minor_score, _PITCH_CLASSES[shift], "minor"
        features["key"] = best_key
        features["mode"] = best_mode
    except Exception:
        pass

    return features


def _trim_audio_bytes(file_path, max_seconds=90):
    """Load only the first max_seconds of audio and re-encode to a small WAV
    buffer, to keep Gemini request size/token cost down."""
    import soundfile as sf
    import io

    y, sr = librosa.load(file_path, sr=22050, mono=True, duration=max_seconds)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def analyze_with_gemini(file_path, local_features, api_keys):
    """Send a trimmed audio clip to Gemini and return the structured style analysis."""
    audio_bytes = _trim_audio_bytes(file_path)

    hint_parts = []
    if local_features.get("bpm"):
        hint_parts.append(f"measured tempo is approximately {local_features['bpm']} BPM")
    if local_features.get("key"):
        hint_parts.append(f"measured musical key is approximately {local_features['key']} {local_features['mode']}")
    hints = (" (" + "; ".join(hint_parts) + ")") if hint_parts else ""

    prompt = (
        "Listen to this music clip and describe its style for use as a reference "
        "to generate a NEW, INSTRUMENTAL-ONLY track (no vocals, regardless of "
        "whether this reference clip has vocals) with Suno.ai" + hints + ". "
        "Your goal is NOT just to land in the right genre bucket — it is to "
        "capture THIS SPECIFIC clip's own rhythmic feel, exact instrumentation/"
        "playing technique, and production texture closely enough that a track "
        "built from your description would sound like a close stylistic sibling "
        "of this one, not a generic example of the genre. Listen closely and "
        "describe what is actually there, even if it's an unusual or less common "
        "combination for the genre. "
        "Respond with: genre, a specific and characterful sub-genre (avoid the "
        "single most obvious/generic label for this genre — pick out what makes "
        "this particular clip distinctive), a short but vivid list of mood/energy "
        "descriptors that capture this clip's specific emotional character and "
        "intensity (be as specific as the clip warrants, not generic filler like "
        "'upbeat' or 'chill' alone — e.g. 'wistful and unresolved', 'defiant and "
        "driving', 'hazy and weightless'), and a list of 4 to 6 specific "
        "instruments/textures chosen to genuinely fit the mood/energy and genre "
        "you just identified — NOT a generic 'rich, professional arrangement' "
        "template. Cover a rhythm layer, a melodic/harmonic layer, and at least "
        "one distinctive textural element, but let the actual instruments vary "
        "widely with the genre and mood (e.g. felt piano and warm strings for a "
        "wistful acoustic mood, distorted guitars and live drums for a driving "
        "rock mood, sparse pads and field-recording texture for a hazy ambient "
        "mood, chopped vocal samples and boom-bap drums for a hip-hop mood). Do "
        "NOT default to a funk/disco/synth-pop palette (slap bass, FM electric "
        "piano, brass stabs, drum machine) unless the identified genre and mood "
        "genuinely call for it — avoid bland single-word generics like 'synth' "
        "or 'drums' alone, and instead name the specific instrument/technique/ "
        "timbre that this particular genre/era/mood combination would actually "
        "use. Critically, for the rhythm-layer entry, describe HOW this clip's "
        "groove is actually played, not just what the instrument is — name the "
        "concrete rhythmic feel using vocabulary like 'syncopated 16th-note "
        "hi-hats', 'swung boom-bap drum groove', 'four-on-the-floor kick with "
        "off-beat bass stabs', 'shuffled triplet feel', or 'ghost-note snare "
        "fills', matched to whatever this specific clip's groove really sounds "
        "like. Also give a short list of 1 to 3 production/mix "
        "quality descriptors, but they must name the SPECIFIC audible effects/ "
        "processing character you actually hear in this clip — concrete texture "
        "words like 'tape-saturated warmth', 'plate reverb wash', 'sidechain-"
        "pumping pads', 'vinyl crackle texture', 'slapback echo', 'tight punchy "
        "compression', or 'wide chorused stereo synths' — NOT vague praise like "
        "'polished mix' or 'professional production' that describes nothing "
        "specific, and NOT technical engineering jargon like exact dB/ms/Hz "
        "values or plugin names, since Suno responds to descriptive texture "
        "language, not mixing parameters. A brief "
        "description of this reference clip's own vocal style (or 'instrumental' "
        "if none — for information only, it will not be used in the generated "
        "track), the decade/era the style evokes, an overall energy level "
        "(e.g. low/mid/high), a short fitting title for the new instrumental "
        "track, in ENGLISH ONLY, using simple, everyday, concrete words that let "
        "someone grasp the song's mood at a glance (e.g. 'Sunny Morning', 'Warm "
        "Afternoon') — avoid abstract, literary, or difficult vocabulary that needs "
        "interpreting (e.g. 'Ephemeral Reverie'), and a lyrics_structure array: an ordered list of Suno bracket "
        "song-structure meta-tags for this new track's arrangement. This "
        "track is CONTINUOUS BACKGROUND MUSIC for a home-shopping broadcast — "
        "it plays underneath a presenter for long stretches and gets looped/"
        "cut at arbitrary points, so it must NOT develop like a song with a "
        "beginning, middle, and end. Build it around ONE central hook/groove "
        "that essentially repeats for the whole track, not a sequence of new "
        "musical ideas: use only 2 to 3 sections, and it's fine — often "
        "better — to reuse the exact same section tag more than once in the "
        "array when a later section really is just a repeat of an earlier "
        "one (e.g. [\"[Main Hook Groove]\", \"[Main Hook Groove + Extra "
        "Layer]\", \"[Main Hook Groove]\"]); do not invent a fresh-sounding "
        "name for every section just for variety, since each new name "
        "signals Suno to generate new content there instead of repeating. "
        "The very first section must already BE the core hook at its real, "
        "full energy — not a quieter or simpler 'intro' version of it — "
        "because it also has to be what the track sounds like if it loops "
        "back to the start. Do NOT automatically bookend the track with a "
        "separate [Intro] section and a separate [Outro] section — that "
        "beginning-middle-end shape is itself a small narrative arc. Keep "
        "the arrangement steady and loop-friendly rather than a narrative "
        "arc: avoid stacking dramatic-development tags like [Buildup] into "
        "[Breakdown] into [Bridge]; at most one section may add or drop a "
        "single layer, nothing more. Within this 2-to-3-section budget, let "
        "the section count mirror how repetitive or varied the REFERENCE "
        "clip itself actually is: if the reference is essentially one groove "
        "on a loop, use 2 sections that are near-literal repeats of each "
        "other; if it has one clearly recurring secondary texture or layer, "
        "use that as the 'plus extra layer' section instead of inventing a "
        "new idea. The energy and dynamism must stay "
        "exactly as strong across EVERY section as the first — do not "
        "gradually build up from a quiet start, and do not wind down or "
        "fade out at the end. Favor section names that describe the "
        "instrumentation/texture of that specific passage (e.g. "
        "\"[Strings Layer]\", \"[Rhythmic Break]\") rather than positional/"
        "narrative words like \"start\", \"intro\", \"buildup\", "
        "\"breakdown\", \"fade\", or \"outro\", since those imply a "
        "rising-and-falling story arc instead of a steady, repeating loop. "
        "Do not include any vocal or lyric section tags like [Verse] "
        "or [Chorus]."
    )

    response = _generate_with_rotation(
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GEMINI_ANALYSIS_SCHEMA,
        ),
        api_keys=api_keys,
    )
    return _response_json(response)


def analyze_category(category, api_keys, count=VARIATION_BATCH_SIZE):
    """Text-only call (no audio/reference track at all) that asks Gemini to
    suggest background-music styles fitting a free-text description, which
    can be EITHER a home-shopping product/category keyword (e.g. '주방가전',
    '50대 여성 패션') OR a direct natural-language description of the music
    itself (e.g. '카페에서 틀기 좋은 잔잔한 음악', '국악을 재즈 오케스트라랑
    퓨전시킨 음악') — see the prompt below for how each is handled. Returns a
    tuple of (list of `count` variation dicts in the same shape as
    regenerate_variations, input_style -- "category" or "literal", so the
    caller knows whether to apply the user's fixed style tags)."""
    prompt = (
        "You are creating INSTRUMENTAL background music to fit a free-text request. "
        f"The request is: '{category}'. "
        "This request is given in one of two styles — decide which one applies before "
        "generating anything, based on what the text itself says:\n"
        "(A) A product/category description for a Korean home-shopping (홈쇼핑/TV shopping) "
        "broadcast, optionally combined with a target audience — such as an age group and/or "
        "gender alongside the product (e.g. '주방가전', '식품', '50대 여성 패션' = fashion for "
        "women in their 50s, '20대 남성 뷰티' = beauty products for men in their 20s). For this "
        "style, infer the music mood/tempo/genre from home-shopping broadcast conventions (e.g. "
        "warm and cozy for kitchen appliances, fresh and upbeat for food, clean and modern for "
        "electronics, urgent and exciting for fashion/beauty sale events), adjusted for the "
        "target audience's taste where one is given (e.g. an older audience generally favors a "
        "more classic, less aggressive sound than a younger audience for the same category), and "
        "keep it energetic enough to hold viewer attention and encourage purchase.\n"
        "(B) A direct, free-form description of the music itself — its mood, genre, fusion, "
        "instrumentation, or a scene/usage it should suit — e.g. '카페에서 틀기 좋은 잔잔한 음악' "
        "(mellow music good for a cafe), '패션쇼에 어울리는 비트감 있는 edm 음악' (beat-driven EDM "
        "fitting a fashion show), '긴장감 넘치는 인트로 음악' (a tense, suspenseful intro feel), "
        "'국악을 재즈 오케스트라랑 퓨전시킨 음악' (Korean traditional gugak fused with a jazz "
        "orchestra). For this style, follow the description LITERALLY as the creative brief — do "
        "NOT reinterpret it as a retail product and do NOT force a 'persuade the viewer to buy' "
        "energy onto it. If the description calls for something calm, mellow, tense, or ambient, "
        "the music must actually BE calm, mellow, tense, or ambient — never pushed toward upbeat "
        "sales energy just because this tool is normally used for shopping BGM. Treat any genre, "
        "fusion, instrument, or scene the text names as a firm creative direction to honor, not a "
        "hint to drift away from.\n"
        f"Generate {count} DISTINCT variations of the result. If the request is style (A), or is "
        "style (B) but broad/open-ended about genre, make the options clearly distinct from each "
        "other (different genre, mood/energy, tempo, and instrumentation) — avoid defaulting to "
        "the single most obvious/generic choice, and avoid letting every option converge on the "
        "same funk/disco/synth-pop instrument palette (slap bass, FM electric piano, brass stabs, "
        "drum machine); pick specific, characterful sub-genres and let each option's own distinct "
        "mood/energy (e.g. one warm and cozy, one urgent and driving, one bright and playful) "
        "genuinely drive its instrument choices — could be orchestral, acoustic, rock, hip-hop, "
        "ambient, electronic, world, etc., whatever best fits that option's mood. If instead the "
        "request is style (B) and already names a specific genre, fusion, or mood (e.g. "
        "'국악-재즈 퓨전', '잔잔한 카페 음악'), keep ALL options within that SAME named genre/mood/ "
        "fusion — vary them through different arrangement, instrumentation choice, or tempo/energy "
        "nuance within that direction instead, never by swapping to an unrelated genre. All "
        "must be instrumental only (no vocals). Give each option its own plausible bpm, a vivid "
        "mood/energy list specific to that option (not generic filler like 'upbeat' alone), "
        "and a list of 4 to 6 specific instruments/textures chosen to genuinely fit that "
        "option's own mood/energy and genre — cover a rhythm layer, a melodic/harmonic layer, "
        "and at least one distinctive textural or signature element; avoid bland single-word "
        "generics like 'synth' or 'drums' alone, instead name the specific instrument/technique/ "
        "timbre that this option's own genre/mood would actually use. Also give each "
        "option a short list of 1 to 3 production/mix quality descriptors that convey a rich, "
        "professionally arranged, non-generic sound (e.g. 'multi-layered arrangement', "
        "'dynamic professional production', 'clean modern mix', 'warm analog', 'live-band "
        "energy') — avoid bland/generic descriptors, and a short title in ENGLISH "
        "ONLY, using simple, everyday, concrete words that let someone grasp the "
        "mood at a glance (e.g. 'Bright Morning', 'Warm Kitchen') — avoid abstract, "
        "literary, or difficult vocabulary that needs interpreting (e.g. 'Ephemeral "
        "Reverie'). Also give an ordered "
        "lyrics_structure array of Suno bracket song-structure meta-tags for that option's "
        "arrangement. This is CONTINUOUS BACKGROUND MUSIC that plays underneath a presenter "
        "for long stretches and gets looped/cut at arbitrary points, so it must NOT develop "
        "like a song with a beginning, middle, and end. Build each option around ONE central "
        "hook/groove that essentially repeats for the whole track, not a sequence of new "
        "musical ideas: use only 2 to 3 sections, and it's fine — often better — to reuse the "
        "exact same section tag more than once in the array when a later section really is "
        "just a repeat of an earlier one (e.g. [\"[Main Hook Groove]\", \"[Main Hook Groove + "
        "Extra Layer]\", \"[Main Hook Groove]\"]); do not invent a fresh-sounding name for "
        "every section just for variety, since each new name signals Suno to generate new "
        "content there instead of repeating. The very first section must already BE the core "
        "hook at this option's own real, settled character — not a quieter or simpler 'intro' "
        "version of it, even if that character is itself calm/mellow — because it also has to "
        "be what the track sounds like if it loops back to the start. "
        "Do NOT automatically bookend every option with a separate [Intro] and a separate "
        "[Outro] section — that beginning-middle-end shape is itself a small narrative arc. "
        "Stay steady/loop-friendly rather than a narrative arc: avoid stacking dramatic-"
        "development tags like [Buildup] into [Breakdown] into [Bridge]; at most one section "
        "may add or drop a single layer, nothing more. The energy/dynamism must stay exactly "
        "as strong across EVERY section as the first — no gradual build-up from a quieter start "
        "and no wind-down/fade-out at the end — whatever that option's own energy level is, calm "
        "or intense. Favor section names that describe the "
        "instrumentation/texture of that passage (e.g. \"[Strings Layer]\", \"[Rhythmic "
        "Break]\") rather than positional/narrative words like \"start\", \"intro\", "
        "\"buildup\", \"breakdown\", \"fade\", or \"outro\". "
        "No vocal/lyric tags like [Verse] or [Chorus]. Also set input_style to \"category\" if "
        "you used interpretation (A) above, or \"literal\" if you used interpretation (B). "
        "Return the variations as a 'variations' array of "
        f"exactly {count} objects."
    )

    response = _generate_with_rotation(
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_variations_schema(count, with_input_style=True),
        ),
        api_keys=api_keys,
    )
    data = _response_json(response)
    return data.get("variations") or [], data.get("input_style")


def regenerate_variations(previous_analysis, reference_bpm, api_keys, count=VARIATION_BATCH_SIZE):
    """Text-only follow-up call (no audio re-sent) that asks Gemini for a
    batch of new variations that preserve the previous analysis's core
    mood/energy while varying genre, tempo, and instrument choices. Used
    both to seed the initial browsable batch (alongside the audio-grounded
    base analysis) and for the 'regenerate' button. Returns a list of
    `count` variation dicts."""
    if count <= 0:
        return []

    bpm_note = f" The previous variation's tempo was about {reference_bpm} BPM." if reference_bpm else ""
    prev_mood = previous_analysis.get("mood") or []
    mood_note = f" Its core mood/energy was: {', '.join(prev_mood)}." if prev_mood else ""

    prompt = (
        "Here is a previous music style analysis, as JSON, for an instrumental "
        "Suno.ai track:\n" + json.dumps(previous_analysis, ensure_ascii=False) + "\n\n"
        f"Generate {count} NEW variations that each stay in the same overall "
        "genre/vibe family AND, most importantly, preserve the SAME core "
        "mood/energy character as this previous analysis." + mood_note + " If the "
        "previous mood was bright and upbeat, every variation must still clearly "
        "read as bright and upbeat — do NOT drift into a different emotional "
        "register (e.g. do not turn it melancholic, moody, or aggressive) just "
        "to create variety. Create variety instead through: a different "
        "plausible tempo per variation (a new bpm value, distinct from before "
        "but still natural for this genre)," + bpm_note +
        " mood/energy descriptors that stay true to that same core character but with "
        "fresh, specific phrasing (not generic filler like 'upbeat' alone), and a fresh "
        "list of 4 to 6 specific instruments/textures per variation that express that SAME "
        "mood through a different genre/instrumentation lens — cover a rhythm layer, a "
        "melodic/harmonic layer, and at least one distinctive textural element, but let the "
        "actual instruments vary widely across variations (could be orchestral, acoustic, "
        "rock, hip-hop, ambient, electronic, world, etc. — whatever expresses that same mood "
        "differently). Do NOT let every variation converge on the same "
        "funk/disco/synth-pop palette (slap bass, FM electric piano, brass stabs, drum "
        "machine) — avoid bland single-word generics like 'synth' or 'drums' alone, instead "
        "name the specific instrument/technique/timbre that each variation's own genre "
        "would actually use, so each feels like a fresh but related take with a rich, "
        "professional arrangement — not a predictable or generic-sounding rehash. Every "
        "variation must also be clearly distinct from the others in the batch (different "
        "genre/instrumentation), not near-duplicates, while all sharing that same core mood. "
        "They must remain instrumental only (no vocals). Give each variation "
        "its own title, different from before and from each other, in ENGLISH ONLY, "
        "using simple, everyday, concrete words that let someone grasp the mood at "
        "a glance (e.g. 'Bright Morning', 'Warm Afternoon') — avoid abstract, "
        "literary, or difficult vocabulary that needs interpreting (e.g. 'Ephemeral "
        "Reverie'), "
        "its own short list of 1 to 3 production/mix quality descriptors that convey a rich, "
        "professionally arranged, non-generic sound (e.g. 'multi-layered arrangement', "
        "'dynamic professional production', 'clean modern mix', 'warm analog', 'live-band "
        "energy') — avoid bland/generic descriptors, "
        "and its own ordered lyrics_structure array of Suno bracket song-structure meta-tags "
        "for that variation's arrangement. This is CONTINUOUS BACKGROUND MUSIC that plays "
        "underneath a presenter for long stretches and gets looped/cut at arbitrary points, "
        "so it must NOT develop like a song with a beginning, middle, and end. Build each "
        "variation around ONE central hook/groove that essentially repeats for the whole "
        "track, not a sequence of new musical ideas: use only 2 to 3 sections, and it's fine "
        "— often better — to reuse the exact same section tag more than once in the array "
        "when a later section really is just a repeat of an earlier one (e.g. [\"[Main Hook "
        "Groove]\", \"[Main Hook Groove + Extra Layer]\", \"[Main Hook Groove]\"]); do not "
        "invent a fresh-sounding name for every section just for variety, since each new name "
        "signals Suno to generate new content there instead of repeating. The very first "
        "section must already BE the core hook at its real, full energy — not a quieter or "
        "simpler 'intro' version of it — because it also has to be what the track sounds like "
        "if it loops back to the start. Do NOT automatically bookend every variation with a "
        "separate [Intro] and a separate [Outro] section — that beginning-middle-end shape is "
        "itself a small narrative arc. Stay steady/loop-friendly rather than a narrative arc "
        "(no stacked [Buildup]->[Breakdown]->[Bridge] progressions); at most one section may "
        "add or drop a single layer, nothing more. The energy/dynamism must stay exactly as "
        "strong across EVERY section as the first — no gradual build-up from a quiet start "
        "and no wind-down/fade-out at the end. Favor section names that describe the "
        "instrumentation/texture of that passage (e.g. \"[Strings Layer]\", \"[Rhythmic "
        "Break]\") rather than positional/narrative words like \"start\", \"intro\", "
        "\"buildup\", \"breakdown\", \"fade\", or \"outro\". "
        "No vocal/lyric tags like [Verse] or [Chorus]. Return them as a 'variations' array of "
        f"exactly {count} objects."
    )

    response = _generate_with_rotation(
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_variations_schema(count),
        ),
        api_keys=api_keys,
    )
    return _response_json(response).get("variations") or []


def _trim_tags_to_budget(compose, mood_n, instr_n, prod_n, max_tags):
    """Shrink a composed tag list down to max_tags by dropping, in order:
    production quality (least essential) -> mood -> instruments, down to
    small floors, then further still as a last resort. Shared by both the
    instrumental and CTA prompt builders so their trimming behavior can't
    drift apart."""
    tags = compose(mood_n, instr_n, prod_n)
    while len(tags) > max_tags and prod_n > 0:
        prod_n -= 1
        tags = compose(mood_n, instr_n, prod_n)
    while len(tags) > max_tags and mood_n > 2:
        mood_n -= 1
        tags = compose(mood_n, instr_n, prod_n)
    while len(tags) > max_tags and instr_n > 3:
        instr_n -= 1
        tags = compose(mood_n, instr_n, prod_n)
    while len(tags) > max_tags and mood_n > 1:
        mood_n -= 1
        tags = compose(mood_n, instr_n, prod_n)
    while len(tags) > max_tags and instr_n > 1:
        instr_n -= 1
        tags = compose(mood_n, instr_n, prod_n)
    return tags


def _finalize_tags(tags, max_len):
    prompt = ", ".join(tags)
    if len(prompt) <= max_len:
        return prompt
    return prompt[: max_len - 1].rstrip(", ") + "…"


def build_suno_prompt(analysis, bpm, max_tags=15, max_len=1000, fixed_tags=None):
    """Assemble a comma-separated Suno 'Style of Music' string from the
    structured analysis, following Suno's current style-field guidance:
    front-load the most important tags (genre, then "instrumental", then
    era, then mood, then instrumentation, then production quality), keep
    the total tag count in the ~8-15 sweet spot (more than that and Suno
    starts dropping tags from the middle), and stay within the field's
    ~1000-character cap. Always instrumental — vocal style is intentionally
    left out of the prompt itself, and the "instrumental" tag is kept near
    the front since Suno weighs earlier tags more heavily.
    If the tag count still runs over budget, production quality is
    trimmed first (least essential), then mood, while instruments are kept
    as long as possible — a rich, varied instrument list is what keeps the
    generated arrangement from sounding generic, so it's protected longest."""
    genre_bits = [b for b in [analysis.get("genre"), analysis.get("sub_genre")] if b]
    era = analysis.get("era_influence")
    mood = analysis.get("mood") or []
    instruments = analysis.get("instruments") or []
    production = analysis.get("production_quality") or []
    energy = analysis.get("energy_level")
    if fixed_tags is None:
        fixed_tags = DEFAULT_FIXED_STYLE_TAGS

    def compose(mood_n, instr_n, prod_n):
        tags = []
        if genre_bits:
            tags.append(" ".join(genre_bits))
        tags.append("instrumental")
        if era:
            tags.append(era)
        tags.extend(mood[:mood_n])
        tags.extend(instruments[:instr_n])
        tags.extend(production[:prod_n])
        if energy:
            tags.append(energy)
        tags.extend(fixed_tags)
        if bpm:
            tags.append(f"{bpm} bpm")
        return tags

    mood_n, instr_n, prod_n = len(mood), len(instruments), len(production)
    tags = _trim_tags_to_budget(compose, mood_n, instr_n, prod_n, max_tags)
    return _finalize_tags(tags, max_len)


def build_lyrics_structure(analysis):
    """Join the model's ordered structure meta-tags into a block of text
    ready to paste into Suno's lyrics field, normalizing bracket formatting."""
    lines = []
    for item in analysis.get("lyrics_structure") or []:
        item = item.strip()
        if not item:
            continue
        if not (item.startswith("[") and item.endswith("]")):
            item = f"[{item}]"
        lines.append(item)
    return "\n".join(lines)


# --- CTA (call-to-action) songs: unlike the instrumental BGM modes above,
# these are complete, normally-structured songs WITH vocals, meant to
# promote a product/topic. They deliberately do not use the BGM
# DEFAULT_FIXED_STYLE_TAGS (seamless-loop/no-sag) since a full song with a
# beginning/middle/end is the opposite of a loop.

CTA_LANGUAGE_NAMES = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
}

# Each hint both sets the bpm band and, for "slow", clarifies that a
# laid-back tempo doesn't mean under-produced -- the glossy/maximalist
# polish from _CTA_GENRE_NOTE still applies regardless of tempo.
CTA_TEMPO_HINTS = {
    "fast": "FAST (~128-150 bpm) — festival EDM-pop or driving K-pop dance energy",
    "medium": "MEDIUM (~100-124 bpm) — glossy, danceable pop energy, not frantic",
    "slow": (
        "SLOW (~70-96 bpm) — a more laid-back tempo, but still fully "
        "polished and produced: think emotional pop/R&B-pop power "
        "ballad rather than EDM-driven, with the chorus still lifting "
        "into a fuller, bigger arrangement even at this slower pace"
    ),
}

GEMINI_CTA_SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string"},
        "sub_genre": {"type": "string"},
        "mood": {"type": "array", "items": {"type": "string"}},
        "instruments": {"type": "array", "items": {"type": "string"}},
        "vocal_style": {"type": "string"},
        "era_influence": {"type": "string"},
        "energy_level": {"type": "string"},
        "production_quality": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
        "bpm": {"type": "integer"},
        "lyrics_lines": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "genre", "mood", "instruments", "vocal_style", "energy_level",
        "production_quality", "title", "bpm", "lyrics_lines",
    ],
}


def _cta_variations_schema(count, with_input_style=False):
    schema = {
        "type": "object",
        "properties": {
            "variations": {
                "type": "array",
                "items": GEMINI_CTA_SCHEMA,
                "minItems": count,
                "maxItems": count,
            },
        },
        "required": ["variations"],
    }
    if with_input_style:
        # See _variations_schema's comment -- same purpose, for the CTA keyword.
        schema["properties"]["input_style"] = {
            "type": "string",
            "enum": ["category", "literal"],
        }
        schema["required"].append("input_style")
    return schema


# Defense in depth alongside the prompt's own safety instructions below,
# since lyrics_lines is free-form user-facing text that gets pasted
# straight into Suno. BLOCK_MEDIUM_AND_ABOVE (not BLOCK_LOW_AND_ABOVE): the
# "low" threshold blocks on the slightest trace of a flagged category,
# which produces frequent false-positive blocks on ordinary commercial
# jingle lyrics (worse for non-English languages); medium still blocks
# genuinely harmful content while cutting those false positives down.
_CTA_SAFETY_SETTINGS = [
    types.SafetySetting(category=category, threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)
    for category in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]

_CTA_LENGTH_NOTE = (
    "Suno times a generated song to the amount of lyric and section "
    "content it's given, NOT to any duration mentioned in the style tags "
    "— writing a short lyric gets a short (often under 1 minute) song "
    "regardless of what the style says. To reliably get a full ~2 to 3 "
    "minute song, use a complete structure: [Verse 1], [Pre-Chorus], "
    "[Chorus], [Verse 2], [Pre-Chorus], [Chorus], a short [Bridge], "
    "[Chorus] again, then [Outro]. Write 4 to 6 lyric lines for EACH "
    "verse/chorus/bridge section (never just 1-2 lines); [Pre-Chorus] "
    "sections can be shorter, 2 to 4 lines, since they're a quick rising "
    "transition rather than a full section. Reuse the exact same chorus "
    "lyrics every time [Chorus] appears, and aim for roughly 28 to 36 "
    "total lyric lines across the whole song (not counting the bracket "
    "tags themselves)."
)

_CTA_GENRE_NOTE = (
    "Lean into the sound of modern chart-topping pop/EDM/K-pop "
    "production — NOT a mellow, laid-back, or flat/plain-sounding "
    "arrangement. Each option should feel like a polished, maximalist, "
    "chart/radio-ready dance-pop track: glossy, punchy, wide-stereo "
    "production with heavy sub-bass/808s, a sidechain-pumping bass (bass "
    "ducks under the kick on every beat), stacked/doubled vocal "
    "harmonies on the hook, and a dense 'everything happening at once' "
    "chorus arrangement. Vary the FLAVOR across options within that "
    "space rather than drifting into acoustic/ambient/lo-fi/orchestral "
    "territory — e.g. one leaning festival EDM-pop with a synth drop, "
    "one leaning K-pop with chant-style group-vocal ad-libs and an "
    "aggressive trap-influenced beat, one leaning glossy four-on-the-"
    "floor dance-pop, one leaning bright synth-pop/electro-pop."
)

_CTA_DYNAMICS_NOTE = (
    "Give the arrangement real dynamic CONTRAST between sections instead "
    "of staying at one flat energy level throughout — this contrast is "
    "exactly what separates a professional-sounding track from a flat, "
    "AI-generated-sounding one. Keep verses noticeably SPARSER and more "
    "intimate (fewer layers, narrower/more centered sound, e.g. vocal + "
    "light beat only) than the chorus. Use [Pre-Chorus] to build rising "
    "tension right before each chorus (e.g. a rising synth riser, "
    "building drum energy, vocal intensity climbing). Make [Chorus] land "
    "with a real lift: the fullest, widest, most maximalist arrangement "
    "and the biggest low end of the whole song, carrying the song's most "
    "memorable melodic hook. You may add a short parenthetical staging "
    "note right after a bracket tag describing that section's "
    "arrangement — keep it to a few words, e.g. \"[Verse 1] (sparse, "
    "intimate, vocal + light beat only)\", \"[Pre-Chorus] (rising synth "
    "riser, building energy)\", or \"[Chorus] (full wide arrangement, "
    "stacked harmonies, heavy sidechained 808 bass, biggest moment of "
    "the song)\"."
)

_CTA_CONTENT_NOTE = (
    "IMPORTANT: Do NOT write the lyrics as product advertising copy — "
    "avoid describing the topic's features, price, quality, or any 'buy "
    "this now' sales pitch; that reads as awkward and unnatural in a "
    "song. Instead, let the lyrics freely express a simple, universal "
    "emotion that matches whichever genre/mood is actually being used for "
    "this option — for an upbeat pop/EDM/K-pop style, a warm, everyday "
    "feel-good mood (e.g. 'feeling good today', 'isn't there something "
    "fun out there?', 'daydreaming about something nice', 'a fluttering, "
    "excited feeling', or 'just plain happiness'); for a different named "
    "genre/mood (e.g. a ballad, or 트로트), the emotion that genre itself "
    "usually carries instead (e.g. heartfelt and sentimental for a "
    "ballad, warm nostalgia for 트로트) — but keep it simple either way. "
    "If a product/topic keyword was given, the lyrics do NOT need to "
    "mention it at all — treat it only as a loose mood/occasion cue (e.g. "
    "a season, a shopping trip, an everyday moment), never as something "
    "the song has to describe or sell."
)

_CTA_SAFETY_NOTE = (
    "The lyrics must be LIGHT and SIMPLE, with NO deep or complex "
    "meaning — think of a short, catchy, feel-good radio/TV jingle mood "
    "piece, not a narrative song with an artistic message. " + _CTA_CONTENT_NOTE +
    " The lyrics must be completely clean and safe: no profanity, sexual "
    "content, violence, hate speech, drugs, self-harm, political "
    "statements, or any other harmful or inappropriate content — "
    "suitable for a general TV shopping-channel audience of all ages."
)


def generate_cta(keyword, language, tempo, api_keys, count=VARIATION_BATCH_SIZE):
    """Text-only call that asks Gemini for `count` distinct, COMPLETE songs
    (with vocals and normal song structure) for a Korean home-shopping CTA,
    with lyrics written in the given language at the given tempo band. The
    keyword can be EITHER a product/topic/occasion to loosely nudge the
    vibe of (e.g. '여름 신상 원피스') OR a direct description of the song's
    own desired genre/mood (e.g. '트로트풍 홍보송', '발라드 느낌의 축하곡') —
    see the prompt below for how each is handled. Returns a tuple of
    (list of `count` variation dicts shaped like GEMINI_CTA_SCHEMA plus bpm,
    input_style -- "category" or "literal", so the caller knows whether to
    apply the user's fixed style tags)."""
    language_name = CTA_LANGUAGE_NAMES.get(language, "Korean")
    tempo_hint = CTA_TEMPO_HINTS.get(tempo, CTA_TEMPO_HINTS["medium"])
    prompt = (
        "You are writing a short, catchy CALL-TO-ACTION (CTA) song for a "
        f"Korean home-shopping/retail context. The request is: '{keyword}'. "
        "This request is given in one of two styles — decide which one "
        "applies before writing anything, based on what the text itself says:\n"
        "(A) A product/topic/occasion keyword (e.g. '여름 신상 원피스', '다이어트 "
        "보조제', '신규 가입 이벤트') that the song is only loosely inspired by. "
        "This is NOT a jingle that describes or sells that topic directly — "
        "it's a warm, upbeat feel-good mood piece the topic merely nudges the "
        "vibe of (see the lyrics guidance below).\n"
        "(B) A direct description of the SONG's own desired genre/mood/style — "
        "e.g. '트로트풍 홍보송' (a trot-style promo song), '발라드 느낌의 축하곡' "
        "(a ballad-style celebration song), '시티팝 느낌의 홍보 음악' (city-pop "
        "style promo music). For this style, build the song in THAT genre/mood "
        "literally — do NOT default to dance-pop/EDM/K-pop just because that's "
        "this tool's usual style.\n"
        "Either way, this is a COMPLETE, fully-formed song with normal song "
        "structure (e.g. intro, verse, chorus, possibly a bridge, outro) and it "
        "includes VOCALS — it is NOT a seamless instrumental loop. "
        f"Generate {count} DISTINCT options, each clearly different in "
        "mood/instrumentation from the others, but ALL options should "
        f"share the same {tempo_hint} tempo feel. If the request is style (A), "
        "or is style (B) but broad/open-ended about genre: " + _CTA_GENRE_NOTE +
        " If instead the request is style (B) and names a specific genre/mood, "
        "build ALL options in THAT SAME named genre/mood instead — ignore the "
        "chart-pop/EDM/K-pop direction above, vary the options through "
        "different instrumentation/vocal_style/arrangement nuance within that "
        "genre, and give production descriptors that convey polish appropriate "
        "to THAT genre's own idea of a professional recording (e.g. warm "
        "analog strings and tasteful reverb for a ballad, a lively "
        "accordion/trot rhythm section for 트로트) rather than generic glossy "
        "pop/EDM maximalism — but still keep it a complete, fully-produced, "
        "radio-ready CTA song in that genre, never a demo-quality rough "
        "sketch. Each option needs: genre, a specific sub_genre, a vivid mood/"
        "energy list, 4 to 6 specific instruments/textures matching whichever "
        "genre applies (a rhythm layer, a melodic/harmonic layer, and at "
        "least one distinctive textural element — for a pop/EDM/K-pop style "
        "e.g. 'sidechained 808 sub-bass', 'stacked supersaw synth lead', "
        "'punchy layered trap hi-hats', 'chant-style group vocal ad-libs'; "
        "for a different named genre, name THAT genre's own characteristic "
        "instruments instead), a vocal_style description (gender/tone/"
        "delivery, e.g. 'bright female pop vocals, powerful belted "
        "delivery'), era_influence, 1 to 3 production/mix quality "
        "descriptors naming specific textures that fit whichever genre "
        "applies (glossy/maximalist/chart-ready for a pop/EDM/K-pop style, "
        "or that other genre's own idea of a polished recording otherwise) "
        "— avoid vague/generic praise like 'professional' or 'radio-ready' "
        "alone, name the specific texture instead — "
        f"energy_level, a bpm matching that {tempo} tempo band, and a "
        "short title in ENGLISH ONLY using "
        "simple, everyday, concrete words. "
        "Also write lyrics_lines: an ORDERED array mixing Suno bracket "
        "section tags (e.g. \"[Verse 1]\", \"[Pre-Chorus]\", "
        "\"[Chorus]\", \"[Bridge]\", \"[Outro]\") with the actual lyric "
        "lines that follow each tag, in the exact order they should "
        "appear — a normal, COMPLETE song structure (NOT a short 2-3 "
        "section repeating loop). " + _CTA_LENGTH_NOTE + " " + _CTA_DYNAMICS_NOTE +
        f" Write the actual lyric lines (not the bracket tags) in "
        f"{language_name}. " + _CTA_SAFETY_NOTE + " Also set input_style to \"category\" if "
        "you used interpretation (A) above, or \"literal\" if you used interpretation (B). "
        f"Return the variations as a 'variations' array of exactly {count} objects."
    )

    response = _generate_with_rotation(
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_cta_variations_schema(count, with_input_style=True),
            safety_settings=_CTA_SAFETY_SETTINGS,
        ),
        api_keys=api_keys,
    )
    data = _response_json(response)
    return data.get("variations") or [], data.get("input_style")


def regenerate_cta(previous_analysis, language, tempo, api_keys, count=VARIATION_BATCH_SIZE):
    """Text-only follow-up call that asks Gemini for `count` new CTA song
    variations preserving the previous analysis's core mood/energy, for
    the 'regenerate' button on the CTA tab."""
    language_name = CTA_LANGUAGE_NAMES.get(language, "Korean")
    tempo_hint = CTA_TEMPO_HINTS.get(tempo, CTA_TEMPO_HINTS["medium"])
    prev_mood = previous_analysis.get("mood") or []
    mood_note = f" Its core mood/energy was: {', '.join(prev_mood)}." if prev_mood else ""

    prev_genre = previous_analysis.get("genre")
    genre_note = f" Its genre was: {prev_genre}." if prev_genre else ""

    prompt = (
        "Here is a previous CTA song style analysis, as JSON:\n"
        + json.dumps(previous_analysis, ensure_ascii=False) + "\n\n"
        f"Generate {count} NEW variations that stay in the SAME genre and "
        "overall vibe family as that previous analysis, preserving its core "
        "mood/energy character." + genre_note + mood_note + " "
        "Create variety through different instrumentation and "
        f"vocal_style, but ALL options should share the same {tempo_hint} "
        "tempo feel. Every option remains a COMPLETE song with "
        "vocals and normal song structure — NOT a repeating instrumental "
        "loop, and keeps the SAME production character as the previous "
        "analysis (whatever that genre's own idea of a polished recording "
        "is — e.g. glossy maximalist pop/EDM/K-pop if that's what it was, "
        "or a ballad's warm acoustic polish, or a trot arrangement's lively "
        "character — never drifting to a different genre's production "
        "style). " + _CTA_LENGTH_NOTE + " " + _CTA_DYNAMICS_NOTE + " Each "
        "option needs its own genre, sub_genre, mood list, 4 to 6 "
        "instruments/textures, vocal_style, era_influence, 1 to 3 "
        "production descriptors naming specific textures that fit that SAME "
        "genre (not vague praise like 'professional' alone), "
        f"energy_level, a bpm matching that {tempo} tempo band, and an "
        "English title, plus its own "
        "lyrics_lines array (bracket section tags, optionally with a "
        "short parenthetical staging note, mixed with the actual lyric "
        "lines that follow each one). Write "
        f"the lyric lines in {language_name}. " + _CTA_SAFETY_NOTE +
        f" Return them as a 'variations' array of exactly {count} objects."
    )

    response = _generate_with_rotation(
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_cta_variations_schema(count),
            safety_settings=_CTA_SAFETY_SETTINGS,
        ),
        api_keys=api_keys,
    )
    return _response_json(response).get("variations") or []


def build_cta_suno_prompt(analysis, bpm, max_tags=15, max_len=1000, fixed_tags=None):
    """Like build_suno_prompt, but for a complete vocal CTA song: includes
    vocal_style instead of "instrumental", and uses DEFAULT_CTA_FIXED_STYLE_TAGS
    (not the BGM-loop DEFAULT_FIXED_STYLE_TAGS) unless the caller supplies its
    own list, since a full song with a beginning/middle/end should not be
    forced into a seamless-loop shape."""
    genre_bits = [b for b in [analysis.get("genre"), analysis.get("sub_genre")] if b]
    era = analysis.get("era_influence")
    mood = analysis.get("mood") or []
    instruments = analysis.get("instruments") or []
    production = analysis.get("production_quality") or []
    energy = analysis.get("energy_level")
    vocal_style = analysis.get("vocal_style")
    if fixed_tags is None:
        fixed_tags = DEFAULT_CTA_FIXED_STYLE_TAGS

    def compose(mood_n, instr_n, prod_n):
        tags = []
        if genre_bits:
            tags.append(" ".join(genre_bits))
        if vocal_style:
            tags.append(vocal_style)
        if era:
            tags.append(era)
        tags.extend(mood[:mood_n])
        tags.extend(instruments[:instr_n])
        tags.extend(production[:prod_n])
        if energy:
            tags.append(energy)
        tags.extend(fixed_tags)
        if bpm:
            tags.append(f"{bpm} bpm")
        return tags

    mood_n, instr_n, prod_n = len(mood), len(instruments), len(production)
    tags = _trim_tags_to_budget(compose, mood_n, instr_n, prod_n, max_tags)
    return _finalize_tags(tags, max_len)


def build_cta_lyrics(analysis):
    """Join Gemini's ordered [section tag] + lyric-line array into text
    ready to paste into Suno's lyrics field. Unlike build_lyrics_structure,
    this does NOT force every line into brackets, since most lines here
    are actual sung lyrics, not structure-only meta-tags."""
    lines = [str(line).strip() for line in (analysis.get("lyrics_lines") or []) if str(line).strip()]
    return "\n".join(lines)

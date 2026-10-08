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


def _response_json(response):
    """Parse a Gemini JSON response, raising a clear RuntimeError instead of
    a bare TypeError when Gemini returned no usable candidate (blocked by
    safety filters, blocked by copyright/recitation matching, or truncated
    by the token limit). Without this, response.text is None in that case
    and json.loads(None) blows up with a message that tells the user
    nothing, surfacing as a generic 500 with no indication of why."""
    text = response.text
    if text:
        return json.loads(text)

    candidates = response.candidates or []
    finish_reason = candidates[0].finish_reason if candidates else None
    reason_name = getattr(finish_reason, "name", None) or (str(finish_reason) if finish_reason else None)
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

def _variations_schema(count):
    return {
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
    suggest home-shopping background-music styles fitting a free-text
    keyword description. The input can be a bare product category
    (e.g. '주방가전', '식품') or a combination of target-audience and
    product keywords (e.g. '50대 여성 패션', '20대 남성 뷰티'). Returns a
    list of `count` variation dicts in the same shape as
    regenerate_variations."""
    prompt = (
        "You are creating INSTRUMENTAL background music for a Korean home-shopping "
        f"(홈쇼핑/TV shopping) broadcast. The target description is: '{category}'. "
        "This description may be a bare product category (e.g. '주방가전', '식품'), or it may "
        "combine a target audience with a product category — such as an age group and/or "
        "gender alongside the product (e.g. '50대 여성 패션' = fashion for women in their 50s, "
        "'20대 남성 뷰티' = beauty products for men in their 20s). Take ALL parts of the "
        "description into account: infer the music mood/tempo/genre that fits BOTH the product "
        "category's shopping-broadcast conventions (e.g. warm and cozy for kitchen appliances, "
        "fresh and upbeat for food, clean and modern for electronics, urgent and exciting for "
        "fashion/beauty sale events) AND the target audience's taste where one is given (e.g. an "
        "older audience generally favors a more classic, less aggressive sound than a younger "
        "audience for the same product category). "
        f"Generate {count} DISTINCT style options for this background music, while staying "
        "energetic enough to hold viewer attention and encourage purchase. Each of the "
        f"{count} options must be clearly distinct from the others (different genre, mood/energy, "
        "tempo, and instrumentation) — avoid defaulting to the single most obvious/generic genre "
        "choice for the category, and avoid letting every option converge on the same "
        "funk/disco/synth-pop instrument palette (slap bass, FM electric piano, brass stabs, "
        "drum machine); pick specific, characterful sub-genres and let each option's own "
        "distinct mood/energy (e.g. one warm and cozy, one urgent and driving, one bright and "
        "playful) genuinely drive its instrument choices — could be orchestral, acoustic, rock, "
        "hip-hop, ambient, electronic, world, etc., whatever best fits that option's mood. All "
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
        "hook at its real, full energy — not a quieter or simpler 'intro' version of it — "
        "because it also has to be what the track sounds like if it loops back to the start. "
        "Do NOT automatically bookend every option with a separate [Intro] and a separate "
        "[Outro] section — that beginning-middle-end shape is itself a small narrative arc. "
        "Stay steady/loop-friendly rather than a narrative arc: avoid stacking dramatic-"
        "development tags like [Buildup] into [Breakdown] into [Bridge]; at most one section "
        "may add or drop a single layer, nothing more. The energy/dynamism must stay exactly "
        "as strong across EVERY section as the first — no gradual build-up from a quiet start "
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


def _cta_variations_schema(count):
    return {
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
    "minute song, use a complete structure: [Verse 1], [Chorus], "
    "[Verse 2], [Chorus], a short [Bridge], [Chorus] again, then "
    "[Outro]. Write 4 to 6 lyric lines for EACH verse/chorus/bridge "
    "section (never just 1-2 lines), reuse the exact same chorus lyrics "
    "every time [Chorus] appears, and aim for roughly 24 to 32 total "
    "lyric lines across the whole song (not counting the bracket tags "
    "themselves)."
)

_CTA_SAFETY_NOTE = (
    "The lyrics must be LIGHT and SIMPLE: just basic, surface-level "
    "information or feeling about the topic, with NO deep or complex "
    "meaning — think of a short, fun, catchy radio/TV commercial jingle, "
    "not a narrative song with an artistic message. The lyrics must be "
    "completely clean and safe: no profanity, sexual content, violence, "
    "hate speech, drugs, self-harm, political statements, or any other "
    "harmful or inappropriate content — suitable for a general TV "
    "shopping-channel audience of all ages."
)


def generate_cta(keyword, language, api_keys, count=VARIATION_BATCH_SIZE):
    """Text-only call that asks Gemini for `count` distinct, COMPLETE songs
    (with vocals and normal song structure) promoting the given keyword/
    topic, with lyrics written in the given language. Returns a list of
    `count` variation dicts shaped like GEMINI_CTA_SCHEMA plus bpm."""
    language_name = CTA_LANGUAGE_NAMES.get(language, "Korean")
    prompt = (
        "You are writing a short, catchy CALL-TO-ACTION (CTA) promotional "
        "song for a Korean home-shopping/retail context, about: "
        f"'{keyword}'. Unlike background music, this is a COMPLETE, "
        "fully-formed song with normal song structure (e.g. intro, verse, "
        "chorus, possibly a bridge, outro) and it includes VOCALS — it is "
        "NOT a seamless instrumental loop. "
        f"Generate {count} DISTINCT options, each clearly different in "
        "genre/mood/tempo/instrumentation from the others. "
        "Each option needs: genre, a specific sub_genre, a vivid mood/"
        "energy list, 4 to 6 specific instruments/textures (a rhythm "
        "layer, a melodic/harmonic layer, and at least one distinctive "
        "textural element), a vocal_style description (gender/tone/"
        "delivery, e.g. 'bright female pop vocals, playful delivery'), "
        "era_influence, 1 to 3 production/mix quality descriptors, "
        "energy_level, a plausible bpm, and a short title in ENGLISH ONLY "
        "using simple, everyday, concrete words. "
        "Also write lyrics_lines: an ORDERED array mixing Suno bracket "
        "section tags (e.g. \"[Verse 1]\", \"[Chorus]\", \"[Bridge]\", "
        "\"[Outro]\") with the actual lyric lines that follow each tag, "
        "in the exact order they should appear — a normal, COMPLETE song "
        "structure (NOT a short 2-3 section repeating loop). " + _CTA_LENGTH_NOTE +
        f" Write the actual lyric lines (not the bracket tags) in "
        f"{language_name}. " + _CTA_SAFETY_NOTE + " Return them as a "
        f"'variations' array of exactly {count} objects."
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


def regenerate_cta(previous_analysis, language, api_keys, count=VARIATION_BATCH_SIZE):
    """Text-only follow-up call that asks Gemini for `count` new CTA song
    variations preserving the previous analysis's core mood/energy, for
    the 'regenerate' button on the CTA tab."""
    language_name = CTA_LANGUAGE_NAMES.get(language, "Korean")
    prev_mood = previous_analysis.get("mood") or []
    mood_note = f" Its core mood/energy was: {', '.join(prev_mood)}." if prev_mood else ""

    prompt = (
        "Here is a previous CTA song style analysis, as JSON:\n"
        + json.dumps(previous_analysis, ensure_ascii=False) + "\n\n"
        f"Generate {count} NEW variations for the same promotional topic, "
        "each staying in the same overall genre/vibe family and "
        "preserving the SAME core mood/energy character." + mood_note + " "
        "Create variety through different tempo, instrumentation, and "
        "vocal_style, while every option remains a COMPLETE song with "
        "vocals and normal song structure — NOT a repeating instrumental "
        "loop. " + _CTA_LENGTH_NOTE + " Each "
        "option needs its own genre, sub_genre, mood list, 4 to 6 "
        "instruments/textures, vocal_style, era_influence, 1 to 3 "
        "production descriptors, energy_level, bpm, and an English "
        "title, plus its own lyrics_lines array (bracket section tags "
        "mixed with the actual lyric lines that follow each one). Write "
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

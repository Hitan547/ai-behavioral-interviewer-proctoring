"""
fluency_scorer.py
-----------------
Measures speech fluency directly from Whisper transcript.
No new libraries needed — pure Python.

Signals:
1. Filler word ratio  — um, uh, like, basically, you know, sort of
2. Speaking pace      — words per minute (ideal = 120-150 for interviews)
3. Incomplete endings — sentences trailing off with conjunctions
4. Repetition         — same word repeated consecutively
5. Answer length      — too short = not enough content
"""

import re


# ── Filler words to detect ─────────────────────────────────────────────────
FILLERS = [
    "um", "uh", "umm", "uhh", "hmm",
    "like", "basically", "literally", "actually",
    "you know", "you see", "i mean", "kind of",
    "sort of", "right", "okay so", "so like",
    "and so", "blah", "etc etc"
]

# ── Ideal interview speaking pace ──────────────────────────────────────────
WPM_IDEAL_MIN = 110
WPM_IDEAL_MAX = 160


def compute_fluency_score(transcript: str, duration_seconds: int = 60) -> float:
    """
    Compute fluency score (0-10) from transcript text.

    Parameters
    ----------
    transcript       : str   Whisper transcript of the answer
    duration_seconds : int   Recording duration in seconds (default 60)

    Returns
    -------
    float  Fluency score 0-10
           0-3  = very poor (lots of fillers, wrong pace, trailing off)
           4-6  = average (some fillers, reasonable pace)
           7-10 = good (clean speech, ideal pace, complete sentences)
    """
    if not transcript or not transcript.strip():
        return 0.0

    text  = transcript.strip()
    lower = text.lower()
    words = text.split()
    total_words = len(words)

    if total_words < 5:
        return 2.0   # too short to score meaningfully

    # ── Signal 1: Filler word ratio ───────────────────────────────────────
    filler_count = 0
    for filler in FILLERS:
        # count occurrences with word boundaries
        pattern = r'\b' + re.escape(filler) + r'\b'
        filler_count += len(re.findall(pattern, lower))

    filler_ratio  = filler_count / total_words
    # 0% fillers = 10, 10%+ fillers = 0
    filler_score  = max(0.0, 10.0 - (filler_ratio * 100))

    # ── Signal 2: Speaking pace ───────────────────────────────────────────
    if duration_seconds > 0:
        wpm = (total_words / duration_seconds) * 60
    else:
        wpm = 130   # assume ideal if no duration

    if WPM_IDEAL_MIN <= wpm <= WPM_IDEAL_MAX:
        pace_score = 10.0
    elif 90 <= wpm < WPM_IDEAL_MIN or WPM_IDEAL_MAX < wpm <= 180:
        pace_score = 6.0
    elif 70 <= wpm < 90 or 180 < wpm <= 210:
        pace_score = 3.0
    else:
        pace_score = 1.0   # too slow or too fast

    # ── Signal 3: Incomplete sentence endings ─────────────────────────────
    # Sentences ending with conjunctions — "So...", "And...", "Because..."
    incomplete = len(re.findall(
        r'\b(so|and|but|because|however|therefore|although)\s*[.!?]',
        lower
    ))
    # Also catch "blah blah", "etc etc", "and such", "and so on"
    vague_endings = len(re.findall(
        r'\b(blah blah|etc etc|and such|and so on|something like that|'
        r'and all that|and everything|and stuff)\b',
        lower
    ))
    incomplete_score = max(0.0, 10.0 - (incomplete * 2) - (vague_endings * 3))

    # ── Signal 4: Word repetition ─────────────────────────────────────────
    # "this this", "I I", "the the" — consecutive duplicates
    repetitions = 0
    for i in range(1, len(words)):
        if words[i].lower() == words[i-1].lower() and len(words[i]) > 2:
            repetitions += 1
    repetition_score = max(0.0, 10.0 - (repetitions * 2))

    # ── Signal 5: Answer length ───────────────────────────────────────────
    # Ideal interview answer: 100-200 words
    if total_words >= 80:
        length_score = 10.0
    elif total_words >= 50:
        length_score = 7.0
    elif total_words >= 25:
        length_score = 4.0
    else:
        length_score = 1.0

    # ── Weighted combination ──────────────────────────────────────────────
    final = (
        0.35 * filler_score
        + 0.25 * pace_score
        + 0.20 * incomplete_score
        + 0.10 * repetition_score
        + 0.10 * length_score
    )

    return round(min(float(final), 10.0), 2)


def get_fluency_breakdown(transcript: str, duration_seconds: int = 60) -> dict:
    """
    Detailed breakdown — useful for STAR coaching display later.
    """
    if not transcript or not transcript.strip():
        return {"fluency_score": 0.0, "details": {}}

    lower       = transcript.lower()
    words       = transcript.split()
    total_words = len(words)

    filler_count = sum(
        len(re.findall(r'\b' + re.escape(f) + r'\b', lower))
        for f in FILLERS
    )

    wpm = (total_words / duration_seconds * 60) if duration_seconds > 0 else 0

    found_fillers = [
        f for f in FILLERS
        if re.search(r'\b' + re.escape(f) + r'\b', lower)
    ]

    return {
        "fluency_score":  compute_fluency_score(transcript, duration_seconds),
        "details": {
            "total_words":    total_words,
            "words_per_min":  round(wpm, 1),
            "filler_count":   filler_count,
            "filler_ratio":   round(filler_count / max(total_words, 1) * 100, 1),
            "fillers_found":  found_fillers,
        }
    }
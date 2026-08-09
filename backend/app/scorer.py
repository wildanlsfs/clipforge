"""
Virality scoring.

Two modes:
  1. LLM mode (settings.LLM_ENABLED): the transcript's *words* are sent
     to any OpenAI-compatible chat endpoint (9router, OpenRouter, Groq,
     a local Ollama/vLLM proxy, ...) with a numbered index next to each
     word. The model returns [start_index, end_index] word ranges
     instead of timestamps -- LLMs are reliable at copying a visible
     number but bad at doing timestamp arithmetic, so we look up the
     actual start/end time from the word list ourselves (same trick
     used by AutoClip). Only the transcript text is sent, never audio
     or video.
  2. Heuristic mode (no key configured, or the call fails): a local,
     zero-cost fallback that windows the transcript and scores it on
     simple signals -- question/exclamation density, number/superlative
     spikes, pause-bounded sentence completeness, and speaking-rate
     "energy". Degrades gracefully; every deployment works out of the
     box with $0 spent.

Both modes score against the same 8-dimension virality rubric
(hook, shock, humor, controversy, insight, emotion, energy, arc
completion -- borrowed from Chopify's scoring model), each 0-10,
summed to a total out of 80. Only candidates >= score_threshold survive.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import settings

log = logging.getLogger("clipforge.scorer")

DIMENSIONS = [
    "hook", "shock", "humor", "controversy",
    "insight", "emotion", "energy", "arc_completion",
]

SCORE_THRESHOLD = 8.0 * len(DIMENSIONS) * 0.55  # ~44/80, i.e. "8+/10 average" bar

# Uses plain __TOKEN__ substitution rather than str.format(): the prompt is
# full of literal JSON braces (as few-shot examples), and format() tries to
# parse every one of those as a field -- a real bug caught in testing
# (KeyError: '"i"' from the un-escaped example on the "numeric index" line).
SYSTEM_PROMPT = """You are an expert short-form video editor who finds viral \
moments in long transcripts for TikTok/Reels/Shorts.

You will receive a transcript as a JSON array of words, each with a numeric \
index: [{"i": 0, "w": "hello"}, {"i": 1, "w": "world"}, ...].

Find up to __MAX_CLIPS__ self-contained segments (each __MIN_S__-__MAX_S__ \
seconds long at ~2.3 words/sec) that would work as standalone viral clips: a \
strong hook in the first 3 seconds, a complete narrative/idea arc, and a payoff.

Score each candidate 0-10 on EACH of these dimensions:
- hook: does it grab attention in the first sentence?
- shock: surprising, counter-intuitive, or unexpected?
- humor: funny or entertaining?
- controversy: opinionated, debatable, provocative?
- insight: teaches something useful or non-obvious?
- emotion: emotionally resonant (inspiring, moving, relatable)?
- energy: delivered with pace/energy, not a dead flat stretch?
- arc_completion: has a clear beginning, middle, and payoff/punchline (not cut mid-thought)?

Respond with ONLY a JSON array (no markdown, no prose) of objects:
[{"start_index": int, "end_index": int, "title": "short catchy title", \
"hook_text": "the exact opening line", "scores": {"hook": n, "shock": n, \
"humor": n, "controversy": n, "insight": n, "emotion": n, "energy": n, \
"arc_completion": n}}]

start_index/end_index MUST be indices from the input array (integers you \
saw in "i"), never timestamps or made-up numbers."""


def _flatten_words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg in transcript.get("segments", []):
        seg_words = seg.get("words") or []
        if seg_words:
            for w in seg_words:
                words.append({"start": w["start"], "end": w["end"], "word": w["word"]})
        else:
            # segment had no word-level timestamps; treat whole segment as one "word"
            words.append({"start": seg["start"], "end": seg["end"], "word": seg["text"]})
    return words


def _total(scores: dict[str, float]) -> float:
    return sum(float(scores.get(d, 0)) for d in DIMENSIONS)


def score_transcript(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    words = _flatten_words(transcript)
    if not words:
        return []

    candidates: list[dict[str, Any]] = []
    if settings.LLM_ENABLED:
        try:
            candidates = _llm_score(words)
        except Exception:
            log.exception("LLM scoring failed, falling back to heuristic scorer")
            candidates = []

    if not candidates:
        candidates = _heuristic_score(words)

    candidates = [c for c in candidates if c["total_score"] >= SCORE_THRESHOLD]
    candidates.sort(key=lambda c: c["total_score"], reverse=True)
    return candidates[: settings.MAX_CLIPS_PER_VIDEO]


def _llm_score(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from openai import OpenAI

    client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY)

    indexed = [{"i": i, "w": w["word"]} for i, w in enumerate(words)]
    prompt = (
        SYSTEM_PROMPT.replace("__MAX_CLIPS__", str(settings.MAX_CLIPS_PER_VIDEO))
        .replace("__MIN_S__", str(settings.MIN_CLIP_SECONDS))
        .replace("__MAX_S__", str(settings.MAX_CLIP_SECONDS))
    )
    # Chunk very long transcripts to stay within context; process in ~2500-word windows.
    chunk_size = 2500
    raw_candidates: list[dict[str, Any]] = []

    for offset in range(0, len(indexed), chunk_size):
        chunk = indexed[offset : offset + chunk_size]
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(chunk)},
            ],
            temperature=0.4,
            stream=False,  # some OpenAI-compatible proxies (e.g. 9router) stream by
                           # default when this is omitted, which the SDK can't parse
                           # as a single response -- pin it explicitly.
        )
        content = resp.choices[0].message.content or "[]"
        raw_candidates.extend(_parse_llm_json(content))

    results = []
    for c in raw_candidates:
        try:
            si, ei = int(c["start_index"]), int(c["end_index"])
            si = max(0, min(si, len(words) - 1))
            ei = max(si + 1, min(ei, len(words) - 1))
            scores = {d: float(c.get("scores", {}).get(d, 0)) for d in DIMENSIONS}
            results.append(
                {
                    "start": words[si]["start"],
                    "end": words[ei]["end"],
                    "title": c.get("title") or "Untitled clip",
                    "hook_text": c.get("hook_text") or "",
                    "scores": scores,
                    "total_score": _total(scores),
                }
            )
        except (KeyError, ValueError, TypeError, IndexError):
            continue
    return results


def _parse_llm_json(content: str) -> list[dict[str, Any]]:
    """Real models are inconsistent about wrapping JSON in code fences or
    adding a stray sentence before/after it (confirmed empirically: the
    same prompt/model produced clean fenced JSON on one call and something
    the naive fence-stripper couldn't parse on another). Try increasingly
    permissive strategies rather than assuming one exact shape."""
    content = content.strip()

    # 1. as-is
    data = _try_json_array(content)
    if data is not None:
        return data

    # 2. strip markdown code fences
    fenced = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
    data = _try_json_array(fenced)
    if data is not None:
        return data

    # 3. grab the outermost [...] span, in case the model added prose
    # before/after the array (e.g. "Here are the clips: [...]")
    match = re.search(r"\[.*\]", content, flags=re.DOTALL)
    if match:
        data = _try_json_array(match.group(0))
        if data is not None:
            return data

    log.warning("could not parse LLM JSON output; raw content: %r", content[:500])
    return []


def _try_json_array(text: str) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


_FILLERS = {"um", "uh", "like", "you", "know", "so", "the", "a", "and"}
_SUPERLATIVE_RE = re.compile(
    r"\b(never|always|worst|best|insane|crazy|secret|nobody|everyone|mistake|"
    r"wrong|truth|shocking|unbelievable|literally|actually|huge|massive)\b",
    re.IGNORECASE,
)


def _heuristic_score(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Zero-cost fallback: slide a window over the transcript and rate it
    on cheap textual/timing signals. No LLM required."""
    results = []
    n = len(words)
    win_words = int(settings.MAX_CLIP_SECONDS * 2.3)
    step = max(1, win_words // 2)

    i = 0
    while i < n:
        j = min(n - 1, i + win_words)
        span = words[i : j + 1]
        if not span:
            break
        duration = span[-1]["end"] - span[0]["start"]
        if duration < settings.MIN_CLIP_SECONDS:
            i += step
            continue
        text = " ".join(w["word"] for w in span)

        hook_words = " ".join(w["word"] for w in span[:12])
        hook = 6.0 if ("?" in hook_words or _SUPERLATIVE_RE.search(hook_words)) else 4.0
        shock = min(10.0, 3.0 + 2.0 * len(_SUPERLATIVE_RE.findall(text)))
        humor = 4.0  # no reliable signal without an LLM; neutral baseline
        controversy = 5.0 if any(p in text.lower() for p in ("i think", "unpopular", "actually")) else 3.0
        insight = 5.0 if any(p in text.lower() for p in ("because", "the reason", "here's why", "means that")) else 3.5
        emotion = 5.0 if text.count("!") >= 1 else 3.5
        non_filler = [w["word"].lower().strip(".,!?") for w in span if w["word"].lower().strip(".,!?") not in _FILLERS]
        energy = min(10.0, 10.0 * len(non_filler) / max(1, len(span)))
        arc = 6.0 if text.rstrip().endswith((".", "!", "?")) else 4.0

        scores = {
            "hook": hook, "shock": shock, "humor": humor, "controversy": controversy,
            "insight": insight, "emotion": emotion, "energy": energy, "arc_completion": arc,
        }
        results.append(
            {
                "start": span[0]["start"],
                "end": span[-1]["end"],
                "title": text[:60] + ("..." if len(text) > 60 else ""),
                "hook_text": hook_words,
                "scores": scores,
                "total_score": _total(scores),
            }
        )
        i += step
    return results

"""Talking to Gemini: the client, text chat with function calling and model fallback, and the
Live (voice) session settings. google-genai is imported lazily so the rest of the API never needs it."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.assistant.application.prompt import LIVE, SYSTEM
from app.assistant.application.tools import TOOLS, describe
from app.core.config import Settings
from app.core.errors import Unavailable, Upstream

log = logging.getLogger("theone.assistant")

ToolRunner = Callable[[str, dict], tuple[dict, dict | None]]

# Models that reported their quota as used up are skipped until this monotonic time.
_cooldown: dict[str, float] = {}


def declarations(types):
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(name=n, description=d, parameters=types.Schema.model_validate(p) if p else None)
        for n, (_, d, p) in TOOLS.items()])]


def client(s: Settings):
    if not s.gemini_api_key:
        raise Unavailable("the assistant is not configured: set GEMINI_API_KEY")
    from google import genai

    return genai.Client(api_key=s.gemini_api_key)


def chat(messages: list[tuple[str, str]], s: Settings, run_tool: ToolRunner) -> dict:
    """messages are (role, text) with role "user" or "assistant". Runs tool calls until the model
    answers, falling back through GEMINI_TEXT_FALLBACKS when a model is over quota or missing."""
    from google.genai import errors, types

    c = client(s)
    contents = [types.Content(role="user" if role == "user" else "model", parts=[types.Part(text=text)]) for role, text in messages]
    config = types.GenerateContentConfig(system_instruction=SYSTEM, tools=declarations(types), temperature=0.3,
                                         automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    every = [s.gemini_text_model, *[x.strip() for x in s.gemini_text_fallbacks.split(",") if x.strip()]]
    models = [x for x in every if _cooldown.get(x, 0) <= time.monotonic()] or every[-1:]
    steps, ui = [], []

    def generate():
        while models:
            for attempt in range(2):
                try:
                    return c.models.generate_content(model=models[0], contents=contents, config=config)
                except errors.APIError as e:
                    if e.code == 503 and attempt == 0:
                        # Overloaded: one quick retry before moving on.
                        time.sleep(1.5)
                        continue
                    if e.code not in (404, 429, 503):
                        raise Upstream("the assistant model returned an error") from e
                    if e.code in (404, 429):
                        _cooldown[models[0]] = time.monotonic() + (3600 if e.code == 429 else 86400)
                    break
            log.warning("assistant model %s unavailable; %s", models[0], f"trying {models[1]}" if len(models) > 1 else "none left")
            models.pop(0)
        raise Unavailable("the assistant models are busy or over quota; try again in a minute")

    for _ in range(6):
        r = generate()
        calls = r.function_calls or []
        if not calls:
            return {"reply": (r.text or "").strip() or "I could not find an answer to that.", "steps": steps, "ui": ui, "model": models[0]}
        contents.append(r.candidates[0].content)
        parts = []
        for fc in calls:
            out, action = run_tool(fc.name, dict(fc.args or {}))
            steps.append(describe(fc.name, dict(fc.args or {})))
            if action:
                ui.append(action)
            parts.append(types.Part.from_function_response(name=fc.name, response=out))
        contents.append(types.Content(role="user", parts=parts))
    return {"reply": "That needed too many lookups. Try a narrower question.", "steps": steps, "ui": ui, "model": models[0]}


CURRENT_PAGE = {"name": "current_page", "description": "What the analyst has open in the console right now: the page, "
                "and on a ring page the ring and any account they selected."}


def live_config(s: Settings, system: str = LIVE, handle: str | None = None):
    """A voice call with Ziva. The accent comes from the system instruction: native-audio models take no regional
    language code. Session resumption and a sliding context window keep the call going past the server's time limits."""
    from google.genai import types

    tools = declarations(types)
    tools[0].function_declarations.append(types.FunctionDeclaration(**CURRENT_PAGE))
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"], system_instruction=system, tools=tools,
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=[x.strip() for x in s.gemini_live_language_codes.split(",") if x.strip()] or None),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=s.gemini_voice))),
        session_resumption=types.SessionResumptionConfig(handle=handle),
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()))

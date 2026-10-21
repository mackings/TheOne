"""TheOne assistant: ask about rings, accounts, alerts and payments by voice or text.

Gemini does the talking; every fact comes from TheOne through read-only tools that run here,
on the server. The assistant cannot change anything: watchlisting, confirming or releasing
stays a deliberate click in the console, where it is audited.

Two ways in:
  POST /assistant/chat   text, using GEMINI_TEXT_MODEL with function calling
  WS   /assistant/live   voice, relaying 16 kHz PCM from the browser to a Gemini Live session
                         (GEMINI_LIVE_MODEL) and 24 kHz PCM back, with transcripts both ways

Data sent to Gemini is kept small: account numbers are masked to their last four digits, raw
phone numbers, device ids and BVNs are never stored by TheOne in the first place.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.auth import STAFF, role_for_key
from app.api.deps import new_uow
from app.assistant.application.tools import describe, run_tool
from app.assistant.infrastructure import gemini
from app.core.config import Settings, get_settings

log = logging.getLogger("theone.assistant")
router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)


@router.get("/status")
def status(s: Settings = Depends(get_settings)):
    return {"enabled": bool(s.gemini_api_key), "text_model": s.gemini_text_model, "live_model": s.gemini_live_model}


@router.post("/chat")
def chat(body: ChatIn, s: Settings = Depends(get_settings)):
    return gemini.chat([(t.role, t.text) for t in body.messages], s, lambda name, args: run_tool(name, args, s, new_uow))




@router.websocket("/live")
async def live(ws: WebSocket):
    """Browser protocol (JSON text frames):
    in:  {"type":"audio","data":<base64 PCM16 mono 16 kHz>} | {"type":"text","text":...} | {"type":"stop"}
    out: {"type":"ready"} | {"type":"audio","data":<base64 PCM16 24 kHz>} | {"type":"user_text"|"assistant_text","text":...}
         | {"type":"step","text":...} | {"type":"ui","action":{...}} | {"type":"turn_complete"} | {"type":"interrupted"}
         | {"type":"error","text":...}
    The API key travels as ?key=, because browsers cannot set headers on a WebSocket."""
    s = get_settings()
    keys = s.role_keys
    role = role_for_key(ws.query_params.get("key"), keys) if keys else "admin"
    if role is None or (role != "admin" and role not in STAFF):
        await ws.close(code=4403)
        return
    await ws.accept()
    if not s.gemini_api_key:
        await ws.send_json({"type": "error", "text": "The assistant is not configured on this server."})
        await ws.close()
        return
    from google.genai import types

    try:
        async with gemini.client(s).aio.live.connect(model=s.gemini_live_model, config=gemini.live_config(s)) as session:
            await ws.send_json({"type": "ready"})

            async def upstream():
                while True:
                    msg = json.loads(await ws.receive_text())
                    if msg.get("type") == "audio":
                        await session.send_realtime_input(audio=types.Blob(data=base64.b64decode(msg["data"]), mime_type="audio/pcm;rate=16000"))
                    elif msg.get("type") == "text" and msg.get("text"):
                        await session.send_realtime_input(text=str(msg["text"])[:2000])
                    elif msg.get("type") == "stop":
                        return

            async def downstream():
                while True:
                    async for r in session.receive():
                        if r.tool_call:
                            replies = []
                            for fc in r.tool_call.function_calls or []:
                                args = dict(fc.args or {})
                                await ws.send_json({"type": "step", "text": describe(fc.name, args)})
                                out, action = await asyncio.to_thread(run_tool, fc.name, args, s, new_uow)
                                if action:
                                    await ws.send_json({"type": "ui", "action": action})
                                replies.append(types.FunctionResponse(id=fc.id, name=fc.name, response=out))
                            await session.send_tool_response(function_responses=replies)
                        sc = r.server_content
                        if not sc:
                            continue
                        if sc.interrupted:
                            await ws.send_json({"type": "interrupted"})
                        if sc.input_transcription and sc.input_transcription.text:
                            await ws.send_json({"type": "user_text", "text": sc.input_transcription.text})
                        if sc.output_transcription and sc.output_transcription.text:
                            await ws.send_json({"type": "assistant_text", "text": sc.output_transcription.text})
                        for p in (sc.model_turn.parts if sc.model_turn else []):
                            if p.inline_data and p.inline_data.data:
                                await ws.send_json({"type": "audio", "data": base64.b64encode(p.inline_data.data).decode()})
                        if sc.turn_complete:
                            await ws.send_json({"type": "turn_complete"})

            up, down = asyncio.create_task(upstream()), asyncio.create_task(downstream())
            done, pending = await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                    raise t.exception()
    except WebSocketDisconnect:
        return
    # Report it and close; the console offers to reconnect.
    except Exception as e:
        log.exception("live assistant session failed")
        try:
            await ws.send_json({"type": "error", "text": f"Voice session ended: {type(e).__name__}"})
            await ws.close()
        except Exception:
            pass

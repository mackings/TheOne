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
from app.assistant.application.prompt import ring_briefing
from app.assistant.application.tools import current_page, describe, ring_facts, run_tool
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




def _in_new_uow(fn, *args):
    uow = new_uow()
    try:
        return fn(uow, *args)
    finally:
        uow.close()


@router.websocket("/live")
async def live(ws: WebSocket):
    """A voice call with Ziva. Browser protocol (JSON text frames):
    in:  {"type":"audio","data":<base64 PCM16 mono 16 kHz>} | {"type":"text","text":...}
         | {"type":"page","path":...,"account":...} | {"type":"stop"}
    out: {"type":"ready"} | {"type":"audio","data":<base64 PCM16 24 kHz>} | {"type":"user_text"|"assistant_text","text":...}
         | {"type":"step","text":...} | {"type":"ui","action":{...}} | {"type":"turn_complete"} | {"type":"interrupted"}
         | {"type":"error","text":...}
    The API key travels as ?key=, because browsers cannot set headers on a WebSocket. With ?ring=<id or number> the call
    opens with Ziva explaining that ring. Gemini closes live connections after a few minutes; the call carries on through
    a fresh connection that resumes the same conversation."""
    s = get_settings()
    keys = s.role_keys
    role = role_for_key(ws.query_params.get("key"), keys) if keys else "admin"
    if role is None or (role != "admin" and role not in STAFF):
        await ws.close(code=4403)
        return
    await ws.accept()
    if not s.gemini_api_key:
        await ws.send_json({"type": "error", "text": "Ziva is not configured on this server."})
        await ws.close()
        return
    from google.genai import types

    ring = ws.query_params.get("ring")
    system = None
    if ring:
        try:
            facts = await asyncio.to_thread(_in_new_uow, ring_facts, s, ring)
        except Exception:
            log.exception("could not load ring %s for a call", ring)
            await ws.send_json({"type": "error", "text": "That ring could not be loaded."})
            await ws.close()
            return
        system = ring_briefing(str(facts["ring"]), json.dumps(facts, ensure_ascii=False))

    inbox: asyncio.Queue = asyncio.Queue()
    page: dict = {}
    handle: str | None = None

    async def from_browser():
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                if msg.get("type") == "page":
                    page.clear()
                    page.update({"path": str(msg.get("path") or "")[:200], "account": msg.get("account")})
                    continue
                await inbox.put(msg)
                if msg.get("type") == "stop":
                    return
        except WebSocketDisconnect:
            await inbox.put({"type": "stop"})

    async def to_gemini(session):
        while True:
            msg = await inbox.get()
            if msg.get("type") == "audio":
                await session.send_realtime_input(audio=types.Blob(data=base64.b64decode(msg["data"]), mime_type="audio/pcm;rate=16000"))
            elif msg.get("type") == "text" and msg.get("text"):
                await session.send_realtime_input(text=str(msg["text"])[:2000])
            elif msg.get("type") == "stop":
                return "stop"

    async def answer(fc) -> types.FunctionResponse:
        args = dict(fc.args or {})
        if fc.name == "current_page":
            out = await asyncio.to_thread(_in_new_uow, current_page, s, dict(page))
        else:
            await ws.send_json({"type": "step", "text": describe(fc.name, args)})
            out, action = await asyncio.to_thread(run_tool, fc.name, args, s, new_uow)
            if action:
                await ws.send_json({"type": "ui", "action": action})
        return types.FunctionResponse(id=fc.id, name=fc.name, response=out)

    async def from_gemini(session):
        nonlocal handle
        while True:
            async for r in session.receive():
                if r.session_resumption_update and r.session_resumption_update.resumable and r.session_resumption_update.new_handle:
                    handle = r.session_resumption_update.new_handle
                if r.go_away:
                    return "resume"
                if r.tool_call:
                    await session.send_tool_response(function_responses=[await answer(fc) for fc in r.tool_call.function_calls or []])
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

    listener = asyncio.create_task(from_browser())
    first = True
    try:
        while True:
            config = gemini.live_config(s, system, handle) if system else gemini.live_config(s, handle=handle)
            async with gemini.client(s).aio.live.connect(model=s.gemini_live_model, config=config) as session:
                if first:
                    await ws.send_json({"type": "ready"})
                    if ring:
                        await session.send_realtime_input(text="Please explain how the fraud in this ring took place.")
                    first = False
                up, down = asyncio.create_task(to_gemini(session)), asyncio.create_task(from_gemini(session))
                done, pending = await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
                for t in pending:
                    t.cancel()
                result = next(iter(done)).result()
            if result != "resume" or not handle:
                break
            log.info("Ziva call resuming on a fresh connection")
    except WebSocketDisconnect:
        return
    except Exception as e:
        log.exception("Ziva call failed")
        try:
            await ws.send_json({"type": "error", "text": f"The call dropped: {type(e).__name__}"})
        except Exception:
            pass
    finally:
        listener.cancel()
        try:
            await ws.close()
        except Exception:
            pass

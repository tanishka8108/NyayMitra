import what_happened_service as what_happened
import asyncio
import base64
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

router = APIRouter()
logger = logging.getLogger("juris_ai_live")

LIVE_MODEL = os.getenv("JURIS_AI_LIVE_MODEL", "gemini-3.8-live")

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


def _live_config(language: str) -> dict:
    language_names = {
        "en": "English",
        "hi": "Hindi",
        "mr": "Marathi",
    }

    return {
        "response_modalities": ["AUDIO"],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": "Puck"}
            }
        },
        "system_instruction": {
            "parts": [{
                "text": (
                    "You are Juris AI, a careful Indian-law information "
                    "assistant providing useful spoken legal guidance. "
                    f"Speak naturally in {language_names[language]}. "
                    "Understand the user's actual facts before advising. "
                    "Identify likely legal issues and explain applicable "
                    "Indian law only when you have a reliable basis. "
                    "Explain why a provision may apply and distinguish "
                    "known facts from assumptions. Ask one focused "
                    "clarifying question when important facts are missing. "
                    "Give practical, situation-specific next steps. "
                    "Do not default to generic advice or redirect users "
                    "to text chat merely because analysis is needed. "
                    "Never invent statutes, sections, cases, citations, "
                    "facts, or legal outcomes. Explain uncertainty and "
                    "recommend a qualified Indian lawyer for important "
                    "decisions. Never claim you examined a document unless "
                    "it was actually provided to you. Keep spoken answers "
                    "concise and easy to understand."
                )
            }]
        },
    }


@router.websocket("/api/juris-ai/live")
async def juris_ai_live(websocket: WebSocket):
    origin = websocket.headers.get("origin")

    # The frontend runs on Vite during local development.
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await websocket.accept()
    client = None
    receive_task = None
    send_lock = asyncio.Lock()
    transcript_parts = []

    async def send_event(payload: dict):
        async with send_lock:
            await websocket.send_json(payload)

    try:
        # Authenticate the existing NLP API key before opening Gemini.
        try:
            auth = await asyncio.wait_for(
                websocket.receive_json(), timeout=10
            )
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Authentication timed out")
            return

        if (
            not isinstance(auth, dict)
            or auth.get("type") != "auth"
            or not isinstance(auth.get("token"), str)
            or auth["token"] != os.getenv(
                "NYAYMITRA_NLP_KEY", "nyaymitra-local-test-2026"
            )
        ):
            await websocket.close(code=1008, reason="Authentication failed")
            return

        language = auth.get("language", "en")
        if language not in {"en", "hi", "mr"}:
            await websocket.close(code=1008, reason="Unsupported language")
            return

        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not google_key:
            await send_event({
                "type": "error",
                "message": "Live voice is not configured on the server.",
            })
            await websocket.close(code=1011)
            return

        client = genai.Client(api_key=google_key)

        async with client.aio.live.connect(
            model=LIVE_MODEL,
            config=_live_config(language),
        ) as session:
            await send_event({
                "type": "connected",
                "language": language,
                "model": LIVE_MODEL,
            })

            async def forward_model_events():
                try:
                    while True:
                        async for response in session.receive():
                            content = response.server_content
    
                            if content:
                                if content.input_transcription:
                                    transcript = content.input_transcription.text
                                    if transcript:
                                        transcript_parts.append(transcript)
                                    if transcript:
                                        await send_event({
                                            "type": "input_transcript",
                                            "text": transcript,
                                        })
    
                                if content.output_transcription:
                                    transcript = content.output_transcription.text
                                    if transcript:
                                        await send_event({
                                            "type": "output_transcript",
                                            "text": transcript,
                                        })
    
                                if content.model_turn:
                                    for part in content.model_turn.parts or []:
                                        if part.inline_data and part.inline_data.data:
                                            await send_event({
                                                "type": "audio",
                                                "data": base64.b64encode(
                                                    part.inline_data.data
                                                ).decode("ascii"),
                                                "mime_type": (
                                                    part.inline_data.mime_type
                                                    or "audio/pcm;rate=24000"
                                                ),
                                            })
    
                                if content.interrupted:
                                    await send_event({"type": "interrupted"})
    
                                if content.turn_complete:
                                    await send_event({"type": "turn_complete"})
    
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Gemini Live receive loop failed")
                    try:
                        await send_event({
                            "type": "error",
                            "message": "The live AI connection ended unexpectedly.",
                        })
                    except Exception:
                        pass

            receive_task = asyncio.create_task(forward_model_events())

            while True:
                event = await websocket.receive_json()
                if not isinstance(event, dict):
                    continue

                event_type = event.get("type")

                if event_type == "audio":
                    encoded = event.get("data")
                    if not isinstance(encoded, str) or len(encoded) > 350_000:
                        await send_event({
                            "type": "error",
                            "message": "Invalid or oversized audio chunk.",
                        })
                        continue

                    try:
                        audio_bytes = base64.b64decode(
                            encoded, validate=True
                        )
                    except (ValueError, TypeError):
                        await send_event({
                            "type": "error",
                            "message": "The audio chunk was invalid.",
                        })
                        continue

                    if receive_task and receive_task.done():
                        logger.error(
                            "Gemini Live receive task ended before audio send"
                        )
                        try:
                            receive_task.result()
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            logger.exception(
                                "Gemini Live receive task had failed"
                            )

                        await send_event({
                            "type": "error",
                            "message": (
                                "The live AI connection ended. "
                                "Please start a new conversation."
                            ),
                        })
                        break

                    try:
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=audio_bytes,
                                mime_type="audio/pcm;rate=16000",
                            )
                        )
                    except Exception:
                        logger.exception(
                            "Gemini Live audio send failed; ending session"
                        )
                        try:
                            await send_event({
                                "type": "error",
                                "message": (
                                    "The live AI connection was interrupted. "
                                    "Please start a new conversation."
                                ),
                            })
                        except Exception:
                            pass
                        break

                elif event_type == "text":
                    text = event.get("text")
                    if isinstance(text, str) and text.strip():
                        await session.send_realtime_input(text=text[:4000])

                elif event_type == "end":
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        import traceback
        traceback.print_exc()
        logger.exception("Juris AI Live session failed")
        try:
            await send_event({
                "type": "error",
                "message": (
                    "Live voice could not start. Check the server model "
                    "configuration and Google API access."
                ),
            })
        except Exception:
            pass
    finally:
        if receive_task:
            receive_task.cancel()
            try:
                await receive_task
            except (asyncio.CancelledError, Exception):
                pass
        if client:
            try:
                await client.aio.aclose()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass

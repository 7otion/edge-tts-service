from __future__ import annotations
import sys
import os
import json
import asyncio
import signal
import logging

# ---------- Logging & binary stdout ----------

logger = logging.getLogger("tts_service")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

if os.name == "nt":
    try:
        import msvcrt
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    except Exception:
        pass

# ---------- Utilities ----------

def send_status(obj: dict) -> None:
    try:
        sys.stderr.write(json.dumps(obj) + "\n")
        sys.stderr.flush()
    except Exception:
        pass

# ---------- Core Service ----------

class TTSService:
    def __init__(self):
        self._running = True
        self._current_task: asyncio.Task | None = None
        self._current_voice: str = "en-US-AriaNeural"

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._on_signal)
            except Exception:
                pass

    def _on_signal(self, *_):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.shutdown())
        except RuntimeError:
            pass

    async def run(self):
        import time
        from datetime import datetime, timezone

        def now_iso():
            return datetime.now(timezone.utc).isoformat()

        send_status({"status": "ready", "ts": now_iso()})
        logger.info("Service ready")

        loop = asyncio.get_running_loop()
        while self._running:
            try:
                raw = await loop.run_in_executor(None, sys.stdin.buffer.readline)
            except Exception as e:
                logger.exception("stdin error: %s", e)
                break

            if not raw:
                logger.info("stdin closed")
                break

            try:
                line = raw.rstrip(b"\r\n")
                line_s = line.decode("utf-8", errors="replace")
            except Exception as e:
                send_status({"status": "error", "message": f"stdin decode failed: {e}"})
                continue

            if not line_s:
                continue

            try:
                msg = json.loads(line_s)
            except Exception as e:
                send_status({"status": "error", "message": f"invalid json: {e}"})
                continue

            cmd = msg.get("cmd")
            if cmd == "speak":
                text = msg.get("text", "")
                voice = msg.get("voice", self._current_voice)
                rate = msg.get("rate", 0)

                if self._current_task and not self._current_task.done():
                    await self._cancel_current()

                self._current_voice = voice
                request_ts = time.time()
                self._current_task = asyncio.create_task(self._speak_and_stream(text, voice, rate, request_ts))

            elif cmd == "cancel":
                await self._cancel_current()

            elif cmd == "restart":
                self._current_voice = msg.get("voice", self._current_voice)
                send_status({"status": "ready", "ts": now_iso()})

            elif cmd == "get_voices":
                await self._get_voices()

            elif cmd == "shutdown":
                await self.shutdown()
                break
            else:
                send_status({"status": "error", "message": f"unknown cmd: {cmd}"})

        await self.shutdown()

    async def _speak_and_stream(self, text: str, voice: str, rate: int, request_ts: float):
        import time
        from datetime import datetime, timezone
        
        def now_iso():
            return datetime.now(timezone.utc).isoformat()

        if not text:
            send_status({"status": "error", "message": "empty text", "ts": now_iso()})
            return

        send_status({"status": "speaking", "ts": now_iso(), "request_ts": request_ts, "voice": voice})
        logger.info("Starting synthesis (voice=%s, rate=%+d)", voice, rate)

        try:
            import edge_tts
            # Edge TTS returns MP3 by default - stream it directly!
            communicate = edge_tts.Communicate(
                text, 
                voice, 
                rate=f"{rate * 5:+d}%"
            )
        except Exception as e:
            logger.exception("edge_tts init failed: %s", e)
            send_status({"status": "error", "message": f"init failed: {e}", "ts": now_iso()})
            return

        try:
            out = sys.stdout.buffer
            first_chunk_time = None
            chunk_count = 0
            
            # Stream MP3 directly from edge-tts to stdout (no conversion needed!)
            async for chunk in communicate.stream():
                if asyncio.current_task().cancelled():
                    raise asyncio.CancelledError()

                # Extract MP3 data from chunk
                mp3_data = None
                if isinstance(chunk, (bytes, bytearray)):
                    mp3_data = bytes(chunk)
                elif isinstance(chunk, dict):
                    if "data" in chunk:
                        mp3_data = bytes(chunk["data"])
                    elif "audio" in chunk:
                        mp3_data = bytes(chunk["audio"])

                if not mp3_data:
                    continue

                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    send_status({
                        "status": "first_audio",
                        "ts": now_iso(),
                        "first_audio_ms": int((first_chunk_time - request_ts) * 1000)
                    })

                # Write raw MP3 directly to stdout
                out.write(mp3_data)
                out.flush()
                chunk_count += 1

            finished_ts = time.time()
            synthesis_ms = int((finished_ts - request_ts) * 1000)

            send_status({
                "status": "finished",
                "ts": now_iso(),
                "synthesis_ms": synthesis_ms,
                "chunks": chunk_count
            })
            logger.info("Synthesis finished: mp3_chunks=%d, synth_ms=%d", chunk_count, synthesis_ms)

        except asyncio.CancelledError:
            logger.info("Cancelled")
            send_status({"status": "cancelled", "ts": now_iso()})
            raise

        except Exception as e:
            logger.exception("Synthesis error: %s", e)
            send_status({"status": "error", "message": str(e), "ts": now_iso()})

    async def _cancel_current(self):
        task = self._current_task
        if task and not task.done():
            logger.info("Cancelling current synthesis")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._current_task = None
        send_status({"status": "cancelled"})

    async def _get_voices(self):
        logger.info("Fetching voices")
        try:
            import edge_tts
            voices = await edge_tts.list_voices()

            voice_list = []
            for v in voices:
                voice_list.append({
                    "id": v.get("ShortName", ""),
                    "name": v.get("Name", v.get("ShortName", "")),
                    "language": v.get("Locale", ""),
                    "gender": v.get("Gender"),
                })

            send_status({"status": "voices", "voices": voice_list})
            logger.info("Returned %d voices", len(voice_list))

        except Exception as e:
            logger.exception("get_voices failed: %s", e)
            send_status({"status": "error", "message": f"Failed: {e}"})

    async def shutdown(self):
        if not self._running:
            return

        logger.info("Shutting down")
        self._running = False

        if self._current_task and not self._current_task.done():
            try:
                self._current_task.cancel()
                await self._current_task
            except Exception:
                pass

        send_status({"status": "shutdown"})

        try:
            sys.stderr.flush()
            sys.stdout.flush()
        except Exception:
            pass

def main():
    service = TTSService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("Fatal error")
    finally:
        try:
            sys.stderr.flush()
            sys.stdout.flush()
        except Exception:
            pass

if __name__ == "__main__":
    main()
"""
Agent 4 — Draft Assembler Agent

Builds the final video from script + assets (fully local, no AWS needed):
  1. Edge TTS (neural, free) → gTTS fallback → silent audio
  2. FFmpeg: normalize audio to clean MP3 (fixes Edge TTS WebM output)
  3. SRT subtitle generation
  4. FFmpeg: combine scene image + audio → scene video clip (Ken Burns motion)
  5. FFmpeg: concatenate all clips → draft MP4
  6. Generate thumbnail from first scene
  7. Return DraftResult with paths + metadata

Error handling philosophy:
  - Each scene is wrapped in try/except — one failure never kills the whole job
  - Audio is validated + re-encoded before passing to FFmpeg
  - Every FFmpeg call captures stderr for debugging
  - Full fallback chain: Ken Burns → static frame → dark background
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from services.agents.script_engineer import StructuredScript
from services.agents.asset_orchestrator import GeneratedAsset
from core.storage import LocalStorage


@dataclass
class DraftResult:
    video_path: str
    thumbnail_path: str
    srt_path: str
    audio_paths: list[str] = field(default_factory=list)
    total_duration: float = 0.0
    scene_count: int = 0

    def to_dict(self) -> dict:
        return {
            "video_path": self.video_path,
            "thumbnail_path": self.thumbnail_path,
            "srt_path": self.srt_path,
            "total_duration": self.total_duration,
            "scene_count": self.scene_count,
        }


class DraftAssemblerAgent:
    """
    Agent 4: Assembles the draft video from TTS audio + scene images.
    Uses Microsoft Edge TTS for near-human narration, with gTTS as fallback.
    """

    POLLY_VOICE_MAP = {
        "hi": "Aditi",
        "en": "Joanna",
        "te": None,
        "ta": None,
        "mr": None,
        "bn": "Aditi",
    }

    # Microsoft Edge TTS neural voices — warm, expressive, near-human quality
    # Free, no API key required
    EDGE_VOICE_MAP = {
        "en":   "en-US-AriaNeural",       # Female, warm, conversational
        "en_m": "en-US-GuyNeural",        # Male, deep, professional
        "hi":   "hi-IN-SwaraNeural",      # Female, natural Hindi
        "hi_m": "hi-IN-MadhurNeural",     # Male, Hindi
        "te":   "te-IN-ShrutiNeural",     # Female, Telugu
        "te_m": "te-IN-MohanNeural",      # Male, Telugu
        "ta":   "ta-IN-PallaviNeural",    # Female, Tamil
        "ta_m": "ta-IN-ValluvarNeural",   # Male, Tamil
        "mr":   "mr-IN-AarohiNeural",     # Female, Marathi
        "mr_m": "mr-IN-ManoharNeural",    # Male, Marathi
        "bn":   "bn-IN-TanishaaNeural",   # Female, Bengali
        "bn_m": "bn-IN-BashkarNeural",    # Male, Bengali
    }

    def __init__(
        self,
        storage: LocalStorage,
        use_polly: bool = False,
        ffmpeg_bin: str = "ffmpeg",
    ):
        self.storage = storage
        self.use_polly = use_polly
        self.ffmpeg_bin = ffmpeg_bin

    # ── Ken Burns motion presets ─────────────────────────────────────────────
    MOTION_PRESETS = [
        # 0  Slow zoom-in towards center
        ("zoom+0.0008", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        # 1  Slow zoom-out from center
        ("if(eq(on\\,1)\\,1.15\\,zoom-0.0008)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        # 2  Pan left → right
        ("1.05", "on/(d)*iw*0.05", "ih/2-(ih/zoom/2)"),
        # 3  Pan right → left
        ("1.05", "iw*0.05-on/(d)*iw*0.05", "ih/2-(ih/zoom/2)"),
        # 4  Diagonal pan + subtle zoom
        ("zoom+0.0006", "on/(d)*iw*0.04", "ih*0.04-on/(d)*ih*0.04"),
        # 5  Pull-back (start close, reveal more)
        ("if(eq(on\\,1)\\,1.2\\,zoom-0.001)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ]

    # ── Main entry point ─────────────────────────────────────────────────────

    async def run(
        self,
        script: StructuredScript,
        assets: list[GeneratedAsset],
        job_id: str,
    ) -> DraftResult:
        """Assemble draft video for a job."""
        output_dir = Path(self.storage.base_path) / "jobs" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_by_scene = {a.scene_id: a for a in assets}
        audio_paths: list[str] = []
        scene_clips: list[str] = []
        srt_entries: list[str] = []
        elapsed = 0.0

        all_scenes = [
            {"id": 0,  "text": script.hook, "duration": 3},
            *[{"id": s.id, "text": s.text, "duration": s.duration} for s in script.scenes],
            {"id": -1, "text": script.cta,  "duration": 3},
        ]

        for scene_idx, scene_data in enumerate(all_scenes):
            sid = scene_data["id"]
            text = scene_data["text"]
            dur = float(scene_data["duration"])
            audio_path = str(output_dir / f"audio_{sid}.mp3")

            # ── 1. Generate and validate TTS audio ───────────────────────────
            try:
                await self._generate_tts(text, script.language, audio_path)
                # Normalize audio to standard mp3 — Edge TTS sometimes outputs
                # WebM/Opus with an .mp3 extension, which FFmpeg cannot decode.
                audio_path = await self._normalize_audio(audio_path, dur)
            except Exception as e:
                logger.warning(f"TTS/normalize failed for scene {sid}: {e} — using silence")
                try:
                    await self._create_silent_audio(dur, audio_path)
                except Exception as e2:
                    logger.error(f"Silent audio also failed for scene {sid}: {e2}")
                    # Last resort: generate inline silence with FFmpeg concat
                    audio_path = await self._make_silence_ffmpeg(dur, str(output_dir / f"silence_{sid}.mp3"))

            audio_paths.append(audio_path)

            # ── 2. Build SRT entry ────────────────────────────────────────────
            start = self._format_srt_time(elapsed)
            end   = self._format_srt_time(elapsed + dur)
            idx   = len(srt_entries) + 1
            srt_entries.append(f"{idx}\n{start} --> {end}\n{text}\n")
            elapsed += dur

            # ── 3. Combine image + audio → scene video clip ───────────────────
            try:
                asset = assets_by_scene.get(
                    sid if sid > 0
                    else (list(assets_by_scene.keys())[0] if assets_by_scene else None)
                )
                image_file = (asset.local_path or asset.image_url) if asset else None
                clip_path  = str(output_dir / f"clip_{sid}.mp4")

                await self._image_to_video(
                    image_src=image_file,
                    audio_path=audio_path,
                    duration=dur,
                    output_path=clip_path,
                    motion_index=scene_idx,
                )

                if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
                    scene_clips.append(clip_path)
                else:
                    logger.error(f"Clip for scene {sid} is missing or empty — skipping")

            except Exception as e:
                logger.error(f"Scene {sid} clip generation failed: {e}")
                # Try a minimal audio-only clip so the video still has sound
                try:
                    clip_path = str(output_dir / f"clip_{sid}.mp4")
                    await self._audio_only_clip(audio_path, dur, clip_path)
                    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
                        scene_clips.append(clip_path)
                except Exception as e2:
                    logger.error(f"Audio-only fallback also failed for scene {sid}: {e2}")

        # ── 4. Concatenate all clips ──────────────────────────────────────────
        draft_path = str(output_dir / "draft.mp4")
        if scene_clips:
            try:
                await self._concatenate_clips(scene_clips, draft_path)
                if not os.path.exists(draft_path) or os.path.getsize(draft_path) == 0:
                    raise RuntimeError("Output draft.mp4 is empty after concat")
            except Exception as e:
                logger.error(f"Concatenation failed: {e} — trying re-encode concat")
                try:
                    await self._concatenate_clips_reencode(scene_clips, draft_path)
                except Exception as e2:
                    logger.error(f"Re-encode concat also failed: {e2}")
                    draft_path = ""
        else:
            logger.error("No clips were produced — draft video will be empty")
            draft_path = ""

        # ── 5. Write SRT file ─────────────────────────────────────────────────
        srt_path = str(output_dir / "subtitles.srt")
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_entries))
        except Exception as e:
            logger.error(f"SRT write failed: {e}")

        # ── 6. Extract thumbnail ──────────────────────────────────────────────
        thumbnail_path = str(output_dir / "thumbnail.jpg")
        if draft_path:
            try:
                await self._extract_thumbnail(draft_path, thumbnail_path)
            except Exception as e:
                logger.warning(f"Thumbnail extraction failed: {e}")

        return DraftResult(
            video_path=draft_path,
            thumbnail_path=thumbnail_path,
            srt_path=srt_path,
            audio_paths=audio_paths,
            total_duration=elapsed,
            scene_count=len(script.scenes),
        )

    # ── TTS generation ────────────────────────────────────────────────────────

    async def _generate_tts(self, text: str, language: str, output_path: str) -> None:
        """Generate TTS audio. Priority: Edge TTS → AWS Polly → gTTS → silence."""
        errors = []

        # 1. Edge TTS — neural quality, free
        try:
            await self._edge_tts(text, language, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return
            else:
                errors.append("Edge TTS produced empty file")
        except Exception as e:
            errors.append(f"Edge TTS: {e}")

        logger.warning(f"Edge TTS failed ({'; '.join(errors)}), trying Polly/gTTS")

        # 2. Polly (if configured)
        polly_voice = self.POLLY_VOICE_MAP.get(language)
        if self.use_polly and polly_voice:
            try:
                await self._polly_tts(text, polly_voice, output_path)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                    return
            except Exception as e:
                errors.append(f"Polly: {e}")
                logger.warning(f"Polly TTS failed: {e}, using gTTS")

        # 3. gTTS
        try:
            await self._gtts_fallback(text, language, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return
        except Exception as e:
            errors.append(f"gTTS: {e}")

        # 4. Silence as last resort — caller handles this
        raise RuntimeError(f"All TTS engines failed: {'; '.join(errors)}")

    async def _edge_tts(self, text: str, language: str, output_path: str) -> None:
        """
        Generate TTS using Microsoft Edge neural voices.
        Note: edge-tts saves in WebM/Opus format regardless of the file extension.
        We save to a temp path first, then let _normalize_audio() convert to real MP3.
        """
        import edge_tts
        voice = self.EDGE_VOICE_MAP.get(language) or self.EDGE_VOICE_MAP.get("en")
        logger.info(f"Edge TTS: voice={voice}, lang={language}, chars={len(text)}")
        communicate = edge_tts.Communicate(
            text=text[:4096],
            voice=voice,
            rate="+5%",
            pitch="+0Hz",
            volume="+0%",
        )
        await communicate.save(output_path)

    async def _polly_tts(self, text: str, voice: str, output_path: str) -> None:
        """Call AWS Polly for TTS synthesis."""
        import boto3
        loop = asyncio.get_event_loop()
        def _call():
            client = boto3.client("polly")
            resp = client.synthesize_speech(
                Text=text[:3000],
                OutputFormat="mp3",
                VoiceId=voice,
                Engine="neural" if voice in ("Joanna", "Matthew") else "standard",
            )
            with open(output_path, "wb") as f:
                f.write(resp["AudioStream"].read())
        await loop.run_in_executor(None, _call)

    async def _gtts_fallback(self, text: str, language: str, output_path: str) -> None:
        """gTTS fallback — produces real MP3."""
        from gtts import gTTS
        loop = asyncio.get_event_loop()
        lang_map = {"hi": "hi", "te": "te", "ta": "ta", "mr": "mr", "bn": "bn", "en": "en"}
        gtts_lang = lang_map.get(language, "en")
        def _call():
            tts = gTTS(text=text, lang=gtts_lang, slow=False)
            tts.save(output_path)
        await loop.run_in_executor(None, _call)

    async def _normalize_audio(self, input_path: str, fallback_duration: float) -> str:
        """
        Re-encode audio to a guaranteed-valid MP3 using FFmpeg.

        Edge TTS actually outputs WebM/Opus containers regardless of the file
        extension. FFmpeg's demuxer gets confused and reports 'Invalid data'.
        This step converts whatever we have into a proper libmp3lame MP3.

        Returns the path of the normalized audio (may be same as input_path).
        """
        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            logger.warning(f"Audio file missing/empty at {input_path}, creating silence")
            await self._create_silent_audio(fallback_duration, input_path)
            return input_path

        out_path = input_path.replace(".mp3", "_norm.mp3")
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-i", input_path,
            "-vn",                        # drop any video stream (WebM has none, but safety)
            "-acodec", "libmp3lame",      # force real MP3 encoding
            "-ar", "44100",               # standard sample rate
            "-ac", "1",                   # mono — smaller, consistent
            "-b:a", "128k",               # good quality for narration
            out_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            # Replace original with normalized version
            try:
                os.replace(out_path, input_path)
            except OSError:
                pass
            logger.info(f"Audio normalized successfully: {input_path}")
            return input_path
        else:
            err = stderr.decode(errors="replace") if stderr else "(no stderr)"
            logger.warning(f"Audio normalization failed ({err[-300:]}), using original")
            # Try to remove the broken out_path if it was created
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except OSError:
                pass
            return input_path

    async def _create_silent_audio(self, duration: float, output_path: str) -> None:
        """Create silent MP3 audio using FFmpeg lavfi source."""
        duration = max(duration, 0.5)
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration),
            "-acodec", "libmp3lame",
            "-b:a", "128k",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            raise RuntimeError(f"Silent audio generation failed: {err[-200:]}")

    async def _make_silence_ffmpeg(self, duration: float, output_path: str) -> str:
        """Guaranteed silence generation — never raises, returns path or ''."""
        try:
            await self._create_silent_audio(duration, output_path)
            return output_path
        except Exception as e:
            logger.error(f"Cannot create silent audio: {e}")
            return output_path  # Return path even if failed — FFmpeg will handle it

    # ── Video clip generation ─────────────────────────────────────────────────

    async def _image_to_video(
        self,
        image_src: Optional[str],
        audio_path: str,
        duration: float,
        output_path: str,
        motion_index: int = 0,
    ) -> None:
        """
        Combine image + audio → animated video clip.

        Fallback chain:
          1. Ken Burns zoompan (cinematic motion)
          2. Static frame with scale/crop (simpler)
          3. Dark background (if no image at all)
          4. Audio-only minimal mp4 (last resort)
        """
        duration = max(duration, 1.0)
        fps = 25
        total_frames = max(int(duration * fps), fps)

        # Resolve image file
        local_image = await self._resolve_image(image_src, output_path)
        has_image = local_image is not None and os.path.exists(local_image) and os.path.getsize(local_image) > 0

        if has_image:
            image_path = local_image
            # Attempt 1: Ken Burns motion
            await self._ffmpeg_ken_burns(
                image_path, audio_path, duration, output_path,
                motion_index, fps, total_frames
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return

            # Attempt 2: Simple static frame
            logger.warning(f"Ken Burns failed for scene {motion_index} — trying static frame")
            await self._ffmpeg_static_frame(image_path, audio_path, duration, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return

        # Attempt 3: Dark gradient background (no image)
        logger.warning(f"Image unavailable for scene {motion_index} — using background color")
        await self._ffmpeg_color_bg(audio_path, duration, output_path, fps)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return

        # Attempt 4: Last resort — audio-only
        raise RuntimeError(f"All video rendering attempts failed for scene {motion_index}")

    async def _ffmpeg_ken_burns(
        self, image_path: str, audio_path: str, duration: float,
        output_path: str, motion_index: int, fps: int, total_frames: int
    ) -> None:
        preset = self.MOTION_PRESETS[motion_index % len(self.MOTION_PRESETS)]
        zoom_expr, x_expr, y_expr = preset

        video_filter = (
            f"scale=2496:1404,"
            f"zoompan="
            f"z='{zoom_expr}':"
            f"x='{x_expr}':"
            f"y='{y_expr}':"
            f"d={total_frames}:"
            f"s=1920x1080:"
            f"fps={fps},"
            f"scale=1920:1080,"
            f"format=yuv420p"
        )
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-loop", "1", "-framerate", str(fps), "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-vf", video_filter,
            "-shortest",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            logger.warning(f"Ken Burns FFmpeg failed: {err[-600:]}")
            # Don't raise — caller checks output file existence

    async def _ffmpeg_static_frame(
        self, image_path: str, audio_path: str, duration: float, output_path: str
    ) -> None:
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264", "-tune", "stillimage", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p",
            "-shortest",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            logger.warning(f"Static frame FFmpeg failed: {err[-400:]}")

    async def _ffmpeg_color_bg(
        self, audio_path: str, duration: float, output_path: str, fps: int = 25
    ) -> None:
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-f", "lavfi", "-i", f"color=c=#0f0f1a:size=1920x1080:r={fps}",
            "-i", audio_path,
            "-c:v", "libx264", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-shortest",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            logger.error(f"Color background FFmpeg failed: {err[-400:]}")

    async def _audio_only_clip(self, audio_path: str, duration: float, output_path: str) -> None:
        """Last-resort: create a near-black 1-frame MP4 with audio."""
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-f", "lavfi", "-i", f"color=c=black:size=2x2:r=1",
            "-i", audio_path,
            "-c:v", "libx264", "-crf", "40",
            "-c:a", "aac", "-b:a", "64k",
            "-t", str(max(duration, 1.0)),
            "-shortest",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            raise RuntimeError(f"Audio-only clip failed: {err[-300:]}")

    async def _resolve_image(self, image_src: Optional[str], output_path: str) -> Optional[str]:
        """Resolve image_src to a local file path. Downloads remote URLs."""
        if not image_src:
            return None

        # Remote URL
        if image_src.startswith("http://") or image_src.startswith("https://"):
            local_path = output_path.replace(".mp4", "_img.jpg")
            try:
                import httpx
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(image_src)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                if os.path.getsize(local_path) > 0:
                    return local_path
            except Exception as e:
                logger.warning(f"Could not download remote image {image_src}: {e}")
            return None

        # Local path
        if os.path.exists(image_src) and os.path.getsize(image_src) > 0:
            return image_src

        logger.warning(f"Image file not found or empty: {image_src}")
        return None

    # ── Concatenation ─────────────────────────────────────────────────────────

    async def _concatenate_clips(self, clip_paths: list[str], output_path: str) -> None:
        """Concatenate scene clips using FFmpeg concat demuxer (stream copy — fast)."""
        valid_clips = [c for c in clip_paths if os.path.exists(c) and os.path.getsize(c) > 0]
        if not valid_clips:
            raise RuntimeError("No valid clips to concatenate")

        list_file = output_path.replace(".mp4", "_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for clip in valid_clips:
                abs_clip = os.path.abspath(clip).replace("\\", "/")
                f.write(f"file '{abs_clip}'\n")

        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            logger.error(f"FFmpeg concat (copy) failed: {err[-800:]}")
            raise RuntimeError(f"FFmpeg concat failed: {err[-400:]}")

    async def _concatenate_clips_reencode(self, clip_paths: list[str], output_path: str) -> None:
        """
        Fallback concatenation that re-encodes everything.
        Slower but handles mismatched stream parameters between clips.
        """
        valid_clips = [c for c in clip_paths if os.path.exists(c) and os.path.getsize(c) > 0]
        if not valid_clips:
            raise RuntimeError("No valid clips to re-encode concat")

        # Build complex filter for concat
        inputs = []
        for clip in valid_clips:
            inputs += ["-i", clip]

        n = len(valid_clips)
        filter_complex = "".join([f"[{i}:v][{i}:a]" for i in range(n)]) + f"concat=n={n}:v=1:a=1[v][a]"
        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            logger.error(f"FFmpeg re-encode concat failed: {err[-800:]}")
            raise RuntimeError(f"Re-encode concat failed: {err[-400:]}")

    async def _extract_thumbnail(self, video_path: str, thumbnail_path: str) -> None:
        """Extract a frame at 1 second as the video thumbnail."""
        if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
            raise FileNotFoundError(f"Video not found for thumbnail: {video_path}")

        cmd = [
            self.ffmpeg_bin, "-hide_banner", "-y",
            "-i", video_path,
            "-ss", "00:00:01",
            "-vframes", "1",
            "-vf", "scale=640:-1",
            thumbnail_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace") if stderr else ""
            raise RuntimeError(f"Thumbnail extraction failed: {err[-200:]}")

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format seconds to SRT timestamp: HH:MM:SS,mmm"""
        seconds = max(seconds, 0.0)
        h  = int(seconds // 3600)
        m  = int((seconds % 3600) // 60)
        s  = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

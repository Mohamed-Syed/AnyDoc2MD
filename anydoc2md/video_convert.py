import json
import os
import shutil
import subprocess
import tempfile

from .config import (
    FFMPEG_EXE,
    FFPROBE_EXE,
    MAX_VIDEO_SCENE_KEYFRAMES,
    MAX_VIDEO_DURATION_SECONDS,
    MAX_VIDEO_KEYFRAMES,
    VIDEO_SCENE_INTERVAL_SECONDS,
    VIDEO_KEYFRAME_INTERVAL_SECONDS,
    VIDEO_TRANSCRIPT_COMPUTE_TYPE,
    VIDEO_TRANSCRIPT_DEVICE,
    VIDEO_TRANSCRIPT_MODEL,
    VISUAL_CONTEXT_BALANCED,
    VISUAL_CONTEXT_MODES,
    VISUAL_CONTEXT_SCENE_BY_SCENE,
    VISUAL_CONTEXT_TRANSCRIPT_ONLY,
)
from .ocr import ocr_image_file
from .text_utils import redact_local_paths
from .video_download import load_download_metadata


class VideoConversionError(RuntimeError):
    """Raised when a video cannot be inspected or processed safely."""


def convert_video(src_path, use_ocr, visual_context=VISUAL_CONTEXT_BALANCED, output_assets_dir=None):
    """Convert a local video into a compact Markdown digest for LLM input."""
    if visual_context not in VISUAL_CONTEXT_MODES:
        visual_context = VISUAL_CONTEXT_BALANCED

    metadata = _probe_video(src_path)
    duration = metadata.get("duration")
    if duration is not None and duration > MAX_VIDEO_DURATION_SECONDS:
        minutes = MAX_VIDEO_DURATION_SECONDS // 60
        return (
            "# Video Digest\n\n"
            f"Source file: `{os.path.basename(src_path)}`\n\n"
            "This video was not processed because it is longer than the "
            f"{minutes}-minute safety limit.\n",
            "refused (video too long)",
        )

    with tempfile.TemporaryDirectory(prefix="anydoc2md-video-") as tmpdir:
        transcript = _build_transcript(src_path, metadata, tmpdir)
        frame_notes = _build_frame_notes(
            src_path,
            duration,
            tmpdir,
            use_ocr,
            visual_context,
            output_assets_dir,
        )

    download_metadata = load_download_metadata(src_path)
    return (
        _render_markdown(src_path, metadata, transcript, frame_notes, download_metadata),
        "video digest",
    )


def _probe_video(src_path):
    try:
        proc = subprocess.run(  # noqa: S603
            [
                FFPROBE_EXE,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                src_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise VideoConversionError(
            "FFmpeg is required for video conversion. Install ffmpeg and ffprobe, "
            "then try the video again."
        ) from e
    except subprocess.CalledProcessError as e:
        detail = redact_local_paths((e.stderr or e.stdout or "").strip())
        message = "Could not inspect this video with ffprobe."
        raise VideoConversionError(f"{message} {detail}".strip()) from e

    try:
        raw = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        raise VideoConversionError("ffprobe returned metadata that could not be read.") from e

    streams = raw.get("streams") or []
    duration = None
    try:
        duration = float((raw.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        pass

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration": duration,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "video_codec": video_stream.get("codec_name"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
    }


def _build_transcript(src_path, metadata, tmpdir):
    if not metadata.get("has_audio"):
        return {
            "status": "skipped",
            "message": "No audio stream was found in this video.",
            "segments": [],
        }

    audio_path = os.path.join(tmpdir, "audio.wav")
    try:
        subprocess.run(  # noqa: S603
            [
                FFMPEG_EXE,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                src_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                audio_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise VideoConversionError(
            "FFmpeg is required for video conversion. Install ffmpeg and ffprobe, "
            "then try the video again."
        ) from e
    except subprocess.CalledProcessError as e:
        detail = redact_local_paths((e.stderr or e.stdout or "").strip())
        return {
            "status": "error",
            "message": f"Audio extraction failed. {detail}".strip(),
            "segments": [],
        }

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {
            "status": "skipped",
            "message": (
                "Install faster-whisper to enable local timestamped transcription "
                "(pip install faster-whisper)."
            ),
            "segments": [],
        }

    try:
        model = WhisperModel(
            VIDEO_TRANSCRIPT_MODEL,
            device=VIDEO_TRANSCRIPT_DEVICE,
            compute_type=VIDEO_TRANSCRIPT_COMPUTE_TYPE,
        )
        segments, _ = model.transcribe(audio_path, vad_filter=True)
        return {
            "status": "ok",
            "message": "",
            "segments": [
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": segment.text.strip(),
                }
                for segment in segments
                if segment.text.strip()
            ],
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Transcription failed: {redact_local_paths(str(e))}",
            "segments": [],
        }


def _build_frame_notes(src_path, duration, tmpdir, use_ocr, visual_context, output_assets_dir):
    if visual_context == VISUAL_CONTEXT_TRANSCRIPT_ONLY:
        return {
            "status": "skipped",
            "mode": visual_context,
            "message": "Visual context was skipped by the selected mode.",
            "frames": [],
        }

    if not use_ocr:
        return {
            "status": "skipped",
            "mode": visual_context,
            "message": "Frame OCR was skipped because OCR is disabled.",
            "frames": [],
        }

    frames_dir = os.path.join(tmpdir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    interval = _frame_interval(duration, visual_context)
    max_frames = _max_frame_count(visual_context)
    pattern = os.path.join(frames_dir, "frame_%04d.jpg")

    try:
        subprocess.run(  # noqa: S603
            [
                FFMPEG_EXE,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                src_path,
                "-vf",
                f"fps=1/{interval:.3f},scale=w=1280:h=1280:force_original_aspect_ratio=decrease",
                "-frames:v",
                str(max_frames),
                "-q:v",
                "3",
                pattern,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise VideoConversionError(
            "FFmpeg is required for video conversion. Install ffmpeg and ffprobe, "
            "then try the video again."
        ) from e
    except subprocess.CalledProcessError as e:
        detail = redact_local_paths((e.stderr or e.stdout or "").strip())
        return {
            "status": "error",
            "message": f"Keyframe extraction failed. {detail}".strip(),
            "frames": [],
        }

    saved_images = _save_scene_images(frames_dir, output_assets_dir) if _keeps_scene_images(visual_context) else {}
    frames = []
    seen_text = set()
    for index, frame_path in enumerate(sorted(_iter_frame_paths(frames_dir))):
        try:
            text = _compact_ocr_text(ocr_image_file(frame_path))
        except Exception as e:
            text = f"OCR failed: {redact_local_paths(str(e))}"
        normalized = " ".join(text.lower().split())
        if normalized and normalized in seen_text:
            continue
        if normalized:
            seen_text.add(normalized)
        frame = {"time": index * interval, "text": text}
        if frame_path in saved_images:
            frame["image"] = saved_images[frame_path]
        frames.append(frame)

    return {"status": "ok", "mode": visual_context, "message": "", "frames": frames}


def _frame_interval(duration, visual_context):
    base_interval = (
        VIDEO_SCENE_INTERVAL_SECONDS
        if visual_context == VISUAL_CONTEXT_SCENE_BY_SCENE
        else VIDEO_KEYFRAME_INTERVAL_SECONDS
    )
    max_frames = _max_frame_count(visual_context)
    if duration and duration > 0:
        return max(base_interval, duration / max(1, max_frames - 1))
    return base_interval


def _max_frame_count(visual_context):
    if visual_context == VISUAL_CONTEXT_SCENE_BY_SCENE:
        return MAX_VIDEO_SCENE_KEYFRAMES
    return MAX_VIDEO_KEYFRAMES


def _keeps_scene_images(visual_context):
    return visual_context == VISUAL_CONTEXT_SCENE_BY_SCENE


def _iter_frame_paths(frames_dir):
    for name in os.listdir(frames_dir):
        if name.lower().endswith((".jpg", ".jpeg", ".png")):
            yield os.path.join(frames_dir, name)


def _save_scene_images(frames_dir, output_assets_dir):
    if not output_assets_dir:
        return {}
    os.makedirs(output_assets_dir, exist_ok=True)
    saved = {}
    for index, frame_path in enumerate(sorted(_iter_frame_paths(frames_dir)), start=1):
        name = f"scene_{index:04d}.jpg"
        dest_path = os.path.join(output_assets_dir, name)
        shutil.copy2(frame_path, dest_path)
        saved[frame_path] = os.path.join(os.path.basename(output_assets_dir), name).replace("\\", "/")
    return saved


def _compact_ocr_text(text):
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    return "\n".join(line for line in lines if line)


def _render_markdown(src_path, metadata, transcript, frame_notes, download_metadata=None):
    lines = [
        f"# Video Digest: {os.path.splitext(os.path.basename(src_path))[0]}",
        "",
        "## Metadata",
        "",
        f"- Source file: `{os.path.basename(src_path)}`",
    ]
    download_metadata = download_metadata or {}
    if download_metadata.get("source_url"):
        lines.append(f"- Source URL: {_single_line(download_metadata['source_url'])}")
    if download_metadata.get("title"):
        lines.append(f"- Source title: {_single_line(download_metadata['title'])}")
    if download_metadata.get("extractor"):
        lines.append(f"- Downloader: yt-dlp ({_single_line(download_metadata['extractor'])})")
    lines.extend(
        [
            f"- Duration: {_format_timestamp(metadata.get('duration'))}",
            f"- Video: {_format_video_stream(metadata)}",
            f"- Audio: {'present' if metadata.get('has_audio') else 'not detected'}",
            f"- Visual context mode: {_format_visual_context_mode(frame_notes.get('mode'))}",
            "- Conversion: local transcript, OCR, and selected visual context; no raw video stored in Markdown",
            "",
            "## Transcript",
            "",
        ]
    )

    if transcript["segments"]:
        for segment in transcript["segments"]:
            lines.extend(
                [
                    f"### {_format_timestamp(segment['start'])} - {_format_timestamp(segment['end'])}",
                    "",
                    segment["text"],
                    "",
                ]
            )
    else:
        lines.extend([f"({transcript['message']})", ""])

    lines.extend(["## Visual Context", ""])
    if frame_notes["frames"]:
        for frame in frame_notes["frames"]:
            text = frame["text"] or "(No text detected.)"
            if frame.get("image"):
                lines.extend([f"![Scene around {_format_timestamp(frame['time'])}]({frame['image']})", ""])
            lines.extend(
                [
                    f"### Around {_format_timestamp(frame['time'])}",
                    "",
                    text,
                    "",
                ]
            )
    else:
        message = frame_notes["message"] or "No keyframes were extracted."
        lines.extend([f"({message})", ""])

    lines.extend(
        [
            "## AI Notes",
            "",
            "- Use the transcript as the primary source of spoken content.",
            "- Use the visual context section for visible text, UI state, and scene changes.",
            "- Scene images are linked only in scene-by-scene mode; raw video is not embedded.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_video_stream(metadata):
    parts = []
    if metadata.get("video_codec"):
        parts.append(str(metadata["video_codec"]))
    if metadata.get("width") and metadata.get("height"):
        parts.append(f"{metadata['width']}x{metadata['height']}")
    return ", ".join(parts) if parts else "unknown"


def _single_line(value):
    return " ".join(str(value).split())


def _format_timestamp(seconds):
    if seconds is None:
        return "unknown"
    seconds = max(0, float(seconds))
    millis = int(round((seconds - int(seconds)) * 1000))
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _format_visual_context_mode(mode):
    labels = {
        VISUAL_CONTEXT_TRANSCRIPT_ONLY: "Transcript only",
        VISUAL_CONTEXT_BALANCED: "Balanced",
        VISUAL_CONTEXT_SCENE_BY_SCENE: "Scene-by-scene",
    }
    return labels.get(mode, labels[VISUAL_CONTEXT_BALANCED])

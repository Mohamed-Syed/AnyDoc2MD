import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from anydoc2md.converter import convert_one
from anydoc2md.video_convert import convert_video
from anydoc2md.video_download import download_metadata_path


def _fake_probe(duration=12.0, has_audio=True):
    streams = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1080,
            "height": 1920,
        }
    ]
    if has_audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return json.dumps({"format": {"duration": str(duration)}, "streams": streams})


def test_video_dispatch_uses_video_converter(tmp_path, monkeypatch):
    path = tmp_path / "reel.mp4"
    path.write_bytes(b"stub")
    monkeypatch.setattr(
        "anydoc2md.converter.convert_video",
        lambda p, use_ocr, *args, **kwargs: (f"video: {p}, ocr={use_ocr}", "video digest"),
    )

    text, method = convert_one(str(path), use_ocr=True)

    assert "reel.mp4" in text
    assert "ocr=True" in text
    assert method == "video digest"


def test_video_digest_with_skipped_transcript_still_uses_keyframe_ocr(tmp_path, monkeypatch):
    path = tmp_path / "reel.mp4"
    path.write_bytes(b"stub")

    def fake_run(args, **kwargs):
        if Path(args[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
            return SimpleNamespace(stdout=_fake_probe(), stderr="")
        if any(str(arg).endswith("frame_%04d.jpg") for arg in args):
            output_pattern = Path(args[-1])
            output_pattern.parent.mkdir(parents=True, exist_ok=True)
            (output_pattern.parent / "frame_0001.jpg").write_bytes(b"jpg")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("anydoc2md.video_convert.ocr_image_file", lambda p: "SALE TODAY")
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_transcript",
        lambda *args, **kwargs: {
            "status": "skipped",
            "message": "Transcription was skipped.",
            "segments": [],
        },
    )

    text, method = convert_video(str(path), use_ocr=True)

    assert method == "video digest"
    assert "Transcription was skipped." in text
    assert "SALE TODAY" in text
    assert str(tmp_path) not in text


def test_video_digest_refuses_overlong_video(tmp_path, monkeypatch):
    path = tmp_path / "lecture.mp4"
    path.write_bytes(b"stub")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=_fake_probe(duration=999999), stderr=""),
    )

    text, method = convert_video(str(path), use_ocr=True)

    assert method == "refused (video too long)"
    assert "safety limit" in text


def test_video_digest_with_transcript_segments(tmp_path, monkeypatch):
    path = tmp_path / "clip.webm"
    path.write_bytes(b"stub")

    def fake_run(args, **kwargs):
        if Path(args[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
            return SimpleNamespace(stdout=_fake_probe(duration=3), stderr="")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_transcript",
        lambda *args, **kwargs: {
            "status": "ok",
            "message": "",
            "segments": [{"start": 0.0, "end": 2.5, "text": "Hello world"}],
        },
    )
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_frame_notes",
        lambda *args, **kwargs: {"status": "ok", "message": "", "frames": []},
    )

    text, method = convert_video(str(path), use_ocr=True)

    assert method == "video digest"
    assert "00:00:00.000 - 00:00:02.500" in text
    assert "Hello world" in text


def test_video_digest_includes_download_source_metadata(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"stub")
    Path(download_metadata_path(str(path))).write_text(
        json.dumps(
            {
                "source_url": "https://example.com/reel/1",
                "title": "Original Reel",
                "extractor": "Generic",
            }
        ),
        encoding="utf-8",
    )

    def fake_run(args, **kwargs):
        if Path(args[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
            return SimpleNamespace(stdout=_fake_probe(duration=3, has_audio=False), stderr="")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_frame_notes",
        lambda *args, **kwargs: {"status": "ok", "message": "", "frames": []},
    )

    text, method = convert_video(str(path), use_ocr=True)

    assert method == "video digest"
    assert "- Source URL: https://example.com/reel/1" in text
    assert "- Source title: Original Reel" in text
    assert "- Downloader: yt-dlp (Generic)" in text


def test_video_digest_keeps_download_metadata_on_single_lines(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"stub")
    Path(download_metadata_path(str(path))).write_text(
        json.dumps(
            {
                "source_url": "https://example.com/reel/1\n- injected: yes",
                "title": "Original\nReel",
                "extractor": "Generic\nOther",
            }
        ),
        encoding="utf-8",
    )

    def fake_run(args, **kwargs):
        if Path(args[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
            return SimpleNamespace(stdout=_fake_probe(duration=3, has_audio=False), stderr="")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_frame_notes",
        lambda *args, **kwargs: {"status": "ok", "message": "", "frames": []},
    )

    text, method = convert_video(str(path), use_ocr=True)

    assert method == "video digest"
    assert "- Source URL: https://example.com/reel/1 - injected: yes" in text
    assert "- Source title: Original Reel" in text
    assert "- Downloader: yt-dlp (Generic Other)" in text


def test_transcript_only_mode_skips_visual_context(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"stub")

    def fake_run(args, **kwargs):
        if Path(args[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
            return SimpleNamespace(stdout=_fake_probe(duration=3), stderr="")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_transcript",
        lambda *args, **kwargs: {"status": "ok", "message": "", "segments": []},
    )

    text, method = convert_video(str(path), use_ocr=True, visual_context="transcript_only")

    assert method == "video digest"
    assert "Visual context mode: Transcript only" in text
    assert "Visual context was skipped by the selected mode." in text


def test_scene_by_scene_mode_links_saved_keyframes(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    assets_dir = tmp_path / "clip_assets"
    path.write_bytes(b"stub")

    def fake_run(args, **kwargs):
        if Path(args[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
            return SimpleNamespace(stdout=_fake_probe(duration=3), stderr="")
        if any(str(arg).endswith("frame_%04d.jpg") for arg in args):
            output_pattern = Path(args[-1])
            output_pattern.parent.mkdir(parents=True, exist_ok=True)
            (output_pattern.parent / "frame_0001.jpg").write_bytes(b"jpg")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "anydoc2md.video_convert._build_transcript",
        lambda *args, **kwargs: {"status": "ok", "message": "", "segments": []},
    )
    monkeypatch.setattr("anydoc2md.video_convert.ocr_image_file", lambda p: "VISIBLE TEXT")

    text, method = convert_video(
        str(path),
        use_ocr=True,
        visual_context="scene_by_scene",
        output_assets_dir=str(assets_dir),
    )

    assert method == "video digest"
    assert "Visual context mode: Scene-by-scene" in text
    assert "![Scene around 00:00:00.000](clip_assets/scene_0001.jpg)" in text
    assert (assets_dir / "scene_0001.jpg").is_file()

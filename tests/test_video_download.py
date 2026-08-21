import sys
from types import SimpleNamespace

import pytest

from anydoc2md.config import MAX_VIDEO_DOWNLOAD_BYTES
from anydoc2md.video_download import (
    VideoDownloadError,
    download_metadata_path,
    download_video,
    load_download_metadata,
    parse_video_urls,
)


def test_download_video_uses_yt_dlp_api_and_writes_source_metadata(tmp_path, monkeypatch):
    progress_events = []

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download):
            assert download is True
            assert url == "https://example.com/watch/123"
            output = tmp_path / "Example Clip [abc123].mp4"
            output.write_bytes(b"video")
            self.opts["progress_hooks"][0](
                {
                    "status": "downloading",
                    "downloaded_bytes": 50,
                    "total_bytes": 100,
                }
            )
            self.opts["progress_hooks"][0]({"status": "finished", "filename": str(output)})
            return {
                "id": "abc123",
                "title": "Example Clip",
                "webpage_url": url,
                "extractor_key": "Example",
                "requested_downloads": [{"filepath": str(output)}],
            }

        def sanitize_info(self, info):
            return dict(info)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    result = download_video(
        "https://example.com/watch/123",
        str(tmp_path),
        progress_callback=progress_events.append,
    )

    assert result.path.endswith("Example Clip [abc123].mp4")
    assert result.title == "Example Clip"
    assert result.source_url == "https://example.com/watch/123"
    assert result.extractor == "Example"
    assert load_download_metadata(result.path)["source_url"] == result.source_url
    assert download_metadata_path(result.path).endswith(".mp4.anydoc2md-source")
    assert progress_events[0]["percent"] == 50
    assert progress_events[-1]["percent"] == 100


def test_download_video_output_template_does_not_duplicate_output_dir(tmp_path, monkeypatch):
    seen_opts = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            seen_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download):
            output = tmp_path / "clip.mp4"
            output.write_bytes(b"video")
            return {"title": "clip", "requested_downloads": [{"filepath": str(output)}]}

        def sanitize_info(self, info):
            return info

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    download_video("https://example.com/watch/123", str(tmp_path))

    assert seen_opts["paths"] == {"home": str(tmp_path)}
    assert seen_opts["outtmpl"]["default"] == "%(title).180B [%(id)s].%(ext)s"
    assert seen_opts["max_filesize"] == MAX_VIDEO_DOWNLOAD_BYTES


def test_download_video_can_use_browser_cookies(tmp_path, monkeypatch):
    seen_cookie_sources = []

    class FakeYoutubeDL:
        def __init__(self, opts):
            seen_cookie_sources.append(opts.get("cookiesfrombrowser"))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download):
            output = tmp_path / "clip.mp4"
            output.write_bytes(b"video")
            return {"title": "clip", "requested_downloads": [{"filepath": str(output)}]}

        def sanitize_info(self, info):
            return info

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    download_video("https://example.com/watch/123", str(tmp_path), use_browser_cookies=True)

    assert seen_cookie_sources == [("chrome",)]


def test_download_video_rejects_non_http_urls(tmp_path):
    with pytest.raises(VideoDownloadError, match="http:// and https://"):
        download_video("file:///tmp/video.mp4", str(tmp_path))


def test_download_video_refuses_output_path_outside_selected_folder(tmp_path, monkeypatch):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "clip.mp4"
    outside_file.write_bytes(b"video")
    output_dir = tmp_path / "downloads"

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download):
            self.opts["progress_hooks"][0]({"status": "finished", "filename": str(outside_file)})
            return {"title": "clip", "requested_downloads": [{"filepath": str(outside_file)}]}

        def sanitize_info(self, info):
            return info

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    with pytest.raises(VideoDownloadError, match="outside the selected output folder"):
        download_video("https://example.com/watch/123", str(output_dir))


def test_parse_video_urls_accepts_multiple_pasted_links():
    text = """
    https://www.instagram.com/reel/one/
    https://youtube.com/shorts/two, https://example.com/watch/three
    https://www.instagram.com/reel/one/
    """

    assert parse_video_urls(text) == [
        "https://www.instagram.com/reel/one/",
        "https://youtube.com/shorts/two",
        "https://example.com/watch/three",
    ]


def test_load_download_metadata_ignores_invalid_sidecar(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    sidecar = download_metadata_path(str(video))
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write("{not json")

    assert load_download_metadata(str(video)) == {}

import json
import os
from dataclasses import dataclass

from .text_utils import redact_local_paths


DOWNLOAD_METADATA_SUFFIX = ".anydoc2md-source"
DOWNLOAD_OUTPUT_TEMPLATE = "%(title).180B [%(id)s].%(ext)s"
COOKIE_BROWSERS = ("chrome", "edge", "firefox")


class VideoDownloadError(RuntimeError):
    """Raised when a URL cannot be downloaded into a local video file."""


@dataclass(frozen=True)
class DownloadedVideo:
    path: str
    title: str
    source_url: str
    extractor: str


def parse_video_urls(text):
    urls = []
    seen = set()
    for part in (text or "").replace(",", "\n").split():
        url = part.strip()
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def download_metadata_path(video_path):
    return video_path + DOWNLOAD_METADATA_SUFFIX


def load_download_metadata(video_path):
    path = download_metadata_path(video_path)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def download_video(url, output_dir, use_browser_cookies=False, progress_callback=None):
    url = (url or "").strip()
    if not url:
        raise VideoDownloadError("Paste a video URL first.")
    if not url.lower().startswith(("http://", "https://")):
        raise VideoDownloadError("Only http:// and https:// video URLs are supported.")

    try:
        import yt_dlp
    except ImportError as e:
        raise VideoDownloadError(
            "yt-dlp is required for URL downloads. Install it with: pip install \"yt-dlp[default]\""
        ) from e

    os.makedirs(output_dir, exist_ok=True)
    browsers = COOKIE_BROWSERS if use_browser_cookies else (None,)
    errors = []
    for browser in browsers:
        try:
            return _download_video_once(yt_dlp, url, output_dir, browser, progress_callback)
        except VideoDownloadError as e:
            errors.append(str(e))

    message = errors[-1] if errors else "The video could not be downloaded."
    if not use_browser_cookies:
        message = (
            f"{message}\n\n"
            "If this video opens in your browser, enable 'Use browser cookies' and try again."
        )
    raise VideoDownloadError(message)


def _download_video_once(yt_dlp, url, output_dir, browser, progress_callback):
    finished_paths = []

    def _progress_hook(event):
        _emit_progress(event, progress_callback)
        if event.get("status") == "finished" and event.get("filename"):
            finished_paths.append(event["filename"])

    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "outtmpl": {"default": DOWNLOAD_OUTPUT_TEMPLATE},
        "paths": {"home": output_dir},
        "progress_hooks": [_progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
    }
    if browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            safe_info = ydl.sanitize_info(info)
    except Exception as e:
        prefix = f"{browser} cookies: " if browser else ""
        raise VideoDownloadError(prefix + redact_local_paths(str(e))) from e

    video_path = _resolve_downloaded_path(safe_info, finished_paths)
    if not video_path:
        raise VideoDownloadError("The download finished, but the output video file could not be found.")
    _assert_inside_output_dir(video_path, output_dir)

    metadata = {
        "source_url": safe_info.get("webpage_url") or url,
        "title": safe_info.get("title") or os.path.splitext(os.path.basename(video_path))[0],
        "extractor": safe_info.get("extractor_key") or safe_info.get("extractor") or "",
        "id": safe_info.get("id") or "",
    }
    _write_download_metadata(video_path, metadata)

    return DownloadedVideo(
        path=video_path,
        title=metadata["title"],
        source_url=metadata["source_url"],
        extractor=metadata["extractor"],
    )


def _emit_progress(event, progress_callback):
    if not progress_callback:
        return

    status = event.get("status")
    if status == "downloading":
        total = event.get("total_bytes") or event.get("total_bytes_estimate")
        downloaded = event.get("downloaded_bytes")
        percent = None
        if total and downloaded is not None:
            percent = max(0, min(100, downloaded / total * 100))
        progress_callback(
            {
                "status": "downloading",
                "percent": percent,
                "downloaded_bytes": downloaded,
                "total_bytes": total,
            }
        )
    elif status == "finished":
        progress_callback({"status": "finished", "percent": 100})


def _resolve_downloaded_path(info, finished_paths):
    for candidate in _candidate_paths(info, finished_paths):
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def _assert_inside_output_dir(video_path, output_dir):
    output_root = os.path.abspath(output_dir)
    resolved_path = os.path.abspath(video_path)
    try:
        is_inside = os.path.commonpath([output_root, resolved_path]) == output_root
    except ValueError:
        is_inside = False
    if not is_inside:
        raise VideoDownloadError("The downloaded file resolved outside the selected output folder.")


def _candidate_paths(info, finished_paths):
    yield from finished_paths
    requested_downloads = info.get("requested_downloads")
    if isinstance(requested_downloads, list):
        for item in requested_downloads:
            if isinstance(item, dict):
                yield item.get("filepath") or item.get("_filename") or item.get("filename")
    yield info.get("filepath") or info.get("_filename") or info.get("filename")


def _write_download_metadata(video_path, metadata):
    try:
        with open(download_metadata_path(video_path), "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

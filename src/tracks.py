"""Cutlist document model: tagged unions parsed once at the boundary.

A cutlist is either a bare segment array (one video track, the short form)
or an object with a ``tracks`` array of tagged track objects. Everything
downstream of ``parse_document`` works on ``Timeline`` and never inspects
a raw document again.
"""

from dataclasses import dataclass, field

VIDEO = "video"
AUDIO = "audio"


class TimelineError(Exception):
    """The cutlist document cannot be parsed into a Timeline."""


@dataclass(frozen=True)
class VideoTrack:
    id: str
    segments: list
    x: int = 0
    y: int = 0
    scale: float = 1.0
    opacity: float = 1.0
    base: bool = False


@dataclass(frozen=True)
class AudioTrack:
    id: str
    asset: str
    start: float = 0.0
    offset: float = 0.0
    duration: float | None = None
    gain: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    duck_under: tuple = field(default_factory=tuple)
    cleanup: bool = False


@dataclass(frozen=True)
class Timeline:
    video: list
    audio: list
    duration: float

    @property
    def base(self):
        return self.video[0]

    @property
    def segments(self):
        return self.base.segments

    def all_segments(self):
        out = []
        for track in self.video:
            for seg in track.segments:
                out.append(dict(seg, track=track.id))
        return out


def _number(obj, key, default, cast=float):
    value = obj.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TimelineError(f"{key} must be a number, got {value!r}")
    return cast(value)


def _segments(raw, track_id):
    if not isinstance(raw, list) or not raw:
        raise TimelineError(f"track '{track_id}': segments must be a non-empty array")
    for i, seg in enumerate(raw):
        if not isinstance(seg, dict):
            raise TimelineError(f"track '{track_id}' segment {i}: must be an object")
        for key in ("start", "end"):
            if key not in seg:
                raise TimelineError(f"track '{track_id}' segment {i}: missing '{key}'")
    return raw


def _video_track(raw, index):
    track_id = raw.get("id") or f"video{index}"
    scale = _number(raw, "scale", 1.0)
    if scale <= 0:
        raise TimelineError(f"track '{track_id}': scale must be > 0")
    segments = _segments(raw.get("segments"), track_id)
    return VideoTrack(
        id=track_id,
        segments=segments,
        x=_number(raw, "x", 0, int),
        y=_number(raw, "y", 0, int),
        scale=scale,
        opacity=_number(raw, "opacity", 1.0),
        base=index == 0,
    )


def _audio_track(raw, index):
    track_id = raw.get("id") or f"audio{index}"
    asset = raw.get("asset")
    if not isinstance(asset, str) or not asset:
        raise TimelineError(f"track '{track_id}': audio track needs an 'asset' path")
    duck = raw.get("duck_under", [])
    if isinstance(duck, str):
        duck = [duck]
    if not isinstance(duck, list) or not all(isinstance(d, str) for d in duck):
        raise TimelineError(f"track '{track_id}': duck_under must be a list of track ids")
    duration = raw.get("duration")
    return AudioTrack(
        id=track_id,
        asset=asset,
        start=_number(raw, "start", 0.0),
        offset=_number(raw, "offset", 0.0),
        duration=None if duration is None else float(duration),
        gain=_number(raw, "gain", 1.0),
        fade_in=_number(raw, "fade_in", 0.0),
        fade_out=_number(raw, "fade_out", 0.0),
        duck_under=tuple(duck),
        cleanup=bool(raw.get("cleanup", False)),
    )


def _timeline_duration(video):
    spans = []
    for track in video:
        segs = track.segments
        spans.append(max(seg["end"] for seg in segs if seg["end"] > seg["start"]))
    if not spans:
        raise TimelineError("no video segments")
    return max(spans)


def parse_document(raw, extra_audio=()):
    """Parse a cutlist document (array or {version, tracks}) into a Timeline."""
    if isinstance(raw, list):
        segments = _segments(raw, "base")
        video = [VideoTrack(id="base", segments=segments, base=True)]
        audio = list(extra_audio)
        return Timeline(video=video, audio=audio, duration=_timeline_duration(video))

    if not isinstance(raw, dict):
        raise TimelineError("cutlist must be an array of segments or an object with 'tracks'")

    tracks = raw.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise TimelineError("cutlist object needs a non-empty 'tracks' array")

    video, audio = [], []
    for i, track in enumerate(tracks):
        if not isinstance(track, dict):
            raise TimelineError(f"track {i}: must be an object")
        kind = track.get("kind")
        if kind == VIDEO:
            video.append(_video_track(track, len(video)))
        elif kind == AUDIO:
            audio.append(_audio_track(track, len(audio)))
        else:
            raise TimelineError(f"track {i}: 'kind' must be 'video' or 'audio', got {kind!r}")

    if not video:
        raise TimelineError("cutlist needs at least one video track")
    ids = [t.id for t in video] + [t.id for t in audio]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise TimelineError(f"duplicate track ids: {duplicates}")

    return Timeline(
        video=video,
        audio=audio + list(extra_audio),
        duration=_timeline_duration(video),
    )


def audio_spec_to_tracks(spec):
    """Convert the legacy AudioSpec (auto-detected soundtrack/voiceover) to tracks."""
    if spec is None:
        return []
    tracks = []
    if spec.soundtrack is not None:
        track_id = "music"
        duck = ("voice",) if spec.voiceover is not None else ()
        tracks.append(AudioTrack(id=track_id, asset=spec.soundtrack, duck_under=duck))
    if spec.voiceover is not None:
        tracks.append(AudioTrack(id="voice", asset=spec.voiceover, cleanup=True))
    return tracks

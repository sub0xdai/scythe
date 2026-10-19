"""Cutlist document parsing: tagged track unions, errors, legacy conversion."""

import unittest

from src.compiler import snap_tracks
from src.compiler.graph import AudioSpec
from src.tracks import (
    AudioTrack,
    TimelineError,
    VideoTrack,
    audio_spec_to_tracks,
    parse_document,
)


def _seg(start, end, **kw):
    return {"start": start, "end": end, **kw}


class ArrayFormTests(unittest.TestCase):
    def test_array_becomes_single_base_track(self):
        timeline = parse_document([_seg(0, 1), _seg(1, 2)])
        self.assertEqual(len(timeline.video), 1)
        self.assertEqual(len(timeline.audio), 0)
        self.assertTrue(timeline.base.base)
        self.assertEqual(timeline.duration, 2)

    def test_empty_array_rejected(self):
        with self.assertRaises(TimelineError):
            parse_document([])

    def test_segment_without_start_rejected(self):
        with self.assertRaises(TimelineError):
            parse_document([{"end": 1}])

    def test_extra_audio_tracks_are_merged(self):
        spec = AudioSpec(soundtrack="audio/m.wav", voiceover="audio/v.wav")
        timeline = parse_document([_seg(0, 1)], audio_spec_to_tracks(spec))
        self.assertEqual([t.id for t in timeline.audio], ["music", "voice"])

    def test_audio_spec_voice_track_cleans_up(self):
        tracks = audio_spec_to_tracks(
            AudioSpec(soundtrack="a.wav", voiceover="b.wav"))
        self.assertTrue(tracks[1].cleanup)
        self.assertEqual(tracks[0].duck_under, ("voice",))

    def test_audio_spec_none_is_empty(self):
        self.assertEqual(audio_spec_to_tracks(None), [])


class DocumentFormTests(unittest.TestCase):
    def test_document_parses_video_and_audio(self):
        document = {
            "version": 2,
            "tracks": [
                {"kind": "video", "id": "base", "segments": [_seg(0, 2)]},
                {"kind": "video", "id": "pip", "x": 10, "scale": 0.4,
                 "segments": [_seg(0.5, 1.5)]},
                {"kind": "audio", "id": "bed", "asset": "a.wav",
                 "duck_under": ["voice"]},
                {"kind": "audio", "asset": "b.wav"},
            ],
        }
        timeline = parse_document(document)
        self.assertEqual([t.id for t in timeline.video], ["base", "pip"])
        self.assertEqual(timeline.video[1].x, 10)
        self.assertEqual(timeline.video[1].scale, 0.4)
        self.assertEqual([t.id for t in timeline.audio], ["bed", "audio1"])
        self.assertEqual(timeline.audio[0].duck_under, ("voice",))
        self.assertEqual(timeline.duration, 2)

    def test_duration_is_longest_video_track(self):
        document = {"tracks": [
            {"kind": "video", "segments": [_seg(0, 1)]},
            {"kind": "video", "id": "top", "segments": [_seg(0, 3)]},
        ]}
        self.assertEqual(parse_document(document).duration, 3)

    def test_missing_tracks_rejected(self):
        with self.assertRaises(TimelineError):
            parse_document({"version": 2})

    def test_unknown_kind_rejected(self):
        with self.assertRaises(TimelineError):
            parse_document({"tracks": [{"kind": "subtitle", "asset": "x"}]})

    def test_no_video_track_rejected(self):
        with self.assertRaises(TimelineError):
            parse_document({"tracks": [{"kind": "audio", "asset": "a.wav"}]})

    def test_duplicate_track_ids_rejected(self):
        document = {"tracks": [
            {"kind": "video", "id": "same", "segments": [_seg(0, 1)]},
            {"kind": "video", "id": "same", "segments": [_seg(0, 1)]},
        ]}
        with self.assertRaises(TimelineError):
            parse_document(document)

    def test_audio_track_needs_asset(self):
        with self.assertRaises(TimelineError):
            parse_document({"tracks": [
                {"kind": "video", "segments": [_seg(0, 1)]},
                {"kind": "audio", "id": "bed"},
            ]})

    def test_duck_under_string_is_accepted(self):
        document = {"tracks": [
            {"kind": "video", "segments": [_seg(0, 1)]},
            {"kind": "audio", "id": "bed", "asset": "a.wav", "duck_under": "voice"},
        ]}
        self.assertEqual(parse_document(document).audio[0].duck_under, ("voice",))

    def test_duck_under_rejects_non_strings(self):
        with self.assertRaises(TimelineError):
            parse_document({"tracks": [
                {"kind": "video", "segments": [_seg(0, 1)]},
                {"kind": "audio", "id": "bed", "asset": "a.wav",
                 "duck_under": [1, 2]},
            ]})


class SnapTracksTests(unittest.TestCase):
    def test_every_track_is_snapped(self):
        document = {"tracks": [
            {"kind": "video", "segments": [_seg(0, 1.01)]},
            {"kind": "video", "id": "pip", "segments": [_seg(0.02, 0.99)]},
        ]}
        snapped = snap_tracks(parse_document(document), 10)
        self.assertEqual(snapped.video[0].segments[0]["end"], 1.0)
        self.assertEqual(snapped.video[1].segments[0]["start"], 0.0)
        self.assertEqual(snapped.duration, 1.0)

    def test_audio_tracks_survive_snapping(self):
        document = {"tracks": [
            {"kind": "video", "segments": [_seg(0, 1)]},
            {"kind": "audio", "id": "bed", "asset": "a.wav"},
        ]}
        snapped = snap_tracks(parse_document(document), 30)
        self.assertEqual(len(snapped.audio), 1)


if __name__ == "__main__":
    unittest.main()

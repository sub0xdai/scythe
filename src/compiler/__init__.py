"""FFmpeg filtergraph compiler.

Pure compile path: config + timeline -> one ffmpeg invocation. No ffmpeg
execution and no file writes happen here; main.py executes the returned
CompiledGraph.
"""

from src.compiler.graph import (
    AudioSpec,
    CompiledGraph,
    VideoOutput,
    compile_graph,
    resolve_transition,
    snap_timeline,
    snap_tracks,
)

__all__ = [
    "AudioSpec",
    "CompiledGraph",
    "VideoOutput",
    "compile_graph",
    "resolve_transition",
    "snap_timeline",
    "snap_tracks",
]

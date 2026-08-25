"""FFmpeg filtergraph compiler (Spec B).

Pure compile path: config + cutlist + audio spec -> one ffmpeg
invocation. No ffmpeg execution and no file writes happen here;
main.py executes the returned CompiledGraph.
"""

from src.compiler.graph import AudioSpec, CompiledGraph, compile_graph, snap_timeline

__all__ = ["AudioSpec", "CompiledGraph", "compile_graph", "snap_timeline"]

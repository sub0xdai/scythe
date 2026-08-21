# hardware-acceleration - Delta Spec

## ADDED Requirements

### Requirement: GPU capability probe

The engine MUST probe ffmpeg for hardware encoders, decoders, and hwaccels in the nvenc, qsv, vaapi, and videotoolbox families, and produce a hardware profile: available encoders, available decoders, available hwaccels, and a chosen encoder.

#### Scenario: Probe reports encoders

- GIVEN an ffmpeg with `h264_nvenc` compiled and a runtime GPU
- WHEN the probe runs
- THEN the profile lists `h264_nvenc` and marks it available

<!-- vox:covered CP-1 -->
#### Scenario: No GPU degrades

- GIVEN an ffmpeg with no hardware encoders
- WHEN the probe runs
- THEN the profile lists zero hardware encoders and the chosen encoder is `libx264`

### Requirement: Encoder decision

The chosen encoder MUST be the first available in preference order nvenc, qsv, vaapi, videotoolbox, falling back to `libx264`. Env overrides `NOX_GPU=off|on` and `NOX_ENCODER=<name>` MUST force selection. A forced encoder that is not invokable MUST abort with a clear error.

<!-- vox:covered CP-1 -->
#### Scenario: NVENC chosen

- GIVEN nvenc available and no override
- WHEN the render runs
- THEN the ffmpeg command uses `h264_nvenc`

<!-- vox:covered CP-1 -->
#### Scenario: CPU fallback

- GIVEN no hardware encoder available
- WHEN the render runs
- THEN the ffmpeg command uses `libx264` and the render succeeds

<!-- vox:covered CP-1 -->
#### Scenario: Forced encoder enforced

- GIVEN `NOX_ENCODER=h264_nvenc` on a machine without a GPU
- WHEN the render runs
- THEN it aborts with a message that the encoder is unavailable

### Requirement: Hardware-aware graph

The hardware profile MUST parameterize the graph compiler. On the hardware path the graph MUST insert the vendor chain, for example hwupload plus format=nv12 before an nvenc encoder, or scale_vaapi for vaapi. On the CPU path the graph MUST be exactly the Spec B graph.

<!-- vox:covered CP-1 -->
#### Scenario: HW nodes on hw path

- GIVEN nvenc selected
- WHEN the graph compiles
- THEN the graph contains upload and download nodes with format=nv12 before the encoder

<!-- vox:covered CP-1 -->
#### Scenario: CPU graph unchanged

- GIVEN `libx264` selected
- WHEN the graph compiles
- THEN the graph contains no upload or download nodes

### Requirement: --check-gpu CLI

A `--check-gpu` flag MUST print a JSON capability report and exit 0 when the chosen encoder is invokable, verified by a dry-run encode to null output. It MUST exit non-zero when the chosen encoder cannot be invoked.

<!-- vox:covered CP-1 -->
#### Scenario: Dry run validates

- GIVEN a machine with a working nvenc path
- WHEN `--check-gpu` runs
- THEN it exits 0 and the JSON includes a successful dry-run result

<!-- vox:covered CP-2 -->
#### Scenario: Broken passthrough detected

- GIVEN a container without GPU device access but with the encoder compiled
- WHEN `--check-gpu` runs
- THEN it exits non-zero and the JSON reports the dry-run failure

### Requirement: Container and runner support

render.sh MUST support a GPU passthrough flag mapping to the podman runtime flags: `--gpu nvidia` adds `--gpus all`, `--gpu vaapi` and `--gpu qsv` add the `/dev/dri` device. The README MUST document the three setups.

<!-- vox:covered CP-2 -->
#### Scenario: NVIDIA flag wired

- GIVEN `./render.sh projects/x --gpu nvidia`
- WHEN the script runs
- THEN podman receives `--gpus all`

#### Scenario: VAAPI flag wired

- GIVEN `./render.sh projects/x --gpu vaapi`
- WHEN the script runs
- THEN podman receives the `/dev/dri` device mount

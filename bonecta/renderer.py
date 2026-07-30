from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bonecta.fonts import get_font_path
from bonecta.models import MediaAsset, MediaKind, Orientation, SizeTier, TimelineSegment, VideoPlan
from bonecta.overlays import PAGE_BG, PAGE_BG_WASH_ALPHA, render_end_card_frame, render_overlays

WIDTH = 1080
HEIGHT = 1920
FPS = 30
CROSSFADE = 0.5
DEFAULT_FONT = get_font_path()
BGM_VOLUME = 0.35
TRANSITION_ZOOM_START = 1.08
BLUR_BG_PAN_SCALE = 1.35
BLUR_BG_ROTATE_DEG = 1.2

# 1枚写真の画角変化（連続ズームではなく静止クロップ）
CROP_CLOSE_SCALE = 1.14
CROP_SHIFT_SCALE = 1.12
CROP_SHIFT_RATIO = 0.72  # 0=左端寄り, 1=右端寄り, 0.5=中央


def _page_bg_tint_filter() -> str:
    """ぼかし背景だけに選挙ドットコム同系色を薄く乗せる。"""
    r, g, b = PAGE_BG
    a = PAGE_BG_WASH_ALPHA / 255.0
    return f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{r:02X}{g:02X}{b:02X}@{a:.3f}:t=fill"


def _pillarbox_overlay(fg_scale: str, bg_chain: str) -> str:
    tint = _page_bg_tint_filter()
    return (
        f"split[bg][fg];"
        f"[bg]{bg_chain},{tint}[bgbl];"
        f"[fg]{fg_scale}[fgsc];"
        f"[bgbl][fgsc]overlay=(W-w)/2:(H-h)/2:format=auto"
    )


def _static_blur_bg_chain() -> str:
    return (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},boxblur=30:5"
    )


def _pan_blur_bg_chain(dur: float) -> str:
    """上下ボケ背景を右→左へゆっくり流す（ループ）。"""
    bg_w = int(WIDTH * BLUR_BG_PAN_SCALE)
    pan_dur = max(dur, 1.0)
    return (
        f"scale={bg_w}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={bg_w}:{HEIGHT},boxblur=30:5,"
        f"crop={WIDTH}:{HEIGHT}:x='(iw-ow)*(1-mod(t/{pan_dur},1))':y='(ih-oh)/2'"
    )


def _rotate_blur_bg_chain(dur: float) -> str:
    """上下ボケ背景をほんの少し揺らす（±1.2度）。"""
    pad_w = int(WIDTH * 1.12)
    pad_h = int(HEIGHT * 1.12)
    rotate_dur = max(dur, 1.0)
    angle = BLUR_BG_ROTATE_DEG * 3.14159265 / 180
    return (
        f"scale={pad_w}:{pad_h}:force_original_aspect_ratio=increase,"
        f"crop={pad_w}:{pad_h},boxblur=30:5,"
        f"rotate='{angle:.6f}*sin(2*PI*t/{rotate_dur})':fillcolor=black:ow={pad_w}:oh={pad_h},"
        f"crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2"
    )


def _static_crop_filter(preset: str) -> str | None:
    """画角プリセットを静止クロップで適用（zoompanなし）。"""
    if preset in ("default", "wide", ""):
        return None
    if preset == "close":
        up_w = int(WIDTH * CROP_CLOSE_SCALE)
        up_h = int(HEIGHT * CROP_CLOSE_SCALE)
        if up_w % 2:
            up_w += 1
        if up_h % 2:
            up_h += 1
        return (
            f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT}"
        )
    if preset in ("left", "right"):
        up_w = int(WIDTH * CROP_SHIFT_SCALE)
        up_h = int(HEIGHT * CROP_SHIFT_SCALE)
        if up_w % 2:
            up_w += 1
        if up_h % 2:
            up_h += 1
        # left = 寄り左（クロップ原点を左寄り）、right は右寄り
        x_ratio = (1.0 - CROP_SHIFT_RATIO) if preset == "left" else CROP_SHIFT_RATIO
        return (
            f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT}:x='(iw-ow)*{x_ratio:.3f}':y='(ih-oh)/2'"
        )
    return None


def _transition_zoom_filter(dur: float) -> str:
    """切替直後0.5秒だけズームインして静止。"""
    total_frames = max(int(dur * FPS), 1)
    zoom_frames = min(max(int(CROSSFADE * FPS), 1), total_frames)
    max_z = TRANSITION_ZOOM_START
    up_w = max(int(WIDTH * max_z * 1.08), WIDTH + 2)
    up_h = max(int(HEIGHT * max_z * 1.08), HEIGHT + 2)
    return (
        f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
        f"crop={up_w}:{up_h},"
        f"zoompan=z='if(lte(on,{zoom_frames}),"
        f"{max_z}-({max_z}-1.0)*on/{zoom_frames},1.0)'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )


def _foreground_scale(asset: MediaAsset, preset: str = "default") -> str:
    if preset == "wide":
        if asset.size_tier == SizeTier.SMALL:
            return "scale=760:-1"
        return "scale=880:-1"
    if asset.size_tier == SizeTier.SMALL:
        return "scale=900:-1"
    return f"scale={WIDTH}:-1"


def _build_image_vf(
    asset: MediaAsset,
    dur: float,
    transition_zoom: bool = False,
    blur_bg_motion: str = "none",
    crop_preset: str = "default",
) -> str:
    preset = crop_preset or "default"
    if asset.orientation == Orientation.PORTRAIT and not asset.needs_blur_background:
        base = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT}"
        )
    else:
        fg_scale = _foreground_scale(asset, preset)
        if blur_bg_motion == "pan":
            bg_chain = _pan_blur_bg_chain(dur)
        elif blur_bg_motion == "rotate":
            bg_chain = _rotate_blur_bg_chain(dur)
        else:
            bg_chain = _static_blur_bg_chain()
        base = _pillarbox_overlay(fg_scale, bg_chain)

    crop = _static_crop_filter(preset)
    if crop:
        base = f"{base},{crop}"

    if transition_zoom:
        return f"{base},{_transition_zoom_filter(dur)}"
    return f"{base},fps={FPS}"


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n{result.stderr[-5000:]}"
        )


def _probe_has_audio(path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return "audio" in result.stdout
    except Exception:
        return False


def _segment_raw_duration(seg: TimelineSegment) -> float:
    return (seg.end_sec - seg.start_sec) + seg.fade_out


def _render_end_card_segment(seg: TimelineSegment, frame_path: Path, work_dir: Path) -> Path:
    out = work_dir / "seg_end_card.mp4"
    dur = max(_segment_raw_duration(seg), 0.5)
    _run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(frame_path),
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={dur}",
            "-vf",
            f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-t",
            str(dur),
            str(out),
        ]
    )
    return out


def _render_segment(seg: TimelineSegment, index: int, work_dir: Path) -> Path:
    out = work_dir / f"seg_{index:02d}.mp4"
    asset = seg.asset
    dur = _segment_raw_duration(seg)
    dur = max(dur, 0.5)

    if asset.kind == MediaKind.END_CARD:
        raise ValueError("END_CARD must be rendered via _render_end_card_segment")

    if asset.kind == MediaKind.NONE or not asset.local_path:
        color = "E60012"
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x{color}:s={WIDTH}x{HEIGHT}:d={dur}:r={FPS}",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=stereo:d={dur}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-t",
                str(dur),
                str(out),
            ]
        )
        return out

    src = str(asset.local_path)

    if asset.is_image:
        vf = _build_image_vf(
            asset, dur, seg.transition_zoom, seg.blur_bg_motion, seg.crop_preset
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                src,
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=stereo:d={dur}",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-t",
                str(dur),
                str(out),
            ]
        )
        return out

    keep_audio = asset.is_video and asset.has_audio
    if asset.orientation == Orientation.PORTRAIT:
        vf = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},fps={FPS}"
        )
    else:
        tint = _page_bg_tint_filter()
        vf = (
            f"split[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},boxblur=30:5,{tint}[bgbl];"
            f"[fg]scale={WIDTH}:-1[fgsc];"
            f"[bgbl][fgsc]overlay=(W-w)/2:(H-h)/2:format=auto,fps={FPS}"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-t",
        str(dur),
    ]
    if keep_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        cmd.append("-an")
    cmd.append(str(out))
    _run(cmd)
    return out


def _xfade_segments(segment_files: list[Path], segments: list[TimelineSegment], work_dir: Path) -> Path:
    if len(segment_files) == 1:
        return segment_files[0]

    out = work_dir / "merged.mp4"
    n = len(segment_files)
    inputs: list[str] = []
    for f in segment_files:
        inputs.extend(["-i", str(f)])

    v_parts: list[str] = []
    offset = _segment_raw_duration(segments[0]) - CROSSFADE
    prev = "[0:v]"
    for i in range(1, n):
        nxt = f"[v{i}]" if i < n - 1 else "[vout]"
        v_parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={CROSSFADE}:offset={max(offset, 0):.3f}{nxt}"
        )
        prev = nxt
        if i < n - 1:
            offset += _segment_raw_duration(segments[i]) - CROSSFADE

    a_parts: list[str] = []
    for i, seg in enumerate(segments):
        dur = _segment_raw_duration(seg)
        if _probe_has_audio(segment_files[i]):
            a_parts.append(f"[{i}:a]atrim=0:{dur},asetpts=PTS-STARTPTS[a{i}]")
        else:
            a_parts.append(
                f"anullsrc=r=44100:cl=stereo,atrim=0:{dur},asetpts=PTS-STARTPTS[a{i}]"
            )

    concat_a = "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
    fc = ";".join(v_parts + a_parts + [concat_a])

    _run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            fc,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-aspect",
            "9:16",
            "-c:a",
            "aac",
            str(out),
        ]
    )
    return out


def _content_end_sec(plan: VideoPlan) -> float:
    """エンドカード開始時刻（左上バッジはこの直前まで表示）。"""
    for seg in plan.segments:
        if seg.asset.kind == MediaKind.END_CARD:
            return seg.start_sec
    return max(plan.total_duration - plan.end_card_duration, 0.0)


def _mix_bgm(
    merged: Path,
    plan: VideoPlan,
    output_path: Path,
    wm_path: Path,
    telop_paths: list[tuple[Path, float, float]],
) -> None:
    dur = plan.total_duration
    has_merged_audio = _probe_has_audio(merged)
    content_end = _content_end_sec(plan)

    # エンドカード中は左上バッジを出さない（wash は本編ぼかし背景／エンド背景側で済ます）
    wm_enable = f"lt(t,{content_end:.3f})"
    fc_parts = [f"[0:v][1:v]overlay=0:0:format=auto:enable='{wm_enable}'[vwm]"]
    inputs = ["-i", str(merged), "-i", str(wm_path)]

    for telop_path, _, _ in telop_paths:
        inputs.extend(["-i", str(telop_path)])

    prev = "vwm"
    for i, (_, start, end) in enumerate(telop_paths):
        inp = i + 2
        out = f"vt{i}" if i < len(telop_paths) - 1 else "vpre"
        fc_parts.append(
            f"[{prev}][{inp}:v]overlay=0:0:format=auto:enable='between(t,{start:.3f},{end:.3f})'[{out}]"
        )
        prev = out

    fc_parts.append(f"[{prev}]null[vfinal]")

    bgm_in = 2 + len(telop_paths)
    fade_out = max(dur - 0.8, 0)

    if plan.has_video_audio and has_merged_audio:
        fc_parts.append(
            f"[0:a]volume=1.0,afade=t=out:st={max(dur - 0.5, 0):.3f}:d=0.5[aout]"
        )
    elif plan.bgm_path and plan.bgm_path.exists():
        inputs.extend(["-i", str(plan.bgm_path)])
        fc_parts.append(
            f"[{bgm_in}:a]aloop=loop=-1:size=2e+09,atrim=0:{dur},"
            f"volume={BGM_VOLUME},afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out:.3f}:d=0.8[aout]"
        )
    elif has_merged_audio:
        fc_parts.append(f"[0:a]volume=0.8[aout]")
    else:
        fc_parts.append(f"anullsrc=r=44100:cl=stereo:d={dur}[aout]")

    _run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(fc_parts),
            "-map",
            "[vfinal]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-aspect",
            "9:16",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-t",
            str(dur),
            str(output_path),
        ]
    )


def build_ffmpeg_command(plan: VideoPlan, output_path: Path, font_path: str = DEFAULT_FONT) -> dict:
    steps = []
    for i, seg in enumerate(plan.segments):
        asset = seg.asset
        layout = "full" if asset.orientation == Orientation.PORTRAIT else "blur_pillarbox"
        steps.append(
            {
                "step": f"segment_{i}",
                "asset_id": asset.id,
                "kind": asset.kind.value,
                "layout": layout,
                "duration_sec": seg.duration,
                "fade_out_sec": seg.fade_out,
                "transition_zoom": seg.transition_zoom,
                "blur_bg_motion": seg.blur_bg_motion,
                "crop_preset": seg.crop_preset,
                "keep_audio": asset.is_video and asset.has_audio,
            }
        )
    steps.append({"step": "xfade", "duration": CROSSFADE})
    steps.append({"step": "overlay", "watermark": plan.watermark, "telops": [t.text for t in plan.telops]})
    steps.append(
        {
            "step": "bgm",
            "path": str(plan.bgm_path) if plan.bgm_path else None,
            "has_video_audio": plan.has_video_audio,
        }
    )
    steps.append({"step": "end_card", "duration": plan.end_card_duration})
    steps.append({"step": "encode", "output": str(output_path), "resolution": f"{WIDTH}x{HEIGHT}"})
    return {"pattern_blocked": plan.blocked, "steps": steps}


def render_video(
    plan: VideoPlan,
    output_path: Path,
    font_path: str = DEFAULT_FONT,
    work_dir: Path | None = None,
    dry_run: bool = False,
) -> Path:
    work_dir = work_dir or output_path.parent / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_ffmpeg_command(plan, output_path, font_path)
    (output_path.parent / "ffmpeg_plan.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if plan.blocked:
        return _render_warning(plan, output_path, font_path)

    if dry_run:
        return output_path

    end_frame = render_end_card_frame(plan, work_dir)

    segment_files: list[Path] = []
    content_segments: list[TimelineSegment] = []
    for i, seg in enumerate(plan.segments):
        if seg.asset.kind == MediaKind.END_CARD:
            segment_files.append(_render_end_card_segment(seg, end_frame, work_dir))
        else:
            segment_files.append(_render_segment(seg, i, work_dir))
        content_segments.append(seg)

    merged = _xfade_segments(segment_files, content_segments, work_dir)
    wm_path, telop_paths = render_overlays(plan, work_dir)
    _mix_bgm(merged, plan, output_path, wm_path, telop_paths)
    return output_path


def _render_warning(plan: VideoPlan, output_path: Path, font_path: str) -> Path:
    from PIL import Image, ImageDraw

    from bonecta.fonts import load_font
    from bonecta.overlays import HEIGHT, WIDTH

    img = Image.new("RGB", (WIDTH, HEIGHT), (51, 51, 51))
    draw = ImageDraw.Draw(img)
    font = load_font(48)
    msg = plan.block_reason or "コンテンツを確認できません"
    tw = draw.textbbox((0, 0), msg, font=font)[2]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 - 24), msg, fill=(255, 255, 255), font=font)
    tmp = output_path.parent / ".work" / "warning.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    img.save(tmp)
    _run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(tmp),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            "5",
            str(output_path),
        ]
    )
    return output_path

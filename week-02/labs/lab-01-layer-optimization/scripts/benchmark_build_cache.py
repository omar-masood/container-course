#!/usr/bin/env python3
"""
Benchmark Docker layer caching for the Week 2 Layer Optimization lab.

This script runs real docker builds for the slow and optimized Dockerfiles,
captures timings + cache behavior, and generates summary charts.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
BUILDKIT_STEP_RE = re.compile(r"^#(?P<id>\d+)\s+\[(?P<index>\d+)/(?P<total>\d+)\]\s+(?P<desc>.+)$")
BUILDKIT_STATUS_RE = re.compile(r"^#(?P<id>\d+)\s+(?P<status>CACHED|DONE(?:\s+.+)?)$")
LEGACY_STEP_RE = re.compile(r"^Step\s+(?P<index>\d+)/(?P<total>\d+)\s+:\s+(?P<desc>.+)$")


@dataclass
class BuildMetrics:
    name: str
    dockerfile: str
    cold_cache: bool
    duration_seconds: float
    total_steps: int
    cached_steps: int
    cache_hit_ratio: float
    pip_layer_cached: Optional[bool]
    log_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run layer-cache benchmarks and generate timing/cache charts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for logs, JSON, and charts.",
    )
    parser.add_argument(
        "--tag-prefix",
        default="data-processor-bench",
        help="Docker image tag prefix used for temporary benchmark images.",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Do not remove benchmark images after the run.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the temporary benchmark workspace for inspection.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation (still writes logs, JSON, and summary report).",
    )
    return parser.parse_args()


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def copy_starter_files(starter_dir: Path, workdir: Path) -> None:
    for item in starter_dir.iterdir():
        destination = workdir / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def append_code_change(app_path: Path, label: str) -> None:
    with app_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n# benchmark-change: {label}\n")


def parse_buildkit(lines: List[str]) -> Dict[str, Optional[float]]:
    steps_by_id: Dict[str, Dict[str, object]] = {}
    total_steps = 0

    for line in lines:
        step_match = BUILDKIT_STEP_RE.match(line)
        if step_match:
            step_id = step_match.group("id")
            step_desc = step_match.group("desc")
            index = int(step_match.group("index"))
            total = int(step_match.group("total"))
            steps_by_id[step_id] = {"desc": step_desc, "index": index, "status": None}
            total_steps = max(total_steps, total)
            continue

        status_match = BUILDKIT_STATUS_RE.match(line)
        if status_match:
            step_id = status_match.group("id")
            if step_id in steps_by_id:
                status = status_match.group("status")
                steps_by_id[step_id]["status"] = "CACHED" if status.startswith("CACHED") else "DONE"

    cached_steps = sum(
        1 for step in steps_by_id.values() if step.get("status") == "CACHED"
    )

    pip_layer_cached: Optional[bool] = None
    for step in steps_by_id.values():
        desc = str(step.get("desc", "")).lower()
        if "run pip install" in desc:
            pip_layer_cached = step.get("status") == "CACHED"
            break

    return {
        "total_steps": total_steps,
        "cached_steps": cached_steps,
        "pip_layer_cached": pip_layer_cached,
    }


def parse_legacy(lines: List[str]) -> Dict[str, Optional[float]]:
    total_steps = 0
    current_desc = ""
    current_is_pip = False
    cached_steps = 0
    pip_layer_cached: Optional[bool] = None

    for line in lines:
        step_match = LEGACY_STEP_RE.match(line)
        if step_match:
            total_steps = max(total_steps, int(step_match.group("total")))
            current_desc = step_match.group("desc")
            current_is_pip = "run pip install" in current_desc.lower()
            if current_is_pip and pip_layer_cached is None:
                pip_layer_cached = False
            continue

        if "Using cache" in line:
            cached_steps += 1
            if current_is_pip:
                pip_layer_cached = True

    return {
        "total_steps": total_steps,
        "cached_steps": cached_steps,
        "pip_layer_cached": pip_layer_cached,
    }


def parse_build_log(raw_log: str) -> Dict[str, Optional[float]]:
    cleaned = strip_ansi(raw_log)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    is_buildkit = any(BUILDKIT_STEP_RE.match(line) for line in lines)
    parsed = parse_buildkit(lines) if is_buildkit else parse_legacy(lines)

    total_steps = int(parsed.get("total_steps") or 0)
    cached_steps = int(parsed.get("cached_steps") or 0)
    cache_hit_ratio = (cached_steps / total_steps) if total_steps else 0.0

    return {
        "total_steps": total_steps,
        "cached_steps": cached_steps,
        "cache_hit_ratio": cache_hit_ratio,
        "pip_layer_cached": parsed.get("pip_layer_cached"),
    }


def run_build(
    *,
    name: str,
    dockerfile: str,
    image_tag: str,
    workdir: Path,
    logs_dir: Path,
    no_cache: bool,
) -> BuildMetrics:
    base_cmd = ["docker", "build"]
    if no_cache:
        base_cmd.append("--no-cache")
    base_cmd.extend(["-t", image_tag, "-f", dockerfile, "."])

    commands = [
        ["docker", "build", "--progress=plain", *base_cmd[2:]],
        base_cmd,
    ]

    command_output = ""
    completed: Optional[subprocess.CompletedProcess[str]] = None
    duration = 0.0

    for attempt_index, cmd in enumerate(commands):
        started = time.perf_counter()
        attempt = subprocess.run(
            cmd,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        duration = time.perf_counter() - started

        if attempt.returncode == 0:
            completed = attempt
            command_output = attempt.stdout if attempt_index == 0 else command_output + "\n" + attempt.stdout
            break

        output = attempt.stdout
        if attempt_index == 0 and "unknown flag: --progress" in output:
            command_output = output
            continue

        completed = attempt
        command_output = output
        break

    if completed is None:
        raise RuntimeError(f"Unexpected internal error while running build '{name}'.")

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{name}.log"
    log_path.write_text(command_output, encoding="utf-8")

    if completed.returncode != 0:
        raise RuntimeError(
            f"Build '{name}' failed with exit code {completed.returncode}. "
            f"See log: {log_path}"
        )

    parsed = parse_build_log(command_output)
    return BuildMetrics(
        name=name,
        dockerfile=dockerfile,
        cold_cache=no_cache,
        duration_seconds=round(duration, 3),
        total_steps=int(parsed["total_steps"]),
        cached_steps=int(parsed["cached_steps"]),
        cache_hit_ratio=round(float(parsed["cache_hit_ratio"]), 4),
        pip_layer_cached=parsed["pip_layer_cached"],  # type: ignore[arg-type]
        log_path=str(log_path),
    )


def generate_charts(results: List[BuildMetrics], output_dir: Path) -> List[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required to generate charts. "
            "Install it with: pip install matplotlib"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    labels = [item.name.replace("_", "\n") for item in results]
    durations = [item.duration_seconds for item in results]

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#E76F51", "#E76F51", "#2A9D8F", "#2A9D8F"]
    bars = ax.bar(labels, durations, color=colors)
    ax.set_title("Docker Build Time Benchmark (Real Runs)")
    ax.set_ylabel("Seconds")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle="--", alpha=0.35)

    for bar, value in zip(bars, durations):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.1f}s",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    times_path = output_dir / "build_times.png"
    fig.tight_layout()
    fig.savefig(times_path, dpi=160)
    plt.close(fig)

    cache_rates = [item.cache_hit_ratio * 100 for item in results]
    pip_cached = [1 if item.pip_layer_cached else 0 for item in results]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    axes[0].bar(labels, cache_rates, color="#457B9D")
    axes[0].set_title("Cached Layer Rate")
    axes[0].set_ylabel("Percent of steps cached")
    axes[0].set_ylim(0, 100)
    axes[0].set_axisbelow(True)
    axes[0].yaxis.grid(True, linestyle="--", alpha=0.35)

    axes[1].bar(labels, pip_cached, color="#264653")
    axes[1].set_title("Was pip install layer cached?")
    axes[1].set_ylabel("Cached")
    axes[1].set_ylim(0, 1.1)
    axes[1].set_yticks([0, 1], labels=["No", "Yes"])
    axes[1].set_axisbelow(True)
    axes[1].yaxis.grid(True, linestyle="--", alpha=0.35)

    cache_path = output_dir / "cache_effectiveness.png"
    fig.tight_layout()
    fig.savefig(cache_path, dpi=160)
    plt.close(fig)

    return [str(times_path), str(cache_path)]


def build_summary(results: List[BuildMetrics]) -> Dict[str, float]:
    metrics_by_name = {item.name: item for item in results}
    slow_rebuild = metrics_by_name["slow_rebuild"].duration_seconds
    fast_rebuild = metrics_by_name["fast_rebuild"].duration_seconds

    if fast_rebuild == 0:
        speedup = 0.0
    else:
        speedup = slow_rebuild / fast_rebuild

    return {
        "slow_rebuild_seconds": slow_rebuild,
        "fast_rebuild_seconds": fast_rebuild,
        "seconds_saved": round(slow_rebuild - fast_rebuild, 3),
        "speedup_factor": round(speedup, 2),
    }


def write_summary_markdown(
    output_dir: Path, results: List[BuildMetrics], summary: Dict[str, float]
) -> Path:
    lines = [
        "# Layer Cache Benchmark Results",
        "",
        "| Build | Dockerfile | Cold Cache | Duration (s) | Cached Steps | Total Steps | Cache Hit % | pip install Cached |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    for item in results:
        pip_cached = "yes" if item.pip_layer_cached else "no"
        lines.append(
            f"| `{item.name}` | `{item.dockerfile}` | "
            f"{'yes' if item.cold_cache else 'no'} | {item.duration_seconds:.3f} | "
            f"{item.cached_steps} | {item.total_steps} | {item.cache_hit_ratio * 100:.1f}% | {pip_cached} |"
        )

    lines.extend(
        [
            "",
            "## Key Comparison",
            "",
            f"- Slow rebuild: **{summary['slow_rebuild_seconds']:.3f}s**",
            f"- Fast rebuild: **{summary['fast_rebuild_seconds']:.3f}s**",
            f"- Time saved: **{summary['seconds_saved']:.3f}s**",
            f"- Speedup: **{summary['speedup_factor']:.2f}x**",
        ]
    )

    report_path = output_dir / "summary.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def cleanup_images(image_tags: List[str]) -> None:
    if not image_tags:
        return
    subprocess.run(
        ["docker", "rmi", "-f", *image_tags],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main() -> None:
    args = parse_args()

    script_dir = Path(__file__).resolve().parent
    lab_dir = script_dir.parent
    course_root = lab_dir.parents[2]
    output_dir = (
        args.output_dir
        if args.output_dir
        else course_root / "assets" / "generated" / "week-02-layer-cache"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"

    starter_dir = lab_dir / "starter"
    optimized_dockerfile = lab_dir / "solution" / "Dockerfile.optimized"

    if not starter_dir.exists():
        raise FileNotFoundError(f"Starter directory not found: {starter_dir}")
    if not optimized_dockerfile.exists():
        raise FileNotFoundError(f"Optimized Dockerfile not found: {optimized_dockerfile}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    image_tags = {
        "slow_cold": f"{args.tag_prefix}:slow-cold-{timestamp}",
        "slow_rebuild": f"{args.tag_prefix}:slow-rebuild-{timestamp}",
        "fast_cold": f"{args.tag_prefix}:fast-cold-{timestamp}",
        "fast_rebuild": f"{args.tag_prefix}:fast-rebuild-{timestamp}",
    }

    results: List[BuildMetrics] = []
    temp_workspace_path: Optional[Path] = None

    with tempfile.TemporaryDirectory(prefix="layer-cache-bench-") as temp_dir:
        workdir = Path(temp_dir)
        copy_starter_files(starter_dir, workdir)
        shutil.copy2(optimized_dockerfile, workdir / "Dockerfile.optimized")

        app_path = workdir / "app.py"
        if not app_path.exists():
            raise FileNotFoundError(f"Expected app.py in benchmark workspace: {app_path}")

        results.append(
            run_build(
                name="slow_cold",
                dockerfile="Dockerfile",
                image_tag=image_tags["slow_cold"],
                workdir=workdir,
                logs_dir=logs_dir,
                no_cache=True,
            )
        )

        append_code_change(app_path, "after-slow-cold")
        results.append(
            run_build(
                name="slow_rebuild",
                dockerfile="Dockerfile",
                image_tag=image_tags["slow_rebuild"],
                workdir=workdir,
                logs_dir=logs_dir,
                no_cache=False,
            )
        )

        results.append(
            run_build(
                name="fast_cold",
                dockerfile="Dockerfile.optimized",
                image_tag=image_tags["fast_cold"],
                workdir=workdir,
                logs_dir=logs_dir,
                no_cache=True,
            )
        )

        append_code_change(app_path, "after-fast-cold")
        results.append(
            run_build(
                name="fast_rebuild",
                dockerfile="Dockerfile.optimized",
                image_tag=image_tags["fast_rebuild"],
                workdir=workdir,
                logs_dir=logs_dir,
                no_cache=False,
            )
        )

        if args.keep_workdir:
            persisted = output_dir / "benchmark-workdir"
            if persisted.exists():
                shutil.rmtree(persisted)
            shutil.copytree(workdir, persisted)
            temp_workspace_path = persisted

    summary = build_summary(results)
    report_path = write_summary_markdown(output_dir, results, summary)
    chart_paths: List[str] = []
    chart_error: Optional[str] = None

    if not args.no_charts:
        try:
            chart_paths = generate_charts(results, output_dir)
        except RuntimeError as exc:
            chart_error = str(exc)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(item) for item in results],
        "summary": summary,
        "charts": chart_paths,
        "report": str(report_path),
    }
    if temp_workspace_path:
        payload["saved_workspace"] = str(temp_workspace_path)
    if chart_error:
        payload["chart_error"] = chart_error

    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not args.keep_images:
        cleanup_images(list(image_tags.values()))

    print(f"Benchmark complete. Results written to: {output_dir}")
    print(f"- JSON: {json_path}")
    print(f"- Report: {report_path}")
    if chart_paths:
        print("- Charts:")
        for chart in chart_paths:
            print(f"  - {chart}")
    elif args.no_charts:
        print("- Charts: skipped (--no-charts)")
    elif chart_error:
        print(f"- Charts: not generated ({chart_error})")


if __name__ == "__main__":
    main()

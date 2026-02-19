#!/usr/bin/env python3
"""
Build and scan vulnerable-app v1/v2/v3 with Trivy, then generate charts.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]


@dataclass
class VersionScanResult:
    version: str
    image_tag: str
    total_vulnerabilities: int
    severity_counts: Dict[str, int]
    high_critical_total: int
    dockerfile_base: str
    requirements_snapshot: Dict[str, str]
    build_log_path: str
    trivy_log_path: str
    trivy_json_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Trivy vulnerability trend charts for v1/v2/v3."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for logs, JSON, report, and charts.",
    )
    parser.add_argument(
        "--tag-prefix",
        default="vulnerable-app-bench",
        help="Docker image tag prefix used for benchmark images.",
    )
    parser.add_argument(
        "--trivy-bin",
        default="trivy",
        help="Trivy executable to use (default: trivy).",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Do not remove benchmark images after completion.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation (still writes JSON/report/logs).",
    )
    return parser.parse_args()


def run_command(
    cmd: List[str],
    cwd: Path,
    *,
    stdout_path: Optional[Path] = None,
    stderr_path: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if stdout_path is not None and stderr_path is not None and stdout_path == stderr_path:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(
            completed.stdout + ("\n" if completed.stdout and completed.stderr else "") + completed.stderr,
            encoding="utf-8",
        )
        return completed

    if stdout_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
    if stderr_path is not None:
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    return completed


def replace_python_base(dockerfile_path: Path, base_image: str) -> str:
    lines = dockerfile_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    updated_lines: List[str] = []
    for line in lines:
        if line.strip().startswith("FROM ") and not replaced:
            updated_lines.append(f"FROM {base_image}")
            replaced = True
        else:
            updated_lines.append(line)
    if not replaced:
        raise RuntimeError(f"Could not find FROM line in {dockerfile_path}")
    dockerfile_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return base_image


def update_requirements(requirements_path: Path, updates: Dict[str, str]) -> Dict[str, str]:
    lines = requirements_path.read_text(encoding="utf-8").splitlines()
    resolved: Dict[str, str] = {}
    output: List[str] = []

    for line in lines:
        stripped = line.strip()
        if "==" in stripped and not stripped.startswith("#"):
            pkg, _, version = stripped.partition("==")
            key = pkg.strip().lower()
            if key in updates:
                new_version = updates[key]
                output.append(f"{pkg.strip()}=={new_version}")
                resolved[key] = new_version
                continue
            resolved[key] = version.strip()
        output.append(line)

    requirements_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return resolved


def parse_requirements_snapshot(requirements_path: Path) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "==" in stripped and not stripped.startswith("#"):
            pkg, _, version = stripped.partition("==")
            snapshot[pkg.strip().lower()] = version.strip()
    return snapshot


def parse_trivy_results(trivy_json: Dict[str, object]) -> Dict[str, int]:
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    seen = set()
    results = trivy_json.get("Results", [])
    if not isinstance(results, list):
        return counts

    for result in results:
        if not isinstance(result, dict):
            continue
        target = str(result.get("Target", "unknown-target"))
        vulns = result.get("Vulnerabilities", [])
        if not isinstance(vulns, list):
            continue
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            sev = str(vuln.get("Severity", "UNKNOWN")).upper()
            pkg = str(vuln.get("PkgName", ""))
            vuln_id = str(vuln.get("VulnerabilityID", ""))
            installed = str(vuln.get("InstalledVersion", ""))
            key = (target, pkg, vuln_id, installed)
            if key in seen:
                continue
            seen.add(key)
            if sev not in counts:
                counts["UNKNOWN"] += 1
            else:
                counts[sev] += 1
    return counts


def generate_charts(results: List[VersionScanResult], output_dir: Path) -> List[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required to generate charts. Install with: pip install matplotlib"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    labels = [item.version for item in results]

    stacked_path = output_dir / "trivy_severity_stacked.png"
    fig, ax = plt.subplots(figsize=(10, 5))
    bottoms = [0] * len(results)
    colors = {
        "CRITICAL": "#b5172f",
        "HIGH": "#f94144",
        "MEDIUM": "#f8961e",
        "LOW": "#90be6d",
        "UNKNOWN": "#577590",
    }
    for severity in SEVERITY_ORDER:
        values = [item.severity_counts.get(severity, 0) for item in results]
        ax.bar(labels, values, bottom=bottoms, color=colors[severity], label=severity)
        bottoms = [a + b for a, b in zip(bottoms, values)]

    for idx, total in enumerate(bottoms):
        ax.text(idx, total, str(total), ha="center", va="bottom", fontsize=9)

    ax.set_title("Trivy Vulnerability Breakdown by Version")
    ax.set_ylabel("Unique vulnerabilities")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle="--", alpha=0.35)
    ax.legend(title="Severity")
    fig.tight_layout()
    fig.savefig(stacked_path, dpi=160)
    plt.close(fig)

    trend_path = output_dir / "trivy_high_critical_trend.png"
    fig, ax = plt.subplots(figsize=(10, 4.8))
    totals = [item.total_vulnerabilities for item in results]
    high_critical = [item.high_critical_total for item in results]

    ax.plot(labels, totals, marker="o", linewidth=2, color="#264653", label="Total")
    ax.plot(labels, high_critical, marker="o", linewidth=2, color="#d62828", label="High + Critical")
    for x, y in zip(labels, totals):
        ax.text(x, y, str(y), ha="center", va="bottom", fontsize=9)
    for x, y in zip(labels, high_critical):
        ax.text(x, y, str(y), ha="center", va="top", fontsize=9)

    ax.set_title("Risk Trend Across Remediation Steps")
    ax.set_ylabel("Vulnerability count")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle="--", alpha=0.35)
    ax.legend()
    fig.tight_layout()
    fig.savefig(trend_path, dpi=160)
    plt.close(fig)

    return [str(stacked_path), str(trend_path)]


def write_summary_markdown(output_dir: Path, results: List[VersionScanResult]) -> Path:
    lines = [
        "# Trivy Scan Trend Summary",
        "",
        "| Version | Base Image | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | Total | High+Critical |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for item in results:
        c = item.severity_counts
        lines.append(
            f"| `{item.version}` | `{item.dockerfile_base}` | "
            f"{c.get('CRITICAL', 0)} | {c.get('HIGH', 0)} | {c.get('MEDIUM', 0)} | "
            f"{c.get('LOW', 0)} | {c.get('UNKNOWN', 0)} | {item.total_vulnerabilities} | "
            f"{item.high_critical_total} |"
        )

    baseline = results[0]
    final = results[-1]
    delta_total = baseline.total_vulnerabilities - final.total_vulnerabilities
    delta_high_critical = baseline.high_critical_total - final.high_critical_total

    lines.extend(
        [
            "",
            "## Improvement",
            "",
            f"- Total vulnerabilities reduced by **{delta_total}**",
            f"- High+Critical reduced by **{delta_high_critical}**",
            f"- Baseline: `{baseline.version}`",
            f"- Final: `{final.version}`",
        ]
    )

    report_path = output_dir / "summary.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def prepare_workspace(starter_dir: Path, version: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix=f"trivy-{version}-"))
    for item in starter_dir.iterdir():
        dest = temp_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    dockerfile = temp_dir / "Dockerfile"
    requirements = temp_dir / "requirements.txt"

    if version in ("v2", "v3"):
        replace_python_base(dockerfile, "python:3.11-slim")

    if version == "v3":
        update_requirements(
            requirements,
            updates={
                "flask": "3.0.0",
                "requests": "2.31.0",
                "werkzeug": "3.0.1",
                "jinja2": "3.1.3",
            },
        )

    return temp_dir


def cleanup_images(tags: List[str]) -> None:
    if not tags:
        return
    subprocess.run(
        ["docker", "rmi", "-f", *tags],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    lab_dir = script_dir.parent
    course_root = lab_dir.parents[2]
    starter_dir = lab_dir / "starter"
    output_dir = (
        args.output_dir
        if args.output_dir
        else course_root / "assets" / "generated" / "week-02-trivy-scan"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    scans_dir = output_dir / "scans"
    scans_dir.mkdir(parents=True, exist_ok=True)

    if not starter_dir.exists():
        raise FileNotFoundError(f"Starter directory not found: {starter_dir}")

    trivy_check = subprocess.run(
        [args.trivy_bin, "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if trivy_check.returncode != 0:
        raise RuntimeError(
            f"Unable to run '{args.trivy_bin} --version'. Install Trivy or set --trivy-bin."
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    versions = ["v1", "v2", "v3"]
    image_tags = {v: f"{args.tag_prefix}:{v}-{timestamp}" for v in versions}
    results: List[VersionScanResult] = []
    workspaces: List[Path] = []

    try:
        for version in versions:
            workspace = prepare_workspace(starter_dir, version)
            workspaces.append(workspace)

            build_log = logs_dir / f"{version}.build.log"
            build_cmd = ["docker", "build", "-t", image_tags[version], "."]
            build_result = run_command(build_cmd, workspace, stdout_path=build_log, stderr_path=build_log)
            if build_result.returncode != 0:
                raise RuntimeError(
                    f"Docker build failed for {version}. See: {build_log}"
                )

            trivy_json_path = scans_dir / f"{version}.trivy.json"
            trivy_log_path = logs_dir / f"{version}.trivy.log"
            trivy_cmd = [
                args.trivy_bin,
                "image",
                "--quiet",
                "--scanners",
                "vuln",
                "--format",
                "json",
                image_tags[version],
            ]
            trivy_result = run_command(
                trivy_cmd,
                workspace,
                stdout_path=trivy_json_path,
                stderr_path=trivy_log_path,
            )
            if trivy_result.returncode not in (0,):
                raise RuntimeError(
                    f"Trivy scan failed for {version} (exit {trivy_result.returncode}). "
                    f"See: {trivy_log_path}"
                )

            try:
                parsed = json.loads(trivy_json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid Trivy JSON for {version}. See: {trivy_json_path}"
                ) from exc

            severity_counts = parse_trivy_results(parsed)
            total = sum(severity_counts.values())
            high_critical = severity_counts["HIGH"] + severity_counts["CRITICAL"]
            requirements_snapshot = parse_requirements_snapshot(workspace / "requirements.txt")
            base_image = "python:3.11-slim" if version in ("v2", "v3") else "python:3.9-slim"

            results.append(
                VersionScanResult(
                    version=version,
                    image_tag=image_tags[version],
                    total_vulnerabilities=total,
                    severity_counts=severity_counts,
                    high_critical_total=high_critical,
                    dockerfile_base=base_image,
                    requirements_snapshot=requirements_snapshot,
                    build_log_path=str(build_log),
                    trivy_log_path=str(trivy_log_path),
                    trivy_json_path=str(trivy_json_path),
                )
            )

    finally:
        for path in workspaces:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

    report_path = write_summary_markdown(output_dir, results)
    chart_paths: List[str] = []
    chart_error: Optional[str] = None
    if not args.no_charts:
        try:
            chart_paths = generate_charts(results, output_dir)
        except RuntimeError as exc:
            chart_error = str(exc)

    summary_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "trivy_version_output": trivy_check.stdout.strip(),
        "results": [asdict(item) for item in results],
        "charts": chart_paths,
        "report": str(report_path),
    }
    if chart_error:
        summary_payload["chart_error"] = chart_error

    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")

    if not args.keep_images:
        cleanup_images(list(image_tags.values()))

    print(f"Trivy benchmark complete. Results written to: {output_dir}")
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

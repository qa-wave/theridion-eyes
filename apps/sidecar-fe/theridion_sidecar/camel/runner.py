"""Apache Camel Maven test runner — writes files to temp dir, executes mvn test,
parses surefire XML reports and returns structured results.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..storage import home_dir
from .runtime import detect_runtime


class CamelTestResult(BaseModel):
    name: str  # method name from surefire report
    classname: str
    status: Literal["passed", "failed", "skipped", "error"]
    duration_ms: float
    failure_message: str | None = None
    failure_stack: str | None = None  # truncated to 2000 chars


class CamelRunReport(BaseModel):
    success: bool  # all tests passed
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_ms: float
    tests: list[CamelTestResult]
    mvn_stdout: str  # truncated to 8000 chars
    mvn_stderr: str  # truncated to 4000 chars
    mvn_exit_code: int
    work_dir: str  # where execution happened (for debug)


def _parse_surefire_xml(xml_path: Path) -> list[CamelTestResult]:
    """Parse a single TEST-*.xml surefire report into CamelTestResult list."""
    results: list[CamelTestResult] = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError:
        return results

    for tc in root.findall("testcase"):
        name = tc.get("name", "")
        classname = tc.get("classname", "")
        time_str = tc.get("time", "0")
        try:
            duration_ms = float(time_str) * 1000.0
        except (ValueError, TypeError):
            duration_ms = 0.0

        failure_message: str | None = None
        failure_stack: str | None = None
        status: Literal["passed", "failed", "skipped", "error"] = "passed"

        failure_el = tc.find("failure")
        error_el = tc.find("error")
        skipped_el = tc.find("skipped")

        if failure_el is not None:
            status = "failed"
            failure_message = failure_el.get("message")
            raw_stack = failure_el.text or ""
            failure_stack = raw_stack[:2000] if raw_stack else None
        elif error_el is not None:
            status = "error"
            failure_message = error_el.get("message")
            raw_stack = error_el.text or ""
            failure_stack = raw_stack[:2000] if raw_stack else None
        elif skipped_el is not None:
            status = "skipped"

        results.append(
            CamelTestResult(
                name=name,
                classname=classname,
                status=status,
                duration_ms=duration_ms,
                failure_message=failure_message,
                failure_stack=failure_stack,
            )
        )

    return results


def _parse_all_surefire_reports(work_dir: Path) -> list[CamelTestResult]:
    """Find and parse all TEST-*.xml files in target/surefire-reports/."""
    reports_dir = work_dir / "target" / "surefire-reports"
    results: list[CamelTestResult] = []
    if not reports_dir.exists():
        return results
    for xml_file in sorted(reports_dir.glob("TEST-*.xml")):
        results.extend(_parse_surefire_xml(xml_file))
    return results


def _write_files(files: dict[str, str], base_dir: Path) -> None:
    """Write all files to base_dir, creating subdirectories as needed."""
    for rel_path, content in files.items():
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        # Make mvnw executable on Unix
        if rel_path in ("mvnw", "./mvnw") or rel_path.endswith("/mvnw"):
            try:
                current_mode = target.stat().st_mode
                target.chmod(current_mode | 0o111)
            except OSError:
                pass


def _run_maven_sync(
    work_dir: Path,
    use_mvnw: bool,
    env: dict[str, str] | None,
) -> tuple[str, str, int]:
    """Run Maven synchronously. Returns (stdout, stderr, returncode)."""
    if use_mvnw and (work_dir / "mvnw").exists():
        cmd = ["./mvnw", "test", "-q", "--no-transfer-progress"]
    else:
        cmd = ["mvn", "test", "-q", "--no-transfer-progress"]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Maven execution timed out (300s)", -1
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", -1
    except Exception as exc:
        return "", str(exc), -1


async def run_camel_test(
    files: dict[str, str],
    use_mvnw: bool = False,
) -> CamelRunReport:
    """Write files to a persistent work dir, run Maven, parse surefire reports.

    Args:
        files: mapping of relative_path -> file content
        use_mvnw: if True and mvnw is present in files, use ./mvnw instead of mvn
    """
    run_id = uuid.uuid4().hex[:8]
    work_dir = home_dir() / "camel-runs" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    _write_files(files, work_dir)

    # Build environment: inject JAVA_HOME if bundled JRE is present
    runtime = detect_runtime()
    env = dict(os.environ)
    if runtime.bundled_jre_present and runtime.bundled_jre_path:
        # JAVA_HOME should point to jre/ dir, not jre/bin/
        bundled_bin = Path(runtime.bundled_jre_path)
        java_home = str(bundled_bin.parent.parent)  # .../jre/bin/java -> .../jre
        env["JAVA_HOME"] = java_home

    stdout, stderr, exit_code = await asyncio.to_thread(
        _run_maven_sync, work_dir, use_mvnw, env
    )

    tests = _parse_all_surefire_reports(work_dir)

    passed = sum(1 for t in tests if t.status == "passed")
    failed = sum(1 for t in tests if t.status == "failed")
    skipped = sum(1 for t in tests if t.status == "skipped")
    errors = sum(1 for t in tests if t.status == "error")
    total = len(tests)

    total_duration_ms = sum(t.duration_ms for t in tests)

    return CamelRunReport(
        success=(exit_code == 0 and failed == 0 and errors == 0),
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration_ms=total_duration_ms,
        tests=tests,
        mvn_stdout=stdout[:8000],
        mvn_stderr=stderr[:4000],
        mvn_exit_code=exit_code,
        work_dir=str(work_dir),
    )

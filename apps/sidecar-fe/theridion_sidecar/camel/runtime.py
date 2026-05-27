"""Java and Maven runtime detection for Apache Camel test execution."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..storage import home_dir


class RuntimeStatus(BaseModel):
    java_available: bool
    java_path: str | None  # absolute path to the java binary
    java_version: str | None  # e.g. "21.0.5"
    java_source: Literal["system", "bundled", "none"]  # bundled = ~/.theridion/runtime/jre

    maven_available: bool
    maven_path: str | None
    maven_version: str | None  # e.g. "3.9.9"

    can_run_tests: bool  # java_available AND (maven_available OR mvnw usable)

    # UI hint: path where bundled JRE would live (or None if not present)
    bundled_jre_path: str | None
    bundled_jre_present: bool


def _bundled_java_path() -> Path | None:
    """Return the path to the bundled JRE java binary if it exists."""
    base = home_dir() / "runtime" / "jre" / "bin"
    candidates = [base / "java.exe", base / "java"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _bundled_jre_expected_path() -> Path:
    """Return the canonical bundled JRE directory path (may not exist)."""
    bin_dir = home_dir() / "runtime" / "jre" / "bin"
    if sys.platform == "win32":
        return bin_dir / "java.exe"
    return bin_dir / "java"


def _run_quiet(cmd: list[str], timeout: int = 5) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode). Never raises."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except Exception:
        return "", "", -1


def _parse_java_version(output: str) -> str | None:
    """Parse Java version string from java -version output (usually on stderr)."""
    # Matches: version "21.0.5", version "1.8.0_392", version "11.0.2"
    m = re.search(r'version\s+"([\d._]+)"', output)
    if m:
        return m.group(1)
    return None


def _parse_maven_version(output: str) -> str | None:
    """Parse Maven version from mvn -version output (on stdout)."""
    # Matches: Apache Maven 3.9.9 (...)
    m = re.search(r"Apache Maven\s+([\d.]+)", output)
    if m:
        return m.group(1)
    return None


def detect_runtime() -> RuntimeStatus:
    """Detect Java and Maven availability on the current system.

    Prefers bundled JRE at ~/.theridion/runtime/jre/ over system Java.
    Never raises — returns best-effort status on any error.
    """
    bundled_path = _bundled_java_path()
    expected_bundled = _bundled_jre_expected_path()

    java_path: str | None = None
    java_version: str | None = None
    java_available = False
    java_source: Literal["system", "bundled", "none"] = "none"

    # Prefer bundled JRE
    if bundled_path is not None:
        java_path = str(bundled_path)
        java_source = "bundled"
        stdout, stderr, rc = _run_quiet([java_path, "-version"])
        combined = stdout + stderr  # -version goes to stderr on most JDKs
        java_version = _parse_java_version(combined)
        java_available = rc == 0
    else:
        # Fall back to system java
        system_java = shutil.which("java")
        if system_java:
            java_path = system_java
            java_source = "system"
            stdout, stderr, rc = _run_quiet([system_java, "-version"])
            combined = stdout + stderr
            java_version = _parse_java_version(combined)
            java_available = rc == 0

    # Maven detection
    maven_path: str | None = None
    maven_version: str | None = None
    maven_available = False

    system_mvn = shutil.which("mvn")
    if system_mvn:
        maven_path = system_mvn
        stdout, stderr, rc = _run_quiet([system_mvn, "-version"])
        combined = stdout + stderr
        maven_version = _parse_maven_version(combined)
        maven_available = rc == 0

    can_run_tests = java_available and (maven_available or True)
    # "or True" because mvnw wrapper in generated files can substitute for mvn

    return RuntimeStatus(
        java_available=java_available,
        java_path=java_path,
        java_version=java_version,
        java_source=java_source,
        maven_available=maven_available,
        maven_path=maven_path,
        maven_version=maven_version,
        can_run_tests=java_available,  # need at least java; mvnw can cover maven
        bundled_jre_path=str(expected_bundled) if expected_bundled else None,
        bundled_jre_present=bundled_path is not None,
    )

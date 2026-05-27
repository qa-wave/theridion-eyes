"""Tests for Camel runtime detection and Maven test runner.

Covers:
  - detect_runtime() returns RuntimeStatus without raising
  - GET /api/camel/runtime endpoint
  - POST /api/camel/run with empty files → 400
  - Surefire XML parser (passed, failed, multiple files)
  - Bundled JRE detection (with monkeypatched home_dir)
  - Minimal Maven project execution (skipped if mvn unavailable)
"""

from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.camel.runtime import RuntimeStatus, detect_runtime
from theridion_sidecar.camel.runner import (
    CamelRunReport,
    _parse_all_surefire_reports,
    _parse_surefire_xml,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# 1. detect_runtime() never raises and returns RuntimeStatus
# ---------------------------------------------------------------------------


def test_detect_runtime_returns_status() -> None:
    status = detect_runtime()
    assert isinstance(status, RuntimeStatus)
    # Required fields must be present (pydantic validates)
    assert isinstance(status.java_available, bool)
    assert isinstance(status.maven_available, bool)
    assert isinstance(status.can_run_tests, bool)
    assert status.java_source in ("system", "bundled", "none")


# ---------------------------------------------------------------------------
# 2. GET /api/camel/runtime → 200 + correct shape
# ---------------------------------------------------------------------------


def test_runtime_endpoint(client: TestClient) -> None:
    resp = client.get("/api/camel/runtime")
    assert resp.status_code == 200
    data = resp.json()
    assert "java_available" in data
    assert "maven_available" in data
    assert "can_run_tests" in data
    assert data["java_source"] in ("system", "bundled", "none")


# ---------------------------------------------------------------------------
# 3. POST /api/camel/run with empty files → 400
# ---------------------------------------------------------------------------


def test_run_without_files_400(client: TestClient) -> None:
    resp = client.post("/api/camel/run", json={"files": {}})
    assert resp.status_code == 400
    assert "no files provided" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Surefire XML parser — passed test
# ---------------------------------------------------------------------------

_SUREFIRE_PASSED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="com.example.HelloTest" tests="1" errors="0" failures="0"
               skipped="0" time="0.123">
      <testcase name="testAlwaysTrue" classname="com.example.HelloTest" time="0.123"/>
    </testsuite>
""")

_SUREFIRE_FAILED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="com.example.FailTest" tests="1" errors="0" failures="1"
               skipped="0" time="0.042">
      <testcase name="testShouldFail" classname="com.example.FailTest" time="0.042">
        <failure message="expected: &lt;true&gt; but was: &lt;false&gt;"
                 type="org.opentest4j.AssertionFailedError">stack trace line 1
    stack trace line 2</failure>
      </testcase>
    </testsuite>
""")

_SUREFIRE_SKIPPED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="com.example.SkipTest" tests="1" errors="0" failures="0"
               skipped="1" time="0.001">
      <testcase name="testSkipped" classname="com.example.SkipTest" time="0.001">
        <skipped/>
      </testcase>
    </testsuite>
""")

_SUREFIRE_ERROR = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="com.example.ErrTest" tests="1" errors="1" failures="0"
               skipped="0" time="0.005">
      <testcase name="testError" classname="com.example.ErrTest" time="0.005">
        <error message="NullPointerException" type="java.lang.NullPointerException">
    at com.example.ErrTest.testError(ErrTest.java:12)</error>
      </testcase>
    </testsuite>
""")


def test_surefire_parser_passed(tmp_path: Path) -> None:
    xml_file = tmp_path / "TEST-com.example.HelloTest.xml"
    xml_file.write_text(_SUREFIRE_PASSED, encoding="utf-8")

    results = _parse_surefire_xml(xml_file)
    assert len(results) == 1
    r = results[0]
    assert r.status == "passed"
    assert r.name == "testAlwaysTrue"
    assert r.classname == "com.example.HelloTest"
    assert r.duration_ms == pytest.approx(123.0)
    assert r.failure_message is None
    assert r.failure_stack is None


# ---------------------------------------------------------------------------
# 5. Surefire XML parser — failed test with message and stack
# ---------------------------------------------------------------------------


def test_surefire_parser_failed(tmp_path: Path) -> None:
    xml_file = tmp_path / "TEST-com.example.FailTest.xml"
    xml_file.write_text(_SUREFIRE_FAILED, encoding="utf-8")

    results = _parse_surefire_xml(xml_file)
    assert len(results) == 1
    r = results[0]
    assert r.status == "failed"
    assert r.name == "testShouldFail"
    assert r.failure_message is not None
    assert "expected" in r.failure_message
    assert r.failure_stack is not None
    assert "stack trace" in r.failure_stack


# ---------------------------------------------------------------------------
# 6. Surefire parser — skipped and error variants
# ---------------------------------------------------------------------------


def test_surefire_parser_skipped(tmp_path: Path) -> None:
    xml_file = tmp_path / "TEST-com.example.SkipTest.xml"
    xml_file.write_text(_SUREFIRE_SKIPPED, encoding="utf-8")
    results = _parse_surefire_xml(xml_file)
    assert len(results) == 1
    assert results[0].status == "skipped"


def test_surefire_parser_error(tmp_path: Path) -> None:
    xml_file = tmp_path / "TEST-com.example.ErrTest.xml"
    xml_file.write_text(_SUREFIRE_ERROR, encoding="utf-8")
    results = _parse_surefire_xml(xml_file)
    assert len(results) == 1
    r = results[0]
    assert r.status == "error"
    assert r.failure_message == "NullPointerException"


# ---------------------------------------------------------------------------
# 7. Surefire parser — multiple XML files merged
# ---------------------------------------------------------------------------


def test_surefire_parser_multiple_files(tmp_path: Path) -> None:
    # Simulate target/surefire-reports/ layout
    reports_dir = tmp_path / "target" / "surefire-reports"
    reports_dir.mkdir(parents=True)

    (reports_dir / "TEST-com.example.HelloTest.xml").write_text(
        _SUREFIRE_PASSED, encoding="utf-8"
    )
    (reports_dir / "TEST-com.example.FailTest.xml").write_text(
        _SUREFIRE_FAILED, encoding="utf-8"
    )

    results = _parse_all_surefire_reports(tmp_path)
    assert len(results) == 2
    statuses = {r.status for r in results}
    assert "passed" in statuses
    assert "failed" in statuses


# ---------------------------------------------------------------------------
# 8. Bundled JRE detection via monkeypatched home_dir
# ---------------------------------------------------------------------------


def test_bundled_jre_preferred(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When ~/.theridion/runtime/jre/bin/java exists, java_source should be 'bundled'."""
    # Create the fake bundled JRE binary
    bin_dir = tmp_path / "runtime" / "jre" / "bin"
    bin_dir.mkdir(parents=True)

    if sys.platform == "win32":
        java_bin = bin_dir / "java.exe"
        java_bin.write_text("@echo openjdk version \"21.0.5\"\r\n", encoding="utf-8")
    else:
        java_bin = bin_dir / "java"
        # Minimal shell script that outputs version string on stderr (like real java)
        java_bin.write_text(
            '#!/bin/sh\necho \'openjdk version "21.0.5" 2021-10-19\' >&2\n',
            encoding="utf-8",
        )
        current_mode = java_bin.stat().st_mode
        java_bin.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Monkeypatch home_dir to return tmp_path
    import theridion_sidecar.camel.runtime as runtime_module
    import theridion_sidecar.storage as storage_module

    monkeypatch.setattr(runtime_module, "home_dir", lambda: tmp_path)

    status = detect_runtime()
    assert status.bundled_jre_present is True
    assert status.java_source == "bundled"
    assert status.java_available is True
    assert status.java_path is not None
    assert "runtime" in status.java_path


# ---------------------------------------------------------------------------
# 9. Bundled JRE absent → source is system or none
# ---------------------------------------------------------------------------


def test_bundled_jre_absent_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no bundled JRE, java_source must be 'system' or 'none'."""
    import theridion_sidecar.camel.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "home_dir", lambda: tmp_path)

    status = detect_runtime()
    assert status.bundled_jre_present is False
    assert status.java_source in ("system", "none")


# ---------------------------------------------------------------------------
# 10. Minimal Maven project run (skipped if mvn/mvnw unavailable)
# ---------------------------------------------------------------------------


MINIMAL_POM = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <project xmlns="http://maven.apache.org/POM/4.0.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
               http://maven.apache.org/xsd/maven-4.0.0.xsd">
      <modelVersion>4.0.0</modelVersion>
      <groupId>com.example</groupId>
      <artifactId>theridion-test</artifactId>
      <version>1.0-SNAPSHOT</version>
      <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
      </properties>
      <dependencies>
        <dependency>
          <groupId>org.junit.jupiter</groupId>
          <artifactId>junit-jupiter</artifactId>
          <version>5.10.0</version>
          <scope>test</scope>
        </dependency>
      </dependencies>
      <build>
        <plugins>
          <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.1.2</version>
          </plugin>
        </plugins>
      </build>
    </project>
""")

MINIMAL_TEST_JAVA = textwrap.dedent("""\
    package com.example;

    import org.junit.jupiter.api.Test;
    import static org.junit.jupiter.api.Assertions.assertTrue;

    public class HelloTest {
        @Test
        void testAlwaysTrue() {
            assertTrue(true);
        }
    }
""")

_runtime = detect_runtime()
_has_mvn = _runtime.maven_available


@pytest.mark.skipif(not _has_mvn, reason="mvn not available on this machine")
def test_run_with_minimal_maven_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration test: run a real minimal Maven project and parse results."""
    import asyncio

    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))

    files = {
        "pom.xml": MINIMAL_POM,
        "src/test/java/com/example/HelloTest.java": MINIMAL_TEST_JAVA,
    }

    report = asyncio.run(
        __import__(
            "theridion_sidecar.camel.runner", fromlist=["run_camel_test"]
        ).run_camel_test(files, use_mvnw=False)
    )

    assert isinstance(report, CamelRunReport)
    assert report.mvn_exit_code == 0
    assert report.total >= 1
    assert report.passed >= 1
    assert report.failed == 0
    assert report.success is True


# ---------------------------------------------------------------------------
# 11. Stack truncation: failure_stack capped at 2000 chars
# ---------------------------------------------------------------------------


def test_surefire_failure_stack_truncated(tmp_path: Path) -> None:
    long_stack = "x" * 5000
    xml_content = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="T" tests="1" errors="0" failures="1" skipped="0" time="0.1">
          <testcase name="t" classname="T" time="0.1">
            <failure message="oops" type="AssertionError">{long_stack}</failure>
          </testcase>
        </testsuite>
    """)
    xml_file = tmp_path / "TEST-T.xml"
    xml_file.write_text(xml_content, encoding="utf-8")
    results = _parse_surefire_xml(xml_file)
    assert len(results) == 1
    assert results[0].failure_stack is not None
    assert len(results[0].failure_stack) == 2000

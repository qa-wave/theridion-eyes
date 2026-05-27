"""Tests for the Apache Camel Maven project generator.

Covers generator logic (unit) and the /api/camel/* endpoints (integration).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.camel.generator import (
    CamelRoute,
    CamelScenario,
    generate_test,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _minimal_route(**kwargs) -> CamelRoute:
    defaults = dict(
        route_dsl="",
        scenarios=[CamelScenario(name="ok", input_body="x", expected_body="x")],
    )
    defaults.update(kwargs)
    return CamelRoute(**defaults)


# ---------------------------------------------------------------------------
# 1. Minimal route — structure
# ---------------------------------------------------------------------------


def test_generate_minimal_route() -> None:
    route = _minimal_route()
    project = generate_test(route)

    assert "camel-test-junit5" in project.pom_xml
    assert "class MyRouteTest extends CamelTestSupport" in project.test_java
    assert "void ok()" in project.test_java
    assert project.route_java != ""
    assert "pom.xml" in project.files


# ---------------------------------------------------------------------------
# 2. Transform scenario — expected body rendered
# ---------------------------------------------------------------------------


def test_generate_with_transform() -> None:
    route = CamelRoute(
        route_dsl='.transform(body().regexReplaceAll("hello", "ahoj"))',
        scenarios=[
            CamelScenario(
                name="replace",
                input_body="hello world",
                expected_body="ahoj world",
            )
        ],
    )
    project = generate_test(route)

    assert 'expectedBodiesReceived("ahoj world")' in project.test_java


# ---------------------------------------------------------------------------
# 3. camelCase method names
# ---------------------------------------------------------------------------


def test_camelcase_method_names() -> None:
    route = _minimal_route(
        scenarios=[
            CamelScenario(
                name="transforms hello to ahoj",
                input_body="hello",
                expected_body="ahoj",
            )
        ]
    )
    project = generate_test(route)

    assert "void transformsHelloToAhoj()" in project.test_java


# ---------------------------------------------------------------------------
# 4. Multiple scenarios → multiple @Test methods
# ---------------------------------------------------------------------------


def test_multiple_scenarios() -> None:
    route = CamelRoute(
        route_dsl="",
        scenarios=[
            CamelScenario(name="first", input_body="a", expected_body="a"),
            CamelScenario(name="second", input_body="b", expected_body="b"),
            CamelScenario(name="third", input_body="c", expected_body="c"),
        ],
    )
    project = generate_test(route)

    assert project.test_java.count("@Test") == 3
    assert "void first()" in project.test_java
    assert "void second()" in project.test_java
    assert "void third()" in project.test_java


# ---------------------------------------------------------------------------
# 5. Input headers → sendBodyAndHeaders
# ---------------------------------------------------------------------------


def test_headers_in_scenario() -> None:
    route = _minimal_route(
        scenarios=[
            CamelScenario(
                name="with header",
                input_body="payload",
                input_headers={"X-Trace": "abc"},
                expected_body="payload",
            )
        ]
    )
    project = generate_test(route)

    assert "sendBodyAndHeaders" in project.test_java
    assert 'Map.of("X-Trace", "abc")' in project.test_java


# ---------------------------------------------------------------------------
# 6. Expected header assertion
# ---------------------------------------------------------------------------


def test_expected_header_assertion() -> None:
    route = _minimal_route(
        scenarios=[
            CamelScenario(
                name="check header",
                input_body="data",
                expected_header_name="Content-Type",
                expected_header_value="application/json",
            )
        ]
    )
    project = generate_test(route)

    assert 'result.expectedHeaderReceived("Content-Type", "application/json")' in project.test_java


# ---------------------------------------------------------------------------
# 7. Custom endpoints propagate to MyRoute.java
# ---------------------------------------------------------------------------


def test_endpoint_substitution() -> None:
    route = _minimal_route(
        input_endpoint="jms:queue:foo",
        output_endpoint="jms:queue:bar",
    )
    project = generate_test(route)

    assert 'from("jms:queue:foo")' in project.route_java
    assert 'to("jms:queue:bar")' in project.route_java


# ---------------------------------------------------------------------------
# 8. AdviceWith mode
# ---------------------------------------------------------------------------


def test_advice_with_mode() -> None:
    route = _minimal_route(use_advice_with=True)
    project = generate_test(route)

    assert "AdviceWith.adviceWith" in project.test_java
    assert "replaceFromWith" in project.test_java


# ---------------------------------------------------------------------------
# 9. ZIP download endpoint
# ---------------------------------------------------------------------------


def test_zip_download(client: TestClient) -> None:
    payload = {
        "route_dsl": "",
        "scenarios": [{"name": "ok", "input_body": "x", "expected_body": "x"}],
    }
    res = client.post("/api/camel/download", json=payload)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"

    content = res.content
    assert len(content) > 1024, "ZIP should be larger than 1 KB"

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()

    assert "pom.xml" in names
    # Check test Java file present (package path may vary)
    test_files = [n for n in names if n.endswith("MyRouteTest.java")]
    assert len(test_files) == 1, f"Expected one MyRouteTest.java in ZIP, got: {names}"


# ---------------------------------------------------------------------------
# 10. POM version propagation
# ---------------------------------------------------------------------------


def test_pom_versions() -> None:
    route = _minimal_route(camel_version="4.4.0", java_version="17")
    project = generate_test(route)

    assert "<camel.version>4.4.0</camel.version>" in project.pom_xml
    assert "<java.version>17</java.version>" in project.pom_xml
    assert "<maven.compiler.source>17</maven.compiler.source>" in project.pom_xml


# ---------------------------------------------------------------------------
# 11. Generate endpoint (JSON response)
# ---------------------------------------------------------------------------


def test_generate_endpoint(client: TestClient) -> None:
    payload = {
        "route_dsl": "",
        "scenarios": [{"name": "smoke", "input_body": "ping", "expected_body": "ping"}],
    }
    res = client.post("/api/camel/generate", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "pom_xml" in body
    assert "test_java" in body
    assert "route_java" in body
    assert "files" in body
    assert "camel-test-junit5" in body["pom_xml"]

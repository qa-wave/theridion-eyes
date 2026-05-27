"""Apache Camel Maven project generator.

Takes a CamelRoute descriptor and produces a complete, runnable Maven
project with JUnit 5 tests using camel-test-junit5.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .templates import (
    ADVICE_WITH_TEST_METHOD,
    MVN_WRAPPER_PROPERTIES,
    MVNW_CMD,
    MVNW_SH,
    POM_XML,
    ROUTE_JAVA,
    TEST_JAVA_FOOTER,
    TEST_JAVA_HEADER,
    TEST_METHOD_BASIC,
    TEST_METHOD_WITH_HEADERS,
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CamelScenario(BaseModel):
    """One test scenario executed against the route."""

    name: str
    input_body: str = ""
    input_headers: dict[str, str] = Field(default_factory=dict)
    expected_body: str | None = None
    expected_body_contains: str | None = None
    expected_header_name: str | None = None
    expected_header_value: str | None = None
    expected_mock_count: int = 1
    expected_status: int | None = None


class CamelRoute(BaseModel):
    """Full description of a Camel route and the tests to generate for it."""

    route_id: str = "my-route"
    package: str = "com.theridion.test"
    input_endpoint: str = "direct:input"
    output_endpoint: str = "mock:result"
    # Raw Java fragment inserted between from(input). and .to(output).
    # The caller supplies the leading dot, e.g.
    #   ".transform(body().regexReplaceAll(\"hello\", \"ahoj\"))"
    route_dsl: str
    scenarios: list[CamelScenario]
    camel_version: str = "4.8.0"
    java_version: str = "21"
    use_advice_with: bool = False


class CamelGeneratedProject(BaseModel):
    """All generated source files for the Maven project."""

    pom_xml: str
    test_java: str
    route_java: str
    mvnw: str
    mvnw_cmd: str
    mvn_wrapper_properties: str
    # Flat map of project-relative path -> file content, ready to zip.
    files: dict[str, str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_class_name(route_id: str) -> str:
    """Convert a kebab/snake route_id to a PascalCase class name.

    "my-route"    -> "MyRoute"
    "order_flow"  -> "OrderFlow"
    """
    parts = re.split(r"[-_\s]+", route_id)
    return "".join(p.capitalize() for p in parts if p)


def _to_camel_case(text: str) -> str:
    """Convert a plain English scenario name to a lowerCamelCase method name.

    "transforms hello to ahoj" -> "transformsHelloToAhoj"
    Only keeps alphanumeric characters.
    """
    words = re.split(r"[\s_\-]+", text.strip())
    clean = [re.sub(r"[^a-zA-Z0-9]", "", w) for w in words]
    clean = [w for w in clean if w]
    if not clean:
        return "test"
    result = clean[0][0].lower() + clean[0][1:] if len(clean[0]) > 1 else clean[0].lower()
    for w in clean[1:]:
        result += w.capitalize()
    return result


def _java_string(value: str) -> str:
    """Wrap a Python string in a Java string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _headers_map_expr(headers: dict[str, str]) -> str:
    """Produce a Java Map.of(...) expression for request headers.

    Falls back to new java.util.HashMap<>() pattern for >10 entries
    (Map.of limit), though in practice test headers stay small.
    """
    if not headers:
        return "Map.of()"
    pairs: list[str] = []
    for k, v in headers.items():
        pairs.append(f"{_java_string(k)}, {_java_string(v)}")
    return "Map.of(" + ", ".join(pairs) + ")"


def _build_assertions(scenario: CamelScenario) -> str:
    """Return Java lines that set expectations on MockEndpoint `result`."""
    lines: list[str] = []
    if scenario.expected_body is not None:
        lines.append(
            f'        result.expectedBodiesReceived({_java_string(scenario.expected_body)});'
        )
    if scenario.expected_body_contains is not None:
        lines.append(
            f'        result.expectedBodyReceived().body(String.class)'
            f'.contains({_java_string(scenario.expected_body_contains)});'
        )
    if scenario.expected_header_name is not None and scenario.expected_header_value is not None:
        lines.append(
            f'        result.expectedHeaderReceived('
            f'{_java_string(scenario.expected_header_name)}, '
            f'{_java_string(scenario.expected_header_value)});'
        )
    return "\n".join(lines)


def _render_test_method(
    scenario: CamelScenario,
    input_endpoint: str,
    output_endpoint: str,
    route_id: str,
    use_advice_with: bool,
) -> str:
    """Render a single @Test method for one scenario."""
    method_name = _to_camel_case(scenario.name)
    input_body_expr = _java_string(scenario.input_body)
    assertions = _build_assertions(scenario)
    has_headers = bool(scenario.input_headers)

    if use_advice_with:
        # Derive a key suitable for getMockEndpoint("mock:<key>")
        # by stripping the scheme if output is already "mock:something".
        if output_endpoint.startswith("mock:"):
            mock_key = output_endpoint[len("mock:"):]
        else:
            mock_key = output_endpoint.replace(":", ".").replace("/", ".")

        return ADVICE_WITH_TEST_METHOD.format(
            method_name=method_name,
            route_id=route_id,
            input_endpoint=input_endpoint,
            output_endpoint=output_endpoint,
            output_endpoint_mock_key=mock_key,
            expected_count=scenario.expected_mock_count,
            assertions=assertions,
            input_body_expr=input_body_expr,
        )

    template = TEST_METHOD_WITH_HEADERS if has_headers else TEST_METHOD_BASIC
    kwargs: dict[str, Any] = dict(
        method_name=method_name,
        input_endpoint=input_endpoint,
        output_endpoint=output_endpoint,
        expected_count=scenario.expected_mock_count,
        assertions=assertions,
        input_body_expr=input_body_expr,
    )
    if has_headers:
        kwargs["headers_expr"] = _headers_map_expr(scenario.input_headers)
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_test(route: CamelRoute) -> CamelGeneratedProject:
    """Generate a complete Maven project for the given Camel route."""
    class_name = _to_class_name(route.route_id)
    test_class_name = class_name + "Test"
    artifact_id = route.route_id

    # --- pom.xml ---
    pom_xml = POM_XML.format(
        package=route.package,
        artifact_id=artifact_id,
        java_version=route.java_version,
        camel_version=route.camel_version,
    )

    # --- MyRoute.java ---
    # Insert route_dsl between from(input). chain and .to(output).
    # If route_dsl is empty, no extra chain step is emitted.
    if route.route_dsl.strip():
        route_dsl_block = "\n            " + route.route_dsl.strip()
    else:
        route_dsl_block = ""

    route_java = ROUTE_JAVA.format(
        package=route.package,
        class_name=class_name,
        input_endpoint=route.input_endpoint,
        route_id=route.route_id,
        route_dsl_block=route_dsl_block,
        output_endpoint=route.output_endpoint,
    )

    # --- MyRouteTest.java ---
    header = TEST_JAVA_HEADER.format(
        package=route.package,
        test_class_name=test_class_name,
        route_class_name=class_name,
    )
    methods: list[str] = []
    for scenario in route.scenarios:
        methods.append(
            _render_test_method(
                scenario,
                input_endpoint=route.input_endpoint,
                output_endpoint=route.output_endpoint,
                route_id=route.route_id,
                use_advice_with=route.use_advice_with,
            )
        )
    test_java = header + "\n" + "\n".join(methods) + TEST_JAVA_FOOTER

    # --- Maven wrapper files ---
    mvnw = MVNW_SH
    mvnw_cmd = MVNW_CMD
    mvn_wrapper_properties = MVN_WRAPPER_PROPERTIES

    # --- Assemble files dict ---
    pkg_path = route.package.replace(".", "/")
    files: dict[str, str] = {
        "pom.xml": pom_xml,
        f"src/main/java/{pkg_path}/{class_name}.java": route_java,
        f"src/test/java/{pkg_path}/{test_class_name}.java": test_java,
        "mvnw": mvnw,
        "mvnw.cmd": mvnw_cmd,
        ".mvn/wrapper/maven-wrapper.properties": mvn_wrapper_properties,
    }

    return CamelGeneratedProject(
        pom_xml=pom_xml,
        test_java=test_java,
        route_java=route_java,
        mvnw=mvnw,
        mvnw_cmd=mvnw_cmd,
        mvn_wrapper_properties=mvn_wrapper_properties,
        files=files,
    )

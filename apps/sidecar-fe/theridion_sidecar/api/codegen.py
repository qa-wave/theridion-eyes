"""Generate code snippets from request configuration."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/codegen", tags=["codegen"])

Language = Literal["python", "javascript", "go", "java", "csharp", "curl", "php", "ruby"]

LANGUAGES: list[dict[str, str]] = [
    {"id": "curl", "label": "cURL"},
    {"id": "python", "label": "Python (requests)"},
    {"id": "javascript", "label": "JavaScript (fetch)"},
    {"id": "go", "label": "Go (net/http)"},
    {"id": "java", "label": "Java (HttpClient)"},
    {"id": "csharp", "label": "C# (HttpClient)"},
    {"id": "php", "label": "PHP (cURL)"},
    {"id": "ruby", "label": "Ruby (Net::HTTP)"},
]


class CodegenInput(BaseModel):
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    language: Language = "curl"


class CodegenOutput(BaseModel):
    language: str
    code: str


@router.get("/languages")
def list_languages() -> list[dict[str, str]]:
    return LANGUAGES


@router.post("/generate", response_model=CodegenOutput)
def generate(body: CodegenInput) -> CodegenOutput:
    generators = {
        "curl": _gen_curl,
        "python": _gen_python,
        "javascript": _gen_javascript,
        "go": _gen_go,
        "java": _gen_java,
        "csharp": _gen_csharp,
        "php": _gen_php,
        "ruby": _gen_ruby,
    }
    gen = generators.get(body.language, _gen_curl)
    return CodegenOutput(language=body.language, code=gen(body))


def _gen_curl(r: CodegenInput) -> str:
    parts = ["curl"]
    if r.method != "GET":
        parts.append(f"-X {r.method}")
    for k, v in r.headers.items():
        parts.append(f"-H '{k}: {v}'")
    if r.body:
        parts.append(f"--data-raw '{r.body}'")
    parts.append(f"'{r.url}'")
    return " \\\n  ".join(parts)


def _gen_python(r: CodegenInput) -> str:
    lines = ["import requests", ""]
    if r.headers:
        lines.append(f"headers = {json.dumps(r.headers, indent=2)}")
    if r.body:
        lines.append(f"data = '''{r.body}'''")
    args = [f"'{r.url}'"]
    if r.headers:
        args.append("headers=headers")
    if r.body:
        args.append("data=data")
    lines.append(f"response = requests.{r.method.lower()}({', '.join(args)})")
    lines.append("print(response.status_code)")
    lines.append("print(response.json())")
    return "\n".join(lines)


def _gen_javascript(r: CodegenInput) -> str:
    opts: dict[str, object] = {"method": r.method}
    if r.headers:
        opts["headers"] = r.headers
    if r.body:
        opts["body"] = "<<BODY>>"
    opts_str = json.dumps(opts, indent=2)
    if r.body:
        opts_str = opts_str.replace('"<<BODY>>"', f"JSON.stringify({r.body})" if r.body.strip().startswith("{") else f"`{r.body}`")
    lines = [
        f"const response = await fetch('{r.url}', {opts_str});",
        "",
        "const data = await response.json();",
        "console.log(response.status, data);",
    ]
    return "\n".join(lines)


def _gen_go(r: CodegenInput) -> str:
    lines = [
        "package main",
        "",
        'import (',
        '    "fmt"',
        '    "io"',
        '    "net/http"',
    ]
    if r.body:
        lines.append('    "strings"')
    lines.append(")")
    lines.append("")
    lines.append("func main() {")
    if r.body:
        lines.append(f'    body := strings.NewReader(`{r.body}`)')
        lines.append(f'    req, _ := http.NewRequest("{r.method}", "{r.url}", body)')
    else:
        lines.append(f'    req, _ := http.NewRequest("{r.method}", "{r.url}", nil)')
    for k, v in r.headers.items():
        lines.append(f'    req.Header.Set("{k}", "{v}")')
    lines.extend([
        "    resp, _ := http.DefaultClient.Do(req)",
        "    defer resp.Body.Close()",
        "    data, _ := io.ReadAll(resp.Body)",
        "    fmt.Println(resp.StatusCode, string(data))",
        "}",
    ])
    return "\n".join(lines)


def _gen_java(r: CodegenInput) -> str:
    lines = [
        "import java.net.http.*;",
        "import java.net.URI;",
        "",
        "var client = HttpClient.newHttpClient();",
    ]
    if r.body:
        lines.append(f'var body = HttpRequest.BodyPublishers.ofString("""{r.body}""");')
        lines.append(f'var request = HttpRequest.newBuilder(URI.create("{r.url}"))')
        lines.append(f'    .method("{r.method}", body)')
    else:
        lines.append(f'var request = HttpRequest.newBuilder(URI.create("{r.url}"))')
        if r.method != "GET":
            lines.append(f'    .method("{r.method}", HttpRequest.BodyPublishers.noBody())')
    for k, v in r.headers.items():
        lines.append(f'    .header("{k}", "{v}")')
    lines.append("    .build();")
    lines.append("var response = client.send(request, HttpResponse.BodyHandlers.ofString());")
    lines.append("System.out.println(response.statusCode() + \" \" + response.body());")
    return "\n".join(lines)


def _gen_csharp(r: CodegenInput) -> str:
    lines = [
        "using var client = new HttpClient();",
        f'var request = new HttpRequestMessage(HttpMethod.{r.method.capitalize()}, "{r.url}");',
    ]
    for k, v in r.headers.items():
        lines.append(f'request.Headers.Add("{k}", "{v}");')
    if r.body:
        lines.append(f'request.Content = new StringContent(@"{r.body}", System.Text.Encoding.UTF8, "application/json");')
    lines.extend([
        "var response = await client.SendAsync(request);",
        "var body = await response.Content.ReadAsStringAsync();",
        "Console.WriteLine($\"{response.StatusCode} {body}\");",
    ])
    return "\n".join(lines)


def _gen_php(r: CodegenInput) -> str:
    lines = ["<?php", "$ch = curl_init();", f"curl_setopt($ch, CURLOPT_URL, '{r.url}');"]
    if r.method != "GET":
        lines.append(f"curl_setopt($ch, CURLOPT_CUSTOMREQUEST, '{r.method}');")
    if r.headers:
        hdrs = ", ".join(f"'{k}: {v}'" for k, v in r.headers.items())
        lines.append(f"curl_setopt($ch, CURLOPT_HTTPHEADER, [{hdrs}]);")
    if r.body:
        lines.append(f"curl_setopt($ch, CURLOPT_POSTFIELDS, '{r.body}');")
    lines.extend([
        "curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);",
        "$response = curl_exec($ch);",
        "echo curl_getinfo($ch, CURLINFO_HTTP_CODE) . ' ' . $response;",
        "curl_close($ch);",
    ])
    return "\n".join(lines)


def _gen_ruby(r: CodegenInput) -> str:
    lines = [
        "require 'net/http'",
        "require 'json'",
        "",
        f"uri = URI('{r.url}')",
        f"req = Net::HTTP::{r.method.capitalize()}.new(uri)",
    ]
    for k, v in r.headers.items():
        lines.append(f"req['{k}'] = '{v}'")
    if r.body:
        lines.append(f"req.body = '{r.body}'")
    lines.extend([
        "res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == 'https') { |http| http.request(req) }",
        "puts \"#{res.code} #{res.body}\"",
    ])
    return "\n".join(lines)

"""String templates for Apache Camel Maven project generation.

All templates use .format() with named placeholders — no external
template engine required.
"""

from __future__ import annotations


POM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>{package}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>{java_version}</java.version>
        <camel.version>{camel_version}</camel.version>
        <maven.compiler.source>{java_version}</maven.compiler.source>
        <maven.compiler.target>{java_version}</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.camel</groupId>
                <artifactId>camel-bom</artifactId>
                <version>${{camel.version}}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.apache.camel</groupId>
            <artifactId>camel-core</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.camel</groupId>
            <artifactId>camel-test-junit5</artifactId>
            <scope>test</scope>
        </dependency>

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
                <version>3.2.5</version>
                <configuration>
                    <useModulePath>false</useModulePath>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
"""


ROUTE_JAVA = """\
package {package};

import org.apache.camel.builder.RouteBuilder;

public class {class_name} extends RouteBuilder {{

    @Override
    public void configure() {{
        from("{input_endpoint}")
            .routeId("{route_id}"){route_dsl_block}
            .to("{output_endpoint}");
    }}
}}
"""


TEST_JAVA_HEADER = """\
package {package};

import org.apache.camel.CamelContext;
import org.apache.camel.ProducerTemplate;
import org.apache.camel.builder.AdviceWith;
import org.apache.camel.component.mock.MockEndpoint;
import org.apache.camel.test.junit5.CamelTestSupport;
import org.junit.jupiter.api.Test;

import java.util.Map;

public class {test_class_name} extends CamelTestSupport {{

    @Override
    protected RouteBuilder createRouteBuilder() {{
        return new {route_class_name}();
    }}
"""

TEST_JAVA_FOOTER = "}\n"


TEST_METHOD_BASIC = """\
    @Test
    void {method_name}() throws Exception {{
        MockEndpoint result = getMockEndpoint("{output_endpoint}");
        result.expectedMessageCount({expected_count});
{assertions}
        template.sendBody("{input_endpoint}", {input_body_expr});
        result.assertIsSatisfied();
    }}
"""

TEST_METHOD_WITH_HEADERS = """\
    @Test
    void {method_name}() throws Exception {{
        MockEndpoint result = getMockEndpoint("{output_endpoint}");
        result.expectedMessageCount({expected_count});
{assertions}
        template.sendBodyAndHeaders("{input_endpoint}", {input_body_expr}, {headers_expr});
        result.assertIsSatisfied();
    }}
"""

ADVICE_WITH_TEST_METHOD = """\
    @Test
    void {method_name}() throws Exception {{
        AdviceWith.adviceWith(context, "{route_id}", a -> {{
            a.replaceFromWith("{input_endpoint}");
            a.mockEndpoints("{output_endpoint}");
        }});
        context.start();

        MockEndpoint result = getMockEndpoint("mock:{output_endpoint_mock_key}");
        result.expectedMessageCount({expected_count});
{assertions}
        template.sendBody("{input_endpoint}", {input_body_expr});
        result.assertIsSatisfied();
    }}
"""


MVNW_SH = """\
#!/bin/sh
# Maven Wrapper bootstrap script (simplified)
# Downloads Maven if not present, then delegates to it.

set -e

MAVEN_VERSION="3.9.9"
MAVEN_DIST_URL="https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/${MAVEN_VERSION}/apache-maven-${MAVEN_VERSION}-bin.zip"
MAVEN_HOME="${HOME}/.m2/wrapper/dists/apache-maven-${MAVEN_VERSION}"
MAVEN_BIN="${MAVEN_HOME}/bin/mvn"

if [ ! -f "${MAVEN_BIN}" ]; then
    echo "Downloading Maven ${MAVEN_VERSION}..."
    mkdir -p "${MAVEN_HOME}"
    TMP_ZIP="${MAVEN_HOME}/apache-maven-${MAVEN_VERSION}-bin.zip"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "${TMP_ZIP}" "${MAVEN_DIST_URL}"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "${TMP_ZIP}" "${MAVEN_DIST_URL}"
    else
        echo "ERROR: curl or wget is required to download Maven." >&2
        exit 1
    fi
    unzip -q "${TMP_ZIP}" -d "${MAVEN_HOME}/tmp"
    mv "${MAVEN_HOME}/tmp/apache-maven-${MAVEN_VERSION}/"* "${MAVEN_HOME}/"
    rm -rf "${MAVEN_HOME}/tmp" "${TMP_ZIP}"
    chmod +x "${MAVEN_BIN}"
fi

exec "${MAVEN_BIN}" "$@"
"""


MVNW_CMD = """\
@echo off
REM Maven Wrapper bootstrap script for Windows (simplified)

set MAVEN_VERSION=3.9.9
set MAVEN_DIST_URL=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/%MAVEN_VERSION%/apache-maven-%MAVEN_VERSION%-bin.zip
set MAVEN_HOME=%USERPROFILE%\\.m2\\wrapper\\dists\\apache-maven-%MAVEN_VERSION%
set MAVEN_BIN=%MAVEN_HOME%\\bin\\mvn.cmd

if exist "%MAVEN_BIN%" goto runMaven

echo Downloading Maven %MAVEN_VERSION%...
if not exist "%MAVEN_HOME%" mkdir "%MAVEN_HOME%"
set TMP_ZIP=%MAVEN_HOME%\\apache-maven-%MAVEN_VERSION%-bin.zip
powershell -Command "Invoke-WebRequest -Uri '%MAVEN_DIST_URL%' -OutFile '%TMP_ZIP%'"
powershell -Command "Expand-Archive -Path '%TMP_ZIP%' -DestinationPath '%MAVEN_HOME%\\tmp' -Force"
xcopy /E /Y "%MAVEN_HOME%\\tmp\\apache-maven-%MAVEN_VERSION%\\*" "%MAVEN_HOME%\\" >nul
rmdir /S /Q "%MAVEN_HOME%\\tmp"
del "%TMP_ZIP%"

:runMaven
"%MAVEN_BIN%" %*
"""


MVN_WRAPPER_PROPERTIES = """\
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
wrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.2/maven-wrapper-3.3.2.jar
"""

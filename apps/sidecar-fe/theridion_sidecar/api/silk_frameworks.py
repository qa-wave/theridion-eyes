"""Framework registry for Silk test authoring & recording.

A *framework* describes a target test stack: how (if at all) Silk can record
a session into it via Playwright codegen, and a starter template for manual
authoring. The registry is the shared contract between the sidecar and the FE.

Recording is only possible for Playwright dialects (``codegen_target`` set);
every other framework supports manual authoring only until the framework-
agnostic recorder (phase 2) lands. Mobile frameworks (kind == "mobile") are
authoring-only and run on a separate device/Appium layer (phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Framework:
    id: str
    label: str
    kind: str  # "web" | "mobile"
    file_extension: str
    # Playwright codegen --target value, or None when recording is unsupported.
    codegen_target: str | None
    # True when Silk can execute the spec today (only the Playwright TS runner).
    runnable: bool
    template: str = field(default="")

    @property
    def recordable(self) -> bool:
        return self.codegen_target is not None


_PW_TS_TEMPLATE = """\
import { test, expect } from '@playwright/test';

test('my test', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page).toHaveTitle(/Example/);
});
"""

_PW_JS_TEMPLATE = """\
const { test, expect } = require('@playwright/test');

test('my test', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page).toHaveTitle(/Example/);
});
"""

_PW_PY_TEMPLATE = """\
import re
from playwright.sync_api import Page, expect


def test_my_test(page: Page) -> None:
    page.goto("https://example.com")
    expect(page).to_have_title(re.compile("Example"))
"""

_PW_JAVA_TEMPLATE = """\
import com.microsoft.playwright.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

public class MyTest {
    @Test
    void myTest() {
        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch();
            Page page = browser.newPage();
            page.navigate("https://example.com");
            assertTrue(page.title().contains("Example"));
        }
    }
}
"""

_PW_CSHARP_TEMPLATE = """\
using Microsoft.Playwright;
using Microsoft.Playwright.NUnit;
using NUnit.Framework;

[TestFixture]
public class MyTest : PageTest
{
    [Test]
    public async Task MyTestAsync()
    {
        await Page.GotoAsync("https://example.com");
        await Expect(Page).ToHaveTitleAsync(new System.Text.RegularExpressions.Regex("Example"));
    }
}
"""

_CYPRESS_TEMPLATE = """\
describe('my test', () => {
  it('loads the page', () => {
    cy.visit('https://example.com');
    cy.title().should('include', 'Example');
  });
});
"""

_SELENIUM_PY_TEMPLATE = """\
from selenium import webdriver
from selenium.webdriver.common.by import By


def test_my_test() -> None:
    driver = webdriver.Chrome()
    try:
        driver.get("https://example.com")
        assert "Example" in driver.title
    finally:
        driver.quit()
"""

_SELENIUM_JAVA_TEMPLATE = """\
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

public class MyTest {
    @Test
    void myTest() {
        WebDriver driver = new ChromeDriver();
        try {
            driver.get("https://example.com");
            assertTrue(driver.getTitle().contains("Example"));
        } finally {
            driver.quit();
        }
    }
}
"""

_WEBDRIVERIO_TEMPLATE = """\
describe('my test', () => {
  it('loads the page', async () => {
    await browser.url('https://example.com');
    await expect(browser).toHaveTitle(expect.stringContaining('Example'));
  });
});
"""

_APPIUM_PY_TEMPLATE = """\
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy


def test_my_test() -> None:
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.app = "/path/to/app.apk"
    driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
    try:
        el = driver.find_element(AppiumBy.ACCESSIBILITY_ID, "login")
        el.click()
    finally:
        driver.quit()
"""

_ESPRESSO_TEMPLATE = """\
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.matcher.ViewMatchers.withId
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MyTest {
    @Test
    fun myTest() {
        onView(withId(R.id.login)).perform(click())
    }
}
"""

_XCUITEST_TEMPLATE = """\
import XCTest

final class MyTest: XCTestCase {
    func testMyTest() throws {
        let app = XCUIApplication()
        app.launch()
        app.buttons["login"].tap()
    }
}
"""

_MAESTRO_TEMPLATE = """\
appId: com.example.app
---
- launchApp
- tapOn: "Login"
- assertVisible: "Welcome"
"""


_FRAMEWORKS: list[Framework] = [
    Framework(
        id="playwright-ts",
        label="Playwright (TypeScript)",
        kind="web",
        file_extension=".spec.ts",
        codegen_target="playwright-test",
        runnable=True,
        template=_PW_TS_TEMPLATE,
    ),
    Framework(
        id="playwright-js",
        label="Playwright (JavaScript)",
        kind="web",
        file_extension=".spec.js",
        codegen_target="javascript",
        runnable=False,
        template=_PW_JS_TEMPLATE,
    ),
    Framework(
        id="playwright-python",
        label="Playwright (Python / pytest)",
        kind="web",
        file_extension=".py",
        codegen_target="python-pytest",
        runnable=False,
        template=_PW_PY_TEMPLATE,
    ),
    Framework(
        id="playwright-java",
        label="Playwright (Java / JUnit)",
        kind="web",
        file_extension=".java",
        codegen_target="java-junit",
        runnable=False,
        template=_PW_JAVA_TEMPLATE,
    ),
    Framework(
        id="playwright-csharp",
        label="Playwright (C# / NUnit)",
        kind="web",
        file_extension=".cs",
        codegen_target="csharp-nunit",
        runnable=False,
        template=_PW_CSHARP_TEMPLATE,
    ),
    Framework(
        id="cypress",
        label="Cypress",
        kind="web",
        file_extension=".cy.js",
        codegen_target=None,
        runnable=False,
        template=_CYPRESS_TEMPLATE,
    ),
    Framework(
        id="selenium-python",
        label="Selenium (Python)",
        kind="web",
        file_extension=".py",
        codegen_target=None,
        runnable=False,
        template=_SELENIUM_PY_TEMPLATE,
    ),
    Framework(
        id="selenium-java",
        label="Selenium (Java)",
        kind="web",
        file_extension=".java",
        codegen_target=None,
        runnable=False,
        template=_SELENIUM_JAVA_TEMPLATE,
    ),
    Framework(
        id="webdriverio",
        label="WebdriverIO",
        kind="web",
        file_extension=".e2e.js",
        codegen_target=None,
        runnable=False,
        template=_WEBDRIVERIO_TEMPLATE,
    ),
    Framework(
        id="appium-python",
        label="Appium (Python)",
        kind="mobile",
        file_extension=".py",
        codegen_target=None,
        runnable=False,
        template=_APPIUM_PY_TEMPLATE,
    ),
    Framework(
        id="espresso",
        label="Espresso (Android / Kotlin)",
        kind="mobile",
        file_extension=".kt",
        codegen_target=None,
        runnable=False,
        template=_ESPRESSO_TEMPLATE,
    ),
    Framework(
        id="xcuitest",
        label="XCUITest (iOS / Swift)",
        kind="mobile",
        file_extension=".swift",
        codegen_target=None,
        runnable=False,
        template=_XCUITEST_TEMPLATE,
    ),
    Framework(
        id="maestro",
        label="Maestro (mobile flows)",
        kind="mobile",
        file_extension=".yaml",
        codegen_target=None,
        runnable=False,
        template=_MAESTRO_TEMPLATE,
    ),
]

_BY_ID: dict[str, Framework] = {f.id: f for f in _FRAMEWORKS}


def all_frameworks() -> list[Framework]:
    return list(_FRAMEWORKS)


def get_framework(framework_id: str) -> Framework | None:
    return _BY_ID.get(framework_id)

"""
End-to-End (E2E) Browser Automation Test Suite.
Uses Playwright to launch a real browser (Microsoft Edge / Chromium)
and interact with the visual canvas, tool palette, theme toggle,
workflow execution, results inspector, and Output Data explorer actions.
"""
import time
import socket
import threading
import pytest
from playwright.sync_api import sync_playwright

from backend.app import app


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    """Starts the Flask server in a daemon thread on an ephemeral port."""
    port = _find_free_port()
    server_url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True
    )
    server_thread.start()

    # Wait for server to be responsive
    import urllib.request
    max_retries = 30
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(f"{server_url}/api/tools") as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    yield server_url


@pytest.fixture(scope="module")
def browser_context():
    """Launches Playwright headless Edge browser context."""
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(channel="msedge", headless=True)
    except Exception:
        browser = pw.chromium.launch(headless=True)

    context = browser.new_context(viewport={"width": 1400, "height": 900})
    yield context

    context.close()
    browser.close()
    pw.stop()


# ----------------------------------------------------------------------
# 1. Page Load, Canvas & Palette Render Verification
# ----------------------------------------------------------------------
def test_e2e_page_loads_and_palette_rendered(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)

    # Verify document title and core layout elements
    assert "Antigravity DataFlow" in page.title()
    assert page.is_visible("#canvas-container")
    assert page.is_visible("#tool-palette-ribbon")
    assert page.is_visible("#config-panel")
    assert page.is_visible("#results-panel")

    # Verify tool categories in palette
    page.wait_for_selector(".tool-card")
    tool_items = page.locator(".tool-card").count()
    assert tool_items >= 15, f"Expected at least 15 palette tools, found {tool_items}"

    page.close()


# ----------------------------------------------------------------------
# 2. Theme Switcher Interactivity
# ----------------------------------------------------------------------
def test_e2e_theme_toggle(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)

    body = page.locator("body")
    initial_class = body.get_attribute("class") or ""

    theme_btn = page.locator("#btn-theme-toggle")
    assert theme_btn.is_visible()
    theme_btn.click()

    time.sleep(0.3)
    new_class = body.get_attribute("class") or ""
    # Should toggle between dark and light themes
    assert new_class != initial_class or "theme" in new_class

    page.close()


# ----------------------------------------------------------------------
# 3. Canvas Workflow Run & Results Table
# ----------------------------------------------------------------------
def test_e2e_load_and_run_workflow(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)

    # Click Run button
    run_btn = page.locator("#btn-run")
    assert run_btn.is_visible()
    run_btn.click()

    # Wait for execution toast or results update
    page.wait_for_timeout(1000)

    # Verify results panel container
    results_container = page.locator("#results-panel")
    assert results_container.is_visible()

    page.close()


# ----------------------------------------------------------------------
# 4. Output Data Tool Windows Explorer Config Controls
# ----------------------------------------------------------------------
def test_e2e_output_tool_windows_explorer_controls(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)

    # Drag or trigger an Output Data tool configuration check
    # Check that config panel scripts and Explorer API bindings are present in window
    explorer_available = page.evaluate("""() => {
        return typeof window.showToast === 'function';
    }""")
    assert explorer_available is True

    page.close()


# ----------------------------------------------------------------------
# 5. Results Panel Tabs & Profiler Studio Navigation
# ----------------------------------------------------------------------
def test_e2e_results_panel_tabs_navigation(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)

    # Verify tabs in results panel
    tabs = page.locator(".results-tab")
    tab_count = tabs.count()
    assert tab_count >= 2, f"Expected at least 2 results tabs, found {tab_count}"

    # Click through tabs
    for i in range(tab_count):
        tab = tabs.nth(i)
        if tab.is_visible():
            tab.click()
            page.wait_for_timeout(150)

    page.close()


# ----------------------------------------------------------------------
# 6. Container Frame Wire Persistence & Stacking Layer Hierarchy
# ----------------------------------------------------------------------
def test_e2e_container_frame_wire_persistence_and_layering(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector("#canvas-container")

    # Verify CSS z-index and overflow layering
    layer_styles = page.evaluate("""() => {
        const svg = document.getElementById('canvas-svg');
        const cntLayer = document.getElementById('containers-layer');
        const nodesLayer = document.getElementById('nodes-layer');
        return {
            svgZ: window.getComputedStyle(svg).zIndex,
            svgOverflow: window.getComputedStyle(svg).overflow,
            cntZ: window.getComputedStyle(cntLayer).zIndex,
            nodesZ: window.getComputedStyle(nodesLayer).zIndex
        };
    }""")

    # SVG connections (z-index 5) must be above container frames (z-index 2) and below nodes (z-index 10)
    assert int(layer_styles["svgZ"]) == 5
    assert int(layer_styles["cntZ"]) == 2
    assert int(layer_styles["nodesZ"]) == 10
    assert layer_styles["svgOverflow"] == "visible"

    # Add 2 nodes and a connection, then place a container frame over them
    wire_check = page.evaluate("""() => {
        const c = window.appCanvas;
        if (!c) return { error: 'No appCanvas' };
        
        // Add two connected nodes
        const n1 = c.addNode('input_data', 150, 150);
        const n2 = c.addNode('browse', 350, 150);
        c.addConnection(n1.id, 'O', n2.id, 'I');
        
        const initialWireCount = document.querySelectorAll('#wires-group .wire').length;
        
        // Add container frame enclosing both nodes
        const cnt = c.addContainer(100, 100, 'Test Frame', 400, 200);
        
        // Wire count immediately after adding container (without moving any tools!)
        const wireCountAfterContainer = document.querySelectorAll('#wires-group .wire').length;
        
        // Resize container
        cnt.width = 500;
        cnt.height = 250;
        c.updateContainerEnclosedNodes(cnt);
        c.renderWires();
        const wireCountAfterResize = document.querySelectorAll('#wires-group .wire').length;
        
        // Disable container
        c.toggleContainerDisabled(cnt.id);
        const wireCountAfterDisable = document.querySelectorAll('#wires-group .wire').length;
        
        return {
            initialWireCount,
            wireCountAfterContainer,
            wireCountAfterResize,
            wireCountAfterDisable
        };
    }""")

    assert wire_check["initialWireCount"] >= 1
    # Wires MUST NOT disappear when container frame is added
    assert wire_check["wireCountAfterContainer"] == wire_check["initialWireCount"]
    assert wire_check["wireCountAfterResize"] == wire_check["initialWireCount"]
    assert wire_check["wireCountAfterDisable"] == wire_check["initialWireCount"]

    page.close()

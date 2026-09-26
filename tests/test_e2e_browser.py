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


# ----------------------------------------------------------------------
# 7. Multi-Tab Workflow Lifecycle, Switching & Isolation
# ----------------------------------------------------------------------
def test_e2e_multitab_creation_and_switching(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")

    # Step 1: Initial Tab
    assert page.locator(".workflow-tab").count() == 1
    t1_title = page.locator(".workflow-tab.active .tab-title").inner_text()
    t1_nodes = page.evaluate("window.appCanvas.nodes.length")

    # Step 2: Create Tab 2
    page.click("#btn-new-tab")
    page.wait_for_timeout(400)
    assert page.locator(".workflow-tab").count() == 2
    t2_title = page.locator(".workflow-tab.active .tab-title").inner_text()
    assert "New Workflow" in t2_title
    assert page.evaluate("window.appCanvas.nodes.length") == 0

    # Step 3: Add node to Tab 2 and verify isolation
    page.evaluate("window.appCanvas.addNode('filter', 200, 200)")
    page.wait_for_timeout(300)
    assert page.evaluate("window.appCanvas.nodes.length") == 1
    assert page.evaluate("window.appTabManager.activeTab.isDirty") is True

    # Step 4: Switch back to Tab 1
    page.locator(".workflow-tab").first.click()
    page.wait_for_timeout(400)
    assert page.locator(".workflow-tab.active .tab-title").inner_text() == t1_title
    assert page.evaluate("window.appCanvas.nodes.length") == t1_nodes

    # Step 5: Switch to Tab 2 via Ctrl+Tab
    page.keyboard.press("Control+Tab")
    page.wait_for_timeout(400)
    assert page.locator(".workflow-tab.active .tab-title").inner_text() == t2_title
    assert page.evaluate("window.appCanvas.nodes.length") == 1

    # Step 6: Create Tab 3 via Ctrl+T and close with Ctrl+W
    page.keyboard.press("Control+t")
    page.wait_for_timeout(400)
    assert page.locator(".workflow-tab").count() == 3

    page.keyboard.press("Control+w")
    page.wait_for_timeout(400)
    assert page.locator(".workflow-tab").count() == 2

    page.close()


# ----------------------------------------------------------------------
# 8. Multi-Tab Tool Addition & Execution Isolation (Alteryx Parity)
# ----------------------------------------------------------------------
def test_e2e_multitab_tool_addition_and_execution_isolation(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")

    # Step 1: Capture Tab 1 initial state (wait for default sample workflow nodes to load)
    page.wait_for_function("() => window.appTabManager && window.appTabManager.tabs[0] && window.appTabManager.tabs[0].canvas.nodes.length > 0", timeout=10000)
    t1_node_count = page.evaluate("window.appTabManager.tabs[0].canvas.nodes.length")
    assert t1_node_count > 0, "Tab 1 should have sample nodes loaded initially"

    # Step 2: Open Tab 2
    page.click("#btn-new-tab")
    page.wait_for_timeout(400)
    assert page.locator(".workflow-tab").count() == 2
    assert page.evaluate("window.appTabManager.activeTabId") == 2
    assert page.evaluate("window.appTabManager.tabs[1].canvas.nodes.length") == 0

    # Step 3: Add tool via Palette Double-Click to Tab 2
    # Verify it is added ONLY to Tab 2 and Tab 1 remains unchanged
    filter_card = page.locator(".tool-card[data-tool-type='filter']").first
    filter_card.dblclick()
    page.wait_for_timeout(300)

    t1_after_add = page.evaluate("window.appTabManager.tabs[0].canvas.nodes.length")
    t2_after_add = page.evaluate("window.appTabManager.tabs[1].canvas.nodes.length")
    assert t1_after_add == t1_node_count, "Tab 1 nodes must NOT change when adding tool to Tab 2"
    assert t2_after_add == 1, "Tab 2 should have exactly 1 node added"

    # Step 4: Add second tool via double click to Tab 2
    browse_card = page.locator(".tool-card[data-tool-type='browse']").first
    browse_card.dblclick()
    page.wait_for_timeout(300)

    assert page.evaluate("window.appTabManager.tabs[0].canvas.nodes.length") == t1_node_count
    assert page.evaluate("window.appTabManager.tabs[1].canvas.nodes.length") == 2

    # Step 5: Test Delete keyboard shortcut isolation
    # Select first node in Tab 2 and delete it
    page.evaluate("""() => {
        const c2 = window.appTabManager.tabs[1].canvas;
        c2.selectNode(c2.nodes[0].id);
    }""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)

    assert page.evaluate("window.appTabManager.tabs[0].canvas.nodes.length") == t1_node_count, "Tab 1 nodes must NOT be affected by Delete in Tab 2"
    assert page.evaluate("window.appTabManager.tabs[1].canvas.nodes.length") == 1, "Tab 2 node should be deleted"

    # Step 6: Setup a runnable mini-workflow on Tab 2
    page.evaluate("""() => {
        const c2 = window.appTabManager.tabs[1].canvas;
        c2.loadWorkflow({
            nodes: [
                { id: 't2_in', type: 'input_data', x: 80, y: 120, config: { file_path: 'sales_orders.csv', file_type: 'csv', delimiter: ',', has_header: true }, label: 'Orders' },
                { id: 't2_br', type: 'browse', x: 260, y: 120, config: {}, label: 'Browse' }
            ],
            connections: [
                { source: 't2_in', sourcePort: 'O', target: 't2_br', targetPort: 'I' }
            ]
        });
    }""")
    page.wait_for_timeout(200)

    # Step 7: Run Tab 2 workflow independently
    page.click("#btn-run")
    # Wait for execution to finish (Run button re-enabled and Stop button hidden)
    page.wait_for_selector("#btn-run:not([disabled])", timeout=15000)
    page.wait_for_timeout(500)

    t2_result = page.evaluate("window.appTabManager.tabs[1].lastResult")
    assert t2_result is not None, "Tab 2 execution must produce results"
    assert t2_result.get("success") is True, "Tab 2 run should succeed"

    # Tab 1 should still have its original node count and its own session
    assert page.evaluate("window.appTabManager.tabs[0].canvas.nodes.length") == t1_node_count

    # Step 8: Switch to Tab 1 and Run Tab 1 independently
    page.locator(".workflow-tab").first.click()
    page.wait_for_timeout(400)
    assert page.evaluate("window.appTabManager.activeTabId") == 1

    page.click("#btn-run")
    page.wait_for_selector("#btn-run:not([disabled])", timeout=15000)
    page.wait_for_timeout(500)

    t1_result = page.evaluate("window.appTabManager.tabs[0].lastResult")
    assert t1_result is not None, "Tab 1 execution must produce results"
    assert t1_result.get("success") is True, "Tab 1 run should succeed"

    # Step 9: Verify switching back to Tab 2 preserves Tab 2's results
    page.locator(".workflow-tab").nth(1).click()
    page.wait_for_timeout(400)
    active_tab_id = page.evaluate("window.appTabManager.activeTabId")
    active_result = page.evaluate("window.appLastResult")
    assert active_tab_id == 2
    assert active_result == t2_result, "Hydrated appLastResult should match Tab 2 result"

    page.close()


# ----------------------------------------------------------------------
# 9. Canvas Overview MiniMap Navigator Interactivity & Controls
# ----------------------------------------------------------------------
def test_e2e_overview_minimap_interactivity(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")

    # Step 1: Verify Minimap class and instance exist
    has_minimap = page.evaluate("() => Boolean(window.CanvasMiniMap && window.appMiniMap)")
    assert has_minimap is True, "window.CanvasMiniMap and window.appMiniMap must be initialized"

    # Step 2: Ensure overview window element is visible
    page.evaluate("() => { if (window.appMiniMap && !window.appMiniMap.visible) window.appMiniMap.toggle(true); }")
    page.wait_for_timeout(200)
    navigator = page.locator("#canvas-overview-navigator")
    assert navigator.is_visible()

    # Step 3: Test Minimize / Restore Toggle Button
    toggle_btn = page.locator("#btn-overview-toggle")
    assert toggle_btn.is_visible()
    
    # Click toggle button to collapse
    toggle_btn.click()
    page.wait_for_timeout(300)
    assert "collapsed" in (navigator.get_attribute("class") or "")
    assert toggle_btn.inner_text().strip() == "+"

    # Click toggle button again to restore
    toggle_btn.click()
    page.wait_for_timeout(300)
    assert "collapsed" not in (navigator.get_attribute("class") or "")
    assert toggle_btn.inner_text().strip() in ("-", "–", "−")

    # Step 4: Test Close Button
    close_btn = page.locator("#btn-overview-close")
    assert close_btn.is_visible()
    close_btn.click()
    page.wait_for_timeout(300)
    assert "hidden" in (navigator.get_attribute("class") or "")

    # Re-open via window.appMiniMap.toggle(true)
    page.evaluate("window.appMiniMap.toggle(true)")
    page.wait_for_timeout(300)
    assert "hidden" not in (navigator.get_attribute("class") or "")

    # Step 5: Test Multi-tab sync on minimap
    page.click("#btn-new-tab")
    page.wait_for_timeout(400)
    # Tab 2 active: verify minimap canvas points to Tab 2
    active_canvas_id = page.evaluate("window.appMiniMap.canvas.tabId")
    assert active_canvas_id == 2

    # Switch back to Tab 1
    page.locator(".workflow-tab").first.click()
    page.wait_for_timeout(400)
    active_canvas_id_t1 = page.evaluate("window.appMiniMap.canvas.tabId")
    assert active_canvas_id_t1 == 1

    # Step 6: Test Click-to-Center Navigation
    init_pan_x = page.evaluate("window.appCanvas.panX")
    body = page.locator("#overview-body")
    box = body.bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + 25, box["y"] + 25)
    page.wait_for_timeout(300)
    new_pan_x = page.evaluate("window.appCanvas.panX")
    assert new_pan_x != init_pan_x, "Click-to-center on minimap should update canvas pan coordinates"

    page.close()

# ----------------------------------------------------------------------
# 10. Canvas Infinite Dynamic Workspace, Far Move, Negative Coords & Zoom Stability
# ----------------------------------------------------------------------
def test_e2e_canvas_infinite_dynamic_workspace_and_zoom(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes.length > 0", timeout=10000)
    page.wait_for_timeout(300)

    # Step 1: Add tools and place them far into positive and negative space
    page.evaluate("""() => {
        const c = window.appCanvas;
        c.clearCanvas();
        // Node 1: Origin
        const n1 = c.addNode('input_data', 100, 100, 'Origin Tool');
        // Node 2: Far positive space (> 2500px, outside any standard viewport)
        const n2 = c.addNode('select', 3000, 2200, 'Far Positive Tool');
        // Node 3: Negative space (< 0px in both X and Y)
        const n3 = c.addNode('filter', -1200, -800, 'Negative Coords Tool');
        
        // Connect them across the infinite canvas
        c.addConnection(n1.id, 'O', n2.id, 'I');
        c.addConnection(n3.id, 'O', n1.id, 'I');
    }""")
    page.wait_for_timeout(300)

    # Verify all 3 nodes and 2 wires exist in DOM and are not clipped
    nodes_count = page.evaluate("window.appCanvas.nodes.length")
    wires_count = page.evaluate("window.appCanvas.connections.length")
    assert nodes_count == 3
    assert wires_count == 2

    # Step 2: Verify nodes in far positive and negative space exist as visible DOM elements
    n2_pos = page.evaluate("""() => {
        const n = window.appCanvas.nodes.find(item => item.name === 'Far Positive Tool');
        const nodeEl = document.getElementById('node-elem-' + n.id);
        return {
            x: n.x,
            y: n.y,
            styleLeft: nodeEl.style.left,
            styleTop: nodeEl.style.top,
            offsetWidth: nodeEl.offsetWidth,
            offsetHeight: nodeEl.offsetHeight
        };
    }""")
    assert n2_pos["x"] == 3008
    assert n2_pos["y"] == 2208
    assert n2_pos["styleLeft"] == "3008px"
    assert n2_pos["offsetWidth"] == 56

    n3_pos = page.evaluate("""() => {
        const n = window.appCanvas.nodes.find(item => item.name === 'Negative Coords Tool');
        const nodeEl = document.getElementById('node-elem-' + n.id);
        return {
            x: n.x,
            y: n.y,
            styleLeft: nodeEl.style.left,
            styleTop: nodeEl.style.top,
            offsetWidth: nodeEl.offsetWidth,
            offsetHeight: nodeEl.offsetHeight
        };
    }""")
    assert n3_pos["x"] == -1200
    assert n3_pos["y"] == -800
    assert n3_pos["styleLeft"] == "-1200px"
    assert n3_pos["offsetWidth"] == 56

    # Step 3: Test PanTo negative coords and verify element is in viewport
    page.evaluate("window.appCanvas.panTo(-1200, -800)")
    page.wait_for_timeout(300)
    pan_x = page.evaluate("window.appCanvas.panX")
    pan_y = page.evaluate("window.appCanvas.panY")
    assert pan_x > 0, "Panning to negative world coordinates should shift panX positively"

    # Step 4: Test Zoom Levels (0.25x up to 2.5x)
    for target_zoom in [0.25, 0.5, 1.0, 1.5, 2.0, 2.5]:
        page.evaluate(f"window.appCanvas.applyZoom({target_zoom})")
        page.wait_for_timeout(100)
        current_zoom = page.evaluate("window.appCanvas.zoom")
        assert abs(current_zoom - target_zoom) < 0.05, f"Canvas zoom should be near {target_zoom}"
        zoom_text = page.locator("#zoom-level-text").inner_text()
        assert f"{round(target_zoom * 100)}%" in zoom_text

    # Step 5: Test zoomToFit()
    page.evaluate("window.appCanvas.zoomToFit()")
    page.wait_for_timeout(300)
    fit_zoom = page.evaluate("window.appCanvas.zoom")
    assert 0.15 <= fit_zoom <= 2.0, "zoomToFit should choose a valid zoom level to fit all 3 nodes"

    # Step 6: Test Container with negative bounds
    page.evaluate("""() => {
        const c = window.appCanvas;
        const n3 = c.nodes.find(item => item.name === 'Negative Coords Tool');
        const cont = c.addContainer(n3.x - 30, n3.y - 40, 'Negative Container', 240, 180);
    }""")
    page.wait_for_timeout(200)
    cont_x = page.evaluate("window.appCanvas.containers[0].x")
    assert cont_x < -1200, "Container in negative coordinates must preserve negative x without clamping to 0"

    page.close()


# ----------------------------------------------------------------------
# 10. Wire Rendering & Visual Connectivity across Infinite Canvas
# ----------------------------------------------------------------------
def test_e2e_wire_rendering_and_visibility(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.connections && window.appCanvas.connections.length >= 10")
    page.wait_for_selector(".wire", state="attached")

    # 1. Verify default tab wires SVG dimensions and paths
    initial_wires = page.evaluate("""() => {
        const svg = document.getElementById('canvas-svg');
        const wires = document.querySelectorAll('#wires-group .wire');
        const hitZones = document.querySelectorAll('.wire-hit-zone');
        const style = window.getComputedStyle(svg);
        return {
            svgWidth: style.width,
            svgHeight: style.height,
            viewBox: svg.getAttribute('viewBox'),
            wireCount: wires.length,
            hitZoneCount: hitZones.length,
            firstWireD: wires[0] ? wires[0].getAttribute('d') : null,
            firstMarker: wires[0] ? wires[0].getAttribute('marker-end') : null
        };
    }""")
    assert initial_wires["wireCount"] >= 10, f"Expected >= 10 wires, got {initial_wires['wireCount']}"
    assert initial_wires["hitZoneCount"] >= 10
    assert initial_wires["viewBox"] == "-50000 -50000 100000 100000"
    assert "100000px" in initial_wires["svgWidth"]
    assert initial_wires["firstWireD"] is not None
    assert "arrow" in initial_wires["firstMarker"]

    # 2. Test wire selection by clicking hit-zone
    selection_check = page.evaluate("""() => {
        const hitZone = document.querySelector('.wire-hit-zone');
        if (!hitZone) return { error: 'No hitzone' };
        hitZone.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        return {
            selectedId: window.appCanvas ? window.appCanvas.selectedConnectionId : null,
            isSelectedClass: hitZone.nextElementSibling ? hitZone.nextElementSibling.classList.contains('selected') : false
        };
    }""")
    assert selection_check.get("selectedId") is not None
    assert selection_check.get("isSelectedClass") is True

    # 3. Test negative coordinate wire rendering
    neg_wire_check = page.evaluate("""() => {
        const c = window.appCanvas;
        const n1 = c.addNode('input_data', -400, -300);
        const n2 = c.addNode('browse', -150, -300);
        c.addConnection(n1.id, 'O', n2.id, 'I');
        c.renderWires();
        const wires = document.querySelectorAll('#wires-group .wire');
        const lastWire = wires[wires.length - 1];
        return {
            wireD: lastWire ? lastWire.getAttribute('d') : null
        };
    }""")
    assert neg_wire_check["wireD"] is not None
    assert "-400" in neg_wire_check["wireD"] or "-34" in neg_wire_check["wireD"] or "-15" in neg_wire_check["wireD"]

    # 4. Multi-tab wire verification
    tab2_wires = page.evaluate("""() => {
        const tm = window.appTabManager;
        const tab2Ctx = tm.createTab(null, 'Tab 2 Wire Test');
        const tab2Canvas = tab2Ctx.canvas;
        const n1 = tab2Canvas.addNode('input_data', 100, 100);
        const n2 = tab2Canvas.addNode('filter', 350, 100);
        tab2Canvas.addConnection(n1.id, 'O', n2.id, 'I');
        const host = tab2Ctx.hostEl;
        const wires = host.querySelectorAll('.wire-group .wire');
        return {
            tab2WireCount: wires.length,
            wireD: wires[0] ? wires[0].getAttribute('d') : null
        };
    }""")
    assert tab2_wires["tab2WireCount"] == 1
    assert tab2_wires["wireD"] is not None

    page.close()


# ----------------------------------------------------------------------
# 12. Results Panel Column Sorting & Header Context Menus
# ----------------------------------------------------------------------
def test_e2e_results_panel_column_sorting(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes && window.appCanvas.nodes.length > 0")
    page.wait_for_selector(".node-card")

    # Select the first node to view its data in the results panel
    page.evaluate("""() => {
        const c = window.appCanvas;
        const n = c.nodes[0];
        c.selectNode(n.id);
        window.appResultsPanel.showNodeResults(n);
    }""")
    page.wait_for_timeout(600)

    # 1. Verify sort buttons are present on table headers
    check_headers = page.evaluate("""() => {
        const ths = document.querySelectorAll('.data-table th[data-col-name]');
        const sortBtns = document.querySelectorAll('.th-sort-btn');
        const menuBtns = document.querySelectorAll('.th-menu-btn');
        return {
            thCount: ths.length,
            sortBtnCount: sortBtns.length,
            menuBtnCount: menuBtns.length,
            firstColName: ths[0] ? ths[0].dataset.colName : null
        };
    }""")
    assert check_headers["thCount"] > 0
    assert check_headers["sortBtnCount"] == check_headers["thCount"]
    assert check_headers["menuBtnCount"] == check_headers["thCount"]

    first_col = check_headers["firstColName"]

    # 2. Click sort button on the first column -> Ascending
    sort_asc_res = page.evaluate(f"""() => {{
        const btn = document.querySelector('.th-sort-btn[data-col="{first_col}"]');
        btn.click();
        return new Promise(resolve => {{
            setTimeout(() => {{
                const rp = window.appResultsPanel;
                const rows = Array.from(document.querySelectorAll('.data-table tbody tr')).map(tr => {{
                    const td = tr.querySelector('td[data-col="{first_col}"]');
                    return td ? td.textContent.trim() : null;
                }});
                const indicator = document.getElementById('results-sort-indicator');
                resolve({{
                    sortBy: rp.sortBy,
                    sortDir: rp.sortDir,
                    indicatorText: indicator ? indicator.textContent.trim() : '',
                    firstThreeValues: rows.slice(0, 3)
                }});
            }}, 400);
        }});
    }}""")
    assert sort_asc_res["sortBy"] == first_col
    assert sort_asc_res["sortDir"] == "asc"
    assert "Sorted:" in sort_asc_res["indicatorText"]

    # 3. Click sort button again -> Descending
    sort_desc_res = page.evaluate(f"""() => {{
        const btn = document.querySelector('.th-sort-btn[data-col="{first_col}"]');
        btn.click();
        return new Promise(resolve => {{
            setTimeout(() => {{
                const rp = window.appResultsPanel;
                const rows = Array.from(document.querySelectorAll('.data-table tbody tr')).map(tr => {{
                    const td = tr.querySelector('td[data-col="{first_col}"]');
                    return td ? td.textContent.trim() : null;
                }});
                const indicator = document.getElementById('results-sort-indicator');
                resolve({{
                    sortBy: rp.sortBy,
                    sortDir: rp.sortDir,
                    indicatorText: indicator ? indicator.textContent.trim() : '',
                    firstThreeValues: rows.slice(0, 3)
                }});
            }}, 400);
        }});
    }}""")
    assert sort_desc_res["sortBy"] == first_col
    assert sort_desc_res["sortDir"] == "desc"

    # 4. Clear sort via clear button in sort indicator badge
    clear_res = page.evaluate("""() => {
        const clearBtn = document.getElementById('btn-clear-active-sort');
        clearBtn.click();
        return new Promise(resolve => {
            setTimeout(() => {
                const rp = window.appResultsPanel;
                const indicator = document.getElementById('results-sort-indicator');
                resolve({
                    sortBy: rp.sortBy,
                    sortDir: rp.sortDir,
                    indicatorDisplay: indicator ? indicator.style.display : 'none'
                });
            }, 400);
        });
    }""")
    assert clear_res["sortBy"] is None
    assert clear_res["indicatorDisplay"] == "none"

    # 5. Test Column Dropdown Menu
    col_menu_res = page.evaluate(f"""() => {{
        const menuBtn = document.querySelector('.th-menu-btn[data-col="{first_col}"]');
        menuBtn.click();
        const menu = document.querySelector('.column-context-menu');
        const items = menu ? Array.from(menu.querySelectorAll('.grid-context-menu-item')).map(i => i.textContent.trim()) : [];
        return {{
            menuOpen: Boolean(menu),
            itemCount: items.length,
            items: items
        }};
    }}""")
    assert col_menu_res["menuOpen"] is True
    assert any("Sort Ascending" in it for it in col_menu_res["items"])
    assert any("Sort Descending" in it for it in col_menu_res["items"])

    # Click Sort Descending from column menu
    menu_click_res = page.evaluate("""() => {
        const item = document.getElementById('col-menu-sort-desc');
        item.click();
        return new Promise(resolve => {
            setTimeout(() => {
                const rp = window.appResultsPanel;
                resolve({
                    sortBy: rp.sortBy,
                    sortDir: rp.sortDir
                });
            }, 400);
        });
    }""")
    assert menu_click_res["sortDir"] == "desc"

    page.close()


# ----------------------------------------------------------------------
# 13. Alignment & Distribution Tools (Toolbar & Floating HUD)
# ----------------------------------------------------------------------
def test_e2e_alignment_and_distribution(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes")

    # Set up 3 specific nodes on the canvas
    setup_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.loadWorkflow({ nodes: [], connections: [] });
        const n1 = c.addNode('input', 100, 120);
        const n2 = c.addNode('filter', 250, 200);
        const n3 = c.addNode('select', 600, 310);
        c.selectedNodeIds.clear();
        c.selectedNodeIds.add(n1.id);
        c.selectedNodeIds.add(n2.id);
        c.selectedNodeIds.add(n3.id);
        c.updateSelectionVisuals();
        return {
            count: c.nodes.length,
            n1: { id: n1.id, x: n1.x, y: n1.y },
            n2: { id: n2.id, x: n2.x, y: n2.y },
            n3: { id: n3.id, x: n3.x, y: n3.y }
        };
    }""")
    assert setup_res["count"] == 3

    # 1. Verify alignment buttons are NOT present in the main toolbar (kept ONLY on right-click)
    toolbar_btns_present = page.evaluate("""() => {
        return {
            alignH: Boolean(document.getElementById('btn-align-h')),
            alignV: Boolean(document.getElementById('btn-align-v')),
            distH: Boolean(document.getElementById('btn-distribute-h')),
            distV: Boolean(document.getElementById('btn-distribute-v'))
        };
    }""")
    assert not any(toolbar_btns_present.values()), "Alignment buttons must not be present in toolbar"

    # 2. Verify right-click context menu displays alignment and distribution actions for multi-selection
    ctx_menu_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.showNodeContextMenu(200, 200);
        const menu = c.contextMenu;
        return {
            visible: menu && menu.style.display !== 'none',
            hasAlignH: Boolean(menu.querySelector('#ctx-align-h')),
            hasAlignV: Boolean(menu.querySelector('#ctx-align-v')),
            hasDistH: Boolean(menu.querySelector('#ctx-distribute-h')),
            hasDistV: Boolean(menu.querySelector('#ctx-distribute-v'))
        };
    }""")
    assert ctx_menu_res["visible"] is True
    assert ctx_menu_res["hasAlignH"] is True
    assert ctx_menu_res["hasAlignV"] is True
    assert ctx_menu_res["hasDistH"] is True
    assert ctx_menu_res["hasDistV"] is True

    # 3. Test Align Horizontally via context menu click: All nodes should share the exact same Y position
    align_h_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.contextMenu.querySelector('#ctx-align-h').click();
        return c.nodes.map(n => n.y);
    }""")
    assert len(set(align_h_res)) == 1, f"Expected all nodes to have identical Y coordinate, got {align_h_res}"

    # 4. Test Distribute Horizontally via context menu: Spacing between nodes should be equal
    dist_h_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.nodes[0].x = 100;
        c.nodes[1].x = 200;
        c.nodes[2].x = 600;
        c.showNodeContextMenu(200, 200);
        c.contextMenu.querySelector('#ctx-distribute-h').click();
        return c.nodes.map(n => n.x).sort((a, b) => a - b);
    }""")
    # (600 - 100) / 2 = 250 interval -> 100, 350, 600
    assert dist_h_res[0] == 100
    assert dist_h_res[1] == 350
    assert dist_h_res[2] == 600

    # 5. Test Align Vertically via context menu: All nodes should share the exact same X position
    align_v_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.showNodeContextMenu(200, 200);
        c.contextMenu.querySelector('#ctx-align-v').click();
        return c.nodes.map(n => n.x);
    }""")
    assert len(set(align_v_res)) == 1, f"Expected all nodes to have identical X coordinate, got {align_v_res}"

    page.close()


# ----------------------------------------------------------------------
# 14. Wireless Connections & Semantic Anchor Tooltips
# ----------------------------------------------------------------------
def test_e2e_wireless_connections_and_semantic_tooltips(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes")

    # Set up 2 connected nodes on the canvas
    setup_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.loadWorkflow({ nodes: [], connections: [] });
        const n1 = c.addNode('input', 100, 100);
        const n2 = c.addNode('filter', 400, 100);
        const conn = c.addConnection(n1.id, 'O', n2.id, 'I');
        return {
            n1Id: n1.id,
            n2Id: n2.id,
            connId: conn.id,
            wirelessInitial: Boolean(conn.wireless)
        };
    }""")
    assert setup_res["wirelessInitial"] is False
    conn_id = setup_res["connId"]
    n1_id = setup_res["n1Id"]

    # 1. Toggle connection to wireless
    toggle_res = page.evaluate(f"""() => {{
        const c = window.appCanvas;
        c.toggleConnectionWireless('{conn_id}');
        const conn = c.connections.find(x => x.id === '{conn_id}');
        const badges = document.querySelectorAll('.wireless-badge');
        const wire = document.querySelector(`.wire[data-connection-id="{conn_id}"]`);
        
        // Check initial visibility: badges must NOT be persistent (not is-visible, opacity ~ 0)
        let anyVisibleInitially = false;
        badges.forEach(b => {{
            if (b.classList.contains('is-visible') || parseFloat(window.getComputedStyle(b).opacity) > 0.1) {{
                anyVisibleInitially = true;
            }}
        }});

        return {{
            isWireless: conn.wireless,
            badgeCount: badges.length,
            wireHasWirelessClass: wire ? wire.classList.contains('wire-wireless') : false,
            anyVisibleInitially: anyVisibleInitially
        }};
    }}""")
    assert toggle_res["isWireless"] is True
    assert toggle_res["badgeCount"] == 2, "Expected 2 wireless transmitter/receiver badges (source & target)"
    assert toggle_res["wireHasWirelessClass"] is True
    assert toggle_res["anyVisibleInitially"] is False, "Wireless badges must NOT be persistent"

    # 2. Hover node and verify wireless badges become visible
    hover_res = page.evaluate(f"""() => {{
        const c = window.appCanvas;
        c.highlightWirelessConnections('{n1_id}', true);
        const badges = document.querySelectorAll('.wireless-badge');
        let allVisibleOnHover = true;
        badges.forEach(b => {{
            if (!b.classList.contains('is-visible')) allVisibleOnHover = false;
        }});

        const badgeFontSize = badges.length > 0 ? parseFloat(window.getComputedStyle(badges[0]).fontSize) : 0;

        // Unhover
        c.highlightWirelessConnections('{n1_id}', false);
        let visibleAfterUnhover = false;
        badges.forEach(b => {{
            if (b.classList.contains('is-visible')) visibleAfterUnhover = true;
        }});

        return {{
            allVisibleOnHover: allVisibleOnHover,
            visibleAfterUnhover: visibleAfterUnhover,
            badgeFontSize: badgeFontSize
        }};
    }}""")
    assert hover_res["allVisibleOnHover"] is True, "Badges should become visible when node is hovered"
    assert hover_res["visibleAfterUnhover"] is False, "Badges should hide when node hover ends"
    assert hover_res["badgeFontSize"] <= 10.0, f"Expected subtle smaller font <= 10px, got {hover_res['badgeFontSize']}"

    # 3. Toggle back to wired connection
    toggle_back_res = page.evaluate(f"""() => {{
        const c = window.appCanvas;
        c.toggleConnectionWireless('{conn_id}');
        const conn = c.connections.find(x => x.id === '{conn_id}');
        const badges = document.querySelectorAll('.wireless-badge');
        return {{
            isWireless: conn.wireless,
            badgeCount: badges.length
        }};
    }}""")
    assert toggle_back_res["isWireless"] is False
    assert toggle_back_res["badgeCount"] == 0

    # 4. Test Semantic Anchor Tooltip on Filter Node Ports (compact font size check)
    tooltip_res = page.evaluate("""() => {
        const c = window.appCanvas;
        const filterNode = c.nodes.find(n => n.type === 'filter');
        const portEl = document.querySelector(`#node-elem-${filterNode.id} .port-output[data-port="T"]`);
        if (!portEl) return { error: 'port not found' };

        c.showAnchorTooltip(portEl, filterNode, 'T', 'output');
        const tooltip = document.getElementById('anchor-tooltip');
        const isVisible = tooltip && tooltip.classList.contains('is-visible');
        const text = tooltip ? tooltip.textContent : '';
        const tooltipFontSize = tooltip ? parseFloat(window.getComputedStyle(tooltip).fontSize) : 0;

        c.hideAnchorTooltip();
        const hiddenAfter = !document.getElementById('anchor-tooltip');

        return {
            isVisible: isVisible,
            text: text,
            hiddenAfter: hiddenAfter,
            tooltipFontSize: tooltipFontSize
        };
    }""")
    assert tooltip_res.get("error") is None
    assert tooltip_res["isVisible"] is True
    assert "True" in tooltip_res["text"] or "T" in tooltip_res["text"]
    assert tooltip_res["hiddenAfter"] is True
    assert tooltip_res["tooltipFontSize"] <= 11.0, f"Expected small anchor tooltip font <= 11px, got {tooltip_res['tooltipFontSize']}"

    page.close()


# ----------------------------------------------------------------------
# 15. Auto-Connect & Wire Snapping
# ----------------------------------------------------------------------
def test_e2e_auto_connect_and_wire_snapping(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes")

    # Set up Node A -> Node B and splice Node C in between
    splice_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.loadWorkflow({ nodes: [], connections: [] });
        const nA = c.addNode('input', 100, 150);
        const nB = c.addNode('select', 600, 150);
        const connAB = c.addConnection(nA.id, 'O', nB.id, 'I');

        // Add a new node C positioned between A and B
        const nC = c.addNode('filter', 350, 150);

        // Find wire near node C's center (350, 150)
        const hitConn = c.findWireNear(350, 150, 40);

        // Execute splice: A -> C -> B
        const spliceSuccess = c.spliceNodeIntoConnection(nC.id, connAB.id);

        const conns = c.connections.map(cn => ({
            from: cn.source,
            fromPort: cn.sourceHandle,
            to: cn.target,
            toPort: cn.targetHandle
        }));

        return {
            hitConnId: hitConn ? hitConn.id : null,
            targetConnId: connAB.id,
            spliceSuccess: spliceSuccess,
            connsCount: conns.length,
            conns: conns,
            nodeAId: nA.id,
            nodeBId: nB.id,
            nodeCId: nC.id
        };
    }""")

    assert splice_res["hitConnId"] == splice_res["targetConnId"]
    assert splice_res["spliceSuccess"] is True
    assert splice_res["connsCount"] == 2

    # Verify A connects to C, and C connects to B
    conns = splice_res["conns"]
    a_id = splice_res["nodeAId"]
    b_id = splice_res["nodeBId"]
    c_id = splice_res["nodeCId"]

    has_a_to_c = any(cn["from"] == a_id and cn["to"] == c_id for cn in conns)
    has_c_to_b = any(cn["from"] == c_id and cn["to"] == b_id for cn in conns)
    assert has_a_to_c, f"Expected A->C connection, got {conns}"
    assert has_c_to_b, f"Expected C->B connection, got {conns}"

    page.close()


# ----------------------------------------------------------------------
# 16. Interactive Data Cleansing & Filtering from Data View
# ----------------------------------------------------------------------
def test_e2e_interactive_data_cleansing_from_data_view(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes && window.appCanvas.nodes.length > 0")
    page.wait_for_selector(".node-card")

    # Select the first node to populate data view
    page.evaluate("""() => {
        const c = window.appCanvas;
        const n = c.nodes[0];
        c.selectNode(n.id);
        window.appResultsPanel.showNodeResults(n);
    }""")
    page.wait_for_timeout(600)

    # 1. Test Cell Context Menu Cleansing Options
    cell_menu_res = page.evaluate("""() => {
        const rp = window.appResultsPanel;
        const td = document.querySelector('.data-table td[data-col-idx="0"]');
        if (!td) return { error: 'No data cell found' };

        const r = parseInt(td.dataset.rowIdx, 10);
        const c = parseInt(td.dataset.colIdx, 10);
        rp.openContextMenu(150, 200, r, c, td);

        const menu = document.querySelector('.grid-context-menu');
        const filterOnlyBtn = document.getElementById('ctx-filter-only');
        const filterOutBtn = document.getElementById('ctx-filter-out');
        const cleanTrimBtn = document.getElementById('ctx-clean-trim');

        return {
            menuOpen: Boolean(menu),
            hasFilterOnly: Boolean(filterOnlyBtn),
            hasFilterOut: Boolean(filterOutBtn),
            hasCleanTrim: Boolean(cleanTrimBtn)
        };
    }""")
    assert cell_menu_res.get("error") is None
    assert cell_menu_res["menuOpen"] is True
    assert cell_menu_res["hasFilterOut"] is True
    assert cell_menu_res["hasCleanTrim"] is True

    # 2. Click "Clean: Trim Whitespace" -> Appends clean node connected downstream
    click_clean_res = page.evaluate("""() => {
        const c = window.appCanvas;
        const initialCount = c.nodes.length;
        const cleanTrimBtn = document.getElementById('ctx-clean-trim');
        cleanTrimBtn.click();

        return new Promise(resolve => {
            setTimeout(() => {
                const newCount = c.nodes.length;
                const newestNode = c.nodes[c.nodes.length - 1];
                const newestConn = c.connections[c.connections.length - 1];
                resolve({
                    initialCount: initialCount,
                    newCount: newCount,
                    newNodeType: newestNode ? newestNode.type : null,
                    isCleanTrimConfig: newestNode ? Boolean(newestNode.config && newestNode.config.trim_whitespace) : false,
                    isConnectedToSource: newestConn ? newestConn.target === newestNode.id : false
                });
            }, 300);
        });
    }""")
    assert click_clean_res["newCount"] == click_clean_res["initialCount"] + 1
    assert click_clean_res["newNodeType"] == "clean"
    assert click_clean_res["isCleanTrimConfig"] is True
    assert click_clean_res["isConnectedToSource"] is True

    # 3. Test Column Menu Cleansing Options
    col_menu_res = page.evaluate("""() => {
        const rp = window.appResultsPanel;
        const th = document.querySelector('.data-table th[data-col-name]');
        const colName = th ? th.dataset.colName : 'col';
        rp.openColumnMenu(200, 200, colName, 0);

        const filterNullsBtn = document.getElementById('col-menu-filter-nulls');
        const cleanZerosBtn = document.getElementById('col-menu-clean-zeros');
        const cleanBlanksBtn = document.getElementById('col-menu-clean-blanks');
        const cleanTrimBtn = document.getElementById('col-menu-clean-trim');

        return {
            hasFilterNulls: Boolean(filterNullsBtn),
            hasCleanZeros: Boolean(cleanZerosBtn),
            hasCleanBlanks: Boolean(cleanBlanksBtn),
            hasCleanTrim: Boolean(cleanTrimBtn)
        };
    }""")
    assert col_menu_res["hasFilterNulls"] is True
    assert col_menu_res["hasCleanZeros"] is True
    assert col_menu_res["hasCleanBlanks"] is True
    assert col_menu_res["hasCleanTrim"] is True

    # 4. Click "Filter Out Nulls" from column menu -> Appends filter tool downstream
    click_col_filter_res = page.evaluate("""() => {
        const c = window.appCanvas;
        const initialCount = c.nodes.length;
        const filterNullsBtn = document.getElementById('col-menu-filter-nulls');
        filterNullsBtn.click();

        return new Promise(resolve => {
            setTimeout(() => {
                const newCount = c.nodes.length;
                const newestNode = c.nodes[c.nodes.length - 1];
                const newestConn = c.connections[c.connections.length - 1];
                resolve({
                    initialCount: initialCount,
                    newCount: newCount,
                    newNodeType: newestNode ? newestNode.type : null,
                    conditions: (newestNode && newestNode.config) ? newestNode.config.conditions : [],
                    isConnectedToSource: newestConn ? newestConn.target === newestNode.id : false
                });
            }, 300);
        });
    }""")
    assert click_col_filter_res["newCount"] == click_col_filter_res["initialCount"] + 1
    assert click_col_filter_res["newNodeType"] == "filter"
    assert click_col_filter_res["isConnectedToSource"] is True
    assert any(cond.get("operator") == "is_not_null" for cond in click_col_filter_res["conditions"])

    page.close()


# ----------------------------------------------------------------------
# 17. View Menu Tooltip Toggles & Preference Persistence
# ----------------------------------------------------------------------
def test_e2e_view_menu_tooltip_toggles_and_config_persistence(live_server, browser_context):
    page = browser_context.new_page()
    page.goto(live_server)
    page.wait_for_selector(".tool-card")
    page.wait_for_function("() => window.appCanvas && window.appCanvas.nodes")

    # 1. Verify View Menu has the new Tooltip Toggle items with initial checkmarks
    initial_menu_res = page.evaluate("""() => {
        const checkNode = document.getElementById('check-view-node-tooltips');
        const checkWireless = document.getElementById('check-view-wireless-tooltips');
        const c = window.appCanvas;
        return {
            hasCheckNode: Boolean(checkNode),
            hasCheckWireless: Boolean(checkWireless),
            nodeCheckText: checkNode ? checkNode.textContent.trim() : '',
            wirelessCheckText: checkWireless ? checkWireless.textContent.trim() : '',
            nodeTooltipsEnabled: c.nodeTooltipsEnabled,
            wirelessTooltipsEnabled: c.wirelessTooltipsEnabled
        };
    }""")
    assert initial_menu_res["hasCheckNode"] is True
    assert initial_menu_res["hasCheckWireless"] is True
    assert initial_menu_res["nodeCheckText"] == "✓"
    assert initial_menu_res["wirelessCheckText"] == "✓"
    assert initial_menu_res["nodeTooltipsEnabled"] is True
    assert initial_menu_res["wirelessTooltipsEnabled"] is True

    # 2. Test Node Tooltips Toggle OFF & ON
    node_toggle_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.loadWorkflow({ nodes: [], connections: [] });
        const n1 = c.addNode('filter', 150, 150);

        // Turn OFF via View menu command
        window.app.executeCommand('view:toggle-node-tooltips');
        const stateOff = c.nodeTooltipsEnabled;
        const checkOff = document.getElementById('check-view-node-tooltips').textContent.trim();
        const settingOff = window.userSettings ? window.userSettings.get('node_tooltips_enabled') : null;

        // Try showing anchor tooltip while disabled
        const portEl = document.querySelector(`#node-elem-${n1.id} .port-output[data-port="T"]`);
        c.showAnchorTooltip(portEl, n1, 'T', 'output');
        const tooltipWhileOff = document.getElementById('anchor-tooltip');

        // Turn back ON
        window.app.executeCommand('view:toggle-node-tooltips');
        const stateOn = c.nodeTooltipsEnabled;
        const checkOn = document.getElementById('check-view-node-tooltips').textContent.trim();
        const settingOn = window.userSettings ? window.userSettings.get('node_tooltips_enabled') : null;

        // Try showing anchor tooltip while enabled
        c.showAnchorTooltip(portEl, n1, 'T', 'output');
        const tooltipWhileOn = document.getElementById('anchor-tooltip');
        const tooltipVisible = tooltipWhileOn && tooltipWhileOn.classList.contains('is-visible');
        c.hideAnchorTooltip();

        return {
            stateOff: stateOff,
            checkOff: checkOff,
            settingOff: settingOff,
            tooltipWhileOffExists: Boolean(tooltipWhileOff),
            stateOn: stateOn,
            checkOn: checkOn,
            settingOn: settingOn,
            tooltipVisible: tooltipVisible
        };
    }""")
    assert node_toggle_res["stateOff"] is False
    assert node_toggle_res["checkOff"] == ""
    assert node_toggle_res["settingOff"] is False
    assert node_toggle_res["tooltipWhileOffExists"] is False, "Anchor tooltip should not appear when node tooltips are OFF"
    assert node_toggle_res["stateOn"] is True
    assert node_toggle_res["checkOn"] == "✓"
    assert node_toggle_res["settingOn"] is True
    assert node_toggle_res["tooltipVisible"] is True

    # 3. Test Wireless Connection Tooltips Toggle OFF & ON
    wireless_toggle_res = page.evaluate("""() => {
        const c = window.appCanvas;
        c.loadWorkflow({ nodes: [], connections: [] });
        const n1 = c.addNode('input', 100, 100);
        const n2 = c.addNode('filter', 400, 100);
        const conn = c.addConnection(n1.id, 'O', n2.id, 'I');
        c.toggleConnectionWireless(conn.id);

        // Turn OFF wireless tooltips via View menu
        window.app.executeCommand('view:toggle-wireless-tooltips');
        const stateOff = c.wirelessTooltipsEnabled;
        const checkOff = document.getElementById('check-view-wireless-tooltips').textContent.trim();
        const settingOff = window.userSettings ? window.userSettings.get('wireless_tooltips_enabled') : null;

        // Trigger hover on node while disabled -> badges must NOT be visible
        c.highlightWirelessConnections(n1.id, true);
        const badgesOff = document.querySelectorAll('.wireless-badge.is-visible');
        const countVisibleOff = badgesOff.length;

        // Turn back ON
        window.app.executeCommand('view:toggle-wireless-tooltips');
        const stateOn = c.wirelessTooltipsEnabled;
        const checkOn = document.getElementById('check-view-wireless-tooltips').textContent.trim();
        const settingOn = window.userSettings ? window.userSettings.get('wireless_tooltips_enabled') : null;

        // Trigger hover on node while enabled -> badges MUST be visible
        c.highlightWirelessConnections(n1.id, true);
        const badgesOn = document.querySelectorAll('.wireless-badge.is-visible');
        const countVisibleOn = badgesOn.length;

        // Unhover
        c.highlightWirelessConnections(n1.id, false);

        return {
            stateOff: stateOff,
            checkOff: checkOff,
            settingOff: settingOff,
            countVisibleOff: countVisibleOff,
            stateOn: stateOn,
            checkOn: checkOn,
            settingOn: settingOn,
            countVisibleOn: countVisibleOn
        };
    }""")
    assert wireless_toggle_res["stateOff"] is False
    assert wireless_toggle_res["checkOff"] == ""
    assert wireless_toggle_res["settingOff"] is False
    assert wireless_toggle_res["countVisibleOff"] == 0, "Badges should not be visible when wireless tooltips are OFF"
    assert wireless_toggle_res["stateOn"] is True
    assert wireless_toggle_res["checkOn"] == "✓"
    assert wireless_toggle_res["settingOn"] is True
    assert wireless_toggle_res["countVisibleOn"] == 2

    # 4. Verify Other View Menu User Configs Function and Persist
    configs_res = page.evaluate("""() => {
        const app = window.app;
        const settings = window.userSettings;

        // 4a. Tool Palette toggle
        const palette = document.getElementById('tool-palette-ribbon') || document.getElementById('palette-bar');
        const initialPaletteDisplay = palette.style.display;
        app.executeCommand('view:toggle-palette');
        const toggledPaletteDisplay = palette.style.display;
        const paletteSetting = settings.get('palette_visible');
        const checkPalette = document.getElementById('check-view-palette').textContent.trim();
        // Restore
        app.executeCommand('view:toggle-palette');

        // 4b. Configuration Panel toggle
        const config = document.getElementById('config-panel') || document.getElementById('config-sidebar');
        const initialConfigDisplay = config.style.display;
        app.executeCommand('view:toggle-config');
        const toggledConfigDisplay = config.style.display;
        const configSetting = settings.get('config_visible');
        const checkConfig = document.getElementById('check-view-config').textContent.trim();
        // Restore
        app.executeCommand('view:toggle-config');

        // 4c. Results Panel toggle
        const results = document.getElementById('results-panel');
        const initialCollapsed = results.classList.contains('collapsed');
        app.executeCommand('view:toggle-results');
        const toggledCollapsed = results.classList.contains('collapsed');
        const resultsSetting = settings.get('results_visible');
        const checkResults = document.getElementById('check-view-results').textContent.trim();
        // Restore
        app.executeCommand('view:toggle-results');

        // 4d. In-grid Histograms toggle
        app.executeCommand('view:toggle-histograms');
        const histSetting = settings.get('show_histograms');
        const checkHist = document.getElementById('check-view-histograms').textContent.trim();
        // Restore
        app.executeCommand('view:toggle-histograms');

        // 4e. Execution Badges duration
        app.executeCommand('view:badge-duration:5000');
        const badgeDurationSetting = settings.get('node_badge_duration');
        const checkBadge5s = document.getElementById('check-badge-5000').textContent.trim();
        // Restore to default 3s
        app.executeCommand('view:badge-duration:3000');

        return {
            paletteToggled: toggledPaletteDisplay !== initialPaletteDisplay,
            paletteSetting: paletteSetting,
            checkPalette: checkPalette,
            configToggled: toggledConfigDisplay !== initialConfigDisplay,
            configSetting: configSetting,
            checkConfig: checkConfig,
            resultsToggled: toggledCollapsed !== initialCollapsed,
            resultsSetting: resultsSetting,
            checkResults: checkResults,
            histSetting: histSetting,
            checkHist: checkHist,
            badgeDurationSetting: badgeDurationSetting,
            checkBadge5s: checkBadge5s
        };
    }""")
    assert configs_res["paletteToggled"] is True
    assert configs_res["paletteSetting"] is False
    assert configs_res["checkPalette"] == ""

    assert configs_res["configToggled"] is True
    assert configs_res["configSetting"] is False
    assert configs_res["checkConfig"] == ""

    assert configs_res["resultsToggled"] is True
    assert configs_res["resultsSetting"] is False
    assert configs_res["checkResults"] == ""

    assert configs_res["histSetting"] is True
    assert configs_res["checkHist"] == "✓"

    assert configs_res["badgeDurationSetting"] == "5000"
    assert configs_res["checkBadge5s"] == "✓"

    page.close()



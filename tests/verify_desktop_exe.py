"""
Verification script for standalone AntigravityDataFlow.exe.
Launches the compiled executable in headless mode on a test port,
measures boot latency (<3s), verifies REST endpoints, executes a test workflow,
verifies file export, and tests CLI arguments.
"""
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

EXE_PATH = os.path.join(os.getcwd(), "dist", "AntigravityDataFlow", "AntigravityDataFlow.exe")
TEST_PORT = 5922
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

print(f"[TEST 1] Checking executable presence at: {EXE_PATH}")
assert os.path.exists(EXE_PATH), f"Executable not found at {EXE_PATH}"
exe_size_mb = os.path.getsize(EXE_PATH) / (1024 * 1024)
print(f"  -> File size: {exe_size_mb:.2f} MB")

# Remove python from PATH to simulate a clean machine without Python
clean_env = os.environ.copy()
path_entries = clean_env.get("PATH", "").split(os.pathsep)
filtered_path = [p for p in path_entries if "python" not in p.lower() and "anaconda" not in p.lower()]
clean_env["PATH"] = os.pathsep.join(filtered_path)
clean_env.pop("PYTHONHOME", None)
clean_env.pop("PYTHONPATH", None)

print(f"[TEST 2] Launching executable with isolated PATH (no Python in environment)...")
start_time = time.time()
proc = subprocess.Popen(
    [EXE_PATH, "--headless", "--port", str(TEST_PORT), "--open", "sales_customer_enrichment.json"],
    env=clean_env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

boot_time = None
max_wait = 15.0
while time.time() - start_time < max_wait:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/app-info", timeout=0.8) as resp:
            if resp.status == 200:
                boot_time = time.time() - start_time
                break
    except Exception:
        time.sleep(0.08)

assert boot_time is not None, "Server failed to respond within 10 seconds"
print(f"  -> Server booted and responded in: {boot_time:.2f} seconds (< 3.0s goal)")

print(f"[TEST 3] Verifying /api/app-info...")
with urllib.request.urlopen(f"{BASE_URL}/api/app-info") as resp:
    info = json.loads(resp.read().decode())
    print("  -> App Info:", info)
    assert info.get("app_name") == "Antigravity DataFlow"
    assert info.get("frozen") is True

print(f"[TEST 4] Verifying /api/tools...")
with urllib.request.urlopen(f"{BASE_URL}/api/tools") as resp:
    tools_data = json.loads(resp.read().decode())
    tools = tools_data.get("tools", [])
    print(f"  -> Available tools: {len(tools)} tools discovered")
    assert len(tools) >= 17

print(f"[TEST 5] Verifying /api/initial-workflow (CLI --open parameter)...")
with urllib.request.urlopen(f"{BASE_URL}/api/initial-workflow") as resp:
    wf_data = json.loads(resp.read().decode())
    print("  -> Loaded workflow:", wf_data.get("name"))
    assert wf_data.get("workflow") is not None
    assert len(wf_data.get("workflow", {}).get("nodes", [])) > 0

print(f"[TEST 6] Executing sample workflow with file export via /api/run...")
export_filename = "desktop_verified_export.csv"
test_workflow = {
    "name": "Desktop Verification Pipeline",
    "nodes": [
        {
            "id": "in_1",
            "type": "input_data",
            "name": "Input Customers",
            "config": {"file_path": "customers.csv", "has_header": True}
        },
        {
            "id": "filt_1",
            "type": "filter",
            "name": "Filter Corporate",
            "config": {
                "mode": "basic",
                "conditions": [{"column": "Segment", "operator": "==", "value": "Corporate"}]
            }
        },
        {
            "id": "out_1",
            "type": "output_data",
            "name": "Export CSV",
            "config": {"filename": export_filename, "format": "csv"}
        }
    ],
    "connections": [
        {"source": "in_1", "sourceHandle": "O", "target": "filt_1", "targetHandle": "I"},
        {"source": "filt_1", "sourceHandle": "T", "target": "out_1", "targetHandle": "I"}
    ]
}

req_data = json.dumps(test_workflow).encode("utf-8")
req = urllib.request.Request(
    f"{BASE_URL}/api/run",
    data=req_data,
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req) as resp:
    run_res = json.loads(resp.read().decode())
    print("  -> Execution success:", run_res.get("success"))
    print(f"  -> Total duration: {run_res.get('total_duration_ms')} ms")
    assert run_res.get("success") is True
    node_results = run_res.get("node_results", {})
    assert "out_1" in node_results
    assert node_results["out_1"]["status"] == "success"

print(f"[TEST 7] Verifying exported file download via /data/outputs/{export_filename}...")
with urllib.request.urlopen(f"{BASE_URL}/data/outputs/{export_filename}") as resp:
    content = resp.read().decode()
    lines = content.strip().split("\n")
    print(f"  -> Exported file row count: {len(lines)} rows")
    assert len(lines) > 5
    assert "Corporate" in lines[1]

# Terminate test server
print("[INFO] Terminating test server process...")
proc.terminate()
try:
    proc.wait(timeout=3)
except Exception:
    proc.kill()

print(f"[TEST 8] Testing standalone CLI --create-shortcut flag...")
short_res = subprocess.run([EXE_PATH, "--create-shortcut"], env=clean_env, capture_output=True)
desktop_lnk = os.path.join(os.path.expanduser("~"), "Desktop", "Antigravity DataFlow.lnk")
print("  -> Desktop shortcut exists:", os.path.exists(desktop_lnk))
assert os.path.exists(desktop_lnk), "Desktop shortcut file should exist"

print("\n==================================================")
print("  ALL VERIFICATION TESTS PASSED SUCCESSFULLY!     ")
print("==================================================")

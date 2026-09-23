"""
Build Script for Antigravity DataFlow Desktop Application.
Packages Python, backend engine, Flask, Waitress, PyWebView, Pandas, OpenPyXL,
static assets, templates, workflows, and sample data into a standalone Windows executable.
"""
import os
import sys
import shutil
import subprocess
import argparse
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from desktop.assets import generate_app_icon


def build_executable(mode="onedir", clean=True):
    print("==================================================")
    print("  Antigravity DataFlow - Desktop Build Automation ")
    print(f"  Packaging mode: {mode}                          ")
    print("==================================================")

    # 1. Ensure icons exist
    ico_path, png_path = generate_app_icon(
        output_dir=os.path.join(BASE_DIR, "assets"),
        static_dir=os.path.join(BASE_DIR, "static")
    )

    # 2. Paths to bundle
    static_dir = os.path.join(BASE_DIR, "static")
    templates_dir = os.path.join(BASE_DIR, "templates")
    data_dir = os.path.join(BASE_DIR, "data")
    workflows_dir = os.path.join(BASE_DIR, "workflows")
    assets_dir = os.path.join(BASE_DIR, "assets")

    # Separator for PyInstaller on Windows is ';'
    sep = ";"

    add_datas = [
        f"{static_dir}{sep}static",
        f"{templates_dir}{sep}templates",
        f"{data_dir}{sep}data",
        f"{workflows_dir}{sep}workflows",
        f"{assets_dir}{sep}assets"
    ]

    # 3. Hidden imports
    hidden_imports = [
        "waitress",
        "openpyxl",
        "openpyxl.cell._writer",
        "pandas",
        "numpy",
        "flask",
        "jinja2",
        "webview",
        "webview.platforms.winforms",
        "pythonnet",
        "clr_loader",
        "werkzeug",
        "werkzeug.serving",
        "werkzeug.datastructures",
        "desktop.diagnostics"
    ]

    # 4. Excluded modules to prevent PyInstaller from pulling in Anaconda's massive scientific ecosystem
    excludes = [
        "scipy",
        "matplotlib",
        "skimage",
        "plotly",
        "bokeh",
        "seaborn",
        "statsmodels",
        "tables",
        "h5py",
        "notebook",
        "nbconvert",
        "nbformat",
        "IPython",
        "ipykernel",
        "jupyter",
        "jupyter_client",
        "jupyter_core",
        "PIL",
        "cv2",
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "keras",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "tkinter",
        "turtle",
        "docutils",
        "sphinx",
        "sympy",
        "pytest",
        "shapely",
        "patsy",
    ]

    # 5. Construct PyInstaller arguments
    main_script = os.path.join(BASE_DIR, "desktop_app.py")
    dist_dir = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")

    if clean:
        print("[INFO] Cleaning prior build artifacts...")
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except Exception as e:
                print(f"[WARN] Could not fully remove build dir: {e}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        main_script,
        "--name=AntigravityDataFlow",
        f"--icon={ico_path}",
        "--windowed",              # Native Windows GUI without cmd prompt window
        "--noconfirm"
    ]

    if mode == "onefile":
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    for d in add_datas:
        cmd.extend(["--add-data", d])

    for h in hidden_imports:
        cmd.extend(["--hidden-import", h])

    for ex in excludes:
        cmd.extend(["--exclude-module", ex])

    print(f"[INFO] Running PyInstaller command...")
    start_time = time.time()
    res = subprocess.run(cmd, cwd=BASE_DIR)

    elapsed = time.time() - start_time
    if res.returncode != 0:
        print(f"[ERROR] PyInstaller failed with exit code {res.returncode}")
        return False

    print(f"[SUCCESS] Build completed in {elapsed:.1f}s!")

    # Verify build output
    if mode == "onedir":
        app_dir = os.path.join(dist_dir, "AntigravityDataFlow")
        exe_path = os.path.join(app_dir, "AntigravityDataFlow.exe")
        
        # Copy 1-click batch helpers into app_dir
        for bat_name in ["Install_DataFlow.bat", "Diagnose_DataFlow.bat", "Launch_DataFlow.bat"]:
            src_bat = os.path.join(BASE_DIR, bat_name)
            if os.path.exists(src_bat):
                shutil.copy2(src_bat, os.path.join(app_dir, bat_name))
            else:
                # Fallback generate if missing
                dst_bat = os.path.join(app_dir, bat_name)
                with open(dst_bat, "w", encoding="utf-8") as f:
                    f.write('@echo off\r\nstart "" "%~dp0AntigravityDataFlow.exe"\r\n')

        # Ensure logs folder exists in app_dir for convenient inspection
        os.makedirs(os.path.join(app_dir, "logs"), exist_ok=True)
        with open(os.path.join(app_dir, "logs", ".gitkeep"), "w", encoding="utf-8") as f:
            f.write("")

        # Copy distribution guide into app_dir
        guide_src = os.path.join(BASE_DIR, "DISTRIBUTION_GUIDE.md")
        if os.path.exists(guide_src):
            shutil.copy2(guide_src, os.path.join(app_dir, "DISTRIBUTION_GUIDE.md"))
            
        # Zip the entire folder for painless transfer
        zip_output = os.path.join(dist_dir, "AntigravityDataFlow_Windows_x64")
        print(f"[INFO] Compressing {app_dir} into {zip_output}.zip...")
        shutil.make_archive(zip_output, "zip", dist_dir, "AntigravityDataFlow")
        zip_file = f"{zip_output}.zip"
        if os.path.exists(zip_file):
            zip_size_mb = os.path.getsize(zip_file) / (1024 * 1024)
            print(f"[OK] Created standalone distribution zip: {zip_file} ({zip_size_mb:.1f} MB)")
    else:
        exe_path = os.path.join(dist_dir, "AntigravityDataFlow.exe")

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[OK] Generated standalone executable: {exe_path} ({size_mb:.1f} MB)")
        return exe_path
    else:
        print(f"[ERROR] Expected executable not found at {exe_path}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity DataFlow Desktop Bundler")
    parser.add_argument("--mode", choices=["onedir", "onefile"], default="onedir", help="Packaging mode (default: onedir)")
    parser.add_argument("--no-clean", action="store_true", help="Do not clean build cache before building")

    args = parser.parse_args()
    build_executable(mode=args.mode, clean=not args.no_clean)

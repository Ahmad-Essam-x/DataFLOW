# Antigravity DataFlow

A visual data-preparation tool for Windows. Build a workflow by dragging tools onto a canvas and connecting them, then run it and inspect the data after every step. It runs on your computer: your files are not uploaded anywhere.

DataFlow is inspired by Alteryx Designer and can open Alteryx `.yxmd` workflows. It is **not** a drop-in replacement: see [Alteryx compatibility](docs/ALTERYX_COMPATIBILITY.md) for what is covered and where results can differ.

## Install

Windows 10 or 11 (64-bit). No Python and no administrator rights needed.

1. Download `AntigravityDataFlow_Setup_<version>.exe` and its `.sha256` file from the team's release location.
2. Run the installer. If Windows shows *"Windows protected your PC"*, choose **More info > Run anyway** (this appears until the installer is code-signed).
3. Start **Antigravity DataFlow** from the Start Menu.

Full instructions, upgrade, uninstall and troubleshooting: [DISTRIBUTION_GUIDE.md](DISTRIBUTION_GUIDE.md).

## Your first workflow (about 10 minutes)

1. **Open a sample.** *File > Workflow Templates...* lists ready-made workflows; open **Customer Sales Analysis**. The canvas shows the tools, connected left to right.
2. **Run it.** Press **Ctrl + Enter** (or the **Run** button in the toolbar). Each tool shows its record count.
3. **Look at the data.** Click any tool. The results panel at the bottom shows its output as a grid, with a profile of every column. Tools with several outputs (for example Filter's True / False, Join's Joined / Left / Right) have a tab per output.
4. **Change something.** Click the Filter tool, change its condition, and run again.
5. **Build your own.** Drag **Input Data** from the palette, choose a CSV or Excel file, then add Select, Filter, Formula, Join, Summarize and so on. Drag from one tool's output dot to the next tool's input dot to connect them. End with **Output Data** to write a file.
6. **Save.** Press **Ctrl + S**. Workflows are plain `.json` files; your work is also auto-saved so it can be recovered after a crash.

## What you can do

- **Bring data in:** CSV, TSV, Excel, Parquet, wildcard sets of files, and (optionally) databases.
- **Prepare it:** select and rename columns, filter, formulas, sort, clean text, find duplicates, sample, number records, running totals.
- **Combine it:** joins (matched / unmatched outputs), union, lookups, append.
- **Reshape it:** summarize, pivot (Cross Tab), unpivot (Transpose), split text, convert dates.
- **Use AI (optional):** *LLM Process* and *Schema Fit* call a language model you choose. A local model (Ollama, LM Studio) keeps everything on your PC; any other host must be approved once, because row values are sent to it.
- **Inspect everything:** data grid, column profiler, charts and an execution log for every tool.
- **Open Alteryx workflows:** *File > Open* a `.yxmd` file. Tools DataFlow cannot run are replaced by a placeholder and listed in a warning: review them before trusting the output.

Every tool is described in the [Tool Reference](docs/TOOL_REFERENCE.md); formulas in the [Formula Reference](docs/FORMULA_REFERENCE.md).

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl + Enter | Run the workflow |
| Ctrl + S / Ctrl + Shift + S | Save / Save as |
| Ctrl + O / Ctrl + N | Open / New workflow |
| Ctrl + T / Ctrl + W | New / close tab |
| Ctrl + F | Search tools |
| Delete | Delete the selected tool or wire |
| Mouse wheel / drag background | Zoom / pan the canvas |
| F1 | Full shortcut list |

## Your data and privacy

- Workflows, settings and logs live in `%LOCALAPPDATA%\AntigravityDataFlow` (back up the `workflows` folder there).
- API keys for AI providers are stored in Windows Credential Manager, never inside workflow files, so workflows are safe to share.
- The app only listens on your own computer (`127.0.0.1`) and rejects requests from web pages.

## Getting help

**Help > Export Support Bundle** creates a zip with logs and version information (no workflows, data or keys) to send to whoever supports the tool. The version is shown in **Help > About**.

## For developers

Running from source, tests, building the installer: [CONTRIBUTING.md](CONTRIBUTING.md). Changes by version: [CHANGELOG.md](CHANGELOG.md).

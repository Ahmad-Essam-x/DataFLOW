import os
import sys
import subprocess

def create_windows_shortcut(target_path, shortcut_path, icon_path=None, working_dir=None, arguments="", description="Antigravity DataFlow - Visual ETL Designer"):
    os.makedirs(os.path.dirname(os.path.abspath(shortcut_path)), exist_ok=True)
    if not working_dir:
        working_dir = os.path.dirname(os.path.abspath(target_path))

    safe_shortcut = shortcut_path.replace('"', '`"')
    safe_target = target_path.replace('"', '`"')
    safe_workdir = working_dir.replace('"', '`"')
    safe_args = arguments.replace('"', '`"')
    safe_desc = description.replace('"', '`"')

    lines = [
        '$WScriptShell = New-Object -ComObject WScript.Shell',
        f'$Shortcut = $WScriptShell.CreateShortcut("{safe_shortcut}")',
        f'$Shortcut.TargetPath = "{safe_target}"',
        f'$Shortcut.WorkingDirectory = "{safe_workdir}"',
        f'$Shortcut.Arguments = "{safe_args}"',
        f'$Shortcut.Description = "{safe_desc}"'
    ]
    if icon_path and os.path.exists(icon_path):
        safe_icon = icon_path.replace('"', '`"')
        lines.append(f'$Shortcut.IconLocation = "{safe_icon},0"')
    lines.append('$Shortcut.Save()')

    ps_script = '; '.join(lines)
    cmd = ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and os.path.exists(shortcut_path):
        return True, shortcut_path
    return False, res.stderr or 'Failed to create shortcut'

def install_desktop_shortcuts(target_exe=None, icon_path=None, app_name="Antigravity DataFlow"):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    arguments = ""
    if not target_exe:
        if getattr(sys, 'frozen', False):
            target_exe = sys.executable
            working_dir = os.path.dirname(sys.executable)
        else:
            target_exe = sys.executable
            working_dir = base_dir
            desktop_script = os.path.join(base_dir, 'desktop_app.py')
            arguments = f'"{desktop_script}"'
    else:
        working_dir = os.path.dirname(os.path.abspath(target_exe))

    if not icon_path or not os.path.exists(icon_path):
        candidates = [
            os.path.join(working_dir, 'assets', 'icon.ico'),
            os.path.join(working_dir, 'icon.ico'),
            os.path.join(base_dir, 'assets', 'icon.ico')
        ]
        if hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, 'assets', 'icon.ico'))
        for c in candidates:
            if c and os.path.exists(c):
                icon_path = c
                break

    user_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    desktop_lnk = os.path.join(user_desktop, f'{app_name}.lnk')

    appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
    start_menu_dir = os.path.join(appdata, r'Microsoft\Windows\Start Menu\Programs')
    start_menu_lnk = os.path.join(start_menu_dir, f'{app_name}.lnk')

    results = {}
    ok1, res1 = create_windows_shortcut(target_exe, desktop_lnk, icon_path, working_dir, arguments)
    results['desktop'] = (ok1, res1)

    ok2, res2 = create_windows_shortcut(target_exe, start_menu_lnk, icon_path, working_dir, arguments)
    results['start_menu'] = (ok2, res2)

    return results

if __name__ == '__main__':
    res = install_desktop_shortcuts()
    print('Desktop shortcut:', res.get('desktop'))
    print('Start menu shortcut:', res.get('start_menu'))

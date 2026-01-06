#!/usr/bin/env python3
"""
OpenCode Session Manager
A web-based GUI tool for managing OpenCode sessions and projects.
Uses FastAPI + Uvicorn for robust HTTP serving.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# =============================================================================
# Dependency Management
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
VENV_DIR = SCRIPT_DIR / "venv"
STATIC_DIR = SCRIPT_DIR / "static"
CONFIG_FILE = STATIC_DIR / "config.txt"

REQUIRED_PACKAGES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
}


def get_venv_python() -> Path:
    """Get the path to the Python executable in the venv."""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def get_venv_pip() -> Path:
    """Get the path to pip in the venv."""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def ensure_venv():
    """Create virtual environment if it doesn't exist."""
    if not VENV_DIR.exists():
        print(f"Creating virtual environment in {VENV_DIR}...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        print("Virtual environment created.")
    return get_venv_python()


def check_and_install_dependencies():
    """Check for missing dependencies and install only what's needed."""
    venv_python = ensure_venv()
    venv_pip = get_venv_pip()
    
    missing_packages = []
    
    print("\nDependency status:")
    print("-" * 40)
    
    for import_name, pip_name in REQUIRED_PACKAGES.items():
        # Check if package is importable in venv
        result = subprocess.run(
            [str(venv_python), "-c", f"import {import_name}"],
            capture_output=True
        )
        if result.returncode != 0:
            missing_packages.append(pip_name)
            print(f"  {import_name:<15} NOT INSTALLED")
        else:
            # Get version if installed
            version_result = subprocess.run(
                [str(venv_python), "-c", f"import {import_name}; print({import_name}.__version__)"],
                capture_output=True,
                text=True
            )
            version = version_result.stdout.strip() if version_result.returncode == 0 else "unknown"
            print(f"  {import_name:<15} OK (v{version})")
    
    print("-" * 40)
    
    if missing_packages:
        print(f"\nInstalling missing dependencies: {', '.join(missing_packages)}")
        subprocess.run(
            [str(venv_pip), "install", "--quiet"] + missing_packages,
            check=True
        )
        print("Dependencies installed.")
    else:
        print("All dependencies satisfied.\n")
    
    return venv_python


def run_in_venv():
    """Re-run this script using the venv Python if not already in venv."""
    # Check if we're already running in the venv
    current_python = Path(sys.executable).resolve()
    venv_python = get_venv_python().resolve()
    
    if current_python == venv_python:
        return False  # Already in venv, continue execution
    
    # Ensure venv exists and has dependencies
    venv_python = check_and_install_dependencies()
    
    # Re-run this script with venv Python
    print("Starting with venv Python...\n")
    
    # Use subprocess on Windows (os.execv doesn't work well there)
    if platform.system() == "Windows":
        result = subprocess.run([str(venv_python), __file__] + sys.argv[1:])
        sys.exit(result.returncode)
    else:
        os.execv(str(venv_python), [str(venv_python), __file__] + sys.argv[1:])


# =============================================================================
# Check if we need to switch to venv (do this before importing FastAPI)
# =============================================================================

if __name__ == "__main__":
    run_in_venv()

# Now we can import FastAPI (we're in the venv)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# =============================================================================
# Global State
# =============================================================================

STORAGE_PATH: Optional[Path] = None
DESKTOP_CACHE_PATH: Optional[Path] = None  # OpenCode Desktop app cache
MAX_UNDO_HISTORY = 10
undo_history: list[dict] = []

# =============================================================================
# Storage Path Detection and Config
# =============================================================================

def get_default_storage_path() -> Optional[Path]:
    """Detect the default OpenCode storage path based on OS."""
    system = platform.system()
    home = Path.home()
    
    if system == "Windows":
        candidates = [
            home / ".local" / "share" / "opencode" / "storage",
            Path(os.environ.get("LOCALAPPDATA", "")) / "opencode" / "storage",
            Path(os.environ.get("APPDATA", "")) / "opencode" / "storage",
        ]
    elif system == "Darwin":
        candidates = [
            home / ".local" / "share" / "opencode" / "storage",
            home / "Library" / "Application Support" / "opencode" / "storage",
        ]
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
        candidates = []
        if xdg_data_home:
            candidates.append(Path(xdg_data_home) / "opencode" / "storage")
        candidates.append(home / ".local" / "share" / "opencode" / "storage")
    
    for path in candidates:
        if path.exists() and path.is_dir():
            return path
    return None


def load_config() -> dict:
    """Load config from config file (supports both legacy text and JSON format)."""
    config = {"storage_path": None, "theme": "default"}
    
    if not CONFIG_FILE.exists():
        return config
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        if not content:
            return config
        
        # Try JSON format first
        if content.startswith("{"):
            try:
                data = json.loads(content)
                if "storage_path" in data:
                    path_str = os.path.expanduser(data["storage_path"])
                    path_str = os.path.expandvars(path_str)
                    path = Path(path_str)
                    if path.exists() and path.is_dir():
                        config["storage_path"] = path
                if "theme" in data:
                    config["theme"] = data["theme"]
                return config
            except json.JSONDecodeError:
                pass
        
        # Legacy text format (just the path)
        path_str = os.path.expanduser(content)
        path_str = os.path.expandvars(path_str)
        path = Path(path_str)
        if path.exists() and path.is_dir():
            config["storage_path"] = path
            
    except (IOError, OSError):
        pass
    
    return config


def save_config(storage_path: Optional[Path] = None, theme: Optional[str] = None):
    """Save config to config file in JSON format."""
    try:
        # Load existing config first
        existing = load_config()
        
        # Update with new values if provided
        if storage_path is not None:
            path_str = str(storage_path)
            home = str(Path.home())
            if path_str.startswith(home):
                path_str = "~" + path_str[len(home):]
            existing["storage_path"] = path_str
        elif existing["storage_path"] is not None:
            path_str = str(existing["storage_path"])
            home = str(Path.home())
            if path_str.startswith(home):
                path_str = "~" + path_str[len(home):]
            existing["storage_path"] = path_str
        
        if theme is not None:
            existing["theme"] = theme
        
        # Convert Path to string for JSON serialization
        save_data = {
            "storage_path": existing["storage_path"] if isinstance(existing["storage_path"], str) else (str(existing["storage_path"]) if existing["storage_path"] else None),
            "theme": existing.get("theme", "default")
        }
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2)
        print(f"Config saved to: {CONFIG_FILE}")
    except (IOError, OSError) as e:
        print(f"Warning: Could not save config: {e}")


def get_desktop_cache_path() -> Optional[Path]:
    """Get the OpenCode Desktop app cache path (default.dat location)."""
    system = platform.system()
    home = Path.home()
    
    if system == "Windows":
        roaming = os.environ.get("APPDATA", "")
        if roaming:
            cache_path = Path(roaming) / "ai.opencode.desktop" / "default.dat"
            if cache_path.exists():
                return cache_path
    elif system == "Darwin":
        cache_path = home / "Library" / "Application Support" / "ai.opencode.desktop" / "default.dat"
        if cache_path.exists():
            return cache_path
    else:
        # Linux - check XDG config
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        cache_path = Path(xdg_config) / "ai.opencode.desktop" / "default.dat"
        if cache_path.exists():
            return cache_path
    
    return None


def initialize_storage_path():
    """Initialize the global storage path from config or auto-detect."""
    global STORAGE_PATH, DESKTOP_CACHE_PATH
    config = load_config()
    STORAGE_PATH = config.get("storage_path")
    if STORAGE_PATH:
        print(f"Loaded storage path from config: {STORAGE_PATH}")
    else:
        STORAGE_PATH = get_default_storage_path()
        if STORAGE_PATH:
            save_config(storage_path=STORAGE_PATH)
            print(f"Auto-detected storage path: {STORAGE_PATH}")
    
    # Also detect Desktop app cache
    DESKTOP_CACHE_PATH = get_desktop_cache_path()
    if DESKTOP_CACHE_PATH:
        print(f"Found OpenCode Desktop cache: {DESKTOP_CACHE_PATH}")


# =============================================================================
# Helper Functions
# =============================================================================

def _now_ms() -> int:
    """Get current timestamp in milliseconds."""
    return int(datetime.now().timestamp() * 1000)


def _find_session_file(session_id: str) -> Tuple[Optional[Path], Optional[str]]:
    """Find a session file by ID across all project directories.
    
    Returns:
        Tuple of (session_file_path, project_id) or (None, None) if not found.
    """
    if not STORAGE_PATH:
        return None, None
    
    session_base = STORAGE_PATH / "session"
    if not session_base.exists():
        return None, None
    
    for project_dir in session_base.iterdir():
        if project_dir.is_dir():
            candidate = project_dir / f"{session_id}.json"
            if candidate.exists():
                return candidate, project_dir.name
    
    return None, None


# =============================================================================
# Backup and Undo Functions
# =============================================================================

def _backup_file(file_path: Path) -> Optional[dict]:
    """Read a file and return its content for backup."""
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return {"path": str(file_path), "content": f.read()}
    except (IOError, OSError):
        return None


def _backup_directory(dir_path: Path) -> list[dict]:
    """Recursively backup all files in a directory."""
    backups = []
    if not dir_path.exists():
        return backups
    try:
        for file_path in dir_path.rglob("*.json"):
            backup = _backup_file(file_path)
            if backup:
                backups.append(backup)
    except (OSError, PermissionError):
        # Handle permission errors or other OS-level issues
        pass
    return backups


def _backup_session_data(session_id: str, project_id: str = None) -> dict:
    """Backup all data for a session."""
    backup = {
        "session_id": session_id,
        "project_id": project_id,
        "session_file": None,
        "messages": [],
        "parts": [],
        "diff_file": None,
        "todo_file": None,
    }
    
    if project_id:
        session_file = STORAGE_PATH / "session" / project_id / f"{session_id}.json"
        backup["session_file"] = _backup_file(session_file)
    else:
        session_file, found_project_id = _find_session_file(session_id)
        if session_file:
            backup["project_id"] = found_project_id
            backup["session_file"] = _backup_file(session_file)
    
    message_dir = STORAGE_PATH / "message" / session_id
    backup["messages"] = _backup_directory(message_dir)
    
    part_base_dir = STORAGE_PATH / "part"
    if message_dir.exists():
        for msg_file in message_dir.glob("*.json"):
            msg_id = msg_file.stem
            part_dir = part_base_dir / msg_id
            backup["parts"].extend(_backup_directory(part_dir))
    
    backup["diff_file"] = _backup_file(STORAGE_PATH / "session_diff" / f"{session_id}.json")
    backup["todo_file"] = _backup_file(STORAGE_PATH / "todo" / f"{session_id}.json")
    
    return backup


def _add_to_undo_history(entry: dict):
    """Add an entry to undo history, maintaining max size."""
    global undo_history
    undo_history.append(entry)
    if len(undo_history) > MAX_UNDO_HISTORY:
        undo_history.pop(0)


def _restore_file(backup: dict):
    """Restore a file from backup."""
    if not backup:
        return
    file_path = Path(backup["path"])
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(backup["content"])


def _delete_session_data(session_id: str):
    """Delete all data associated with a session."""
    message_dir = STORAGE_PATH / "message" / session_id
    if message_dir.exists():
        for msg_file in message_dir.glob("*.json"):
            msg_id = msg_file.stem
            part_dir = STORAGE_PATH / "part" / msg_id
            if part_dir.exists():
                shutil.rmtree(str(part_dir))
    
    if message_dir.exists():
        shutil.rmtree(str(message_dir))
    
    diff_file = STORAGE_PATH / "session_diff" / f"{session_id}.json"
    if diff_file.exists():
        diff_file.unlink()
    
    todo_file = STORAGE_PATH / "todo" / f"{session_id}.json"
    if todo_file.exists():
        todo_file.unlink()


def _cleanup_desktop_cache_sessions(session_ids: list[str]):
    """Remove session entries from OpenCode Desktop cache."""
    if not DESKTOP_CACHE_PATH or not DESKTOP_CACHE_PATH.exists():
        return
    
    try:
        with open(DESKTOP_CACHE_PATH, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        modified = False
        session_id_set = set(session_ids)
        
        # Remove keys that reference deleted sessions
        keys_to_remove = []
        for key in list(cache_data.keys()):
            if ".v1" in key or ".v2" in key:
                for session_id in session_id_set:
                    if session_id in key:
                        keys_to_remove.append(key)
                        break
        
        for key in keys_to_remove:
            del cache_data[key]
            modified = True
        
        # Clean notification list
        if "notification.v1" in cache_data:
            try:
                notif_data = json.loads(cache_data["notification.v1"])
                original_count = len(notif_data.get("list", []))
                notif_data["list"] = [
                    n for n in notif_data.get("list", [])
                    if n.get("session", "") not in session_id_set
                ]
                new_count = len(notif_data.get("list", []))
                if new_count < original_count:
                    cache_data["notification.v1"] = json.dumps(notif_data)
                    modified = True
            except (json.JSONDecodeError, TypeError):
                pass
        
        if modified:
            with open(DESKTOP_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
    except (json.JSONDecodeError, IOError):
        pass


def _cleanup_desktop_cache_by_worktree(worktree: str):
    """Remove all Desktop cache entries for a worktree path (project)."""
    if not DESKTOP_CACHE_PATH or not DESKTOP_CACHE_PATH.exists() or not worktree:
        return
    
    import base64
    
    try:
        with open(DESKTOP_CACHE_PATH, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Encode the worktree path to base64 (OpenCode Desktop uses this as key prefix)
        worktree_b64 = base64.b64encode(worktree.encode('utf-8')).decode('utf-8').rstrip('=')
        
        modified = False
        keys_to_remove = []
        
        # Find all keys that start with this worktree's base64 encoding
        for key in list(cache_data.keys()):
            if key.startswith(worktree_b64):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del cache_data[key]
            modified = True
        
        # Also clean notification list for this directory
        if "notification.v1" in cache_data:
            try:
                notif_data = json.loads(cache_data["notification.v1"])
                original_count = len(notif_data.get("list", []))
                notif_data["list"] = [
                    n for n in notif_data.get("list", [])
                    if n.get("directory", "") != worktree
                ]
                new_count = len(notif_data.get("list", []))
                if new_count < original_count:
                    cache_data["notification.v1"] = json.dumps(notif_data)
                    modified = True
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Clean layout sessionTabs (check multiple versions)
        for layout_key in ["layout.v4", "layout.v6"]:
            if layout_key in cache_data:
                try:
                    layout_data = json.loads(cache_data[layout_key])
                    if "sessionTabs" in layout_data:
                        original_tabs = layout_data["sessionTabs"]
                        layout_data["sessionTabs"] = {
                            k: v for k, v in original_tabs.items()
                            if not k.startswith(worktree_b64)
                        }
                        if len(layout_data["sessionTabs"]) < len(original_tabs):
                            cache_data[layout_key] = json.dumps(layout_data)
                            modified = True
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Remove project from server.v3 projects list
        if "server.v3" in cache_data:
            try:
                server_data = json.loads(cache_data["server.v3"])
                if "projects" in server_data and "local" in server_data["projects"]:
                    original_projects = server_data["projects"]["local"]
                    # Filter out the project with matching worktree
                    server_data["projects"]["local"] = [
                        p for p in original_projects
                        if p.get("worktree", "") != worktree
                    ]
                    if len(server_data["projects"]["local"]) < len(original_projects):
                        cache_data["server.v3"] = json.dumps(server_data)
                        modified = True
            except (json.JSONDecodeError, TypeError):
                pass
        
        if modified:
            with open(DESKTOP_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
    except (json.JSONDecodeError, IOError):
        pass


def _migrate_desktop_cache_worktree(old_worktree: str, new_worktree: str):
    """Migrate Desktop cache entries from old worktree path to new worktree path."""
    if not DESKTOP_CACHE_PATH or not DESKTOP_CACHE_PATH.exists():
        return
    if not old_worktree or not new_worktree or old_worktree == new_worktree:
        return
    
    import base64
    
    try:
        with open(DESKTOP_CACHE_PATH, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Encode paths to base64
        old_b64 = base64.b64encode(old_worktree.encode('utf-8')).decode('utf-8').rstrip('=')
        new_b64 = base64.b64encode(new_worktree.encode('utf-8')).decode('utf-8').rstrip('=')
        
        modified = False
        keys_to_rename = {}
        
        # Find all keys that start with old worktree's base64 and rename them
        for key in list(cache_data.keys()):
            if key.startswith(old_b64):
                new_key = new_b64 + key[len(old_b64):]
                keys_to_rename[key] = new_key
        
        for old_key, new_key in keys_to_rename.items():
            cache_data[new_key] = cache_data.pop(old_key)
            modified = True
        
        # Update notification list directories
        if "notification.v1" in cache_data:
            try:
                notif_data = json.loads(cache_data["notification.v1"])
                notif_modified = False
                for notif in notif_data.get("list", []):
                    if notif.get("directory") == old_worktree:
                        notif["directory"] = new_worktree
                        notif_modified = True
                if notif_modified:
                    cache_data["notification.v1"] = json.dumps(notif_data)
                    modified = True
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Update layout sessionTabs (check multiple versions)
        for layout_key in ["layout.v4", "layout.v6"]:
            if layout_key in cache_data:
                try:
                    layout_data = json.loads(cache_data[layout_key])
                    if "sessionTabs" in layout_data:
                        new_tabs = {}
                        tabs_modified = False
                        for key, value in layout_data["sessionTabs"].items():
                            if key.startswith(old_b64):
                                new_key = new_b64 + key[len(old_b64):]
                                new_tabs[new_key] = value
                                tabs_modified = True
                            else:
                                new_tabs[key] = value
                        if tabs_modified:
                            layout_data["sessionTabs"] = new_tabs
                            cache_data[layout_key] = json.dumps(layout_data)
                            modified = True
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Update server.v3 projects list worktree path
        if "server.v3" in cache_data:
            try:
                server_data = json.loads(cache_data["server.v3"])
                if "projects" in server_data and "local" in server_data["projects"]:
                    projects_modified = False
                    for project in server_data["projects"]["local"]:
                        if project.get("worktree") == old_worktree:
                            project["worktree"] = new_worktree
                            projects_modified = True
                    if projects_modified:
                        cache_data["server.v3"] = json.dumps(server_data)
                        modified = True
            except (json.JSONDecodeError, TypeError):
                pass
        
        if modified:
            with open(DESKTOP_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
    except (json.JSONDecodeError, IOError):
        pass


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(title="OpenCode Session Manager")

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/favicon.ico")
async def favicon():
    """Return a simple SVG favicon with unicode character."""
    # Unicode nerd emoji: 🤓
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-size="80">🤓</text>
    </svg>'''
    return Response(content=svg.encode('utf-8'), media_type="image/svg+xml")


@app.post("/api/shutdown")
async def shutdown():
    """Shutdown the application."""
    def shutdown_server():
        time.sleep(0.5)  # Give time for response to be sent
        os._exit(0)
    
    threading.Thread(target=shutdown_server, daemon=True).start()
    return {"message": "Shutting down..."}


@app.get("/api/storage-path")
async def get_storage_path():
    return {
        "path": str(STORAGE_PATH) if STORAGE_PATH else "",
        "valid": STORAGE_PATH is not None and STORAGE_PATH.exists()
    }


@app.post("/api/storage-path")
async def set_storage_path(request: Request):
    global STORAGE_PATH
    data = await request.json()
    path = Path(data.get("path", ""))
    
    if not path.exists():
        raise HTTPException(status_code=400, detail="Path does not exist")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    
    expected_dirs = ["session", "project", "message"]
    if not all((path / d).exists() for d in expected_dirs):
        raise HTTPException(
            status_code=400,
            detail="Invalid OpenCode storage directory. Expected 'session', 'project', and 'message' subdirectories."
        )
    
    STORAGE_PATH = path
    save_config(storage_path=path)
    return {"path": str(STORAGE_PATH), "valid": True}


@app.get("/api/theme")
async def get_theme():
    """Get the current theme from config."""
    config = load_config()
    return {"theme": config.get("theme", "default")}


@app.post("/api/theme")
async def set_theme(request: Request):
    """Set and save the theme to config."""
    data = await request.json()
    theme = data.get("theme", "default")
    
    valid_themes = ["default", "glitch", "midnight", "forest"]
    if theme not in valid_themes:
        raise HTTPException(status_code=400, detail=f"Invalid theme. Must be one of: {', '.join(valid_themes)}")
    
    save_config(theme=theme)
    return {"theme": theme}


@app.get("/api/browse")
async def browse_folder():
    system = platform.system()
    
    try:
        if system == "Windows":
            script = '''
            Add-Type -AssemblyName System.Windows.Forms
            $form = New-Object System.Windows.Forms.Form
            $form.TopMost = $true
            $form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
            $form.ShowInTaskbar = $false
            $form.Show()
            $form.Activate()
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = "Select OpenCode storage folder"
            $dialog.ShowNewFolderButton = $false
            $result = $dialog.ShowDialog($form)
            $form.Close()
            if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
                $dialog.SelectedPath
            }
            '''
            result = subprocess.run(["powershell", "-Command", script], capture_output=True, text=True)
            selected_path = result.stdout.strip()
            if selected_path:
                return {"path": selected_path}
        elif system == "Darwin":
            script = 'choose folder with prompt "Select OpenCode storage folder"'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip().replace("alias ", "").replace(":", "/")
                if path.startswith("Macintosh HD"):
                    path = path[12:]
                return {"path": path}
        else:
            for cmd in [["zenity", "--file-selection", "--directory"], ["kdialog", "--getexistingdirectory"]]:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        return {"path": result.stdout.strip()}
                except FileNotFoundError:
                    continue
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return {"path": ""}


def _is_global_project(data: dict) -> bool:
    """Check if a project is the global/General project."""
    return data.get("id") == "global"


def _project_needs_fix(data: dict) -> bool:
    """Check if a project is missing required OpenCode fields or git setup.
    
    Excludes the 'global' project since OpenCode manages it specially.
    """
    # Skip the global project - OpenCode reformats it automatically
    if _is_global_project(data):
        return False
    
    # Check if project ID is not a valid git commit hash (40 hex chars)
    project_id = data.get("id", "")
    if len(project_id) != 40 or not all(c in "0123456789abcdef" for c in project_id.lower()):
        return True
    
    if "vcs" not in data or data.get("vcs") != "git":
        return True
    if "icon" not in data or not isinstance(data.get("icon"), dict):
        return True
    if "sandboxes" not in data:
        return True
    return False


@app.get("/api/projects")
async def get_projects(search: str = ""):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    projects = []
    project_dir = STORAGE_PATH / "project"
    session_dir = STORAGE_PATH / "session"
    
    if not project_dir.exists():
        return {"projects": []}
    
    for project_file in project_dir.glob("*.json"):
        try:
            with open(project_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            project_id = project_file.stem
            name = data.get("name", project_id)
            worktree = data.get("worktree", "")
            
            if search and search.lower() not in name.lower() and search.lower() not in worktree.lower():
                continue
            
            project_session_dir = session_dir / project_id
            session_count = len(list(project_session_dir.glob("*.json"))) if project_session_dir.exists() else 0
            
            projects.append({
                "id": project_id,
                "name": name,
                "worktree": worktree,
                "session_count": session_count,
                "created": data.get("time", {}).get("created"),
                "updated": data.get("time", {}).get("updated"),
                "needs_fix": _project_needs_fix(data),
            })
        except (json.JSONDecodeError, IOError):
            continue
    
    projects.sort(key=lambda x: x.get("updated") or 0, reverse=True)
    return {"projects": projects}


@app.post("/api/projects/fix-all")
async def fix_all_projects():
    """Fix all projects that are missing required OpenCode fields or git setup.
    
    This will:
    1. Initialize git repos for non-git worktrees
    2. Rename project files to use the correct git root commit ID
    3. Move session directories to match new project IDs
    4. Add missing OpenCode fields
    
    Excludes the 'global' project since OpenCode manages it specially.
    """
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    project_dir = STORAGE_PATH / "project"
    session_base_dir = STORAGE_PATH / "session"
    if not project_dir.exists():
        return {"fixed": [], "count": 0, "errors": []}
    
    fixed = []
    errors = []
    
    for project_file in list(project_dir.glob("*.json")):
        try:
            with open(project_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Skip the global project (empty or "/" worktree)
            if _is_global_project(data):
                continue
        except (json.JSONDecodeError, IOError):
            errors.append({"file": project_file.stem, "error": "Failed to read project file"})
            continue
        
        try:
            old_project_id = project_file.stem
            project_name = data.get("name", old_project_id)
            worktree = data.get("worktree", "")
            needs_fix = False
            
            # Check if project ID needs to be updated (not a valid 40-char git hash)
            is_valid_git_id = len(old_project_id) == 40 and all(c in "0123456789abcdef" for c in old_project_id.lower())
            
            if not is_valid_git_id and worktree and Path(worktree).exists():
                # Ensure git repo exists and get proper project ID
                success, new_project_id, error = _ensure_git_repo(worktree)
                
                if success and new_project_id and new_project_id != old_project_id:
                    # Check if target project file already exists
                    new_project_file = project_dir / f"{new_project_id}.json"
                    if new_project_file.exists():
                        errors.append({
                            "file": old_project_id,
                            "error": f"Cannot migrate: project with ID {new_project_id} already exists"
                        })
                        continue
                    
                    # Update project data with new ID
                    data["id"] = new_project_id
                    data["vcs"] = "git"
                    
                    # Move session directory if it exists
                    old_session_dir = session_base_dir / old_project_id
                    new_session_dir = session_base_dir / new_project_id
                    if old_session_dir.exists():
                        if new_session_dir.exists():
                            # Merge sessions into existing directory
                            for session_file in old_session_dir.glob("*.json"):
                                shutil.move(str(session_file), str(new_session_dir / session_file.name))
                            old_session_dir.rmdir()
                        else:
                            shutil.move(str(old_session_dir), str(new_session_dir))
                    
                    # Write new project file and delete old one
                    _ensure_project_fields(data)
                    data["time"]["updated"] = _now_ms()
                    with open(new_project_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    project_file.unlink()
                    
                    fixed.append(f"{project_name} (migrated to git ID)")
                    continue
                elif not success:
                    errors.append({"file": old_project_id, "error": error or "Failed to ensure git repo"})
                    continue
            
            # Just fix missing fields if ID is already valid
            if _ensure_project_fields(data):
                needs_fix = True
            
            if needs_fix:
                data["time"]["updated"] = _now_ms()
                with open(project_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                fixed.append(project_name)
                
        except Exception as e:
            errors.append({"file": project_file.stem, "error": str(e)})
    
    return {"fixed": fixed, "count": len(fixed), "errors": errors}


@app.get("/api/projects/{project_id}/sessions")
async def get_sessions(project_id: str, search: str = ""):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    sessions = []
    session_dir = STORAGE_PATH / "session" / project_id
    
    if not session_dir.exists():
        return {"sessions": []}
    
    for session_file in session_dir.glob("*.json"):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            session_id = session_file.stem
            title = data.get("title", session_id)
            
            if search and search.lower() not in title.lower() and search.lower() not in session_id.lower():
                continue
            
            file_size = session_file.stat().st_size
            
            sessions.append({
                "id": session_id,
                "title": title,
                "created": data.get("time", {}).get("created"),
                "updated": data.get("time", {}).get("updated"),
                "size": file_size,
            })
        except (json.JSONDecodeError, IOError):
            continue
    
    sessions.sort(key=lambda x: x.get("updated") or 0, reverse=True)
    return {"sessions": sessions}


@app.get("/api/sessions/search")
async def search_all_sessions(search: str = ""):
    """Search sessions across all projects.
    
    Returns sessions matching the search term from all projects,
    along with project information for each session.
    """
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    if not search:
        return {"sessions": []}
    
    sessions = []
    session_base_dir = STORAGE_PATH / "session"
    project_dir = STORAGE_PATH / "project"
    
    if not session_base_dir.exists():
        return {"sessions": []}
    
    # Load all projects for name lookup
    project_map = {}
    if project_dir.exists():
        for project_file in project_dir.glob("*.json"):
            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                project_id = project_file.stem
                project_map[project_id] = {
                    "id": project_id,
                    "name": data.get("name", project_id),
                    "worktree": data.get("worktree", "")
                }
            except (json.JSONDecodeError, IOError):
                continue
    
    # Search through all project session folders
    search_lower = search.lower()
    for project_folder in session_base_dir.iterdir():
        if not project_folder.is_dir():
            continue
        
        project_id = project_folder.name
        project_info = project_map.get(project_id, {
            "id": project_id,
            "name": project_id,
            "worktree": ""
        })
        
        for session_file in project_folder.glob("*.json"):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                session_id = session_file.stem
                title = data.get("title", session_id)
                
                # Search in title, session_id, and project name
                if (search_lower not in title.lower() and 
                    search_lower not in session_id.lower() and
                    search_lower not in project_info["name"].lower()):
                    continue
                
                file_size = session_file.stat().st_size
                
                sessions.append({
                    "id": session_id,
                    "title": title,
                    "created": data.get("time", {}).get("created"),
                    "updated": data.get("time", {}).get("updated"),
                    "size": file_size,
                    "project_id": project_id,
                    "project_name": project_info["name"],
                })
            except (json.JSONDecodeError, IOError):
                continue
    
    sessions.sort(key=lambda x: x.get("updated") or 0, reverse=True)
    return {"sessions": sessions}


@app.post("/api/projects/{project_id}/check-repair")
async def check_repair_project(project_id: str):
    """Check and repair a project and its sessions.
    
    This will:
    1. Check if project needs git initialization and do it if needed
    2. Migrate project to correct git-based ID if needed
    3. Fix all session files to have correct projectID field
    4. Move sessions from wrong folders to correct folder
    5. Add missing OpenCode fields to project
    
    Returns a report of all issues found and fixed.
    """
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    project_dir = STORAGE_PATH / "project"
    session_base_dir = STORAGE_PATH / "session"
    project_file = project_dir / f"{project_id}.json"
    
    if not project_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    
    report = {
        "project_id": project_id,
        "issues_found": [],
        "fixes_applied": [],
        "errors": [],
        "new_project_id": None,
    }
    
    try:
        with open(project_file, "r", encoding="utf-8") as f:
            project_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read project file: {e}")
    
    # Skip global project
    if _is_global_project(project_data):
        report["issues_found"].append("This is the global project - skipping")
        return report
    
    project_name = project_data.get("name", project_id)
    worktree = project_data.get("worktree", "")
    old_project_id = project_id
    new_project_id = project_id
    
    # Check if project ID is valid (40-char git hash)
    is_valid_git_id = len(project_id) == 40 and all(c in "0123456789abcdef" for c in project_id.lower())
    
    # Step 1: Check git repo and migrate project ID if needed
    if not is_valid_git_id:
        report["issues_found"].append(f"Project ID '{project_id}' is not a valid git commit hash")
        
        if worktree and Path(worktree).exists():
            success, git_project_id, error = _ensure_git_repo(worktree)
            
            if success and git_project_id:
                new_project_id = git_project_id
                report["new_project_id"] = new_project_id
                
                # Check if target already exists
                new_project_file = project_dir / f"{new_project_id}.json"
                if new_project_file.exists() and new_project_id != old_project_id:
                    report["errors"].append(f"Cannot migrate: project with ID {new_project_id} already exists")
                    return report
                
                # Update project data
                project_data["id"] = new_project_id
                project_data["vcs"] = "git"
                _ensure_project_fields(project_data)
                project_data["time"]["updated"] = _now_ms()
                
                # Write new project file
                with open(new_project_file, "w", encoding="utf-8") as f:
                    json.dump(project_data, f, indent=2)
                
                # Delete old project file if different
                if old_project_id != new_project_id:
                    project_file.unlink()
                    report["fixes_applied"].append(f"Migrated project ID: {old_project_id} -> {new_project_id}")
                
                # Move session directory
                old_session_dir = session_base_dir / old_project_id
                new_session_dir = session_base_dir / new_project_id
                
                if old_session_dir.exists() and old_project_id != new_project_id:
                    if not new_session_dir.exists():
                        new_session_dir.mkdir(parents=True, exist_ok=True)
                    
                    for session_file in old_session_dir.glob("*.json"):
                        target = new_session_dir / session_file.name
                        shutil.move(str(session_file), str(target))
                        report["fixes_applied"].append(f"Moved session file: {session_file.name}")
                    
                    # Remove old directory if empty
                    if not any(old_session_dir.iterdir()):
                        old_session_dir.rmdir()
                        report["fixes_applied"].append(f"Removed empty session directory: {old_project_id}")
            else:
                report["errors"].append(f"Failed to initialize git: {error}")
                return report
        else:
            report["errors"].append(f"Worktree path does not exist: {worktree}")
            return report
    else:
        # Just ensure project fields are correct
        if _ensure_project_fields(project_data):
            project_data["time"]["updated"] = _now_ms()
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2)
            report["fixes_applied"].append("Added missing OpenCode fields to project")
    
    # Step 2: Fix session files in the project's session directory
    session_dir = session_base_dir / new_project_id
    if session_dir.exists():
        for session_file in session_dir.glob("*.json"):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                
                needs_save = False
                session_project_id = session_data.get("projectID", "")
                session_directory = session_data.get("directory", "")
                
                # Fix projectID if wrong
                if session_project_id != new_project_id:
                    report["issues_found"].append(
                        f"Session {session_file.stem} has wrong projectID: {session_project_id}"
                    )
                    session_data["projectID"] = new_project_id
                    report["fixes_applied"].append(
                        f"Fixed session {session_file.stem} projectID: {session_project_id} -> {new_project_id}"
                    )
                    needs_save = True
                
                # Fix directory if it doesn't match project worktree
                if worktree and session_directory != worktree:
                    report["issues_found"].append(
                        f"Session {session_file.stem} has wrong directory: {session_directory}"
                    )
                    session_data["directory"] = worktree
                    report["fixes_applied"].append(
                        f"Fixed session {session_file.stem} directory: {session_directory} -> {worktree}"
                    )
                    needs_save = True
                
                if needs_save:
                    session_data["time"]["updated"] = _now_ms()
                    with open(session_file, "w", encoding="utf-8") as f:
                        json.dump(session_data, f, indent=2)
                        
            except (json.JSONDecodeError, IOError) as e:
                report["errors"].append(f"Failed to process session {session_file.stem}: {e}")
    
    # Step 3: Look for orphaned sessions in other directories that belong to this project
    # (sessions with projectID matching old_project_id or new_project_id but in wrong folder)
    for other_dir in session_base_dir.iterdir():
        if not other_dir.is_dir():
            continue
        if other_dir.name == new_project_id:
            continue  # Already processed
        
        for session_file in other_dir.glob("*.json"):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                
                session_project_id = session_data.get("projectID", "")
                
                # Check if this session belongs to our project
                if session_project_id in (old_project_id, new_project_id):
                    report["issues_found"].append(
                        f"Found orphaned session {session_file.stem} in folder {other_dir.name}"
                    )
                    
                    # Fix projectID, directory, and move to correct folder
                    session_data["projectID"] = new_project_id
                    if worktree:
                        session_data["directory"] = worktree
                    session_data["time"]["updated"] = _now_ms()
                    
                    # Ensure target directory exists
                    if not session_dir.exists():
                        session_dir.mkdir(parents=True, exist_ok=True)
                    
                    target_file = session_dir / session_file.name
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(session_data, f, indent=2)
                    
                    session_file.unlink()
                    report["fixes_applied"].append(
                        f"Moved orphaned session {session_file.stem} from {other_dir.name} to {new_project_id}"
                    )
            except (json.JSONDecodeError, IOError):
                continue  # Skip files we can't read
    
    # Step 4: Ensure project is registered in Desktop cache (server.v3.projects.local)
    if worktree and DESKTOP_CACHE_PATH and DESKTOP_CACHE_PATH.exists():
        try:
            with open(DESKTOP_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            cache_modified = False
            
            # Check server.v3 projects list
            if "server.v3" in cache_data:
                try:
                    server_data = json.loads(cache_data["server.v3"])
                    if "projects" not in server_data:
                        server_data["projects"] = {"local": []}
                    if "local" not in server_data["projects"]:
                        server_data["projects"]["local"] = []
                    
                    # Check if worktree is in the projects list
                    worktree_exists = any(
                        p.get("worktree") == worktree 
                        for p in server_data["projects"]["local"]
                    )
                    
                    if not worktree_exists:
                        report["issues_found"].append(
                            f"Project not found in Desktop cache server.v3.projects.local"
                        )
                        # Add the project to the list
                        server_data["projects"]["local"].append({
                            "worktree": worktree,
                            "expanded": True
                        })
                        cache_data["server.v3"] = json.dumps(server_data)
                        cache_modified = True
                        report["fixes_applied"].append(
                            f"Added project to Desktop cache server.v3.projects.local"
                        )
                except (json.JSONDecodeError, TypeError) as e:
                    report["errors"].append(f"Failed to parse server.v3 cache: {e}")
            else:
                # server.v3 doesn't exist, create it
                report["issues_found"].append("Desktop cache server.v3 key not found")
                server_data = {
                    "list": [],
                    "projects": {
                        "local": [{"worktree": worktree, "expanded": True}]
                    }
                }
                cache_data["server.v3"] = json.dumps(server_data)
                cache_modified = True
                report["fixes_applied"].append("Created server.v3 in Desktop cache with project")
            
            if cache_modified:
                with open(DESKTOP_CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f)
        except (json.JSONDecodeError, IOError) as e:
            report["errors"].append(f"Failed to update Desktop cache: {e}")
    
    return report


@app.get("/api/sessions/{session_id}/preview")
async def get_session_preview(session_id: str):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    message_dir = STORAGE_PATH / "message" / session_id
    
    if not message_dir.exists():
        return {"messages": [], "error": "No messages found"}
    
    messages = []
    message_files = []
    
    for msg_file in message_dir.glob("*.json"):
        try:
            with open(msg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            message_files.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    
    message_files.sort(key=lambda x: x.get("time", {}).get("created", 0))
    
    for msg in message_files:
        role = msg.get("role", "unknown")
        message_id = msg.get("id", "")
        content_parts = []
        
        message_part_dir = STORAGE_PATH / "part" / message_id
        if message_part_dir.exists():
            part_files = []
            for part_file in message_part_dir.glob("*.json"):
                try:
                    with open(part_file, "r", encoding="utf-8") as f:
                        part_data = json.load(f)
                    part_files.append(part_data)
                except (json.JSONDecodeError, IOError):
                    continue
            
            part_files.sort(key=lambda x: x.get("id", ""))
            
            for part_data in part_files:
                part_type = part_data.get("type", "")
                if part_type == "text":
                    text = part_data.get("text", "")
                    if text:
                        content_parts.append(text)
                elif part_type == "tool-invocation":
                    tool_name = part_data.get("toolInvocation", {}).get("toolName", "unknown")
                    content_parts.append(f"[Tool: {tool_name}]")
                elif part_type == "tool-result":
                    content_parts.append("[Tool Result]")
        
        if not content_parts:
            content = msg.get("content", "")
            if content:
                content_parts.append(content)
        
        if content_parts:
            messages.append({
                "role": role,
                "content": "\n".join(content_parts),
                "created": msg.get("time", {}).get("created"),
            })
    
    return {"messages": messages}


@app.get("/api/sessions/{session_id}/stats")
async def get_session_stats(session_id: str):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    stats = {
        "session_id": session_id,
        "message_count": 0,
        "total_size": 0,
        "created": None,
        "updated": None,
        "has_diffs": False,
        "has_todos": False,
    }
    
    session_file, _ = _find_session_file(session_id)
    
    if session_file:
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            stats["created"] = data.get("time", {}).get("created")
            stats["updated"] = data.get("time", {}).get("updated")
            stats["total_size"] += session_file.stat().st_size
        except (json.JSONDecodeError, IOError):
            pass
    
    message_dir = STORAGE_PATH / "message" / session_id
    if message_dir.exists():
        message_files = list(message_dir.glob("*.json"))
        stats["message_count"] = len(message_files)
        stats["total_size"] += sum(f.stat().st_size for f in message_files)
    
    diff_file = STORAGE_PATH / "session_diff" / f"{session_id}.json"
    stats["has_diffs"] = diff_file.exists()
    if diff_file.exists():
        stats["total_size"] += diff_file.stat().st_size
    
    todo_file = STORAGE_PATH / "todo" / f"{session_id}.json"
    stats["has_todos"] = todo_file.exists()
    if todo_file.exists():
        stats["total_size"] += todo_file.stat().st_size
    
    return stats


def _get_git_root_commit(worktree: str) -> Optional[str]:
    """Get the root commit hash of a git repository (used as OpenCode project ID)."""
    try:
        git_dir = Path(worktree) / ".git"
        if not git_dir.exists():
            return None
        
        result = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "--all"],
            cwd=worktree,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None
        
        # Get all root commits, sort them, and take the first one (matches OpenCode behavior)
        roots = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        if not roots:
            return None
        
        roots.sort()
        return roots[0]
    except Exception:
        return None


def _ensure_git_repo(worktree: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Ensure a directory is a git repository with at least one commit.
    
    If not a git repo, initializes one and creates an initial commit.
    
    Returns:
        Tuple of (success, project_id, error_message)
    """
    if not worktree or not Path(worktree).exists():
        return False, None, "Worktree path does not exist"
    
    git_dir = Path(worktree) / ".git"
    
    try:
        # Check if already a git repo
        if not git_dir.exists():
            # Initialize git repository
            result = subprocess.run(
                ["git", "init"],
                cwd=worktree,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, None, f"Failed to initialize git: {result.stderr}"
        
        # Check if there are any commits
        project_id = _get_git_root_commit(worktree)
        
        if not project_id:
            # No commits yet - create an initial commit
            # First, configure git user if not set (required for commit)
            subprocess.run(
                ["git", "config", "user.email", "opencode@local"],
                cwd=worktree,
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "OpenCode Session Manager"],
                cwd=worktree,
                capture_output=True
            )
            
            # Create .gitkeep if directory is empty (git won't commit empty dirs)
            gitkeep = Path(worktree) / ".gitkeep"
            if not any(Path(worktree).iterdir()) or all(p.name == ".git" for p in Path(worktree).iterdir()):
                gitkeep.touch()
            
            # Stage all files and create initial commit
            subprocess.run(
                ["git", "add", "-A"],
                cwd=worktree,
                capture_output=True
            )
            
            result = subprocess.run(
                ["git", "commit", "-m", "Initial commit (created by OpenCode Session Manager)", "--allow-empty"],
                cwd=worktree,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, None, f"Failed to create initial commit: {result.stderr}"
            
            # Now get the root commit
            project_id = _get_git_root_commit(worktree)
            if not project_id:
                return False, None, "Failed to get root commit after initialization"
        
        return True, project_id, None
    
    except Exception as e:
        return False, None, str(e)


@app.post("/api/projects")
async def create_project(request: Request):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    data = await request.json()
    name = data.get("name", "").strip()
    worktree = data.get("worktree", "").strip()
    
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    
    if not worktree:
        raise HTTPException(status_code=400, detail="Worktree path is required for OpenCode compatibility")
    
    if not Path(worktree).exists():
        raise HTTPException(status_code=400, detail="Worktree path does not exist")
    
    project_dir = STORAGE_PATH / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure directory is a git repo (initialize if needed) and get project ID
    success, project_id, error = _ensure_git_repo(worktree)
    if not success or not project_id:
        raise HTTPException(status_code=400, detail=error or "Failed to initialize git repository")
    
    # Check if project already exists
    if (project_dir / f"{project_id}.json").exists():
        raise HTTPException(
            status_code=400,
            detail="A project for this git repository already exists. The project ID is based on the git root commit."
        )
    
    # Create project data with all OpenCode-required fields
    now = _now_ms()
    project_data = {
        "id": project_id,
        "name": name,
        "worktree": worktree,
        "vcs": "git",
        "time": {
            "created": now,
            "updated": now
        },
        "icon": {
            "color": "cyan",
            "url": ""
        },
        "sandboxes": []
    }
    
    # Write project file
    project_file = project_dir / f"{project_id}.json"
    with open(project_file, "w", encoding="utf-8") as f:
        json.dump(project_data, f, indent=2)
    
    # Create session directory for the project
    session_dir = STORAGE_PATH / "session" / project_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Add to undo history
    _add_to_undo_history({
        "type": "create_project",
        "description": f"Create project '{name}'",
        "project_id": project_id,
        "file_path": str(project_file),
        "session_dir": str(session_dir)
    })
    
    return {"success": True, "project_id": project_id, "name": name}


def _ensure_project_fields(project_data: dict) -> bool:
    """Ensure project has all OpenCode-required fields. Returns True if changes were made."""
    changed = False
    
    # Ensure 'vcs' field exists
    if "vcs" not in project_data:
        worktree = project_data.get("worktree", "")
        if worktree and Path(worktree).exists() and (Path(worktree) / ".git").exists():
            project_data["vcs"] = "git"
        else:
            project_data["vcs"] = ""
        changed = True
    
    # Ensure 'icon' field exists with required structure
    if "icon" not in project_data or not isinstance(project_data["icon"], dict):
        project_data["icon"] = {"color": "cyan", "url": ""}
        changed = True
    else:
        if "color" not in project_data["icon"]:
            project_data["icon"]["color"] = "cyan"
            changed = True
        if "url" not in project_data["icon"]:
            project_data["icon"]["url"] = ""
            changed = True
    
    # Ensure 'sandboxes' field exists
    if "sandboxes" not in project_data:
        project_data["sandboxes"] = []
        changed = True
    
    # Ensure 'time' field exists with required structure
    if "time" not in project_data or not isinstance(project_data["time"], dict):
        now = _now_ms()
        project_data["time"] = {"created": now, "updated": now}
        changed = True
    else:
        if "created" not in project_data["time"]:
            project_data["time"]["created"] = _now_ms()
            changed = True
        if "updated" not in project_data["time"]:
            project_data["time"]["updated"] = _now_ms()
            changed = True
    
    return changed


@app.put("/api/projects/{project_id}/update")
async def update_project(project_id: str, request: Request):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    data = await request.json()
    project_file = STORAGE_PATH / "project" / f"{project_id}.json"
    if not project_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    
    with open(project_file, "r", encoding="utf-8") as f:
        project_data = json.load(f)
    
    # Store old values for undo
    old_name = project_data.get("name", "")
    old_worktree = project_data.get("worktree", "")
    
    # Track what changed
    changes = []
    new_project_id = None
    new_worktree = old_worktree
    migrated = False
    
    # Ensure all required OpenCode fields exist
    if _ensure_project_fields(project_data):
        changes.append("added missing OpenCode fields")
    
    # Update name
    if "new_name" in data and data["new_name"] != old_name:
        project_data["name"] = data["new_name"]
        changes.append(f"name: '{old_name}' -> '{data['new_name']}'")
    
    # Update worktree - may require migration if git root commit differs
    if "worktree" in data and data["worktree"] != old_worktree:
        new_worktree = data["worktree"]
        
        if new_worktree and Path(new_worktree).exists():
            # Check if git already exists before we potentially create it
            git_already_exists = (Path(new_worktree) / ".git").exists()
            
            success, git_project_id, error = _ensure_git_repo(new_worktree)
            if success:
                project_data["vcs"] = "git"
                
                # Check if this requires migration (different git root = different project ID)
                if git_project_id and git_project_id != project_id:
                    # Need to migrate to new project ID
                    new_project_id = git_project_id
                    migrated = True
                    
                    if git_already_exists:
                        changes.append(f"migrated to new git repo")
                    else:
                        changes.append(f"migrated to new git repo (git initialized)")
                else:
                    if git_already_exists:
                        changes.append("worktree changed")
                    else:
                        changes.append("worktree changed (git initialized)")
            else:
                project_data["vcs"] = ""
                changes.append(f"worktree changed (git init failed: {error})")
        else:
            project_data["vcs"] = ""
            changes.append("worktree changed")
        
        project_data["worktree"] = new_worktree
    
    if changes:
        project_data["time"]["updated"] = _now_ms()
        
        if migrated and new_project_id:
            # Migration: move everything to new project ID
            new_project_file = STORAGE_PATH / "project" / f"{new_project_id}.json"
            old_session_dir = STORAGE_PATH / "session" / project_id
            new_session_dir = STORAGE_PATH / "session" / new_project_id
            
            # Update project data with new ID
            project_data["id"] = new_project_id
            
            # Check if target project already exists (merge scenario)
            merged_into_existing = False
            target_project_name = ""
            if new_project_file.exists():
                # Merge into existing project - keep the existing project file
                # but we may want to update name if user provided one
                merged_into_existing = True
                try:
                    with open(new_project_file, "r", encoding="utf-8") as f:
                        existing_project_data = json.load(f)
                    target_project_name = existing_project_data.get("name", new_project_id)
                    
                    # If user is renaming, update the target project's name
                    if "new_name" in data and data["new_name"] != old_name:
                        existing_project_data["name"] = data["new_name"]
                        existing_project_data["time"]["updated"] = _now_ms()
                        with open(new_project_file, "w", encoding="utf-8") as f:
                            json.dump(existing_project_data, f, indent=2)
                except (json.JSONDecodeError, IOError):
                    pass
            else:
                # Create new project file
                with open(new_project_file, "w", encoding="utf-8") as f:
                    json.dump(project_data, f, indent=2)
            
            # Move sessions to new project folder
            sessions_moved = 0
            if old_session_dir.exists():
                new_session_dir.mkdir(parents=True, exist_ok=True)
                for session_file in old_session_dir.glob("*.json"):
                    try:
                        # Update session's projectID and directory
                        with open(session_file, "r", encoding="utf-8") as f:
                            session_data = json.load(f)
                        session_data["projectID"] = new_project_id
                        session_data["directory"] = new_worktree
                        
                        # Move to new location
                        new_session_file = new_session_dir / session_file.name
                        with open(new_session_file, "w", encoding="utf-8") as f:
                            json.dump(session_data, f, indent=2)
                        
                        # Delete old file
                        session_file.unlink()
                        sessions_moved += 1
                    except (json.JSONDecodeError, IOError) as e:
                        pass  # Skip problematic files
                
                # Remove old session directory if empty
                try:
                    if old_session_dir.exists() and not any(old_session_dir.iterdir()):
                        old_session_dir.rmdir()
                except OSError:
                    pass
            
            # Delete old project file
            try:
                project_file.unlink()
            except OSError:
                pass
            
            # Migrate Desktop cache entries from old worktree to new worktree
            if old_worktree and new_worktree and old_worktree != new_worktree:
                try:
                    _migrate_desktop_cache_worktree(old_worktree, new_worktree)
                except Exception:
                    pass  # Don't fail migration if cache update fails
            
            changes.append(f"{sessions_moved} sessions moved")
            
            # Add to undo history (migration is complex, store info for reference)
            if merged_into_existing:
                changes.append(f"merged into existing project '{target_project_name}'")
            
            _add_to_undo_history({
                "type": "migrate_project",
                "description": f"Migrate project '{project_data.get('name', '')}': {', '.join(changes)}",
                "old_project_id": project_id,
                "new_project_id": new_project_id,
                "old_name": old_name,
                "old_worktree": old_worktree,
                "sessions_moved": sessions_moved,
                "merged": merged_into_existing
            })
            
            return {
                "success": True, 
                "name": project_data.get("name", ""), 
                "worktree": project_data.get("worktree", ""),
                "migrated": True,
                "merged": merged_into_existing,
                "target_project_name": target_project_name if merged_into_existing else "",
                "new_project_id": new_project_id,
                "sessions_moved": sessions_moved
            }
        else:
            # Simple update, no migration
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2)
            
            # If worktree changed (but same project ID), migrate Desktop cache entries
            if old_worktree and new_worktree and old_worktree != new_worktree:
                try:
                    _migrate_desktop_cache_worktree(old_worktree, new_worktree)
                except Exception:
                    pass  # Don't fail update if cache migration fails
            
            _add_to_undo_history({
                "type": "update_project",
                "description": f"Edit project '{old_name}': {', '.join(changes)}",
                "project_id": project_id,
                "old_name": old_name,
                "old_worktree": old_worktree,
                "file_path": str(project_file)
            })
    
    return {"success": True, "name": project_data.get("name", ""), "worktree": project_data.get("worktree", "")}


@app.put("/api/sessions/{session_id}/rename")
async def rename_session(session_id: str, request: Request):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    data = await request.json()
    session_file, _ = _find_session_file(session_id)
    
    if not session_file:
        raise HTTPException(status_code=404, detail="Session not found")
    
    with open(session_file, "r", encoding="utf-8") as f:
        session_data = json.load(f)
    
    old_title = session_data.get("title", "")
    new_title = data.get("new_name", "")
    
    if old_title != new_title:
        session_data["title"] = new_title
        session_data["time"]["updated"] = _now_ms()
        
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)
        
        # Add to undo history
        _add_to_undo_history({
            "type": "rename_session",
            "description": f"Rename session '{old_title}' -> '{new_title}'",
            "session_id": session_id,
            "old_title": old_title,
            "file_path": str(session_file)
        })
    
    return {"success": True, "title": new_title}


@app.post("/api/sessions/move")
async def move_session(request: Request):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    data = await request.json()
    session_id = data.get("session_id", "")
    target_project_id = data.get("target_project_id", "")
    
    source_file, source_project_id = _find_session_file(session_id)
    
    if not source_file:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if source_project_id == target_project_id:
        return {"success": True, "message": "Session already in target project"}
    
    # Get target project's worktree to update session directory
    target_project_file = STORAGE_PATH / "project" / f"{target_project_id}.json"
    target_worktree = ""
    if target_project_file.exists():
        try:
            with open(target_project_file, "r", encoding="utf-8") as f:
                target_project_data = json.load(f)
            target_worktree = target_project_data.get("worktree", "")
        except (json.JSONDecodeError, IOError):
            pass
    
    # Read session data and update projectID and directory
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        
        old_project_id = session_data.get("projectID", source_project_id)
        old_directory = session_data.get("directory", "")
        session_data["projectID"] = target_project_id
        if target_worktree:
            session_data["directory"] = target_worktree
        session_data["time"]["updated"] = _now_ms()
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session file: {e}")
    
    target_dir = STORAGE_PATH / "session" / target_project_id
    if not target_dir.exists():
        target_dir.mkdir(parents=True)
    
    target_file = target_dir / f"{session_id}.json"
    
    # Write updated session data to target location
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2)
    
    # Remove source file
    source_file.unlink()
    
    # Add to undo history
    _add_to_undo_history({
        "type": "move_session",
        "description": f"Move session to project '{target_project_id}'",
        "session_id": session_id,
        "source_project_id": source_project_id,
        "target_project_id": target_project_id,
        "old_project_id_in_file": old_project_id,
        "old_directory": old_directory
    })
    
    return {"success": True, "message": f"Session moved to {target_project_id}"}


@app.delete("/api/projects")
async def delete_projects(request: Request):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    data = await request.json()
    deleted = []
    errors = []
    project_backups = []
    project_names = []
    deleted_session_ids = []
    
    deleted_worktrees = []
    
    for project_id in data.get("ids", []):
        try:
            project_backup = {"project_id": project_id, "project_file": None, "sessions": []}
            project_worktree = ""
            
            project_file = STORAGE_PATH / "project" / f"{project_id}.json"
            if project_file.exists():
                project_backup["project_file"] = _backup_file(project_file)
                try:
                    with open(project_file, "r", encoding="utf-8") as f:
                        project_data = json.load(f)
                    project_names.append(project_data.get("name", project_id))
                    project_worktree = project_data.get("worktree", "")
                except (json.JSONDecodeError, KeyError, IOError):
                    project_names.append(project_id)
            
            session_dir = STORAGE_PATH / "session" / project_id
            if session_dir.exists():
                for session_file in session_dir.glob("*.json"):
                    session_id = session_file.stem
                    session_backup = _backup_session_data(session_id, project_id)
                    project_backup["sessions"].append(session_backup)
                    deleted_session_ids.append(session_id)
            
            project_backups.append(project_backup)
            
            if project_file.exists():
                project_file.unlink()
            
            if session_dir.exists():
                for session_file in session_dir.glob("*.json"):
                    session_id = session_file.stem
                    _delete_session_data(session_id)
                shutil.rmtree(str(session_dir))
            
            if project_worktree:
                deleted_worktrees.append(project_worktree)
            
            deleted.append(project_id)
        except Exception as e:
            errors.append({"id": project_id, "error": str(e)})
    
    # Clean up OpenCode Desktop cache entries for deleted sessions and worktrees
    if DESKTOP_CACHE_PATH and DESKTOP_CACHE_PATH.exists():
        try:
            if deleted_session_ids:
                _cleanup_desktop_cache_sessions(deleted_session_ids)
            for worktree in deleted_worktrees:
                _cleanup_desktop_cache_by_worktree(worktree)
        except Exception as e:
            errors.append({"id": "desktop_cache", "error": str(e)})
    
    if deleted:
        description = f"Delete {len(deleted)} project(s): {', '.join(project_names[:3])}"
        if len(project_names) > 3:
            description += f" (+{len(project_names) - 3} more)"
        _add_to_undo_history({"type": "delete_projects", "description": description, "projects": project_backups})
    
    return {"deleted": deleted, "errors": errors}


@app.delete("/api/sessions")
async def delete_sessions(request: Request):
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    data = await request.json()
    deleted = []
    errors = []
    session_backups = []
    session_names = []
    
    for session_id in data.get("ids", []):
        try:
            session_backup = _backup_session_data(session_id)
            
            if session_backup["session_file"]:
                try:
                    session_data = json.loads(session_backup["session_file"]["content"])
                    session_names.append(session_data.get("title", session_id[:20]))
                except (json.JSONDecodeError, KeyError, TypeError):
                    session_names.append(session_id[:20])
            
            session_backups.append(session_backup)
            
            session_file, _ = _find_session_file(session_id)
            
            if session_file:
                session_file.unlink()
            
            _delete_session_data(session_id)
            deleted.append(session_id)
        except Exception as e:
            errors.append({"id": session_id, "error": str(e)})
    
    # Clean up OpenCode Desktop cache entries for deleted sessions
    if deleted and DESKTOP_CACHE_PATH and DESKTOP_CACHE_PATH.exists():
        try:
            _cleanup_desktop_cache_sessions(deleted)
        except Exception as e:
            errors.append({"id": "desktop_cache", "error": str(e)})
    
    if deleted:
        description = f"Delete {len(deleted)} session(s): {', '.join(session_names[:3])}"
        if len(session_names) > 3:
            description += f" (+{len(session_names) - 3} more)"
        _add_to_undo_history({"type": "delete_sessions", "description": description, "sessions": session_backups})
    
    return {"deleted": deleted, "errors": errors}


@app.get("/api/undo/status")
async def get_undo_status():
    if not undo_history:
        return {"available": False, "description": ""}
    last_entry = undo_history[-1]
    return {"available": True, "description": last_entry.get("description", "Unknown operation"), "count": len(undo_history)}


@app.post("/api/undo")
async def perform_undo():
    global undo_history
    
    if not undo_history:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    
    entry = undo_history.pop()
    restored = []
    errors = []
    
    if entry["type"] == "delete_sessions":
        for session_backup in entry["sessions"]:
            try:
                if session_backup["session_file"]:
                    _restore_file(session_backup["session_file"])
                for msg_backup in session_backup["messages"]:
                    _restore_file(msg_backup)
                for part_backup in session_backup["parts"]:
                    _restore_file(part_backup)
                if session_backup["diff_file"]:
                    _restore_file(session_backup["diff_file"])
                if session_backup["todo_file"]:
                    _restore_file(session_backup["todo_file"])
                restored.append(session_backup["session_id"])
            except Exception as e:
                errors.append({"id": session_backup["session_id"], "error": str(e)})
    
    elif entry["type"] == "delete_projects":
        for project_backup in entry["projects"]:
            try:
                if project_backup["project_file"]:
                    _restore_file(project_backup["project_file"])
                for session_backup in project_backup["sessions"]:
                    if session_backup["session_file"]:
                        _restore_file(session_backup["session_file"])
                    for msg_backup in session_backup["messages"]:
                        _restore_file(msg_backup)
                    for part_backup in session_backup["parts"]:
                        _restore_file(part_backup)
                    if session_backup["diff_file"]:
                        _restore_file(session_backup["diff_file"])
                    if session_backup["todo_file"]:
                        _restore_file(session_backup["todo_file"])
                restored.append(project_backup["project_id"])
            except Exception as e:
                errors.append({"id": project_backup["project_id"], "error": str(e)})
    
    elif entry["type"] == "update_project":
        try:
            project_file = Path(entry["file_path"])
            with open(project_file, "r", encoding="utf-8") as f:
                project_data = json.load(f)
            project_data["name"] = entry["old_name"]
            project_data["worktree"] = entry["old_worktree"]
            project_data["time"]["updated"] = _now_ms()
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2)
            restored.append(entry["project_id"])
        except Exception as e:
            errors.append({"id": entry["project_id"], "error": str(e)})
    
    elif entry["type"] == "rename_session":
        try:
            session_file = Path(entry["file_path"])
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            session_data["title"] = entry["old_title"]
            session_data["time"]["updated"] = _now_ms()
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
            restored.append(entry["session_id"])
        except Exception as e:
            errors.append({"id": entry["session_id"], "error": str(e)})
    
    elif entry["type"] == "move_session":
        try:
            # Move back from target to source and restore original projectID and directory
            target_file = STORAGE_PATH / "session" / entry["target_project_id"] / f"{entry['session_id']}.json"
            source_dir = STORAGE_PATH / "session" / entry["source_project_id"]
            if not source_dir.exists():
                source_dir.mkdir(parents=True)
            source_file = source_dir / f"{entry['session_id']}.json"
            
            # Read session data and restore original projectID and directory
            with open(target_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            
            # Restore original projectID (use old_project_id_in_file if available, else source_project_id)
            original_project_id = entry.get("old_project_id_in_file", entry["source_project_id"])
            session_data["projectID"] = original_project_id
            
            # Restore original directory if it was saved
            if "old_directory" in entry:
                session_data["directory"] = entry["old_directory"]
            
            session_data["time"]["updated"] = _now_ms()
            
            # Write to source location
            with open(source_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
            
            # Remove target file
            target_file.unlink()
            
            restored.append(entry["session_id"])
        except Exception as e:
            errors.append({"id": entry["session_id"], "error": str(e)})
    
    elif entry["type"] == "create_project":
        try:
            # Undo create = delete the project (only if it has no sessions)
            project_file = Path(entry["file_path"])
            session_dir = Path(entry["session_dir"])
            
            # Check if project has sessions
            if session_dir.exists() and any(session_dir.glob("*.json")):
                errors.append({"id": entry["project_id"], "error": "Cannot undo: project now has sessions"})
            else:
                if project_file.exists():
                    project_file.unlink()
                if session_dir.exists():
                    session_dir.rmdir()  # Only removes if empty
                restored.append(entry["project_id"])
        except Exception as e:
            errors.append({"id": entry["project_id"], "error": str(e)})
    
    return {"restored": restored, "errors": errors}


# =============================================================================
# Orphan Detection and Cleanup
# =============================================================================

def _get_all_valid_session_ids() -> set:
    """Get all valid session IDs from the session directories."""
    session_ids = set()
    session_base = STORAGE_PATH / "session"
    if session_base.exists():
        for project_dir in session_base.iterdir():
            if project_dir.is_dir():
                for session_file in project_dir.glob("*.json"):
                    session_ids.add(session_file.stem)
    return session_ids


def _get_all_valid_message_ids() -> set:
    """Get all valid message IDs from the message directories."""
    message_ids = set()
    message_base = STORAGE_PATH / "message"
    if message_base.exists():
        for session_dir in message_base.iterdir():
            if session_dir.is_dir():
                for msg_file in session_dir.glob("*.json"):
                    message_ids.add(msg_file.stem)
    return message_ids


def _get_message_to_session_map() -> dict:
    """Build a map of message ID -> session ID from message directory structure."""
    msg_to_session = {}
    message_base = STORAGE_PATH / "message"
    if message_base.exists():
        for session_dir in message_base.iterdir():
            if session_dir.is_dir():
                session_id = session_dir.name
                for msg_file in session_dir.glob("*.json"):
                    msg_to_session[msg_file.stem] = session_id
    return msg_to_session


def _get_projects_with_sessions() -> set:
    """Get all project IDs that have at least one session."""
    projects_with_sessions = set()
    session_base = STORAGE_PATH / "session"
    if session_base.exists():
        for project_dir in session_base.iterdir():
            if project_dir.is_dir():
                # Check if this project dir has any session files
                session_files = list(project_dir.glob("*.json"))
                if session_files:
                    projects_with_sessions.add(project_dir.name)
    return projects_with_sessions


@app.get("/api/orphans/scan")
async def scan_orphans():
    """Scan for orphaned data in storage folders.
    
    Detects:
    - orphan_projects: Projects with no sessions (excluding 'global')
    - session_diffs: Files referencing non-existent sessions
    - todos: Files referencing non-existent sessions
    - messages: Directories for non-existent sessions
    - parts: Directories for non-existent messages
    - mismatched_messages: Message files where internal sessionID doesn't match directory
    - mismatched_parts: Part files with invalid sessionID or messageID references
    - stale_cache_sessions: Sessions in Desktop cache that don't exist on disk
    """
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    orphans = {
        "orphan_projects": [],
        "session_diffs": [],
        "todos": [],
        "messages": [],
        "parts": [],
        "mismatched_messages": [],
        "mismatched_parts": [],
        "stale_cache_sessions": [],
        "total_count": 0,
        "total_size": 0
    }
    
    # Get all valid session IDs
    valid_sessions = _get_all_valid_session_ids()
    
    # Get all valid message IDs
    valid_messages = _get_all_valid_message_ids()
    
    # Build message -> session mapping for cross-reference validation
    msg_to_session = _get_message_to_session_map()
    
    # Get projects that have sessions
    projects_with_sessions = _get_projects_with_sessions()
    
    # Check for orphan projects (projects with no sessions)
    # NOTE: Skip "global" - OpenCode auto-creates it for non-git sessions
    project_dir = STORAGE_PATH / "project"
    if project_dir.exists():
        for project_file in project_dir.glob("*.json"):
            project_id = project_file.stem
            if project_id not in projects_with_sessions and project_id != "global":
                try:
                    with open(project_file, 'r', encoding='utf-8') as f:
                        project_data = json.load(f)
                    size = project_file.stat().st_size
                    orphans["orphan_projects"].append({
                        "path": str(project_file),
                        "project_id": project_id,
                        "name": project_data.get("name", project_id),
                        "worktree": project_data.get("worktree", ""),
                        "size": size
                    })
                    orphans["total_size"] += size
                except (json.JSONDecodeError, IOError):
                    pass
    
    # Check session_diff folder for orphans
    session_diff_dir = STORAGE_PATH / "session_diff"
    if session_diff_dir.exists():
        for diff_file in session_diff_dir.glob("*.json"):
            session_id = diff_file.stem
            if session_id not in valid_sessions:
                size = diff_file.stat().st_size
                orphans["session_diffs"].append({
                    "path": str(diff_file),
                    "session_id": session_id,
                    "size": size
                })
                orphans["total_size"] += size
    
    # Check todo folder for orphans
    todo_dir = STORAGE_PATH / "todo"
    if todo_dir.exists():
        for todo_file in todo_dir.glob("*.json"):
            session_id = todo_file.stem
            if session_id not in valid_sessions:
                size = todo_file.stat().st_size
                orphans["todos"].append({
                    "path": str(todo_file),
                    "session_id": session_id,
                    "size": size
                })
                orphans["total_size"] += size
    
    # Check message folder for orphaned session directories AND mismatched sessionIDs
    message_dir = STORAGE_PATH / "message"
    if message_dir.exists():
        for session_msg_dir in message_dir.iterdir():
            if session_msg_dir.is_dir():
                session_id = session_msg_dir.name
                if session_id not in valid_sessions:
                    # Entire directory is orphaned
                    dir_size = sum(f.stat().st_size for f in session_msg_dir.rglob("*") if f.is_file())
                    file_count = len(list(session_msg_dir.rglob("*.json")))
                    orphans["messages"].append({
                        "path": str(session_msg_dir),
                        "session_id": session_id,
                        "file_count": file_count,
                        "size": dir_size
                    })
                    orphans["total_size"] += dir_size
                else:
                    # Directory is valid, but check each message file's internal sessionID
                    for msg_file in session_msg_dir.glob("*.json"):
                        try:
                            with open(msg_file, 'r', encoding='utf-8') as f:
                                msg_data = json.load(f)
                            internal_session_id = msg_data.get("sessionID", "")
                            if internal_session_id and internal_session_id != session_id:
                                size = msg_file.stat().st_size
                                orphans["mismatched_messages"].append({
                                    "path": str(msg_file),
                                    "message_id": msg_file.stem,
                                    "directory_session_id": session_id,
                                    "internal_session_id": internal_session_id,
                                    "size": size,
                                    "issue": f"sessionID mismatch: file in '{session_id}' but references '{internal_session_id}'"
                                })
                                orphans["total_size"] += size
                        except (json.JSONDecodeError, IOError):
                            # Skip files that can't be read
                            pass
    
    # Check part folder for orphaned message directories AND mismatched references
    part_dir = STORAGE_PATH / "part"
    if part_dir.exists():
        for msg_part_dir in part_dir.iterdir():
            if msg_part_dir.is_dir():
                message_id = msg_part_dir.name
                if message_id not in valid_messages:
                    # Entire directory is orphaned
                    dir_size = sum(f.stat().st_size for f in msg_part_dir.rglob("*") if f.is_file())
                    file_count = len(list(msg_part_dir.rglob("*.json")))
                    orphans["parts"].append({
                        "path": str(msg_part_dir),
                        "message_id": message_id,
                        "file_count": file_count,
                        "size": dir_size
                    })
                    orphans["total_size"] += dir_size
                else:
                    # Directory is valid, check each part file's internal references
                    expected_session_id = msg_to_session.get(message_id, None)
                    for part_file in msg_part_dir.glob("*.json"):
                        try:
                            with open(part_file, 'r', encoding='utf-8') as f:
                                part_data = json.load(f)
                            
                            issues = []
                            internal_session_id = part_data.get("sessionID", "")
                            internal_message_id = part_data.get("messageID", "")
                            
                            # Check if sessionID in part matches expected session
                            if internal_session_id:
                                if internal_session_id not in valid_sessions:
                                    issues.append(f"sessionID '{internal_session_id}' doesn't exist")
                                elif expected_session_id and internal_session_id != expected_session_id:
                                    issues.append(f"sessionID mismatch: expected '{expected_session_id}', got '{internal_session_id}'")
                            
                            # Check if messageID in part matches the directory
                            if internal_message_id and internal_message_id != message_id:
                                issues.append(f"messageID mismatch: in dir '{message_id}' but references '{internal_message_id}'")
                            
                            # Check if internal messageID exists
                            if internal_message_id and internal_message_id not in valid_messages:
                                issues.append(f"messageID '{internal_message_id}' doesn't exist")
                            
                            if issues:
                                size = part_file.stat().st_size
                                orphans["mismatched_parts"].append({
                                    "path": str(part_file),
                                    "part_id": part_file.stem,
                                    "directory_message_id": message_id,
                                    "internal_session_id": internal_session_id,
                                    "internal_message_id": internal_message_id,
                                    "expected_session_id": expected_session_id,
                                    "size": size,
                                    "issues": issues
                                })
                                orphans["total_size"] += size
                        except (json.JSONDecodeError, IOError):
                            # Skip files that can't be read
                            pass
    
    # Check OpenCode Desktop cache for stale session references
    if DESKTOP_CACHE_PATH and DESKTOP_CACHE_PATH.exists():
        try:
            with open(DESKTOP_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Extract session IDs from cache keys and notification data
            stale_sessions_found = set()
            for key, value in cache_data.items():
                # Check notification list for stale sessions
                if key == "notification.v1":
                    try:
                        notif_data = json.loads(value)
                        for notif in notif_data.get("list", []):
                            session_id = notif.get("session", "")
                            if session_id and session_id.startswith("ses_"):
                                if session_id not in valid_sessions:
                                    stale_sessions_found.add(session_id)
                    except (json.JSONDecodeError, TypeError):
                        pass
                # Check other keys that might contain session references
                elif ".v1" in key or ".v2" in key:
                    # Keys like "path/prompt/ses_xxx.v1" or "path/terminal/ses_xxx.v1"
                    parts = key.split("/")
                    for part in parts:
                        if part.startswith("ses_") and ".v" in part:
                            session_id = part.split(".v")[0]
                            if session_id not in valid_sessions:
                                stale_sessions_found.add(session_id)
            
            for session_id in stale_sessions_found:
                orphans["stale_cache_sessions"].append({
                    "session_id": session_id,
                    "cache_file": str(DESKTOP_CACHE_PATH),
                    "size": 0  # Can't easily determine per-entry size
                })
        except (json.JSONDecodeError, IOError):
            pass
    
    orphans["total_count"] = (
        len(orphans["orphan_projects"]) +
        len(orphans["session_diffs"]) + 
        len(orphans["todos"]) + 
        len(orphans["messages"]) + 
        len(orphans["parts"]) +
        len(orphans["mismatched_messages"]) +
        len(orphans["mismatched_parts"]) +
        len(orphans["stale_cache_sessions"])
    )
    
    return orphans


@app.post("/api/orphans/cleanup")
async def cleanup_orphans():
    """Delete all orphaned data including mismatched internal references."""
    if not STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Storage path not configured")
    
    # First scan for orphans to get the complete picture
    valid_sessions = _get_all_valid_session_ids()
    valid_messages = _get_all_valid_message_ids()
    msg_to_session = _get_message_to_session_map()
    projects_with_sessions = _get_projects_with_sessions()
    
    deleted = {
        "orphan_projects": 0,
        "session_diffs": 0,
        "todos": 0,
        "messages": 0,
        "parts": 0,
        "mismatched_messages": 0,
        "mismatched_parts": 0,
        "stale_cache_sessions": 0,
        "total_size_freed": 0
    }
    errors = []
    
    # Delete orphan projects (projects with no sessions)
    # NOTE: Skip "global" project - OpenCode auto-creates it and needs it
    project_dir = STORAGE_PATH / "project"
    if project_dir.exists():
        for project_file in project_dir.glob("*.json"):
            project_id = project_file.stem
            if project_id not in projects_with_sessions and project_id != "global":
                try:
                    size = project_file.stat().st_size
                    project_file.unlink()
                    deleted["orphan_projects"] += 1
                    deleted["total_size_freed"] += size
                except Exception as e:
                    errors.append({"path": str(project_file), "error": str(e)})
    
    # Delete orphaned session_diffs
    session_diff_dir = STORAGE_PATH / "session_diff"
    if session_diff_dir.exists():
        for diff_file in session_diff_dir.glob("*.json"):
            if diff_file.stem not in valid_sessions:
                try:
                    size = diff_file.stat().st_size
                    diff_file.unlink()
                    deleted["session_diffs"] += 1
                    deleted["total_size_freed"] += size
                except Exception as e:
                    errors.append({"path": str(diff_file), "error": str(e)})
    
    # Delete orphaned todos
    todo_dir = STORAGE_PATH / "todo"
    if todo_dir.exists():
        for todo_file in todo_dir.glob("*.json"):
            if todo_file.stem not in valid_sessions:
                try:
                    size = todo_file.stat().st_size
                    todo_file.unlink()
                    deleted["todos"] += 1
                    deleted["total_size_freed"] += size
                except Exception as e:
                    errors.append({"path": str(todo_file), "error": str(e)})
    
    # Delete orphaned message directories AND mismatched message files
    message_dir = STORAGE_PATH / "message"
    if message_dir.exists():
        for session_msg_dir in message_dir.iterdir():
            if session_msg_dir.is_dir():
                session_id = session_msg_dir.name
                if session_id not in valid_sessions:
                    # Delete entire orphaned directory
                    try:
                        dir_size = sum(f.stat().st_size for f in session_msg_dir.rglob("*") if f.is_file())
                        shutil.rmtree(str(session_msg_dir))
                        deleted["messages"] += 1
                        deleted["total_size_freed"] += dir_size
                    except Exception as e:
                        errors.append({"path": str(session_msg_dir), "error": str(e)})
                else:
                    # Check individual message files for mismatched sessionIDs
                    for msg_file in session_msg_dir.glob("*.json"):
                        try:
                            with open(msg_file, 'r', encoding='utf-8') as f:
                                msg_data = json.load(f)
                            internal_session_id = msg_data.get("sessionID", "")
                            if internal_session_id and internal_session_id != session_id:
                                size = msg_file.stat().st_size
                                msg_file.unlink()
                                deleted["mismatched_messages"] += 1
                                deleted["total_size_freed"] += size
                        except (json.JSONDecodeError, IOError):
                            pass
                        except Exception as e:
                            errors.append({"path": str(msg_file), "error": str(e)})
    
    # Delete orphaned part directories AND mismatched part files
    part_dir = STORAGE_PATH / "part"
    if part_dir.exists():
        for msg_part_dir in part_dir.iterdir():
            if msg_part_dir.is_dir():
                message_id = msg_part_dir.name
                if message_id not in valid_messages:
                    # Delete entire orphaned directory
                    try:
                        dir_size = sum(f.stat().st_size for f in msg_part_dir.rglob("*") if f.is_file())
                        shutil.rmtree(str(msg_part_dir))
                        deleted["parts"] += 1
                        deleted["total_size_freed"] += dir_size
                    except Exception as e:
                        errors.append({"path": str(msg_part_dir), "error": str(e)})
                else:
                    # Check individual part files for mismatched references
                    expected_session_id = msg_to_session.get(message_id, None)
                    for part_file in msg_part_dir.glob("*.json"):
                        try:
                            with open(part_file, 'r', encoding='utf-8') as f:
                                part_data = json.load(f)
                            
                            has_issues = False
                            internal_session_id = part_data.get("sessionID", "")
                            internal_message_id = part_data.get("messageID", "")
                            
                            # Check for invalid sessionID
                            if internal_session_id:
                                if internal_session_id not in valid_sessions:
                                    has_issues = True
                                elif expected_session_id and internal_session_id != expected_session_id:
                                    has_issues = True
                            
                            # Check for mismatched or invalid messageID
                            if internal_message_id:
                                if internal_message_id != message_id:
                                    has_issues = True
                                if internal_message_id not in valid_messages:
                                    has_issues = True
                            
                            if has_issues:
                                size = part_file.stat().st_size
                                part_file.unlink()
                                deleted["mismatched_parts"] += 1
                                deleted["total_size_freed"] += size
                        except (json.JSONDecodeError, IOError):
                            pass
                        except Exception as e:
                            errors.append({"path": str(part_file), "error": str(e)})
    
    # Clean up stale sessions from OpenCode Desktop cache
    if DESKTOP_CACHE_PATH and DESKTOP_CACHE_PATH.exists():
        try:
            with open(DESKTOP_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            modified = False
            keys_to_remove = []
            
            # Find and remove stale session keys
            for key in list(cache_data.keys()):
                if ".v1" in key or ".v2" in key:
                    parts = key.split("/")
                    for part in parts:
                        if part.startswith("ses_") and ".v" in part:
                            session_id = part.split(".v")[0]
                            if session_id not in valid_sessions:
                                keys_to_remove.append(key)
                                break
            
            # Clean notification list
            if "notification.v1" in cache_data:
                try:
                    notif_data = json.loads(cache_data["notification.v1"])
                    original_count = len(notif_data.get("list", []))
                    notif_data["list"] = [
                        n for n in notif_data.get("list", [])
                        if n.get("session", "").startswith("ses_") and n.get("session") in valid_sessions
                        or not n.get("session", "").startswith("ses_")
                    ]
                    new_count = len(notif_data.get("list", []))
                    if new_count < original_count:
                        cache_data["notification.v1"] = json.dumps(notif_data)
                        deleted["stale_cache_sessions"] += (original_count - new_count)
                        modified = True
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # Remove stale keys
            for key in keys_to_remove:
                del cache_data[key]
                deleted["stale_cache_sessions"] += 1
                modified = True
            
            # Write back if modified
            if modified:
                with open(DESKTOP_CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f)
        except Exception as e:
            errors.append({"path": str(DESKTOP_CACHE_PATH), "error": str(e)})
    
    return {"deleted": deleted, "errors": errors}


# =============================================================================
# Main Entry Point
# =============================================================================

def open_browser(port: int):
    """Open the browser after a short delay."""
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{port}")


def check_existing_instance(port: int) -> bool:
    """Check if another instance is already running on the port.
    
    Returns True if we should continue starting, False if we should exit.
    """
    import socket
    import urllib.request
    import urllib.error
    
    # First check if port is in use
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    
    if result != 0:
        # Port is free, no existing instance
        return True
    
    # Port is in use - check if it's our app by hitting the API
    try:
        req = urllib.request.Request(f'http://localhost:{port}/api/storage-path', method='GET')
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                # It's our app! Ask user what to do
                print(f"\n*** Another instance is already running on port {port} ***\n")
                print("Options:")
                print("  [1] Open browser to existing instance (default)")
                print("  [2] Shutdown existing instance and start new one")
                print("  [3] Exit")
                print()
                
                try:
                    choice = input("Enter choice [1/2/3]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    choice = "3"
                
                if choice == "2":
                    # Shutdown existing instance
                    print("Shutting down existing instance...")
                    try:
                        shutdown_req = urllib.request.Request(
                            f'http://localhost:{port}/api/shutdown',
                            method='POST',
                            headers={'Content-Type': 'application/json'}
                        )
                        urllib.request.urlopen(shutdown_req, timeout=5)
                    except urllib.error.URLError:
                        pass  # Expected - server is shutting down
                    
                    # Wait for port to be freed
                    print("Waiting for port to be freed...")
                    for _ in range(10):
                        time.sleep(0.5)
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        if sock.connect_ex(('127.0.0.1', port)) != 0:
                            sock.close()
                            print("Port freed. Starting new instance...\n")
                            return True
                        sock.close()
                    
                    print("Warning: Port may still be in use. Attempting to start anyway...\n")
                    return True
                    
                elif choice == "3":
                    print("Exiting.")
                    return False
                    
                else:
                    # Default: open browser to existing instance
                    print(f"Opening browser to existing instance...")
                    webbrowser.open(f"http://localhost:{port}")
                    return False
                    
    except urllib.error.URLError:
        # Port is in use but not by our app
        print(f"\n*** Error: Port {port} is already in use by another application ***")
        print("Please close the other application or change the port.")
        input("Press Enter to exit...")
        return False
    except Exception as e:
        print(f"Error checking existing instance: {e}")
        return True
    
    return True


if __name__ == "__main__":
    PORT = 8765
    
    print("=" * 50)
    print("OpenCode Session Manager")
    print("=" * 50)
    
    # Check for existing instance before doing anything else
    if not check_existing_instance(PORT):
        sys.exit(0)
    
    initialize_storage_path()
    
    if STORAGE_PATH:
        print(f"Storage path: {STORAGE_PATH}")
    else:
        print("Storage path not detected. Please configure it in the UI.")
    
    print(f"\nStarting server at http://localhost:{PORT}")
    print("Press Ctrl+C to stop\n")
    
    # Open browser in background thread
    browser_thread = threading.Thread(target=open_browser, args=(PORT,), daemon=True)
    browser_thread.start()
    
    # Start uvicorn server
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")

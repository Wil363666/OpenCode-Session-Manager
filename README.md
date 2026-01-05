# OpenCode Session Manager

A web-based GUI tool for managing OpenCode sessions and projects.

## Features

- **Project Management**: View, filter, rename, and delete projects
- **Session Management**: View, filter, rename, move, and delete sessions
- **Session Preview**: Full scrollable conversation history with syntax highlighting
- **Session Stats**: Message count, size, timestamps, and metadata
- **Drag & Drop**: Move sessions between projects
- **Bulk Operations**: Ctrl+Click to multi-select items for deletion
- **Undo Support**: Restore deleted projects/sessions with Ctrl+Z (up to 10 operations)
- **Search/Filter**: Integrated search in both project and session columns
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Persistent Config**: Storage path saved to config file for future sessions
- **Auto-managed Dependencies**: FastAPI and Uvicorn are automatically installed in a local virtual environment

## Requirements

- Python 3.10+
- Dependencies (auto-installed to local venv):
  - FastAPI
  - Uvicorn

## Installation

No manual installation required. Simply run the Python script:

```bash
python opencode_session_manager.py
```

On first run, the script will:
1. Create a virtual environment (`venv/`) in the script directory
2. Check for missing dependencies and install only what's needed
3. Re-launch itself using the venv Python
4. Open the browser to `http://localhost:8765`

Subsequent runs will skip installation if all dependencies are satisfied.

## Usage

1. **Start the application**:
   ```bash
   python opencode_session_manager.py
   ```

2. **Browser opens automatically** to `http://localhost:8765`

3. **Configure storage path**: 
   - The app auto-detects the OpenCode storage path
   - If not found, use the **Browse** button to select it manually
   - Once configured, the path is saved to `OpenCodeSessionManagerConfig.txt`
   - Default locations:
     - Windows: `%USERPROFILE%\.local\share\opencode\storage`
     - macOS: `~/.local/share/opencode/storage`
     - Linux: `~/.local/share/opencode/storage` (or `$XDG_DATA_HOME/opencode/storage`)

## Configuration File

The storage path is persisted in `OpenCodeSessionManagerConfig.txt` (same directory as the script).

- **Format**: Single line containing the path
- **Portable paths**: Uses `~` for home directory (e.g., `~/.local/share/opencode/storage`)
- **Environment variables**: Supports `%USERPROFILE%`, `$HOME`, etc.
- **Auto-created**: Generated automatically when a valid path is detected or set

## Interface

```
+------------------+------------------+----------------------+------------------+
|    Projects      |    Sessions      |      Preview         |  Session Stats   |
+------------------+------------------+----------------------+------------------+
| [Search...]      | [Search...]      |                      |                  |
|                  |                  | User: Hello...       | Messages: 42     |
| > Project1       | > Session1       |                      | Size: 1.2 MB     |
|   Project2       |   Session2       | Assistant: Hi...     | Created: ...     |
|   Project3       |   Session3       |                      | Modified: ...    |
|                  |                  |                      |                  |
+------------------+------------------+----------------------+------------------+
|  [Undo]  [Delete]  [Edit]                                                     |
+-------------------------------------------------------------------------------+
```

## Operations

### Select Items
- **Single click**: Select one item
- **Ctrl+Click**: Multi-select items (same column only)

### Move Sessions
- Drag a session from the Sessions column
- Drop it on a project in the Projects column

### Delete Items
- Select item(s) and click **Delete** (or press `Delete` key)
- Confirm in the modal dialog
- Deletes all associated data (messages, diffs, todos)

### Undo Deletions
- Click **Undo** button or press `Ctrl+Z` to restore deleted items
- Supports up to 10 undo operations
- Restores all associated files (messages, diffs, todos)
- Undo history is cleared when the application is restarted

### Rename Items
- Select a single item and click **Edit**
- Enter new name and save

### Filter/Search
- Type in the search box at the top of each column
- Filters by name/title and path (for projects)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Z` | Undo last delete operation |
| `Delete` | Open delete confirmation for selected items |
| `Escape` | Close modal dialogs |
| `Enter` | Confirm edit (when edit modal is open) |

## Data Safety

- **Confirmation required**: All delete operations require confirmation
- **Detailed preview**: Delete modal shows exactly what will be removed
- **Undo support**: Deleted items can be restored with Ctrl+Z
- **Complete cleanup**: Deleting sessions removes all related data:
  - Session file (`storage/session/<project>/<session>.json`)
  - Messages (`storage/message/<session>/`)
  - Message parts (`storage/part/<message_id>/`)
  - Diffs (`storage/session_diff/<session>.json`)
  - Todos (`storage/todo/<session>.json`)

## Managing "Global" Sessions

Sessions created without a specific project folder are stored in `storage/session/global/`. These appear in the Session Manager and can be:
- Moved to a proper project via drag & drop
- Deleted to clean up orphaned sessions
- Viewed and inspected like any other session

## Troubleshooting

### "Storage path not configured"
- Click **Browse** and navigate to your OpenCode storage folder
- The folder should contain `session`, `project`, and `message` subdirectories

### "Invalid OpenCode storage directory"
- Ensure the selected folder is the `storage` directory, not the parent `opencode` directory

### Port already in use
- Edit the script and change `PORT = 8765` to another port

### Browser doesn't open automatically
- Manually navigate to `http://localhost:8765`

## Technical Details

- **Single file application**: Everything is contained in `opencode_session_manager.py`
- **FastAPI + Uvicorn**: Robust async HTTP server with automatic reload detection
- **Auto-managed venv**: Dependencies installed in local `venv/` directory
- **Smart dependency check**: Only installs missing packages on startup
- **Embedded frontend**: HTML/CSS/JS embedded in Python script
- **In-memory undo**: Deleted files are backed up in memory (not on disk)

## License

MIT License - Feel free to modify and distribute.

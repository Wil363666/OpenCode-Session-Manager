# OpenCode Session Manager

A web-based GUI tool for managing OpenCode sessions and projects. Browse, search, organize, and clean up your OpenCode data with ease.

<img width="1920" alt="Screenshot" src="https://github.com/user-attachments/assets/6bfa19ab-186e-4d66-bbeb-722bbf2b0009" />

---

## Features

**Session & Project Management**
- Browse all your OpenCode projects with session counts
- View sessions with titles, timestamps, and message previews
- Edit, rename, and delete projects and sessions
- Drag & drop sessions between projects
- Undo support for recently deleted items

**Global Search**
- Search across all sessions from all projects simultaneously
- Results show project badges for easy identification
- Clicking a result highlights the corresponding project

**Preview Search**
- Search through message content within conversations
- Navigate between matches with arrow buttons or keyboard
- Match counter shows current position (e.g., "3/12")

**Data Integrity Tools**
- Check & Repair: Fix project issues, migrate IDs, initialize git repos
- Orphan Scanner: Find and clean up orphaned data files
- Batch fix all projects with one click

**Customization**
- 4 color themes: Default, Glitch, Midnight, Forest
- Settings persist across sessions

---

## Requirements

- Python 3.8 or higher
- Internet connection (first run only, to install dependencies)

Dependencies (auto-installed):
- FastAPI
- Uvicorn

---

## Installation

Clone the repository:

```
git clone https://github.com/yourusername/opencode-session-manager.git
cd opencode-session-manager
```

Run the application:

```
python opencode_session_manager.py
```

On first run, the application will:
1. Create a virtual environment
2. Install required dependencies
3. Auto-detect your OpenCode storage path
4. Open your browser to the UI at http://localhost:8765

---

## Storage Path

The application auto-detects your OpenCode storage location:

| OS | Default Path |
|:---|:-------------|
| Windows | `~/.local/share/opencode/storage` |
| macOS | `~/.local/share/opencode/storage` |
| Linux | `~/.local/share/opencode/storage` |

You can manually set the path using the "Browse" button.

---

## Keyboard Shortcuts

| Key | Action |
|:----|:-------|
| Delete | Delete selected item |
| Escape | Close modal dialogs |
| Enter | Confirm dialog / Next search match |
| Shift+Enter | Previous search match |
| Ctrl+Z | Undo last deletion |
| Ctrl+Click | Multi-select items |

---

## Configuration

Settings are stored in `static/config.txt`:

```json
{
  "storage_path": "~/.local/share/opencode/storage",
  "theme": "glitch"
}
```

---

## License

MIT License

---

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

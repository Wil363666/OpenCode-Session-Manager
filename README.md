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

## Quick Start

The fastest way to run the application:

```bash
uvx --from git+https://github.com/yourusername/opencode-session-manager opencode-session-manager
```

This single command downloads, installs, and runs the application instantly!

---

## Requirements

- Python 3.8 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

Dependencies:
- FastAPI
- Uvicorn

### Why Use uv?

`uv` is a blazingly fast Python package installer and resolver written in Rust. Benefits include:

- **10-100x faster** than pip for dependency resolution and installation
- **Isolated environments** - each tool gets its own virtual environment
- **Zero configuration** - works out of the box
- **Run without installing** - use `uvx` to run tools instantly
- **Better dependency resolution** - consistent, reproducible environments

Install uv:

```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

---

## Installation

### Method 1: Using uvx (Recommended - No Clone Required)

Run directly without installation using `uvx`:

```bash
uvx --from git+https://github.com/yourusername/opencode-session-manager opencode-session-manager
```

This will:
- Fetch the latest version from GitHub
- Install dependencies in an isolated environment
- Run the application immediately

### Method 2: Using uv tool install (Install as a CLI tool)

Install globally as a command-line tool:

```bash
uv tool install git+https://github.com/yourusername/opencode-session-manager
```

Then run anytime with:

```bash
opencode-session-manager
```

To update to the latest version:

```bash
uv tool upgrade opencode-session-manager
```

To uninstall:

```bash
uv tool uninstall opencode-session-manager
```

### Method 3: Clone and Run with uv

Clone the repository:

```bash
git clone https://github.com/yourusername/opencode-session-manager.git
cd opencode-session-manager
```

Run with uv:

```bash
uv run opencode-session-manager
```

On first run, the application will:
1. Install required dependencies (handled by uv)
2. Auto-detect your OpenCode storage path
3. Open your browser to the UI at http://localhost:8765

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

## Development

### Setting Up Development Environment

Clone the repository:

```bash
git clone https://github.com/yourusername/opencode-session-manager.git
cd opencode-session-manager
```

### Running in Development Mode

```bash
# Using uv run (automatically manages dependencies)
uv run opencode-session-manager
```

uv will automatically:
- Create an isolated virtual environment
- Install all dependencies from pyproject.toml
- Run the application

### Building and Publishing

Build the package:

```bash
uv build
```

This creates distribution files in the `dist/` directory.

---

## License

MIT License

---

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Test locally: `uv run opencode-session-manager`
5. Commit your changes: `git commit -am 'Add feature'`
6. Push to your fork: `git push origin feature-name`
7. Open a Pull Request

# class-notes

Watches MacWhisper's export folder for new summary files, reformats them
with Claude, and pushes structured notes into your Obsidian vault via the
Local REST API plugin.

## Setup

### 1. Install

```bash
pipx install ~/Documents/repos/class-notes
```

### 2. Configure

On first run, a config file is created at:

```
~/.config/class-notes/config.toml
```

Edit it to set your **Obsidian REST API token** (Obsidian → Settings → Local REST API).

### 3. Set ANTHROPIC_API_KEY

Add to `~/.zshrc`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Run before class

```bash
class-notes --class advanced-edm
```

Leave it running in a terminal tab. When MacWhisper exports a summary,
the note appears in Obsidian automatically. Press `Ctrl+C` to stop.

## How it works

1. MacWhisper records your Zoom session and auto-exports a summary `.txt` to `~/Documents/MacWhisper/`
2. The watcher detects any new file with "summary" in the name
3. It sends the summary to Claude with a formatting prompt
4. Claude returns a structured note with YAML frontmatter
5. The note is pushed to your Obsidian vault via the Local REST API

## Note filename

The Obsidian note title comes from the MacWhisper transcript title.
Name your transcript something like `"Advanced EDM — Session 12"` before
recording and the note will be created as `Advanced EDM — Session 12.md`
in the configured vault folder.

## Adding a second class

In `~/.config/class-notes/config.toml`:

```toml
[classes.my-other-class]
name = "Other Class Name"
vault_path = "03 - SLAM Academy/Other Class Name"
tags = ["class", "production", "slam-academy"]
```

Then run with `--class my-other-class`.

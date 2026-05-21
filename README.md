# class-notes

Watches MacWhisper's export folder for new summary files, reformats them
with Claude, and pushes structured notes into your Obsidian vault via the
Local REST API plugin.

> **MacWhisper Pro required.** Auto-export of summaries is a Pro feature.

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

Edit it to fill in the required values:

```toml
# Folder MacWhisper exports summaries to (Pro feature)
watch_dir = "~/Documents/MacWhisper"

# Obsidian Local REST API — Settings → Local REST API → API key
obsidian_host = "http://localhost:27124"
obsidian_token = "YOUR_OBSIDIAN_TOKEN_HERE"

[classes.my-class]
name = "My Class Name"
vault_path = "Folder/Subfolder"   # vault-relative path for the note
tags = ["class", "my-tag"]
```

### 3. Set ANTHROPIC_API_KEY

Store it in the macOS Keychain and load it in `~/.oh-my-zsh/custom/exports.zsh`
(or `~/.zshrc`):

```bash
# Store once
security add-generic-password -a "$USER" -s anthropic-api-key -w

# In your shell config
export ANTHROPIC_API_KEY=$(security find-generic-password -a "$USER" -s anthropic-api-key -w 2>/dev/null)
```

### 4. Run before class

```bash
class-notes --class my-class
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
vault_path = "Folder/Other Class Name"
tags = ["class", "my-tag"]
```

Then run with `--class my-other-class`.

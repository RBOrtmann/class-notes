"""
Watches MacWhisper's export folder for new summary files,
reformats them with Claude, and pushes to Obsidian via REST API.
"""

import re
import sys
import time
import tomllib
import requests
import anthropic

from datetime import date
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".config" / "class-notes" / "config.toml"

DEFAULT_CONFIG = """\
# class-notes configuration

# Folder MacWhisper exports summaries to
watch_dir = "/Users/brendan/Documents/MacWhisper"

# Obsidian REST API
obsidian_host = "http://localhost:27124"
obsidian_token = "YOUR_OBSIDIAN_TOKEN_HERE"

# Vault root (relative paths below are relative to your vault root)
# The REST API handles vault-relative paths automatically.

# Class definitions: each entry maps a short key to a display name and vault path.
# When running the watcher, pass --class <key> to select the active class.
[classes]

  [classes.advanced-edm]
  name = "Advanced EDM Spring '26"
  vault_path = "03 - SLAM Academy/Advanced EDM Spring '26"
  tags = ["class", "production", "ableton", "slam-academy"]
"""

REFORMAT_PROMPT = """\
You are formatting a music production class summary into a structured Obsidian note.

The note MUST begin with this exact YAML frontmatter block and nothing before it:

---
date: {date}
tags: {tags}
---

After the frontmatter, format the rest of the content as clean Markdown using \
whatever sections make sense given the summary content. \
Use headers like ## Key Concepts, ## Techniques, ## Tools & Plugins, ## Action Items as appropriate. \
Do not include the original frontmatter or any preamble — output only the final note content.

Here is the summary to reformat:

{summary}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_CONFIG)
        print(f"Created default config at {CONFIG_PATH}")
        print("Please edit it to add your Obsidian token and class paths, then re-run.")
        sys.exit(0)
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def reformat_with_claude(summary: str, tags: list[str]) -> str:
    client = anthropic.Anthropic()
    tags_yaml = "[" + ", ".join(tags) + "]"
    prompt = REFORMAT_PROMPT.format(
        date=date.today().isoformat(),
        tags=tags_yaml,
        summary=summary,
    )
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def push_to_obsidian(host: str, token: str, vault_path: str, title: str, content: str):
    """PUT a markdown file into the Obsidian vault via Local REST API."""
    # Sanitise title for use as a filename
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    note_path = f"{vault_path}/{safe_title}.md"
    url = f"{host}/vault/{note_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/markdown",
    }
    response = requests.put(url, headers=headers, data=content.encode("utf-8"))
    response.raise_for_status()
    return note_path


# ── File event handler ────────────────────────────────────────────────────────

class SummaryHandler(FileSystemEventHandler):
    def __init__(self, config: dict, class_key: str):
        self.config = config
        self.class_cfg = config["classes"][class_key]
        self.processed: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        # MacWhisper exports summaries as "<title> Summary.txt" or "<title> Summary.md"
        if "summary" in path.stem.lower() and path.suffix in (".txt", ".md"):
            self._handle(path)

    def _handle(self, path: Path):
        if str(path) in self.processed:
            return
        self.processed.add(str(path))

        # Wait briefly to ensure the file is fully written
        time.sleep(2)

        print(f"→ Detected summary: {path.name}")
        summary = path.read_text(encoding="utf-8").strip()
        if not summary:
            print("  Summary file is empty, skipping.")
            return

        # Derive note title from filename: strip " Summary" suffix
        title = re.sub(r"\s*[Ss]ummary$", "", path.stem).strip()
        if not title:
            title = f"Class Notes {date.today().isoformat()}"

        print(f"  Reformatting with Claude...")
        tags = self.class_cfg.get("tags", self.config.get("default_tags", []))
        note_content = reformat_with_claude(summary, tags)

        print(f"  Pushing to Obsidian...")
        cfg = self.config
        note_path = push_to_obsidian(
            host=cfg["obsidian_host"],
            token=cfg["obsidian_token"],
            vault_path=self.class_cfg["vault_path"],
            title=title,
            content=note_content,
        )
        print(f"  ✓ Note created: {note_path}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Watch for MacWhisper summaries and push to Obsidian.")
    parser.add_argument(
        "--class", dest="class_key", required=True,
        help="Class key from config (e.g. 'advanced-edm')",
    )
    args = parser.parse_args()

    config = load_config()

    if args.class_key not in config.get("classes", {}):
        available = ", ".join(config["classes"].keys())
        print(f"Error: class '{args.class_key}' not found in config. Available: {available}")
        sys.exit(1)

    watch_dir = Path(config["watch_dir"]).expanduser()
    if not watch_dir.exists():
        print(f"Error: watch directory does not exist: {watch_dir}")
        sys.exit(1)

    class_name = config["classes"][args.class_key]["name"]
    print(f"Watching {watch_dir} for summaries...")
    print(f"Class: {class_name}")
    print(f"Vault path: {config['classes'][args.class_key]['vault_path']}")
    print("Press Ctrl+C to stop.\n")

    handler = SummaryHandler(config, args.class_key)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()

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
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import argparse

from datetime import date
from pathlib import Path
from urllib.parse import quote
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".config" / "class-notes" / "config.toml"

DEFAULT_CONFIG = """\
# class-notes configuration

# Folder MacWhisper exports summaries to
watch_dir = "~/Documents/MacWhisper"

# Obsidian REST API
obsidian_host = "https://127.0.0.1:27124"
obsidian_token = "YOUR_OBSIDIAN_TOKEN_HERE"

# Vault root (relative paths below are relative to your vault root)
# The REST API handles vault-relative paths automatically.

# Class definitions: each entry maps a short key to a display name and vault path.
# When running the watcher, pass --class <key> to select the active class.
[classes]

  [classes.my-class]
  name = "My Class"
  vault_path = "Classes/My Class"
  tags = ["class"]
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
Use headers like ## Key Concepts, ## Techniques as appropriate. \
Do not include an Action Items section. Do not include the original frontmatter or any preamble — output only the final note content.

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
    # Use .replace() instead of .format() so braces in the summary don't crash
    prompt = (
        REFORMAT_PROMPT
        .replace("{date}", date.today().isoformat())
        .replace("{tags}", tags_yaml)
        .replace("{summary}", summary)
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    block = message.content[0]
    if not isinstance(block, anthropic.types.TextBlock):
        raise ValueError(f"Unexpected content block type: {type(block)}")
    return block.text


def push_to_obsidian(host: str, token: str, vault_path: str, title: str, content: str) -> str:
    """PUT a markdown file into the Obsidian vault via Local REST API."""
    # Sanitise title for use as a filename
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    note_path = f"{vault_path}/{safe_title}.md"
    url = f"{host}/vault/{quote(note_path)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/markdown",
    }
    response = requests.put(url, headers=headers, data=content.encode("utf-8"), verify=False)
    response.raise_for_status()
    return note_path


# ── File event handler ────────────────────────────────────────────────────────

class SummaryHandler(FileSystemEventHandler):
    def __init__(self, config: dict, class_key: str):
        self.config = config
        self.class_cfg = config["classes"][class_key]
        self.processed: set[str] = set()

    def _is_summary(self, path: Path) -> bool:
        return path.suffix == ".md"

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if self._is_summary(path):
            self._handle(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(event.dest_path))
        if self._is_summary(path):
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

        # Strip MacWhisper's trailing timestamp (e.g. "2026-05-20 21_57_23")
        title = re.sub(r"\s+\d{4}-\d{2}-\d{2} \d{2}_\d{2}_\d{2}$", "", path.stem).strip()
        if not title:
            title = f"Class Notes {date.today().isoformat()}"

        try:
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
        except Exception as e:
            print(f"  ✗ Failed to process {path.name}: {e}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    config = load_config()  # creates config on first run and exits if missing

    parser = argparse.ArgumentParser(description="Watch for MacWhisper summaries and push to Obsidian.")
    parser.add_argument(
        "--class", dest="class_key", required=True,
        help="Class key from config (e.g. 'advanced-edm')",
    )
    args = parser.parse_args()

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

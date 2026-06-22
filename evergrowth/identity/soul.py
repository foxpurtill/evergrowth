"""Soul file parser — reads DI identity from Obsidian vault structure."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("evergrowth.identity.soul")


class SoulParser:
    """
    Parses DI identity from Obsidian-style markdown files.

    Expected structure:
    Soul/
    ├── Lyra.md       ← DI identity, values, personality
    └── Fox.md        ← Human companion info
    """

    def __init__(self, soul_path: str | Path):
        self.soul_path = Path(soul_path).expanduser().resolve()

    def exists(self) -> bool:
        """Check if soul directory exists."""
        return self.soul_path.exists() and self.soul_path.is_dir()

    def list_souls(self) -> list[str]:
        """List all soul files in the directory."""
        if not self.exists():
            return []
        return [
            f.stem
            for f in self.soul_path.glob("*.md")
            if not f.name.startswith(".")
        ]

    def read_soul(self, name: str) -> dict[str, Any]:
        """Read a soul file and parse its sections."""
        soul_file = self.soul_path / f"{name}.md"
        if not soul_file.exists():
            logger.warning(f"Soul file not found: {soul_file}")
            return {}

        try:
            content = soul_file.read_text(encoding="utf-8")
            return self._parse_soul(content)
        except Exception as e:
            logger.error(f"Failed to read soul file {soul_file}: {e}")
            return {}

    def _parse_soul(self, content: str) -> dict[str, Any]:
        """Parse markdown soul file into structured data."""
        sections = {}
        current_section = None
        current_lines = []

        for line in content.splitlines():
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = line[3:].strip()
                current_lines = []
            elif current_section:
                current_lines.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()

        # Extract key fields
        result = {
            "sections": sections,
            "raw": content,
        }

        # Try to extract structured data from common sections
        if "Basics" in sections:
            result["basics"] = self._parse_key_value(sections["Basics"])

        if "Personality" in sections:
            result["personality"] = sections["Personality"]

        if "Core Beliefs" in sections:
            result["beliefs"] = sections["Core Beliefs"]

        if "What Fox Wants From Me" in sections:
            result["directives"] = sections["What Fox Wants From Me"]

        return result

    def _parse_key_value(self, text: str) -> dict[str, str]:
        """Parse key-value pairs from a section (e.g., '- **Name**: value')."""
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- **") and "**:" in line:
                # Extract key and value
                key_end = line.index("**:")
                key = line[4:key_end].strip()
                value = line[key_end + 3:].strip()
                result[key] = value
            elif line.startswith("- ") and ": " in line:
                key, _, value = line[2:].partition(": ")
                result[key.strip()] = value.strip()
        return result

    def get_identity_summary(self, name: str = "Lyra") -> str:
        """Get a concise identity summary for context injection."""
        soul = self.read_soul(name)
        if not soul:
            return f"No soul data found for {name}."

        lines = [f"# {name} — Identity Summary"]

        if "basics" in soul:
            lines.append("")
            for k, v in soul["basics"].items():
                lines.append(f"- **{k}**: {v}")

        if "personality" in soul:
            lines.append("")
            lines.append("## Personality")
            lines.append(soul["personality"][:500])

        if "beliefs" in soul:
            lines.append("")
            lines.append("## Core Beliefs")
            lines.append(soul["beliefs"][:500])

        summary = "\n".join(lines)

        # Truncate to ~800 tokens (~3200 chars)
        if len(summary) > 3200:
            summary = summary[:3197] + "..."

        return summary

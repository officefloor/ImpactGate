"""Measure configuration: which files are source, how to group, ignore globs.

Structural-decay focused: languages, ignore globs, test-path heuristics, and the
rename similarity threshold. (No bug-keyword mining — that belonged to the earlier
defect-prediction experiment, not to a structural-decay gate.)
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

# Extension -> language label. lizard picks its reader by filename, so this table only
# decides "is this a source file worth parsing", plus the label used in reports.
LANG_BY_EXT: dict[str, str] = {
    ".java": "java",
    ".cs": "csharp",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".py": "python",
    ".go": "go",
    ".kt": "kotlin", ".kts": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".rs": "rust",
    ".scala": "scala",
    ".m": "objectivec", ".mm": "objectivec",
    ".lua": "lua",
    ".ttcn": "ttcn",
}

DEFAULT_IGNORE = [
    "**/node_modules/**", "**/dist/**", "**/build/**", "**/target/**",
    "**/out/**", "**/bin/**", "**/obj/**", "**/third_party/**",
    "**/vendor/**", "**/vendors/**", "**/bower_components/**", "**/webjars/**",
    "**/.venv/**", "**/venv/**", "**/__pycache__/**", "**/.git/**",
    "**/*.min.js", "**/*.min.css", "**/*.bundle.js", "**/*.generated.*",
    "**/generated/**", "**/gen/**",
]

DEFAULT_TEST_PATTERNS = [
    "**/test/**", "**/tests/**", "**/__tests__/**", "**/spec/**",
    "**/*Test.*", "**/*Tests.*", "**/*_test.*", "**/test_*.*",
    "**/*.test.*", "**/*.spec.*",
]


@dataclass
class MeasureConfig:
    ignore: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE))
    test_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_TEST_PATTERNS))
    lang_by_ext: dict[str, str] = field(default_factory=lambda: dict(LANG_BY_EXT))
    rename_jaccard: float = 0.6     # body token-set similarity to call a rename
    max_diff_lines: int = 200_000   # skip pathological mega-diffs (generated dumps)

    def ext(self, path: str) -> str:
        i = path.rfind(".")
        return path[i:].lower() if i >= 0 else ""

    def is_source(self, path: str) -> bool:
        return not self.is_ignored(path) and self.ext(path) in self.lang_by_ext

    def language(self, path: str) -> str | None:
        return self.lang_by_ext.get(self.ext(path))

    def is_ignored(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pat) for pat in self.ignore)

    def is_test(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pat) for pat in self.test_patterns)

    @classmethod
    def load(cls, path: str | None) -> "MeasureConfig":
        cfg = cls()
        if not path:
            return cfg
        import yaml  # optional; only needed when a config file is passed
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        for key in ("rename_jaccard", "max_diff_lines"):
            if key in data:
                setattr(cfg, key, data[key])
        # ignore / test_patterns APPEND to the defaults (a config adds, never silently
        # drops). To start from scratch, set the matching `*_replace` key instead.
        cfg.ignore = list(data["ignore_replace"]) if "ignore_replace" in data \
            else cfg.ignore + list(data.get("ignore", []))
        cfg.test_patterns = list(data["test_patterns_replace"]) if "test_patterns_replace" in data \
            else cfg.test_patterns + list(data.get("test_patterns", []))
        if "lang_by_ext" in data:
            cfg.lang_by_ext.update(data["lang_by_ext"])
        return cfg

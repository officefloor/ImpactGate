"""Unit model + language-plugin registry.

A plugin parses one file version (bytes) into Units — a function/method with its
cohesion container, line range and cyclomatic complexity. Parsing is a pure function
of the bytes, so callers may cache by content hash.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Unit:
    """One function/method in one version of a file."""
    name: str          # identity within the file, e.g. "Owner::addOwner" or "helper"
    container: str     # cohesion scope for WMC_other: class name, or "" = file scope
    start_line: int    # 1-based, inclusive
    end_line: int
    cc: int            # cyclomatic complexity
    nloc: int


class LanguagePlugin:
    name: str = "base"
    extensions: tuple[str, ...] = ()      # empty = default fallback

    def parse(self, blob: bytes, path: str) -> list[Unit]:
        raise NotImplementedError


_REGISTRY: dict[str, LanguagePlugin] = {}


def register(plugin: LanguagePlugin, *, default: bool = False) -> None:
    for ext in plugin.extensions:
        _REGISTRY[ext] = plugin
    if default:
        _REGISTRY[""] = plugin


def get_plugin(ext: str) -> LanguagePlugin | None:
    return _REGISTRY.get(ext) or _REGISTRY.get("")

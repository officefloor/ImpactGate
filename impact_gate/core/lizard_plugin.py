"""Default multi-language plugin backed by lizard.

lizard gives per-function cyclomatic complexity, NLOC and line ranges across many
languages, and class-qualifies method names as ``Class::method`` where it can. We use
that qualifier as the cohesion container; free functions fall back to file scope
(container == "").
"""
from __future__ import annotations

import lizard

from .cognitive import cognitive_complexity
from .units import LanguagePlugin, Unit, register


def _container(name: str) -> tuple[str, str]:
    """"Owner::addOwner" -> ("Owner", "addOwner"); "helper" -> ("", "helper")."""
    if "::" in name:
        head, _, tail = name.rpartition("::")
        return head, tail
    return "", name


class LizardPlugin(LanguagePlugin):
    name = "lizard"
    extensions = ()      # registered as the default fallback for every known extension

    def parse(self, blob: bytes, path: str) -> list[Unit]:
        src = blob.decode("utf-8", errors="replace")
        try:
            info = lizard.analyze_file.analyze_source_code(path, src)
        except Exception:
            return []
        lines = src.split("\n")
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        units: list[Unit] = []
        for f in info.function_list:
            container, _short = _container(f.name)
            body = "\n".join(lines[f.start_line - 1:f.end_line])   # signature + body span
            units.append(Unit(
                name=f.name,
                container=container,
                start_line=f.start_line,
                end_line=f.end_line,
                cc=f.cyclomatic_complexity,
                nloc=f.nloc,
                cognitive=cognitive_complexity(body, ext),
            ))
        return units


register(LizardPlugin(), default=True)

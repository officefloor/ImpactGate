"""Git access: subprocess only, no network, no working-tree checkout required.

Trimmed to what the gate needs: blob streaming (cat-file --batch), a -U0 rename-aware
diff, and the diff parser. Reads objects directly, so it is safe against a read-only
clone and never mutates the repo.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass
class FileDiff:
    status: str = "M"           # A / M / D / R
    old_path: str | None = None
    new_path: str | None = None
    is_binary: bool = False
    added: list[tuple[int, int]] = field(default_factory=list)    # (start, count) in NEW file
    removed: list[tuple[int, int]] = field(default_factory=list)  # (start, count) in OLD file
    add_total: int = 0
    del_total: int = 0

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""


class GitRepo:
    def __init__(self, path: str):
        self.path = path
        self._batch: subprocess.Popen | None = None

    def _run(self, *args: str) -> str:
        out = subprocess.run(["git", "-C", self.path, "-c", "diff.mnemonicprefix=false", *args],
                             check=True, capture_output=True)
        return out.stdout.decode("utf-8", errors="replace")

    def diff(self, old: str, new: str) -> list[FileDiff]:
        """Parse a -U0 rename-aware diff into per-file line ranges + totals."""
        text = self._run("diff", "-U0", "-M", "--no-color", "--no-ext-diff",
                         "--find-renames", old, new)
        return parse_diff(text)

    # ---- blob streaming via a persistent cat-file --batch -----------------
    def _ensure_batch(self) -> subprocess.Popen:
        if self._batch is None or self._batch.poll() is not None:
            self._batch = subprocess.Popen(
                ["git", "-C", self.path, "cat-file", "--batch"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            )
        return self._batch

    def blob(self, rev: str, path: str) -> tuple[str, bytes] | None:
        """(<blob oid>, contents) of <rev>:<path>, or None if absent.

        An empty `rev` addresses the index (stage 0), i.e. ":path", used to read
        staged content without a checkout.
        """
        proc = self._ensure_batch()
        assert proc.stdin and proc.stdout
        proc.stdin.write(f"{rev}:{path}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode("utf-8", errors="replace").strip()
        if not header or header.endswith(("missing", "ambiguous")):
            return None
        parts = header.split()
        oid = parts[0]
        try:
            size = int(parts[-1])
        except ValueError:
            return None
        data = proc.stdout.read(size)
        proc.stdout.read(1)  # trailing newline
        return oid, data

    def close(self) -> None:
        if self._batch and self._batch.poll() is None:
            try:
                self._batch.stdin.close()  # type: ignore[union-attr]
                self._batch.terminate()
            except Exception:
                pass


def _parse_hunk_header(line: str) -> Hunk | None:
    # @@ -old_start[,old_count] +new_start[,new_count] @@ ...
    try:
        body = line[3:line.index(" @@", 3)]
        old_part, new_part = body.split(" +")
        old_part = old_part.lstrip("-")

        def rng(s: str) -> tuple[int, int]:
            if "," in s:
                a, b = s.split(",")
                return int(a), int(b)
            return int(s), 1

        os_, oc = rng(old_part)
        ns_, nc = rng(new_part)
        return Hunk(os_, oc, ns_, nc)
    except (ValueError, IndexError):
        return None


def _dequote_path(raw: str) -> str:
    """Reverse git's C-style diff path quoting (default core.quotePath=true).

    A path with special or non-ASCII bytes appears wrapped in double quotes with
    C escapes, e.g. `"caf\303\251.py"` for `café.py`. Returns the raw path
    unchanged if it isn't quoted.
    """
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        return raw
    body = raw[1:-1]
    out = bytearray()
    i = 0
    simple_escapes = {"\\": "\\", '"': '"', "a": "\a", "b": "\b", "f": "\f",
                      "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in "01234567":
                j = i + 1
                end = min(j + 3, len(body))
                k = j
                while k < end and body[k] in "01234567":
                    k += 1
                out.append(int(body[j:k], 8) & 0xFF)
                i = k
                continue
            esc = simple_escapes.get(nxt)
            if esc is not None:
                out.extend(esc.encode("utf-8"))
                i += 2
                continue
        out.extend(c.encode("utf-8"))
        i += 1
    return out.decode("utf-8", errors="replace")


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    in_hunk = False
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            cur = FileDiff()
            files.append(cur)
            in_hunk = False
        elif cur is None:
            continue
        elif line.startswith("@@"):
            in_hunk = True
            h = _parse_hunk_header(line)
            if h:
                if h.old_count > 0:
                    cur.removed.append((h.old_start, h.old_count))
                    cur.del_total += h.old_count
                if h.new_count > 0:
                    cur.added.append((h.new_start, h.new_count))
                    cur.add_total += h.new_count
        elif in_hunk:
            continue
        elif line.startswith("new file"):
            cur.status = "A"
        elif line.startswith("deleted file"):
            cur.status = "D"
        elif line.startswith("rename from "):
            cur.status = "R"
            cur.old_path = _dequote_path(line[len("rename from "):])
        elif line.startswith("rename to "):
            cur.new_path = _dequote_path(line[len("rename to "):])
        elif line.startswith("copy to "):
            cur.new_path = _dequote_path(line[len("copy to "):])
        elif line.startswith("Binary files"):
            cur.is_binary = True
        elif line.startswith("--- "):
            # An unquoted path containing a space gets a trailing tab sentinel
            # so the boundary is unambiguous; strip it before dequoting.
            p = _dequote_path(line[4:].rstrip("\t"))
            if p != "/dev/null":
                cur.old_path = p[2:] if p.startswith(("a/", "b/")) else p
        elif line.startswith("+++ "):
            p = _dequote_path(line[4:].rstrip("\t"))
            if p != "/dev/null":
                cur.new_path = p[2:] if p.startswith(("a/", "b/")) else p
    return files

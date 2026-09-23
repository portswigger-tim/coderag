"""Language-neutral shapes the tree-sitter layer produces."""

from __future__ import annotations

from dataclasses import dataclass, field

# Why one symbol referenced another. Drives both the USES section of a context
# pack and how much weight the reference carries when ranking.
ReferenceVia = str  # "call" | "param" | "return" | "instantiates" | "constant" | "base"


@dataclass(slots=True)
class Symbol:
    """A definition: function, method, class, interface, struct, enum, const."""

    name: str
    kind: str
    start_line: int      # 1-indexed, inclusive
    end_line: int        # 1-indexed, inclusive
    signature: str = ""
    docstring: str = ""
    parent: str | None = None   # enclosing symbol's local name, for methods
    body: str = ""
    # Byte span, used to attribute references to their enclosing definition.
    # Lines are too coarse: `class C extends B { m() {} }` is one line, and
    # line-based attribution would hand B's reference to m() instead of C.
    start_byte: int = 0
    end_byte: int = 0

    @property
    def local_qname(self) -> str:
        """Name qualified within its file, e.g. 'PricingService.apply'."""
        return f"{self.parent}.{self.name}" if self.parent else self.name

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass(slots=True)
class Reference:
    """One symbol using another by name. Resolution happens later, repo-wide."""

    from_local_qname: str
    target_name: str
    via: ReferenceVia
    line: int
    byte: int = 0


@dataclass(slots=True)
class Import:
    """An import statement, kept unresolved until the repo-wide pass."""

    module: str                  # dotted or path-like, as written
    names: list[str] = field(default_factory=list)   # empty means whole-module
    alias: str | None = None
    line: int = 0


@dataclass(slots=True)
class ParsedFile:
    path: str
    lang: str
    symbols: list[Symbol] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    module_docstring: str = ""
    loc: int = 0
    # Set when the language has no type annotations to extract, so a context
    # pack can say so rather than implying the USES list is complete.
    types_unavailable: bool = False

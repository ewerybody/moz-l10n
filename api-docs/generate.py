#!/usr/bin/env python3
"""Generate moz-l10n Python API reference Markdown for the Zensical site.

The page layout is *discovered* from the `moz.l10n` package tree rather than
hand-maintained: the base pydoc-markdown config (loaders + renderer) lives in
`pyproject.toml`, and this script injects the pages before rendering. This way
new modules/formats show up in the docs automatically.

Layout rules (all pages land under `<docs_dir>/python/`):
  - the root package            -> `python/index.md`
  - a plain module (e.g. model) -> `python/<path>.md`
  - a "leaf" package            -> `python/<path>.md` (its own + submodule API,
                                    combined via a `.*` glob)
  - a "container" package       -> `python/<path>/index.md` listing only its own
    (one holding subpackages,      public members; each child gets its own page
     e.g. formats)                 by recursing the same rules

Run from anywhere via `npm run docgenpy`.
"""

from __future__ import annotations

import os
from pathlib import Path

import docspec
from pydoc_markdown import PydocMarkdown
from pydoc_markdown.contrib.renderers.mkdocs import MkdocsRenderer
from pydoc_markdown.util.pages import Page, Pages

ROOT_PACKAGE = "moz.l10n"
API_DOCS = Path(__file__).resolve().parent
REPO_ROOT = API_DOCS.parent
CONFIG = "pyproject.toml"

# Package paths (relative to ROOT_PACKAGE, dotted) to skip entirely. Empty by
# default so the reference stays complete; add e.g. "bin" here to drop them.
EXCLUDE: set[str] = set()

# docspec member kinds that represent documentable, defined API (as opposed to
# imports, which show up as Indirection).
_API_KINDS = (docspec.Class, docspec.Function, docspec.Variable)
_SKIP_MEMBERS = {"annotations", "__all__", "__doc__"}


def main() -> None:
    os.chdir(REPO_ROOT)

    pdm = PydocMarkdown()
    pdm.load_config(CONFIG)

    modules = pdm.load_modules()
    pdm.process(modules)

    pages = build_pages(modules)
    pages.insert(0, Page(title="Home", name="index", source="README.md"))
    # Make ty happy ensuring this is the correct renderer type.
    assert isinstance(pdm.renderer, MkdocsRenderer)
    pdm.renderer.pages = pages

    pdm.render(modules)

    print(
        f"Generated home page + {len(pages) - 1} Python API page(s) "
        "under api-docs/docs/"
    )


def _rel(name: str) -> str:
    """Path of `name` relative to the root package, dotted ('' for the root)."""
    if name == ROOT_PACKAGE:
        return ""
    return name[len(ROOT_PACKAGE) + 1 :]


def _excluded(name: str) -> bool:
    rel = _rel(name)
    return any(rel == e or rel.startswith(e + ".") for e in EXCLUDE)


def _slug(name: str) -> str:
    """`python/...` page name (no extension) for a module/package name."""
    rel = _rel(name)
    return "python/index" if rel == "" else "python/" + rel.replace(".", "/")


def _public_members(module: docspec.Module) -> list[str]:
    """Fully-qualified names of a module's own public, defined members."""
    return [
        f"{module.name}.{m.name}"
        for m in module.members
        if isinstance(m, _API_KINDS)
        and not m.name.startswith("_")
        and m.name not in _SKIP_MEMBERS
    ]


def build_pages(modules: list[docspec.Module]) -> Pages[Page]:
    by_name = {m.name: m for m in modules if not _excluded(m.name)}
    names = set(by_name)

    def direct_children(name: str) -> list[str]:
        prefix = name + "."
        return sorted(
            n for n in names if n.startswith(prefix) and "." not in n[len(prefix) :]
        )

    def is_package(name: str) -> bool:
        return bool(direct_children(name))

    def is_leaf_package(name: str) -> bool:
        children = direct_children(name)
        return bool(children) and not any(is_package(c) for c in children)

    pages: Pages[Page] = Pages()
    for name in sorted(names):
        children = direct_children(name)
        title = _rel(name).rsplit(".", 1)[-1] or ROOT_PACKAGE
        child_pkgs = [c for c in children if is_package(c)]

        # Submodules of a leaf package are folded into that package's single
        # page, so they get no page of their own.
        parent = name.rsplit(".", 1)[0]
        if not children and parent in names and is_leaf_package(parent):
            continue

        if not children:
            # Plain module: its own members.
            contents = [name, f"{name}.*"]
            page_name = _slug(name)
        elif child_pkgs:
            # Container package: only its own API; children get their own pages.
            contents = [name, *_public_members(by_name[name])]
            page_name = _slug(name)
            if name != ROOT_PACKAGE:
                page_name += "/index"
        else:
            # Leaf package: fold the whole subtree (own + submodules) into one page.
            contents = [f"{name}.*"]
            page_name = _slug(name)

        pages.append(Page(title=title, name=page_name, contents=contents))
    return pages


if __name__ == "__main__":
    main()

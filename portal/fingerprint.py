"""Reader code fingerprints that follow shared code automatically (FP_AUTO_V1, 2026-09-23).

A reader's code_sha must change whenever code that shapes its output changes, and only then. FP_NARROW (2026-09-23)
did this by hand for two readers: Economic Studies hashed the parts of the Resources reader it runs, Permits the parts
of the Technical reader. This module does it for any reader, without a list to maintain:

    from portal import fingerprint as FP
    SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, FP.code_sha(__file__, own=(C.__file__,)))

code_sha hashes the reader's file and its `own` helper files whole, then reads the reader's imports and, for every
other portal module it imports (`from portal import project_names as PN`, `from portal.extractors import technical
as T`), hashes exactly the code the reader reaches through that alias: each `PN.name` it uses, plus whatever those
use from the module's top level, followed to the end. A new shared helper, or a new borrowed function, is covered
the day it is imported; nobody has to remember to add it.

Not followed: portal.facts (the store's own types; a change there is a store change, gated separately) and the
standard library.
"""
import ast
import hashlib
import importlib
import os

NOT_FOLLOWED = {"portal.facts", "portal.fingerprint"}


def borrowed_source(mod, alias, user_file):
    """The source of the parts of `mod` that user_file uses through `alias`: every `alias.NAME`, plus whatever those
    use from mod's top level, followed to the end. A change anywhere else in mod leaves the result alone."""
    src = open(mod.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    top = {}
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in (ast.get_source_segment(src, node.test) or ""):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [(a.asname or a.name).split(".")[0] for a in node.names]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tg = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n.id for t in tg for n in ast.walk(t) if isinstance(n, ast.Name)]
        else:
            # module-level code that changes a name (a loop filling a table, a .update() call): filed under every
            # name it stores into or calls a method on
            names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]
            names += [n.value.id for n in ast.walk(node)
                      if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)]
        for nm in names:
            top.setdefault(nm, []).append(node)
    user = ast.parse(open(user_file, encoding="utf-8").read())
    want = sorted({n.attr for n in ast.walk(user)
                   if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == alias})
    seen, nodes, stack = set(), [], list(want)
    while stack:
        nm = stack.pop()
        if nm in seen:
            continue
        seen.add(nm)
        for node in top.get(nm, ()):
            if node not in nodes:
                nodes.append(node)
                stack.extend(n.id for n in ast.walk(node) if isinstance(n, ast.Name))
    lines = src.splitlines()
    parts = []
    for node in sorted(nodes, key=lambda n: n.lineno):
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        parts.append("\n".join(lines[first - 1:node.end_lineno]))
    return "uses " + " ".join(want) + "\n" + "\n\n".join(parts)


def portal_imports(user_file):
    """[(module name, alias)] for every portal module user_file imports at its top level."""
    tree = ast.parse(open(user_file, encoding="utf-8").read())
    out = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("portal"):
            for a in node.names:
                out.append((node.module + "." + a.name, a.asname or a.name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("portal."):
                    out.append((a.name, a.asname or a.name.split(".")[-1]))
    return out


def code_sha(user_file, own=()):
    """sha1 over user_file and `own` files whole, then the borrowed code of every other portal module user_file
    imports, in import order. Suffixed with the own files' names, like the readers' earlier fingerprints."""
    h = hashlib.sha1()
    whole = [os.path.abspath(user_file)] + [os.path.abspath(p) for p in own]
    for p in whole:
        with open(p, "rb") as fh:
            h.update(fh.read())
    for modname, alias in portal_imports(user_file):
        if modname in NOT_FOLLOWED:
            continue
        mod = importlib.import_module(modname)
        if os.path.abspath(mod.__file__) in whole:
            continue
        h.update(("\n# borrowed " + modname + "\n").encode("utf-8"))
        h.update(borrowed_source(mod, alias, user_file).encode("utf-8"))
    return h.hexdigest() + "".join("-" + os.path.basename(p) for p in own)


def uses(user_file, modname):
    """Does user_file import modname (e.g. "portal.project_names")? Used by the accuracy gate."""
    return any(m == modname for m, _a in portal_imports(user_file))

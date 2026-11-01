"""The §8.4 runtime rule, enforced by a test rather than by discipline.

Master Reference v1.0 §8.4, and `CLAUDE.md`: **no runtime machine translation
of anything a worker reads or hears; model-generated free text never reaches a
patient-facing surface. This holds regardless of what the code happens to do
today and will be enforced by a test.** This is that test.

It works on the import graph rather than on behaviour, deliberately. A
behavioural test can only catch a path it thinks to exercise; a reachability
assertion catches a path nobody thought about, including one added next year
by someone who never read the master document. If a new module calls a
language model, or an existing sender grows a dependency that reaches one,
this file fails and the author has to come here and say why.

Two allow-lists, each entry with its reason. Both are expected to shrink.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

#: Module names that may call a language model, each with the reason it is
#: permitted. Anything else that imports a model client fails this file.
PERMITTED_MODEL_CALLERS = {
    "services.population_intelligence": (
        "Aggregate narrative over a whole cohort for the dashboard, read by "
        "trained staff and never by a worker. Downstream of every clinical "
        "decision, with a deterministic fallback when the call fails (§4.3 "
        "module 4). This one is permanent."
    ),
    "services.ai_risk_engine": (
        "The prototype's classifier. On the classification path today, which "
        "§9.1 forbids: the deterministic cascade is the tier of record. "
        "Removed by item 1.9 (docs/IMPLEMENTATION_PLAN.md §7) -- this entry "
        "is a record of a known defect, not a permission."
    ),
}

#: Modules that put text in front of a worker: over SMS, over USSD, or on the
#: handset. None of them may reach a model caller, directly or transitively.
PATIENT_FACING_SENDERS = (
    "services.notifications",
    "services.ussd_handler",
    "services.education_messages",
    "services.tier_messages",
    "services.explanation_shona",
    "services.advice_engine",
    "services.referral_cascade",
    "services.referrals",
    "services.content_store",
    "routers.ussd",
    "routers.content",
)

#: Top-level names that belong to this codebase rather than to a dependency.
_LOCAL_ROOTS = {
    "services", "routers", "scripts",
    "database", "db_models", "models", "models_v2", "questions",
}
_MODEL_CLIENT_ROOTS = ("google",)


def _modules() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for package in ("services", "routers"):
        for path in sorted((BACKEND / package).glob("*.py")):
            if path.name != "__init__.py":
                out[f"{package}.{path.stem}"] = path
    out["main"] = BACKEND / "main.py"
    return out


def _imports(path: Path) -> tuple[set[str], bool]:
    """Local modules this file imports, and whether it imports a model client."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    local: set[str] = set()
    calls_model = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(_MODEL_CLIENT_ROOTS):
                calls_model = True
            if node.module.split(".")[0] in _LOCAL_ROOTS:
                if node.module in ("services", "routers"):
                    # `from services import notifications, outreach`
                    local.update(f"{node.module}.{alias.name}" for alias in node.names)
                else:
                    local.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_MODEL_CLIENT_ROOTS):
                    calls_model = True
                if alias.name.split(".")[0] in _LOCAL_ROOTS:
                    local.add(alias.name)
    return local, calls_model


@pytest.fixture(scope="module")
def graph():
    modules = _modules()
    edges: dict[str, set[str]] = {}
    callers: set[str] = set()
    for name, path in modules.items():
        local, calls_model = _imports(path)
        edges[name] = {dep for dep in local if dep in modules}
        if calls_model:
            callers.add(name)
    return edges, callers


def _reachable(edges: dict[str, set[str]], start: str) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        for dep in edges.get(stack.pop(), ()):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return seen


# ------------------------------------------------------- who may call a model

def test_only_permitted_modules_call_a_language_model(graph):
    """A new model caller has to be added to PERMITTED_MODEL_CALLERS with a
    written reason, which is the review conversation this test exists to
    force."""
    _, callers = graph
    assert callers == set(PERMITTED_MODEL_CALLERS), (
        "the set of modules calling a language model changed.\n"
        f"  now:      {sorted(callers)}\n"
        f"  permitted: {sorted(PERMITTED_MODEL_CALLERS)}\n"
        "Adding one means writing down why it is not on a patient-facing "
        "path (§8.4), or not adding it."
    )


def test_every_permitted_caller_carries_a_reason(graph):
    for module, reason in PERMITTED_MODEL_CALLERS.items():
        assert len(reason) > 40, f"{module} needs a real reason, not a label"


# --------------------------------------------- what a worker may be sent

@pytest.mark.parametrize("sender", PATIENT_FACING_SENDERS)
def test_no_patient_facing_sender_can_reach_a_language_model(graph, sender):
    """The core assertion. Every string these modules put in front of a worker
    must be traceable to a human author, so none of them may reach a model
    client by any import path."""
    edges, callers = graph
    assert sender in edges, f"{sender} no longer exists -- update this list"
    reached = _reachable(edges, sender) & callers
    assert not reached, (
        f"{sender} can reach {sorted(reached)}. Model-generated free text "
        "must never reach a patient-facing surface (§8.4). If this module no "
        "longer sends to a worker, take it out of PATIENT_FACING_SENDERS and "
        "say so; do not relax the assertion."
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known defect, item 1.9. routers/screening.py returns Gemini's "
        "explanation_english to the mobile application's result screen, which "
        "a worker reads -- so model text is on a patient-facing surface today. "
        "docs/IMPLEMENTATION_PLAN.md §7 removes it. strict=True means this "
        "flips to a HARD FAILURE the moment 1.9 lands, which is the signal to "
        "delete this marker and move routers.screening into "
        "PATIENT_FACING_SENDERS above."
    ),
)
def test_the_screening_route_is_free_of_model_text(graph):
    edges, callers = graph
    assert not (_reachable(edges, "routers.screening") & callers)


# ----------------------------------- the store cannot be a translation layer

def test_the_content_store_returns_only_stored_bytes(tmp_path):
    """§8.4's first clause. Whatever `render()` returns, minus the substituted
    values, is byte-for-byte the string an author wrote and the Clinical Lead
    approved -- there is no transformation step where a translation could be
    generated, and no code path that could add one without this failing."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    import database
    from db_models import Base, MessageText
    from services import content_store

    engine = create_engine(f"sqlite:///{tmp_path / 'rule.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        content_store.load(
            db,
            {
                "area": "runtime_rule",
                "messages": [
                    {
                        "code": "rule.check",
                        "channel": "app",
                        "status": "approved",
                        "approved_by": "Clinical Lead",
                        "approved_at": "2026-11-01",
                        "purpose": "Asserts that render returns stored bytes.",
                        "placeholders": ["who"],
                        "text": {
                            "en": "STORED ENGLISH for {who}.",
                            "sn": "TEST sn for {who}.",
                            "nd": "TEST nd for {who}.",
                        },
                    }
                ],
            },
        )
        db.commit()

        for language in ("en", "sn", "nd"):
            stored = db.scalar(
                select(MessageText.text_value).where(MessageText.language == language)
            )
            out = content_store.render(db, "rule.check", language, {"who": "X"})
            assert out["text"] == stored.replace("{who}", "X")
            assert out["language"] == language
    finally:
        db.close()


def test_the_store_has_no_write_route(client):
    """Content enters through a migration generated from `content/`, on a pull
    request the Clinical Lead approves (§11.4). An HTTP write route would be a
    way around that approval, which is the one thing this store exists to make
    impossible.

    Asserted against the running application rather than by introspecting the
    route table, because what matters is what a request can actually do."""
    assert client.get("/api/v2/content").status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, "/api/v2/content")
        assert response.status_code == 405, (
            f"{method} /api/v2/content returned "
            f"{response.status_code}, not 405. The content store is read-only "
            "over HTTP: a write route is a way around the Clinical Lead's "
            "approval."
        )


# --------------------------------------- the production boot path stays clean

#: Third-party packages that are in `requirements-dev.txt` but NOT in
#: `requirements.txt`, so they do not exist on the Render instance.
def _dev_only_packages() -> set[str]:
    def names(path):
        out = set()
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#")[0].strip()
            if not line or line.startswith("-r"):
                continue
            out.add(line.split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip().lower())
        return out

    runtime = names(BACKEND / "requirements.txt")
    return names(BACKEND / "requirements-dev.txt") - runtime


#: Import name where it differs from the distribution name.
_IMPORT_NAMES = {"pyyaml": "yaml"}

#: `requests` is listed in requirements-dev.txt and also arrives in
#: production transitively, via google-genai -> google-auth. Treating it as
#: dev-only here is deliberately conservative: a runtime module that imports
#: it directly would be depending on another package's dependency, which
#: breaks the day that package changes transport. Africa's Talking is called
#: over httpx, which is a declared runtime dependency.


def test_no_runtime_module_imports_a_dev_only_dependency():
    """`main.py` imports every router, so anything a router can reach runs on
    the production instance at boot.

    This exists because the content store very nearly shipped importing
    `scripts/validate_content.py` for its septet arithmetic. That script
    imports PyYAML at module level, PyYAML is deliberately dev-only, and the
    result would have been `ModuleNotFoundError` on the Render boot -- the same
    class of failure as 11 September, where `init_db()` took the whole API
    down. The arithmetic moved to `services/content_format.py`, which has no
    dependencies, and this test keeps it that way.

    A validator, a seed script or a migration may use a dev-only package. A
    module reachable from a router may not.
    """
    dev_only = _dev_only_packages()
    assert dev_only, "expected requirements-dev.txt to add packages"
    forbidden = {_IMPORT_NAMES.get(name, name) for name in dev_only}

    modules = _modules()
    offences: list[str] = []
    for name, path in modules.items():
        if name == "main":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots = [node.module.split(".")[0]]
            elif isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            for root in roots:
                if root in forbidden:
                    offences.append(f"{name} imports {root} (line {node.lineno})")

    assert not offences, (
        "a module reachable from a router imports a package that is not in "
        "requirements.txt, so the production boot would fail with "
        "ModuleNotFoundError:\n  " + "\n  ".join(offences) +
        f"\ndev-only packages: {sorted(forbidden)}"
    )

"""
Build script to wrap commands for docs, test coverage, badge generation, etc.

Generate coverage reports:
  scons cov

Clean coverage reports:
  scons cov --clean
"""

from SCons import Node
from typing import Callable
import json
import subprocess


def run(*args, **kwargs) -> subprocess.CompletedProcess:
    """
    Run the command and return the CompletedProcess. Essentially a wrapper for
    subprocess.run() with custom defaults.
    """
    cmd = list(args)

    print(f"Running: {' '.join(cmd)}")

    process: subprocess.CompletedProcess = subprocess.run(
        cmd, text=True, **kwargs
    )

    return process


def alias(
    name: str,
    targets: list[Node],
    sources: list[Node],
    builder: Callable,
    always: bool = False,
    shell: bool = True,
):
    """
    Create and return an alias, and perform bookkeeping.
    """
    node = env.Command(targets, sources, builder, shell=shell)
    env.Clean(node, targets)

    if always:
        AlwaysBuild(node)

    return env.Alias(name, node)


env = Environment()

PACKAGE = "trilium_alchemy"

BUILD_DIR = "build"

# output directories
TEST_BUILD_DIR = f"{BUILD_DIR}/test"
MYPY_BUILD_DIR = f"{BUILD_DIR}/mypy"
PYRIGHT_BUILD_DIR = f"{BUILD_DIR}/pyright"
DOC_BUILD_DIR = f"{BUILD_DIR}/doc"
BADGE_BUILD_DIR = "badges"

# ------------------------------------------------------------------------------
# Alias: test
# ------------------------------------------------------------------------------
test_junit = env.File(f"{TEST_BUILD_DIR}/junit.xml")
test_cov_data = env.File(f"{TEST_BUILD_DIR}/.coverage")
test_cov_html = env.Dir(f"{TEST_BUILD_DIR}/htmlcov")
test_cov_xml = env.File(f"{TEST_BUILD_DIR}/coverage.xml")

test_targets = [
    test_junit,
    test_cov_data,
    test_cov_html,
    test_cov_xml,
]


def run_pytest(target, source, env):
    run(
        "pytest",
        "--cov",
        "--cov-report=html",
        "--cov-report=xml",
        f"--junitxml={str(target[0])}",
    )


test = alias("test", test_targets, [], run_pytest)

# ------------------------------------------------------------------------------
# Alias: mypy
# ------------------------------------------------------------------------------
mypy_html = env.Dir(f"{MYPY_BUILD_DIR}/html")
mypy_xml = env.Dir(f"{MYPY_BUILD_DIR}/xml")

mypy_targets = [
    mypy_html,
    mypy_xml,
]


def run_mypy(target, source, env):
    process = run(
        "mypy",
        "--html-report",
        str(target[0]),
        "--cobertura-xml-report",
        str(target[1]),
        PACKAGE,
    )


mypy = alias("mypy", mypy_targets, [], run_mypy, always=True)

# ------------------------------------------------------------------------------
# Alias: pyright
# ------------------------------------------------------------------------------
pyright_json = env.File(f"{PYRIGHT_BUILD_DIR}/report.json")

pyright_targets = [
    pyright_json,
]


def run_pyright(target, source, env):
    process = run(
        "pyright",
        "--outputjson",
        PACKAGE,
        capture_output=True,
    )

    with open(str(target[0]), "w") as fh:
        fh.write(process.stdout)
    print(f"Saved pyright report to: {str(target[0])}")

    # parse report
    report = json.loads(process.stdout)

    errors = report["summary"]["errorCount"]
    warnings = report["summary"]["warningCount"]

    print(f"  {errors} errors, {warnings} warnings")


pyright = alias("pyright", pyright_targets, [], run_pyright, always=True)

# ------------------------------------------------------------------------------
# Alias: analysis
# ------------------------------------------------------------------------------
analysis = env.Alias("analysis", [mypy, pyright])

# ------------------------------------------------------------------------------
# Alias: doc
# ------------------------------------------------------------------------------
doc_html = env.Dir(f"{DOC_BUILD_DIR}/html")

doc_targets = [
    doc_html,
]


def run_sphinx(target, source, env):
    run(
        "sphinx-build",
        "-T",  # show full traceback upon error
        "doc",
        str(target[0]),
    )


# always=True to always rebuild and rely on sphinx's caching mechanism
doc = alias("doc", doc_targets, [], run_sphinx, always=True)

# ------------------------------------------------------------------------------
# Alias: badges
# ------------------------------------------------------------------------------
badge_pytest = env.File(f"{BADGE_BUILD_DIR}/tests.svg")
badge_cov = env.File(f"{BADGE_BUILD_DIR}/cov.svg")

badge_targets = [
    badge_pytest,
    badge_cov,
]


def run_genbadge(target, source, env):
    run(
        "genbadge",
        "tests",
        "-i",
        str(source[0]),
        "-o",
        str(target[0]),
    )

    run(
        "genbadge",
        "coverage",
        "-i",
        str(source[1]),
        "-o",
        str(target[1]),
    )


badges = alias(
    "badges", badge_targets, [test_junit, test_cov_xml], run_genbadge
)


# ------------------------------------------------------------------------------
# Alias: format
# ------------------------------------------------------------------------------
def run_format(target, source, env):
    run(
        "black",
        ".",
    )

    run(
        "toml-sort",
        "-i",
        "pyproject.toml",
    )


format_ = alias("format", ["format"], [], run_format, always=True)

"""
Doit file to wrap development workflow commands.
"""

from pathlib import Path
import shutil

from doit.task import Task
from doit.tools import create_folder


PACKAGE = "trilium_alchemy"

# badges output
BADGES_PATH = Path("badges")
PYTEST_BADGE = BADGES_PATH / "tests.svg"
COV_BADGE = BADGES_PATH / "cov.svg"

# artifact output
OUT_PATH = Path("__out__")

# test coverage results
TESTS_PATH = OUT_PATH / "test"
JUNIT_PATH = TESTS_PATH / "junit.xml"
COV_PATH = TESTS_PATH / "cov"
COV_HTML_PATH = COV_PATH / "html"
COV_XML_PATH = COV_PATH / "coverage.xml"

# documentation
DOC_PATH = OUT_PATH / "doc"
DOC_HTML_PATH = DOC_PATH / "html"

# static analysis results
ANALYSIS_PATH = OUT_PATH / "analysis"
MYPY_PATH = ANALYSIS_PATH / "mypy"
MYPY_HTML_PATH = MYPY_PATH / "html"
MYPY_XML_PATH = MYPY_PATH / "xml"
PYRIGHT_PATH = ANALYSIS_PATH / "pyright"
PYRIGHT_JSON_PATH = PYRIGHT_PATH / "report.json"


def cleanup_dir(output_dir: Path):
    if output_dir.exists():
        shutil.rmtree(output_dir)


def task_pytest() -> Task:
    """
    Run pytest and generate coverage reports.
    """

    args = [
        "pytest",
        f"--cov={PACKAGE}",
        f"--cov-report=html:{COV_HTML_PATH}",
        f"--cov-report=xml:{COV_XML_PATH}",
        f"--junitxml={JUNIT_PATH}",
    ]

    return Task(
        "test",
        actions=[
            (create_folder, [COV_PATH]),
            " ".join(args),
        ],
        targets=[
            f"{COV_HTML_PATH}/index.html",
            COV_XML_PATH,
            JUNIT_PATH,
        ],
        file_dep=[],
        clean=[(cleanup_dir, [COV_PATH])],
    )


def task_badges() -> Task:
    """
    Generate badges from coverage results.
    """

    tests_args = [
        "genbadge",
        "tests",
        f"-i {JUNIT_PATH}",
        f"-o {PYTEST_BADGE}",
    ]

    cov_args = [
        "genbadge",
        "coverage",
        f"-i {COV_XML_PATH}",
        f"-o {COV_BADGE}",
    ]

    return Task(
        "badges",
        actions=[
            (create_folder, [BADGES_PATH]),
            " ".join(tests_args),
            " ".join(cov_args),
        ],
        targets=[
            PYTEST_BADGE,
            COV_BADGE,
        ],
        file_dep=[
            JUNIT_PATH,
            COV_XML_PATH,
        ],
    )


def task_doc() -> Task:
    """
    Generate documentation.
    """

    args = [
        "sphinx-build",
        "-T",  # show full traceback upon error
        "doc",
        str(DOC_HTML_PATH),
    ]

    return Task(
        "doc",
        actions=[
            (create_folder, [DOC_HTML_PATH]),
            " ".join(args),
        ],
        targets=[
            f"{DOC_HTML_PATH}/index.html",
        ],
        file_dep=[],
        clean=[(cleanup_dir, [DOC_HTML_PATH])],
    )


def task_format() -> Task:
    """
    Run formatters.
    """

    black_args = [
        "black",
        ".",
    ]

    toml_sort_args = [
        "toml-sort",
        "-i",
        "pyproject.toml",
    ]

    return Task(
        "format",
        actions=[
            " ".join(black_args),
            " ".join(toml_sort_args),
        ],
        targets=[],
        file_dep=[],
    )


def task_analysis() -> Task:
    """
    Run static analysis tools.
    """

    # TODO: command line option to filter specific path

    mypy_args = [
        "mypy",
        "--html-report",
        str(MYPY_HTML_PATH),
        "--cobertura-xml-report",
        str(MYPY_XML_PATH),
        PACKAGE,
    ]

    # TODO: get json output from stdout
    pyright_args = [
        "pyright",
        PACKAGE,
    ]

    return Task(
        "analysis",
        actions=[
            " ".join(mypy_args),
            " ".join(pyright_args),
        ],
        targets=[],
        file_dep=[],
    )

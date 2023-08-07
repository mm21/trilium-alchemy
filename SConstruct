"""
Build script to wrap commands for docs, test coverage, badge generation, etc.

Generate coverage reports:
  scons cov

Clean coverage reports:
  scons cov --clean
"""

import subprocess

env = Environment()

PACKAGE = "trilium_client"
BUILD_DIR = "build"

TEST_BUILD_DIR = f"{BUILD_DIR}/test"
test_junit = env.File(f"{TEST_BUILD_DIR}/junit.xml")
test_cov_data = env.File(f"{TEST_BUILD_DIR}/.coverage")
test_cov_html = env.Dir(f"{TEST_BUILD_DIR}/htmlcov")
test_cov_xml = env.File(f"{TEST_BUILD_DIR}/coverage.xml")

test_artifacts = [
    test_junit,
    test_cov_data,
    test_cov_html,
    test_cov_xml,
]

DOC_BUILD_DIR = f"{BUILD_DIR}/doc"
doc_html = env.Dir(f"{DOC_BUILD_DIR}/html")
doc_source = env.Dir("doc/source")

BADGE_BUILD_DIR = "badges"
badge_pytest = env.File(f"{BADGE_BUILD_DIR}/tests.svg")
badge_cov = env.File(f"{BADGE_BUILD_DIR}/cov.svg")

badge_artifacts = [
    badge_pytest,
    badge_cov,
]


def run(*args):
    cmd = list(args)

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)


def run_pytest(target, source, env):
    run(
        "pytest",
        "--cov",
        "--cov-report=html",
        "--cov-report=xml",
        f"--junitxml={str(target[0])}",
    )


def run_sphinx(target, source, env):
    run(
        "sphinx-build",
        "-T",  # show full traceback upon error
        str(source[0]),
        str(target[0]),
    )


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


# tests
test = env.Command(test_artifacts, [], run_pytest, shell=True)
env.Clean(test, test_artifacts)
env.Alias("test", test)

# html docs
html = env.Command(doc_html, doc_source, run_sphinx, shell=True)
env.Clean(html, doc_html)
env.Alias("html", html)
AlwaysBuild(html)

# badges
badges = env.Command(
    badge_artifacts, [test_junit, test_cov_xml], run_genbadge, shell=True
)
env.Clean(badges, badge_artifacts)
env.Alias("badges", badges)

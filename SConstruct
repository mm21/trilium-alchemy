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

COV_BUILD_DIR = f"{BUILD_DIR}/cov"
cov_data = env.File(f"{COV_BUILD_DIR}/.coverage")
cov_html = env.Dir(f"{COV_BUILD_DIR}/htmlcov")
cov_xml = env.File(f"{COV_BUILD_DIR}/coverage.xml")

cov_artifacts = [
    cov_data,
    cov_html,
    cov_xml,
]

DOC_BUILD_DIR = f"{BUILD_DIR}/doc"
doc_html = env.Dir(f"{DOC_BUILD_DIR}/html")
doc_source = env.Dir("doc/source")


def run(*args):
    cmd = list(args)

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)


def run_pytest_cov(target, source, env):
    run(
        "pytest",
        "--cov",
        "--cov-report=html",
        "--cov-report=xml",
    )


def run_sphinx(target, source, env):
    run(
        "sphinx-build",
        "-T",  # show full traceback upon error
        str(source[0]),
        str(target[0]),
    )


# coverage
cov = env.Command(cov_artifacts, [], run_pytest_cov, shell=True)
env.Clean(cov, cov_artifacts)
env.Alias("cov", cov)

# html docs
html = env.Command(doc_html, doc_source, run_sphinx, shell=True)
env.Clean(html, doc_html)
env.Alias("html", html)
AlwaysBuild(html)

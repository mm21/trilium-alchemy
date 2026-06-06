import nox
from nox import Session

nox.options.envdir = "__cache__/nox"

PYTHON_VERSIONS = [
    "3.12.13",
    "3.13.13",
]


@nox.session(python=PYTHON_VERSIONS)
def test(session: Session):
    session.run_install(
        "uv",
        "sync",
        "--group=dev",
        "--frozen",
        f"--python={session.python}",  # explicitly pin the version
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("pytest", *session.posargs)

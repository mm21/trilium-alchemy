from dataclasses import replace

from pyprojkit import (
    DocConfig,
    ProjectConfig,
    PythonVersions,
    RequiresPython,
    SphinxConfig,
    create_kitchen_sink_tools,
)

config = ProjectConfig(
    package="trilium_alchemy",
    requires_python=RequiresPython((3, 12)),
    pinned_python=PythonVersions(3, (12, 14)),
    tools=replace(
        create_kitchen_sink_tools(),
        doc=DocConfig(sphinx=SphinxConfig(copy_env_var="TRILIUM_ALCHEMY_DOCS_DIR")),
    ),
)

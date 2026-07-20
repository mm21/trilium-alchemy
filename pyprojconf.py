from dataclasses import replace

from pyprojkit import (
    AnalysisConfig,
    DocConfig,
    ProjectConfig,
    PythonVersions,
    SphinxConfig,
    ToolsConfig,
)

config = ProjectConfig(
    package="trilium_alchemy",
    python=PythonVersions(3, (12, 14)),
    packages_dir="src",
    tools=replace(
        ToolsConfig.default(),
        doc=DocConfig(sphinx=SphinxConfig(copy_env_var="TRILIUM_ALCHEMY_DOCS_DIR")),
        analysis=AnalysisConfig(),
    ),
)

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys

import sphinx
import autodoc2
import trilium_alchemy

sys.path.append(".")
import util

project = "TriliumAlchemy"
copyright = "2023, mm21"
author = "mm21"
release = "0.1.0"

package = "trilium_alchemy"

env = util.Env(package)

# -- General configuration -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

keep_warnings = True

default_role = "any"

extensions = [
    "myst_parser",
    "autodoc2",
    "sphinx.ext.githubpages",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx_copybutton",
    "sphinxcontrib.plantuml",
]

myst_enable_extensions = [
    "colon_fence",
    "fieldlist",
    "attrs_inline",
]

suppress_warnings = ["myst.header"]

todo_include_todos = True
todo_link_only = True

autodoc2_packages = [
    "../../trilium_alchemy",
]
autodoc2_index_template = None
autodoc2_render_plugin = "renderer.MystRenderer"
autodoc2_output_dir = "build/autodoc2"
autodoc2_module_all_regexes = [".*"]
autodoc2_hidden_objects = ["dunder", "private"]
autodoc2_class_inheritance = True
autodoc2_docstrings = "all"

# TODO: this can be used to avoid some custom operations, but it would need
# to be set after symbols are populated in db_fixup to avoid hard-coding
# a long list here
"""
autodoc2_replace_annotations = [
    ('trilium_alchemy.core.note.Note', 'Note')
]
"""

# custom config to enable setting "all" and creating canonical mappings
# TODO: need to discuss/submit PR
autodoc2_db_fixup = env.db_fixup

toc_object_entries_show_parents = "hide"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    # "packaging": ("https://packaging.pypa.io/en/latest", None),
}

templates_path = ["_templates"]
exclude_patterns = []

plantuml_output_format = "svg_img"


# -- Options for HTML output ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme_options = {
#    "announcement": "",
# }

html_baseurl = "https://mm21.github.com/trilium-alchemy/"

html_theme = "furo"

html_title = "TriliumAlchemy"

html_theme_options = {
    "light_logo": "logo-light.svg",
    "dark_logo": "logo-dark.svg",
}

html_static_path = ["_static"]

html_js_files = ["custom.js"]

# -- Custom config -------------------------------------------------------------


def setup(app):
    app.connect("doctree-read", env.doctree_read)
    app.add_css_file("custom.css")

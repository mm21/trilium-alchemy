"""
TriliumAlchemy wrapper for VSCode-Dark theme: 
https://github.com/greengeek/trilium-vscode-dark-theme
"""

from trilium_alchemy import BaseThemeNote


class VSCodeDark(BaseThemeNote):
    theme_name = "VSCode-Dark"
    content_file = "vscode-dark.css"

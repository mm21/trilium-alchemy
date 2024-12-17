"""
Root note and top-level hierarchy.
"""

from trilium_alchemy import BaseRootNote, BaseRootSystemNote, children, label

from .events import Events
from .extensions.themes.vscode_dark import VSCodeDark
from .people import People
from .places import Places


class System(BaseRootSystemNote):
    """
    Root `System` note.
    """

    themes = [VSCodeDark]


@label("eventTrackerRoot")  # define on a note manually for installation
@label("hideChildrenOverview", inheritable=True)
@children(
    People,
    Places,
    Events,
)
class Root(BaseRootNote):
    title = "EventTracker"
    system = System

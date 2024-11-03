from trilium_alchemy import BaseRoot, BaseRootSystem, children, label

from .events import Events
from .extensions.themes.vscode_dark import VSCodeDark
from .people import People
from .places import Places


class System(BaseRootSystem):
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
class Root(BaseRoot):
    title = "EventTracker"
    system = System

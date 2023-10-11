"""
This package will contain functionality related to synchronization of subtrees
from multiple {obj}`Session`s. There will tentatively be a `SyncState` which 
encapsulates the metadata of the subtree when it was last synced. This will 
be used to determine deltas (creates/updates/deletes) for each of the sessions
compared to the last sync.

To initially build `SyncState`, it can be created from any
{obj}`Session`.
"""

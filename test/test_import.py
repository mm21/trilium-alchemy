from abc import ABCMeta
import trilium_alchemy


def test_import():
    # make sure symbols are accessible by fully qualified path
    assert isinstance(trilium_alchemy.core.Session, type)
    assert isinstance(trilium_alchemy.core.note.Note, ABCMeta)
    assert isinstance(trilium_alchemy.core.branch.Branch, ABCMeta)
    assert isinstance(trilium_alchemy.core.attribute.Label, type)
    assert isinstance(trilium_alchemy.core.attribute.Relation, type)
    assert isinstance(trilium_alchemy.core.attribute.Attribute, ABCMeta)
    assert isinstance(trilium_alchemy.core.entity.Entity, ABCMeta)

    # ensure no internal symbols accidentally exported
    assert all([not sym.startswith("_") for sym in trilium_alchemy.__all__])

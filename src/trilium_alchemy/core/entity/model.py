from __future__ import annotations

from abc import ABC, abstractmethod

from alchemizer import BaseDriver as _BaseDriver
from alchemizer import BaseEntityModel as _BaseEntityModel
from pydantic import BaseModel
from trilium_client.models.attachment import Attachment as EtapiAttachmentModel
from trilium_client.models.attribute import Attribute as EtapiAttributeModel
from trilium_client.models.branch import Branch as EtapiBranchModel
from trilium_client.models.note import Note as EtapiNoteModel

from ..session import Session


class BaseDriver[ModelT: BaseModel](_BaseDriver[Session, ModelT], ABC):
    """
    Implements interface to backing store for note, either to Trilium itself (through
    ETAPI) or another mechanism like a filesystem.
    """


class BaseEntityModel[EtapiModelT: BaseModel, DriverT: BaseDriver](
    _BaseEntityModel[EtapiModelT, DriverT], ABC
):
    """
    Abstraction of data model which is stored as a record in Trilium's database,
    encapsulating both locally modified data and data as received from Trilium.
    """

    @property
    @abstractmethod
    def etapi_model(self) -> type[EtapiModelT]:
        """
        Pydantic model used in etapi.
        """
        ...

    def check_newer(self, model: EtapiModelT) -> bool:
        assert isinstance(
            model,
            (
                EtapiNoteModel,
                EtapiAttributeModel,
                EtapiBranchModel,
                EtapiAttachmentModel,
            ),
        )
        assert model.utc_date_modified
        return (
            self.backing_data is None
            or model.utc_date_modified > self.backing_data["utc_date_modified"]
        )

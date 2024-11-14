"""
Implementation of session functionality.

Eventually will be generalized to accommodate different types of sessions:
- Filesystem-based (yaml descriptors for note metadata)
- Database-based (Apache couchdb?)
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Iterable
from enum import Enum, auto
from typing import TYPE_CHECKING, Callable, Literal, cast

import requests
from trilium_client import ApiClient, Configuration, DefaultApi
from trilium_client.exceptions import ApiException
from trilium_client.models.app_info import AppInfo
from trilium_client.models.branch import Branch as EtapiBranchModel
from trilium_client.models.login201_response import Login201Response
from trilium_client.models.login_request import LoginRequest
from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.search_response import SearchResponse

from .cache import Cache

if TYPE_CHECKING:
    from .entity.entity import BaseEntity
    from .entity.types import State
    from .note.note import Note

__all__ = ["Session"]

default_session: Session | None = None


class SessionType(Enum):
    """
    Type of session.
    """

    ETAPI = auto()
    """Interface to Trilium server"""

    FILE = auto()
    """Interface to filesystem"""


class Session:
    """
    Interface to Trilium and context in which to store changes to entities.

    Changes to entities are tracked as they're made by the user. The user
    must then invoke {obj}`Session.flush` to commit them.

    For details and example usage, see {ref}`sessions` in the
    user guide.
    """

    _type = SessionType.ETAPI
    """
    Type of session.
    """

    _host: str
    """
    Host as configured by user.
    """

    _token: str
    """
    Token as passed by user, or returned by Trilium if a `password` was
    provided by user.
    """

    _api: DefaultApi | None
    """
    ETAPI client object.
    """

    _cache: Cache
    """
    Cache object.
    """

    _etapi_headers: dict[str, str]
    """
    Common ETAPI HTTP headers for manual requests.
    """

    _root_position_base_val: int | None = None
    """
    Base position of root tree (just the position of root__hidden branch).
    Access using Session._root_position_base.
    """

    _logout_pending: bool = False
    """
    Indicates if this session was created using a password rather than API
    token. In that case, the Session will automatically logout when exiting
    a context, and logout() will invoke the logout API.
    """

    _root: Note
    """
    Root note.
    """

    def __init__(
        self,
        host: str,
        token: str | None = None,
        password: str | None = None,
        default: bool = True,
    ):
        """
        Either `token` or `password` is required; if both are provided, `token`
        takes precedence.

        :param host: Hostname of Trilium server
        :param token: ETAPI token
        :param password: Trilium password, if no token provided
        :param default: Register this as the default session; in this case, `session` may be omitted from entity constructors
        """

        from .note.note import Note

        # ensure no existing default session, if requested to use as default
        if default:
            global default_session
            assert (
                default_session is None
            ), f"Attempt to create default Session {self} when default {default_session} already registered"
            default_session = self

        if token is None:
            # get token from password
            assert (
                password is not None
            ), "Either token or password is required to connect to Trilium"

            # get token from password
            token = Session.login(host, password)

            # set flag to enable logging out later
            self._logout_pending = True

        self._host = host
        self._token = token
        self._etapi_headers = {"Authorization": self._token}

        # create ETAPI client config
        config = Configuration(
            host=self._base_path, api_key={"EtapiTokenAuth": token}
        )

        # create api
        self._api = DefaultApi(ApiClient(config))

        # create cache
        self._cache = Cache(self)

        # test connection to trilium server
        try:
            app_info: AppInfo = self.api.get_app_info()
            logging.debug(f"Got Trilium version: {app_info.app_version}")
        except ApiException as e:
            logging.error(
                f"Failed to connect to Trilium server using token={self._token}"
            )
            raise

        # set root note
        self._root = Note(note_id="root", session=self)

    def __enter__(self):
        logging.debug(f"Entering context: {self}")
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        if exc_type:
            logging.error(f"Exiting context with error: {self}")
            return

        logging.debug(f"Exiting context: {self}")

        # flush pending changes
        self.flush()

        # if default, deregister it
        self.deregister_default()

        # logout if the user provided a password
        if self._logout_pending:
            self.logout()

    def flush(
        self,
        entities: Iterable[BaseEntity] | None = None,
    ):
        """
        Commits pending changes to Trilium via ETAPI.

        If `entities`{l=python} passed, only flushes those entities
        and their dependencies.

        If `entities = None`{l=python}, flushes all dirty entities.

        ```{note}
        You may equivalently invoke {obj}`Entity.flush` to flush an
        {obj}`BaseEntity` along with its dependencies.
        ```

        :param entities: Entities for which to commit changes, internally processed as a {obj}`set` and sorted according to dependencies
        """
        self._cache.flush(entities)

    def search(
        self,
        query: str,
        order_by: str | None = None,
        order_direction: Literal["asc", "desc"] | None = None,
        limit: int | None = None,
        fast_search: bool = False,
        include_archived_notes: bool = False,
        ancestor_note: Note | None = None,
        ancestor_depth: int | None = None,
        debug: bool = False,
    ) -> list[Note]:
        """
        Perform note search using query string as described at:
        <https://github.com/zadam/trilium/wiki/Search>

        :param query: Query string
        :param order_by: Name of the property/label to order search results by
        :param order_direction: Ascending (`"asc"`) or descending (`"desc"`), ascending by default
        :param limit: Limit the number of results to receive
        :param fast_search: Enable fast search (doesn't search content)
        :param include_archived_notes: Include archived notes
        :param ancestor_note: Search only in subtree of provided note
        :param ancestor_depth: Define how deep in the tree should the notes be searched
        :param debug: Get debug information in the response (search query parsing)

        :returns: List of notes
        """

        from .note.note import Note

        ancestor_note_id: str | None = (
            ancestor_note.note_id if ancestor_note is not None else None
        )

        # take bool in interface and convert to str
        fast_search_arg: str = str(fast_search).lower()
        include_archived_notes_arg: str = str(include_archived_notes).lower()
        debug_arg = str(debug).lower()

        # take int in interface and convert to str
        ancestor_depth_arg: str | None
        ancestor_depth_arg = (
            str(ancestor_depth) if ancestor_depth is not None else None
        )

        response: SearchResponse = self.api.search_notes(
            query,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
            fast_search=fast_search_arg,
            include_archived_notes=include_archived_notes_arg,
            ancestor_note_id=ancestor_note_id,
            ancestor_depth=ancestor_depth_arg,
            debug=debug_arg,
        )

        # print debug info, if any
        if response.debug_info:
            logging.debug(f"Got search debug: {response.debug_info}")

        return [
            Note._from_model(model, session=self) for model in response.results
        ]

    def backup(self, name: str):
        """
        Create backup with provided name, e.g. `now` will write `backup-now.db`.

        :param name: Name of backup to write
        """
        self.api.create_backup(name)

    def get_today_note(self) -> Note:
        """
        Returns today's day note. Gets created if doesn't exist.
        """
        return self.get_day_note(datetime.date.today())

    def get_day_note(self, date: datetime.date) -> Note:
        """
        Returns a day note for a given date. Gets created if doesn't exist.

        :param date: Date object, e.g. `datetime.date(2023, 7, 5)`{l=python}
        """
        return self._etapi_wrapper(self.api.get_day_note, date)

    def get_week_note(self, date: datetime.date) -> Note:
        """
        Returns a week note for a given date. Gets created if doesn't exist.

        :param date: Date object, e.g. `datetime.date(2023, 7, 5)`{l=python}
        """
        return self._etapi_wrapper(self.api.get_week_note, date)

    def get_month_note(self, month: str) -> Note:
        """
        Returns a month note for a given date. Gets created if doesn't exist.

        :param month: Month in the form `yyyy-mm`, e.g. `2023-07`
        """
        return self._etapi_wrapper(self.api.get_month_note, month)

    def get_year_note(self, year: str) -> Note:
        """
        Returns a year note for a given date. Gets created if doesn't exist.

        :param year: Year as string
        """
        return self._etapi_wrapper(self.api.get_year_note, year)

    def get_inbox_note(self, date: datetime.date) -> Note:
        """
        Returns an "inbox" note into which note can be created. Date will
        be used depending on whether the inbox is a fixed note
        (identified with `#inbox` label) or a day note in a journal.

        :param date: Date object, e.g. `datetime.date(2023, 7, 5)`{l=python}
        """
        return self._etapi_wrapper(self.api.get_inbox_note, date)

    def get_app_info(self) -> AppInfo:
        """
        Returns app info. See <https://github.com/mm21/trilium-client/blob/main/docs/AppInfo.md> for its definition.
        """

        app_info: AppInfo = self.api.get_app_info()
        return app_info

    def refresh_note_ordering(self, note: Note) -> None:
        """
        Refresh ordering of provided note's children for any connected clients.

        ```{note}
        This API is automatically invoked after any child branch positions
        are adjusted. It should rarely be required, but is
        provided for completeness.
        ```
        """
        from .note.note import Note

        assert isinstance(note, Note)
        self.api.post_refresh_note_ordering(note.note_id)

    @classmethod
    def login(cls, host: str, password: str) -> str:
        """
        Login using a password and get an ETAPI token.

        ```{note}
        You can implicitly login by passing `password` when creating
        a {obj}`Session`. This API should rarely be required, but
        is provided for completeness.
        ```

        :param host: Hostname of Trilium server
        :param password: Trilium password

        :returns: ETAPI token
        """

        # avoid creating an api object, but use generated models

        request_model = LoginRequest(password=password)

        response: requests.models.Response = requests.post(
            f"{host}/etapi/auth/login",
            headers={"Content-Type": "application/json"},
            data=request_model.model_dump_json(),
        )

        assert (
            response.status_code == 201
        ), f"Login attempt returned status code {response.status_code}"

        response_model = Login201Response.model_validate(
            json.loads(response.text)
        )

        assert isinstance(response_model.auth_token, str)
        token: str = cast(str, response_model.auth_token)

        return token

    def logout(self):
        """
        Deletes the currently active API token, if this `Session` was created
        with a `password` rather than `token`.

        ```{warning}
        Subsequent attempts to invoke ETAPI methods using this `Session`,
        such as those invoked by {meth}`flush <Session.flush>`, will fail.
        ```

        If this {obj}`Session` was instead created with a token, a warning
        will be generated and no action will be taken. For token-based sessions
        there's no corresponding login.
        """

        if self._logout_pending:
            if self.dirty_count:
                logging.warning(
                    f"Logging out with {self.dirty_count} dirty entities"
                )

            self.api.logout()
            self._logout_pending = False

            # cleanup as we can't use api object anymore
            # TODO: cleanup cache? but should be garbage collected
            # once there are no more refs to this Session
            self._api = None

    def deregister_default(self):
        """
        If this session was registered as default, deregister it. No-op
        otherwise.
        """
        if self._is_default:
            global default_session
            default_session = None

    @property
    def root(self) -> Note:
        """
        Helper to lookup root note.
        """
        return self._root

    @root.setter
    def root(self, note: Note):
        """
        Needed to enable operations like:

        session.root += my_note
        """
        assert note is self._root

    @property
    def dirty_count(self) -> int:
        """
        Number of dirty {obj}`BaseEntity` objects.
        """
        return len(self.dirty_set)

    @property
    def dirty_set(self) -> set[BaseEntity]:
        """
        All dirty {obj}`BaseEntity` objects.
        """
        return {e for e in self._cache.dirty_set}

    @property
    def dirty_map(
        self,
    ) -> dict[State, set[BaseEntity],]:
        """
        Mapping of state to dirty {obj}`BaseEntity` objects
        in that state.

        Example usage:
        ```
        create_set = my_session.dirty_map[State.CREATE]
        ```
        """

        from .entity.types import State

        index: dict[State, set[BaseEntity]] = {
            State.CREATE: set(),
            State.UPDATE: set(),
            State.DELETE: set(),
        }

        for entity in self._cache.dirty_set:
            index[entity._state].add(entity)

        return index

    @property
    def host(self) -> str:
        """
        Host as configured by user.
        """
        return self._host

    @property
    def api(self) -> DefaultApi:
        """
        ETAPI client object. Used internally and exposed for manual
        low-level operations. For its documentation, see: <https://github.com/mm21/trilium-client>
        """
        assert self._api is not None
        return self._api

    @property
    def _base_path(self) -> str:
        """
        Return API base path from config. This is the host appended with
        `/etapi`.
        """
        return f"{self.host}/etapi"

    @property
    def _root_position_base(self) -> int:
        """
        Return the position of root__hidden branch, used as the base for
        child branches of the root note. If child branch positions aren't
        above root__hidden branch, the hidden subtree can be selected in the UI
        when a note range is selected.

        It should be 999999999, but best to get it dynamically and cache it.

        TODO: just use functools.lru_cache
        """

        # lookup base position if not set
        if self._root_position_base_val is None:
            # could instantiate Branch to get its position, but use etapi
            # directly to avoid tampering with cache
            model: EtapiBranchModel = self.api.get_branch_by_id("root__hidden")
            assert model is not None

            self._root_position_base_val = model.note_position
            assert isinstance(self._root_position_base_val, int)

        return self._root_position_base_val

    @property
    def _is_default(self) -> bool:
        global default_session
        return default_session is self

    def _etapi_wrapper(self, method: Callable, *args, **kwargs) -> Note:
        from .note.note import Note

        model: EtapiNoteModel = method(*args, **kwargs)
        return Note._from_model(model, session=self)


class SessionContainer:
    """
    Indicates that an object is associated with a Session.
    """

    _session: Session

    def __init__(self, session: Session):
        self._session = session


def normalize_session(session: Session | None) -> Session:
    """
    Interface to get default Session if none provided.
    """

    if session is not None:
        return session

    # get default
    global default_session

    assert default_session is not None, "No session provided and no default set"

    return default_session

"""Extra admin commands to manage GeoNode and GeoServer.

This script adds some functions to perform DomiNode related tasks in a more
expedite manner.

"""

import typing
from pathlib import Path

import httpx
import typer

from .constants import (
    DepartmentName,
    GeofenceAccess,
    UserRole,
)

_help_intro = 'Manage GeoNode'

app = typer.Typer(
    short_help=_help_intro,
    help=_help_intro
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GEONODE_BASE_URL = 'http://localhost'
DEFAULT_GEOSERVER_BASE_URL = 'http://localhost/geoserver'
DEFAULT_GEONODE_USERNAME = 'admin'
DEFAULT_GEONODE_PASSWORD = 'admin'
DEFAULT_GEOSERVER_ADMIN_USERNAME = 'admin'
DEFAULT_GEOSERVER_ADMIN_PASSWORD = 'geoserver'
_ANY = '*'


class GeoNodeManager:
    client: httpx.Client
    base_url: str
    username: str
    password: str
    geoserver_application_client_id: str
    geoserver_application_client_secret: str

    def __init__(
            self,
            client: httpx.Client,
            base_url: str = DEFAULT_GEONODE_BASE_URL,
            username: str = DEFAULT_GEONODE_USERNAME,
            password: str = DEFAULT_GEONODE_PASSWORD,
            geoserver_client_id: str = None,
            geoserver_client_secret: str = None,
    ):
        self.client = client
        self.base_url = (
            base_url if not base_url.endswith('/') else base_url.rstrip('/'))
        self.username = username
        self.password = password
        self.geoserver_application_client_id = geoserver_client_id
        self.geoserver_application_client_secret = geoserver_client_secret

    def login(self) -> httpx.Response:
        return self._modify_server_state(
            f'{self.base_url}/account/login/',
            login=self.username,
            password=self.password
        )

    def logout(self) -> httpx.Response:
        return self._modify_server_state(f'{self.base_url}/account/logout/')

    def get_existing_groups(
            self,
            pagination_url: str = None
    ) -> typing.List[typing.Dict]:
        """Retrieve existing groups via GeoNode's REST API"""
        url = pagination_url or f'{self.base_url}/api/group_profile/'
        response = self.client.get(url)
        response.raise_for_status()
        payload = response.json()
        group_profiles: typing.List = payload['objects']
        next_page = payload['meta']['next']
        if next_page is not None:
            group_profiles.extend(self.get_existing_groups(next_page))
        return group_profiles

    def create_group(self, name: str, description: str) -> httpx.Response:
        """Create a new GeoNode group.

        The GeoNode REST API does not have a way to create new groups. As such,
        as a workaround measure, we impersonate a web browser and create the
        group using the main GUI.

        """

        return self._modify_server_state(
            f'{self.base_url}/groups/create/',
            title=name,
            description=description,
            access='public-invite'
        )

    def get_geoserver_access_token(self) -> str:
        response = self.client.post(
            f'{self.base_url}/o/token/',
            data={
                'grant_type': 'password',
                'username': self.username,
                'password': self.password,
            },
            auth=(
                self.geoserver_application_client_id,
                self.geoserver_application_client_secret
            )
        )
        response.raise_for_status()
        payload = response.json()
        return payload['access_token']

    def _modify_server_state(self, url: str, **data):
        """Modify GeoNode state.

        This function is used in the context of making web requests as if we
        were a web browser.

        This function is tailored to the way django CSRF security features
        behave. It first makes a GET request to the specified URL in order to
        retrieve the appropriate CSRF token from the response's cookies. Then
        it makes the actual POST request, with the data to modify the backend.
        This second request sends back the CSRF token, which proves to django
        that the request is legitimate.

        """

        idempotent_response = self.client.get(url)
        idempotent_response.raise_for_status()
        request_data = data.copy()
        request_data.update({
            'csrfmiddlewaretoken': idempotent_response.cookies['csrftoken'],
        })
        modifier_response = self.client.post(
            url,
            data=request_data,
            headers={
                'Referer': url,
            },
            cookies=idempotent_response.cookies
        )
        return modifier_response


class GeoServerManager:
    client: httpx.Client
    base_url: str
    access_token: str
    headers: dict

    def __init__(
            self,
            client: httpx.Client,
            base_url: str,
            username: str = DEFAULT_GEOSERVER_ADMIN_USERNAME,
            password: str = DEFAULT_GEOSERVER_ADMIN_PASSWORD,
            access_token: typing.Optional[str] = None
    ):
        self.client = client
        self.base_url = base_url
        self.username = username
        self.password = password
        self.access_token = access_token
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    @classmethod
    def from_geonode_manager(cls, geonode_manager: GeoNodeManager):
        access_token = geonode_manager.get_geoserver_access_token()
        return cls(
            geonode_manager.client,
            f'{geonode_manager.base_url}/geoserver',
            access_token
        )

    def list_workspaces(self):
        self.client.headers = self.headers

        response = self.client.get(
            f'{self.base_url}/rest/workspaces',
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        return response.json()

    def create_workspace(self, name):
        self.client.headers = self.headers

        response = self.client.post(
            f'{self.base_url}/rest/workspaces',
            auth=(self.username, self.password),
            json={
                    "workspace": {
                        "name": name
                    }
                }
        )
        if response.status_code != 201:
            return False
        return True

    def get_workspace(self, name):
        self.client.headers = self.headers

        response = self.client.get(
            f'{self.base_url}/rest/workspaces/{name}',
            auth=(self.username, self.password)
        )
        if response.status_code != 200:
            return None
        return response.json()

    def create_postgis_store(
            self,
            workspace_name: str,
            store_name: str,
            host: str,
            port: str,
            database: str,
            user: str,
            password: str
    ):
        datastore = {
           "name": store_name,
           "connectionParameters": {
              "host": host,
              "port": port,
              "database": database,
              "user": user,
              "passwd": password,
              "dbtype": "postgis"
           }
        }
        self.client.headers = self.headers

        response = self.client.post(
            f'{self.base_url}/rest/workspaces/{workspace_name}/datastores',
            auth=(self.username, self.password),
            json=datastore
        )
        response.raise_for_status()
        return response.json()

    def list_geofence_admin_rules(self) -> typing.List:
        self.client.headers = self.headers

        response = self.client.get(
            f'{self.base_url}/rest/geofence/adminrules',
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        return response.json().get('rules', [])

    def create_geofence_admin_rule(
            self,
            workspace: str,
            role_name: str,
            role: UserRole,
    ):
        if role == UserRole.EDITOR:
            access = GeofenceAccess.ADMIN
        else:
            access = GeofenceAccess.USER

        self.client.headers = self.headers

        response = self.client.post(
            f'{self.base_url}/rest/geofence/adminrules',
            auth=(self.username, self.password),
            json={
                'priority': 0,
                'userName': _ANY,
                'roleName': role_name,
                'addressRange': _ANY,
                'workspace': workspace,
                'access': access.name
            }
        )
        response.raise_for_status()
        return response


@app.command()
def bootstrap(
        geonode_base_url: str = DEFAULT_GEONODE_BASE_URL,
        geoserver_base_url: str = DEFAULT_GEOSERVER_BASE_URL,
        geonode_username: str = DEFAULT_GEONODE_USERNAME,
        geonode_password: str = DEFAULT_GEONODE_PASSWORD,
        geoserver_username: str = DEFAULT_GEOSERVER_ADMIN_USERNAME,
        geoserver_password: str = DEFAULT_GEOSERVER_ADMIN_PASSWORD
):
    """Perform initial bootstrap of GeoNode and GeoServer"""
    internal_group_name = 'dominode-internal'
    with httpx.Client() as client:
        geonode_manager = GeoNodeManager(client, geonode_base_url, geonode_username, geonode_password)
        geonode_manager.login()
        existing_groups = geonode_manager.get_existing_groups()
        geoserver_manager = GeoServerManager(client, geoserver_base_url, geoserver_username, geoserver_password)

        for department in DepartmentName:
            _add_department(
                geonode_manager,
                department, [i['title'] for i in existing_groups]
            )
            typer.echo(f'Bootstrapping deparment {department.value} in geoserver')
            _bootstrap_department_in_geoserver(
                geoserver_manager,
                department
            )
        typer.echo(f'Creating group {internal_group_name!r}...')
        geonode_manager.create_group(
            internal_group_name,
            'A group for internal DomiNode users'
        )
        geonode_manager.logout()


    pass


@app.command()
def add_department(
        department: DepartmentName,
        base_url: str = DEFAULT_GEONODE_BASE_URL,
        username: str = DEFAULT_GEONODE_USERNAME,
        password: str = DEFAULT_GEONODE_PASSWORD,
):
    with httpx.Client() as client:
        manager = GeoNodeManager(client, base_url, username, password)
        manager.login()
        existing_groups = manager.get_existing_groups()
        _add_department(
            manager,
            department,
            [i['title'] for i in existing_groups]
        )
        manager.logout()


def get_geonode_group_name(department: DepartmentName) -> str:
    return f'{department.value}-editor'


def get_geoserver_group_name(department: DepartmentName) -> str:
    return get_geonode_group_name(department).upper()


def _add_department(
        manager: GeoNodeManager,
        department: DepartmentName,
        existing_groups: typing.List[str]
):
    group_name = get_geonode_group_name(department)
    description = (
        f'A group for users that are allowed to administer {department.value} '
        f'datasets'
    )
    if group_name not in existing_groups:
        typer.echo(f'Creating group {group_name!r}...')
        manager.create_group(group_name, description)
        geoserver_manager = GeoServerManager.from_geonode_manager(manager)
        _bootstrap_department_in_geoserver(geoserver_manager, department)
    else:
        typer.echo(f'group {group_name!r} already exists, ignoring...')


def _bootstrap_department_in_geoserver(
        manager: GeoServerManager,
        department: DepartmentName
):
    """Bootstrap a department in GeoServer

    This function performs the following steps:

    1. create geoserver workspace, in case it does not already exist. If the
       workspace already exists, the function shall return immediately.

    2. Create the relevant geofence admin rules for the workspace -
       The `{department}-editor` group shall be able to administer the
       corresponding workspace.

    3. Create a postgis store in the workspace - this requires using specific
       DB credentials, which provide specific access controls - the DB user
       that is used for each department workspace shall only be able to access
       layers on the **public** schema of the DB AND the user shall only be
       allowed to access layers owned by his own department AND even this
       access must be readonly.

    """

    # TODO: Needs additional work on the database bootstrap script.
    #  Create a `{department}-geoserver` DB user, which shall have readonly
    #  access to department layers on the `public` schema only

    existing_workspaces = manager.list_workspaces()
    workspace_name = department.value
    workspace_exists = False

    # 1. create the workspace

    workspace = manager.get_workspace(workspace_name)
    typer.echo(f'Workspace {workspace}')
    if workspace is None:
        manager.create_workspace(workspace_name)
    else:
        workspace_exists = True

    if not workspace_exists:
        # 2. create the geofence admin rules
        existing_rules = manager.list_geofence_admin_rules()
        group_name = get_geoserver_group_name(department)
        role_name = f'ROLE_{group_name}'

        typer.echo(f'Existing rules {existing_rules}, role name {role_name}')

        if role_name not in [i['roleName'] for i in existing_rules]:
            typer.echo(f'Creating Geoserver admin rule for {department.value}...')
            manager.create_geofence_admin_rule(
                department.value, role_name, UserRole.EDITOR)
        # 3. create the postgis db store
        # manager.create_postgis_store(
        #     workspace_name,
        #     "postgis_store",
        #     "localhost",
        #     5432,
        #     db,
        #     user,
        #     password)
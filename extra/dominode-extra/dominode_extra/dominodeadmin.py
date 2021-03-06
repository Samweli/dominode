"""Extra commands to manage the DomiNode system"""

import typer
from pathlib import Path

from . import minioadmin
from . import dbadmin

app = typer.Typer()
app.add_typer(minioadmin.app, name='minio')
app.add_typer(dbadmin.app, name='db')


@app.command()
def bootstrap(
        db_service_name: str,
        minio_endpoint_alias: str,
        db_service_fle: Path = dbadmin.DEFAULT_CONFIG_DIR,
        minio_client_config_dir: Path = minioadmin.DEFAULT_CONFIG_DIR,
):
    dbadmin.bootstrap(db_service_name, db_service_fle)
    minioadmin.bootstrap(minio_endpoint_alias, minio_client_config_dir)

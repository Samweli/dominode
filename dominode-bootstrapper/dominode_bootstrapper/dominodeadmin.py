"""Extra commands to manage the DomiNode system"""

import typer
import typing

from . import (
    dbadmin,
    geonodeadmin,
    minioadmin,
)

app = typer.Typer()
app.add_typer(dbadmin.app, name='db')
app.add_typer(geonodeadmin.app, name='geonode')
app.add_typer(minioadmin.app, name='minio')


@app.command()
def bootstrap(
        db_user_name: str,
        db_user_password: str,
        minio_access_key: str,
        minio_secret_key: str,
        geonode_base_url: str,
        geonode_username: str,
        geonode_password: str,
        geoserver_username: str,
        geoserver_password: str,
        db_name: typing.Optional[str] = None,
        db_host: str = 'localhost',
        db_port: int = 5432,
        minio_alias: typing.Optional[str] = 'dominode_bootstrapper',
        minio_host: str = 'localhost',
        minio_port: int = 9000,
        minio_protocol: str = 'https'
):
    typer.echo('Bootstrapping DomiNode database...')
    try:
        dbadmin.bootstrap(
            db_user_name,
            db_user_password,
            db_name or db_user_name,
            db_host,
            db_port
        )
    except Exception as e:
        typer.echo(f'Error: {e}...skipping')
        pass
    typer.echo('Bootstrapping DomiNode minIO...')
    try:
        minioadmin.bootstrap(
            minio_access_key,
            minio_secret_key,
            minio_alias,
            minio_host,
            minio_port,
            minio_protocol
        )
    except Exception as e:
        typer.echo(f'Error: {e}...skipping')
        pass

    geonodeadmin.bootstrap(

    )
    typer.echo('Done!')

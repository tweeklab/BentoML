from __future__ import annotations

import sys
import logging

import click

logger = logging.getLogger(__name__)

DEFAULT_DEV_SERVER_HOST = "127.0.0.1"


def add_serve_command(cli: click.Group) -> None:

    from bentoml._internal.log import configure_server_logging
    from bentoml._internal.configuration.containers import BentoMLContainer

    @cli.command()
    @click.argument("bento", type=click.STRING, default=".")
    @click.option(
        "--production",
        type=click.BOOL,
        help="Run the BentoServer in production mode",
        is_flag=True,
        default=False,
        show_default=True,
    )
    @click.option(
        "--port",
        type=click.INT,
        default=BentoMLContainer.service_port.get(),
        help="The port to listen on for the REST api server",
        envvar="BENTOML_PORT",
        show_default=True,
    )
    @click.option(
        "--host",
        type=click.STRING,
        default=None,
        help="The host to bind for the REST api server [defaults: 127.0.0.1(dev), 0.0.0.0(production)]",
        envvar="BENTOML_HOST",
    )
    @click.option(
        "--api-workers",
        type=click.INT,
        default=None,
        help="Specify the number of API server workers to start. Default to number of available CPU cores in production mode",
        envvar="BENTOML_API_WORKERS",
    )
    @click.option(
        "--backlog",
        type=click.INT,
        default=BentoMLContainer.api_server_config.backlog.get(),
        help="The maximum number of pending connections.",
        show_default=True,
    )
    @click.option(
        "--reload",
        type=click.BOOL,
        is_flag=True,
        help="Reload Service when code changes detected, this is only available in development mode",
        default=False,
        show_default=True,
    )
    @click.option(
        "--working-dir",
        type=click.Path(),
        help="When loading from source code, specify the directory to find the Service instance",
        default=".",
        show_default=True,
    )
    @click.option(
        "--ssl-certfile",
        type=str,
        default=None,
        help="SSL certificate file",
    )
    @click.option(
        "--ssl-keyfile",
        type=str,
        default=None,
        help="SSL key file",
    )
    @click.option(
        "--ssl-keyfile-password",
        type=str,
        default=None,
        help="SSL keyfile password",
    )
    @click.option(
        "--ssl-version",
        type=int,
        default=None,
        help="SSL version to use (see stdlib 'ssl' module)",
    )
    @click.option(
        "--ssl-cert-reqs",
        type=int,
        default=None,
        help="Whether client certificate is required (see stdlib 'ssl' module)",
    )
    @click.option(
        "--ssl-ca-certs",
        type=str,
        default=None,
        help="CA certificates file",
    )
    @click.option(
        "--ssl-ciphers",
        type=str,
        default=None,
        help="Ciphers to use (see stdlib 'ssl' module)",
    )
    def serve(  # type: ignore (unused warning)
        bento: str,
        production: bool,
        port: int,
        host: str | None,
        api_workers: int | None,
        backlog: int,
        reload: bool,
        working_dir: str,
        ssl_certfile: str | None,
        ssl_keyfile: str | None,
        ssl_keyfile_password: str | None,
        ssl_version: int | None,
        ssl_cert_reqs: int | None,
        ssl_ca_certs: str | None,
        ssl_ciphers: str | None,
    ) -> None:
        """Start a :code:`BentoServer` from a given ``BENTO`` 🍱

        ``BENTO`` is the serving target, it can be the import as:
            - the import path of a :code:`bentoml.Service` instance
            - a tag to a Bento in local Bento store
            - a folder containing a valid `bentofile.yaml` build file with a `service` field, which provides the import path of a :code:`bentoml.Service` instance
            - a path to a built Bento (for internal & debug use only)

        e.g.:

        \b
        Serve from a bentoml.Service instance source code (for development use only):
            :code:`bentoml serve fraud_detector.py:svc`

        \b
        Serve from a Bento built in local store:
            :code:`bentoml serve fraud_detector:4tht2icroji6zput3suqi5nl2`
            :code:`bentoml serve fraud_detector:latest`

        \b
        Serve from a Bento directory:
            :code:`bentoml serve ./fraud_detector_bento`

        \b
        If :code:`--reload` is provided, BentoML will detect code and model store changes during development, and restarts the service automatically.

            The `--reload` flag will:
            - be default, all file changes under `--working-dir` (default to current directory) will trigger a restart
            - when specified, respect :obj:`include` and :obj:`exclude` under :obj:`bentofile.yaml` as well as the :obj:`.bentoignore` file in `--working-dir`, for code and file changes
            - all model store changes will also trigger a restart (new model saved or existing model removed)
        """
        configure_server_logging()

        if sys.path[0] != working_dir:
            sys.path.insert(0, working_dir)

        if production:
            if reload:
                logger.warning(
                    "'--reload' is not supported with '--production'; ignoring"
                )

            from bentoml.serve import serve_production

            serve_production(
                bento,
                working_dir=working_dir,
                port=port,
                host=BentoMLContainer.service_host.get() if host is None else host,
                backlog=backlog,
                api_workers=api_workers,
                ssl_keyfile=ssl_keyfile,
                ssl_certfile=ssl_certfile,
                ssl_keyfile_password=ssl_keyfile_password,
                ssl_version=ssl_version,
                ssl_cert_reqs=ssl_cert_reqs,
                ssl_ca_certs=ssl_ca_certs,
                ssl_ciphers=ssl_ciphers,
            )
        else:
            from bentoml.serve import serve_development

            serve_development(
                bento,
                working_dir=working_dir,
                port=port,
                host=DEFAULT_DEV_SERVER_HOST if host is None else host,
                reload=reload,
                ssl_keyfile=ssl_keyfile,
                ssl_certfile=ssl_certfile,
                ssl_keyfile_password=ssl_keyfile_password,
                ssl_version=ssl_version,
                ssl_cert_reqs=ssl_cert_reqs,
                ssl_ca_certs=ssl_ca_certs,
                ssl_ciphers=ssl_ciphers,
            )

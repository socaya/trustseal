"""Dump the OpenAPI spec to a file for publishing in CI."""
from __future__ import annotations

import json

import click
import yaml
from flask.cli import AppGroup, with_appcontext

from app.services.openapi import spec_as_dict

openapi_cli = AppGroup("openapi", help="OpenAPI specification tools.")


@openapi_cli.command("dump")
@click.option(
    "--output",
    default="openapi.yaml",
    show_default=True,
    help="File path to write.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    show_default=True,
)
@with_appcontext
def dump(output: str, fmt: str) -> None:
    document = spec_as_dict()
    if fmt == "json":
        text = json.dumps(document, indent=2, sort_keys=True)
    else:
        text = yaml.safe_dump(document, sort_keys=False)
    with open(output, "w", encoding="utf-8") as fh:
        fh.write(text)
    click.echo(f"openapi {fmt} written to {output}")

"""
Logout utility for composio CLI

Usage:
    composio logout
"""

import click
from composio.cli.context import pass_context, Context
from composio.exceptions import ComposioSDKError


@click.command(name="logout")
@pass_context
def _logout(context: Context) -> None:
    """Logout from the session."""
    try:
        context.user_data.api_key = None
        context.user_data.store()
    except ComposioSDKError as e:
        raise click.ClickException(message=e.message) from e
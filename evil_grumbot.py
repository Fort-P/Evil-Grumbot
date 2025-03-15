import logging
import os
import socket
from typing import Any, Literal

import discord
from discord import app_commands
from mcstatus import JavaServer

from custom_logger import Logger

# Initialise a custom logger
logger = Logger('evil.grumbot')

MAX_RETRIES = 5


class MyBot(discord.Client):
    """Custom Discord bot client."""

    def __init__(self, **kwargs: Any):
        discord.VoiceClient.warn_nacl = False

        intents = discord.Intents.default()
        super().__init__(intents=intents, command_prefix="!",
                         activity=discord.Game(name='Gwaff'), **kwargs)

        self.synced = False

    async def on_ready(self) -> None:
        """
        Event handler for when the bot is ready.
        Syncs commands with the Discord server.
        """
        if not self.synced:
            await tree.sync()
            for server in self.guilds:
                await tree.sync(guild=discord.Object(id=server.id))
                logging.info("- " + server.name)
            self.synced = True
        logging.info("Ready!")

    async def on_app_command_completion(self, interaction: discord.Interaction,
                                        command: app_commands.Command) -> None:
        """
        Event handler for when an application command is completed.
        Logs the command usage.
        """
        logger.info(f"User '{interaction.user.name}' "
                    f"used command '{command.name}' "
                    f"in guild '{interaction.guild.name}'")


# Initialize the bot and command tree
bot = MyBot()
tree = app_commands.CommandTree(bot)


class Server:
    """
    Class representing a Minecraft server.
    """

    def __init__(self, name: str, ip: str, channels: list[int], secret: bool = False,
                 supports_querying: bool = True):
        self.name = name
        self.ip = ip
        self.channels = channels
        self.secret = secret
        self.supports_querying = supports_querying


servers = [Server("Survival", "173.233.142.94:25565", [930585547842404372, 930322945040072734],
                  supports_querying=False),
           Server("Events", "173.233.142.10:25565", [1241016401502928967, 1237006920863453225],
                  supports_querying=False),
           Server("Creative", "173.233.142.2:25565", [930324293840171028], supports_querying=False),
           Server("Testing", "173.233.142.3:25565", [646113723550924849], True,
                  supports_querying=False),
           Server("Events Building", "140.238.96.87:25565", [], True, supports_querying=False)]

server_type = Literal[*[s.name for s in servers]]
server_options = Literal["Default", *[s.name for s in servers if not s.secret]]


def get_server_from_channel(channel_id: int) -> Server:
    """
    Get the server name based on the channel ID.

    Args:
        channel_id (int): The channel ID.

    Returns:
        str: The server name.
    """
    for s in servers:
        if channel_id in s.channels:
            return s
    raise ValueError(f"Channel ID '{channel_id}' not found.")


def get_server(server: server_type) -> Server:
    """
    Get the server IP address based on the server name.

    Args:
        server (server_type): The server name.

    Returns:
        str: The server IP address.
    """
    for s in servers:
        if s.name == server:
            return s
    raise ValueError(f"Server '{server}' not found.")


def get_server_info(server: Server):
    """
    Get the server information of the given server.

    Args:
        server (server_type): The server name.

    Returns:
        The server information.
    """
    server_lookup = JavaServer.lookup(server.ip)

    count = 0
    while count < MAX_RETRIES:
        try:
            return server_lookup.status()
        except socket.timeout:
            logging.warning(f"Status TimeoutError {count}")
            count += 1
        except Exception as e:
            logging.warning(f"Status Unknown exception {e} {count}")
            count += 1


def get_players_query(server: Server) -> list:
    """
    Get the server query information of the given server.

    Args:
        server (server_type): The server name.
    """
    server_lookup = JavaServer.lookup(server.ip)
    query = server_lookup.query()
    return query.players.names


def compose_response(server, status, player_list) -> str:
    """
    Compose the response message for the server status.

    Args:
        server (Server): The server object.
        status: The server status response.
        player_list (list): The list of players.
    """
    server_name = f"**Spooncraft {server.name} Server**\n"
    player_count = status.players.online
    max_count = status.players.max
    if player_count == 0:
        return f"{server_name}**No online players**"

    if len(player_list) == 0 and player_count >= 1:
        player_list.append('Anonymous Player')
    elif len(player_list) < player_count:
        player_list.append('...')
    players_str = ', '.join(player_list)

    return f"{server_name}**Online players ({player_count}/{max_count}):**\n```{players_str}```"


@tree.command(name="list", description="Lists the active members of a spooncraft server.")
@app_commands.describe(server='Optional. The Minecraft server to check.',
                       hidden='Optional. Hide from others in this server.')
@app_commands.allowed_installs(guilds=True, users=True)
async def send_data(interaction: discord.Interaction, server: server_options = "Default",
                    hidden: bool = True):
    """
    Command to list active members of a specified Minecraft server.

    Args:
        interaction (discord.Interaction): The interaction object.
        server (server_type): The Minecraft server to check.
        hidden (bool): Whether to hide the response from others.
    """
    await interaction.response.defer(ephemeral=hidden)

    selected_server: Server
    if server == "Default":
        try:
            selected_server = get_server_from_channel(interaction.channel_id)
        except ValueError:
            await interaction.followup.send("**You must either select a server "
                                            "or be in a recognised channel**")
            return
    else:
        selected_server = get_server(server)

    # Attempt to get the server information.
    status = get_server_info(selected_server)

    # Attempt an error had occurred.
    if status is None:
        await interaction.followup.send(f"**An unexpected error occurred**")
        return

    if status.players.online == 0:
        await interaction.followup.send(compose_response(selected_server, status, []))
        return

    # Attempt to get the player list
    player_list = []
    if selected_server.supports_querying:
        try:
            player_list = get_players_query(selected_server)
            print(player_list)
        except socket.timeout:
            logging.error(f"Using backup for '{selected_server.name}', despite being supported.")
    if len(player_list) == 0:
        player_list = [i.name for i in status.players.sample if i.name != "Anonymous Player"]
    print(player_list)

    await interaction.followup.send(compose_response(selected_server, status, player_list))
    return


def run_the_bot(token) -> None:
    """
    Runs the bot with the provided token.

    Args:
        token (str): The bot token.
    """
    bot.run(token)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)8s [%(asctime)s] %(filename)13s | %(message)s',
                        datefmt='%H:%M:%S')

    TOKEN = os.environ.get('BOT_TOKEN')
    run_the_bot(TOKEN)

    logging.info("Fin!")

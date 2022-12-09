import json
import socket
import sqlite3
import discord
import asyncio
from typing import Optional
from discord import app_commands
from mcstatus import JavaServer

with open("config.json") as f: CONFIG = json.load(f)

TEST_GUILD = discord.Object(id=CONFIG["test_guild"])
TESTING = CONFIG["testing"]
TOKEN = CONFIG["token"]

conn = sqlite3.connect("servers.db")

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # This copies the global commands over to your guild.
        if TESTING:
            self.tree.copy_global_to(guild=TEST_GUILD)
            await self.tree.sync(guild=TEST_GUILD)
        else:
            await self.tree.sync()

intents = discord.Intents.default()
client = MyClient(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    await client.change_presence(activity=discord.Game(name="Minecraft"))


@client.tree.command()
@app_commands.describe(address='The address and port of the server')
@app_commands.guild_only
async def check_server(interaction: discord.Interaction, address: Optional[str] = None):
    """Check who's online on a server"""
    
    if address == None:
        cur = conn.cursor()
        cur.execute("SELECT MCAddress FROM Servers WHERE ID=?", (interaction.guild.id,))
        row = cur.fetchone()
        if row:
            address = row[0]
        else:
            embed = discord.Embed(description=f"This Discord server does not have a default Minecraft server; you must specify one.", color=0xe01b24)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    
    if ":" not in address:
        real_address = address + ":25565"
    else:
        real_address = address
        
    await interaction.response.defer()
    
    try:
        server = await JavaServer.async_lookup(real_address)
        try:
            status = await server.async_status()
        except socket.gaierror:
            embed = discord.Embed(description=f"That is not a valid address.", color=0xe01b24)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except asyncio.exceptions.TimeoutError:
            embed = discord.Embed(description=f"This server is offline.", color=0xe01b24)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except ConnectionRefusedError:
            embed = discord.Embed(description=f"The connection was refused.", color=0xe01b24)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(title=address, description=status.description, color=0x99c1f1)
        embed.add_field(name="Software", value=status.version.name, inline=False)
        if status.players.sample:
            embed.add_field(name=f"Players ({status.players.online}/{status.players.max})", value="\n".join(["- " + player.name for player in status.players.sample]), inline=False)
        else:
            embed.add_field(name=f"Players (0/{status.players.max})", value="(None)", inline=False)
        embed.set_footer(text=f"Ping: {status.latency:.3f}ms")
        
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(description=f"Failed to ping server.", color=0xe01b24)
        await interaction.followup.send(embed=embed, ephemeral=True)
        raise e

@client.tree.command()
@app_commands.describe(address='The address and port of the new default server')
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.guild_only
async def set_default_server(interaction: discord.Interaction, address: str):
    """Set the default Minecraft server to check with the `check_server` command"""
    
    if ":" not in address:
        real_address = address + ":25565"
    else:
        real_address = address
    
    await interaction.response.defer()
    
    try:
        server = await JavaServer.async_lookup(real_address)
        try:
            status = await server.async_status()
        except socket.gaierror:
            embed = discord.Embed(description=f"**Not updated:** That is not a valid address.", color=0xe01b24)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except asyncio.exceptions.TimeoutError:
            embed = discord.Embed(description=f"**Not updated:** Server must be online.", color=0xe01b24)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except ConnectionRefusedError:
            embed = discord.Embed(description=f"**Not updated:** Connection refused.", color=0xe01b24)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    
        cur = conn.cursor()    
        cur.execute("INSERT OR REPLACE INTO Servers (ID, MCAddress) VALUES (?, ?)", (interaction.guild.id, address))
        conn.commit()
        
        embed = discord.Embed(description=f"Successfully updated default server to `{address}`", color=0x33d17a)
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        embed = discord.Embed(description=f"Failed to update default server.", color=0xe01b24)
        await interaction.followup.send(embed=embed, ephemeral=True)
        raise e

try:
    # https://discord.com/api/oauth2/authorize?client_id=932292231203782698&permissions=2684357632&scope=bot%20applications.commands
    client.run(TOKEN)
except KeyboardInterrupt:
    conn.close()

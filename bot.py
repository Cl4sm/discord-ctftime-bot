#!/usr/bin/env python3
import os
import requests
import random
import time
import logging

from typing import Any, List
from datetime import datetime, timezone

import discord
import json

from discord import app_commands
from dotenv import load_dotenv


log = logging.getLogger(__name__)


load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

TOKEN=os.getenv("TOKEN")
SERVER=int(os.getenv("SHELLPHISH_GUILD_ID"))
ROLE_CHANNEL=int(os.getenv("SHELLPHISH_ROLE_ID"))
ANNOUNCEMENT_CHANNEL=int(os.getenv("SHELLPHISH_ANNOUNCEMENT_ID"))
SHELLPHISH_ACADEMY_CHANNEL=int(os.getenv("SHELLPHISH_ACADEMY_ID"))

# SERVER=int(os.getenv("TEST_GUILD_ID"))
# ROLE_CHANNEL=int(os.getenv("TEST_ROLE_ID"))
# ANNOUNCEMENT_CHANNEL=int(os.getenv("TEST_ANNOUNCEMENT_ID"))

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

STATE_FILE = ".active_roles.json"

def get_current_emoji_to_role(message_id: int):
    data = (None, None, None)
    with open(STATE_FILE, "r") as f:
        data = json.load(f)

    for ctf in data:
        if str(message_id) in data["messages"]:
            return {int(x) for x in data["messages"]}, int(data["emoji"]), int(data["role"])

    return None

def save_active_emoji_message(ctf_name: str, messages: List[discord.Message], emoji: discord.Emoji, role: discord.Role):
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    data += [
        {
            "ctf_name": ctf_name,
            "messages": [message.id for message in messages],
            "emoji": emoji.id,
            "role": role.id
        }
    ]
    with open(STATE_FILE, "w+") as f:
        json.dump(data, f, indent=4)


def get_ctftime_info(ctftime_url: str):
    event_id = [x for x in ctftime_url.split("/") if x][-1]
    response = requests.get(f"https://ctftime.org/api/v1/events/{event_id}/", headers={"User-Agent": "Gecko"})
    data = response.json()
    return data

def get_epoch_from_time(time_str: str):
    # Convert string to datetime object in UTC
    dt = datetime.fromisoformat(time_str)

    # Convert datetime to epoch time
    epoch_time = int(dt.replace(tzinfo=timezone.utc).timestamp())
    return epoch_time

def ctftime_to_discord_str(ctftime_data: dict):
    out_str = f"<t:{get_epoch_from_time(ctftime_data['start'])}:F>-<t:{get_epoch_from_time(ctftime_data['finish'])}:F>"
    return out_str

async def create_announcement(ctf_name: str, time_info: str, emoji: discord.Emoji, message: discord.Message, is_academy: bool):
    out_str = f"@everyone We'll be playing {ctf_name} ({time_info})! hit the {emoji} in #{message.channel.mention} to play!"
    if is_academy:
        out_str = f"@everyone We'll be playing {ctf_name} as Shellphish Academy ({time_info})! hit the {emoji} in #{message.channel.mention} to play!"
    channel = client.get_channel(ANNOUNCEMENT_CHANNEL)
    await channel.send(out_str)

    if not is_academy:
        return
    out_str = f"@everyone We'll be playing {ctf_name} ({time_info})! hit the {emoji} to play!"
    channel = client.get_channel(SHELLPHISH_ACADEMY_CHANNEL)
    await channel.send(out_str)

async def create_role_react(role: discord.Role, ctf_name: str, is_academy: bool):
    messages = []
    channel =  client.get_channel(ROLE_CHANNEL)
    emoji = random.choice(client.emojis)

    message = await channel.send(f"React to give yourself a role for {ctf_name}!\n\n{emoji}: `{role.name}`", silent=True)
    await message.add_reaction(emoji)
    messages.append(message)

    if is_academy:
        channel =  client.get_channel(SHELLPHISH_ACADEMY_CHANNEL)
        message = await channel.send(f"React to give yourself a role for {ctf_name}!\n\n{emoji}: `{role.name}`", silent=True)
        await message.add_reaction(emoji)
        messages.append(message)

    save_active_emoji_message(ctf_name, messages, emoji, role)
    return emoji, messages[0]

async def create_category(guild: discord.Guild, role: str, category: str, url: str, username: str, password: str):
    dc_role = await guild.create_role(name=role)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        dc_role: discord.PermissionOverwrite(read_messages=True)
    }
    category_channel = await guild.create_category(category, position=8, overwrites=overwrites)
    channel_topic = f"URL: {url}" + "\n"
    if username:
        channel_topic += f"Username: {username}" + "\n"
    if password:
        channel_topic += f"Password: {password}" + "\n"
    await category_channel.create_text_channel(f"{role}-general", topic=channel_topic)
    await category_channel.create_forum(f"{role}-challs")
    await category_channel.create_voice_channel(f"{role}-general")
    return dc_role

@tree.command(
    name="create_ctf",
    description="Sets up a CTF by creating the category, role, and announcement",
    guild=discord.Object(id=SERVER)
)
async def create_ctf(interaction: discord.Interaction, ctftime_url: str, category_name: str, role_name: str, username: str = None, password: str = None, shellphish_academy: bool = False):
    shellphish_academy = shellphish_academy.lower() == "true" if isinstance(shellphish_academy, str) else False
    log.info("%s %s %s %s %s %s", ctftime_url, category_name, role_name, username, password, shellphish_academy)
    guild: discord.Guild = interaction.guild
    data = get_ctftime_info(ctftime_url)
    log.info("CREATING CATEGORY")
    role = await create_category(guild, role_name, category_name, data["url"], username, password)
    log.info("CREATING EMOJI")
    emoji, message = await create_role_react(role, data["title"], shellphish_academy)
    log.info("CREATING ANNOUNCEMENT")
    await create_announcement(data["title"], ctftime_to_discord_str(data), emoji, message, shellphish_academy)
    out_str = "Created CTF Successfully!\n"
    out_str += f"Category: {category_name}" + "\n"
    out_str += f"Role: {role_name}" + "\n"
    out_str += f"URL: {data['url']}" + "\n"
    out_str += f"Username: {username}" + "\n"
    out_str += f"Password: {password}" + "\n"
    out_str += f"Shellphish Academy: {shellphish_academy}"
    log.info(out_str)
    await interaction.response.send_message(out_str, ephemeral=True)

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=SERVER))
    log.info("Ready!")

class EmptyRole:
    def __init__(self, id):
        self.id = id

@client.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.Member):
    res = get_current_emoji_to_role(reaction.message.id)

    if res is None:
        return

    message_ids, emoji_id, role_id = res

    if user.id == client.user.id:
        return

    if reaction.message.id not in message_ids or reaction.emoji.id != emoji_id:
        return

    await user.add_roles(EmptyRole(role_id))

client.run(TOKEN)

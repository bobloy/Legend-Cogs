import discord
from discord.ext import commands
from random import randint
import requests
import asyncio
import random
import json
from cogs.utils import checks
from .utils.dataIO import dataIO
import os

creditIcon = "https://i.imgur.com/TP8GXZb.png"
credits = "Cog by Bobloy"



class activity:
    """tournament!"""

    def __init__(self, bot):
        self.bot = bot
        self.path = 'data/activity/settings.json'
        self.settings = dataIO.load_json(self.path)
        
    def save_data(self):
        """Saves the json"""
        dataIO.save_json(self.path, self.settings)
    
    @commands.group()
    async def activity(self):
    """Check activity in clans"""

    @commands.group(no_pm=True, aliases=['setactivity'])
    async def activityset(self, ctx):
    """Adjust settings for activity checks"""

def check_folders():
    if not os.path.exists("data/tourney"):
        print("Creating data/tourney folder...")
        os.makedirs("data/tourney")

def check_files():
    f = "data/tourney/settings.json"
    if not dataIO.is_valid_json(f):
        dataIO.save_json(f, {})

def setup(bot):
    check_folders()
    check_files()
    n = activity(bot)
    bot.add_cog(n)
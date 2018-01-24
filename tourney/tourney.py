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

from fake_useragent import UserAgent
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

import aiohttp

from cogs.utils.chat_formatting import pagify

from proxybroker import Broker

lastTag = '0'
creditIcon = "https://i.imgur.com/TP8GXZb.png"
credits = "Cog by GR8 | Titan"

proxies_list = [
"67.63.33.7"
]


# Converts maxPlayers to Cards
def getCards(maxPlayers):
	if maxPlayers == 50: return 25
	if maxPlayers == 100: return 100
	if maxPlayers == 200: return 400
	if maxPlayers == 1000: return 2000

# Converts maxPlayers to Cards
def getCoins(maxPlayers):
	if maxPlayers == 50: return 175
	if maxPlayers == 100: return 700
	if maxPlayers == 200: return 2800
	if maxPlayers == 1000: return 14000

# Converts seconds to time
def sec2tme(sec):
	m, s = divmod(sec, 60)
	h, m = divmod(m, 60)

	if h is 0:
		if m is 0:
			return "{} seconds".format(s)
		else:
			return "{} minutes, {} secs".format(m,s)
	else:
		return "{} hour, {} mins".format(h,m)

def time_str(obj, isobj):
	"""JSON serializer for datetiem and back"""

	fmt = '%Y%m%d%H%M%S' # ex. 20110104172008 -> Jan. 04, 2011 5:20:08pm 

	# if isinstance(obj, (datetime, date)):
	if isobj:
		return obj.strftime(fmt)
	else:
		return datetime.strptime(obj, fmt)


class tournament:
	"""tournament!"""

	def __init__(self, bot):
		self.bot = bot
		self.path = 'data/tourney/settings.json'
		self.cachepath = 'data/tourney/tourneycache.json'
		self.settings = dataIO.load_json(self.path)
		self.tourneyCache = dataIO.load_json(self.cachepath)
		self.auth = dataIO.load_json('cogs/auth.json')
		self.cacheUpdated = False
		self.session = aiohttp.ClientSession()
		self.queue = asyncio.Queue()
		self.broker = Broker(self.queue)
		self.proxylist = list(proxies_list)
	
	def __unload(self):
		self.session.close()
		
	def save_data(self):
		"""Saves the json"""
		dataIO.save_json(self.path, self.settings)
	
	def save_cache(self):
		"""Saves the cache json"""
		dataIO.save_json(self.cachepath, self.tourneyCache)

	def getAuth(self):
		return {"auth" : self.auth['token']}

	async def _is_allowed(self, member):
		return True
		server = member.server
		botcommander_roles = [discord.utils.get(server.roles, name=r) for r in ["Member", "Family Representative", "Clan Manager", "Clan Deputy", "Co-Leader", "Hub Officer", "admin", "Guest"]]
		botcommander_roles = set(botcommander_roles)
		author_roles = set(member.roles)
		if len(author_roles.intersection(botcommander_roles)):
			return True
		else:
			return False
	
	async def _fetch(self, url, proxy_url, headers):
		resp = None
		try:
			async with aiohttp.ClientSession() as session:
				async with session.get(url, timeout=30, proxy=proxy_url, headers=headers) as resp:
					data = await resp.json()
		except (aiohttp.errors.ClientOSError, aiohttp.errors.ClientResponseError,
				aiohttp.errors.ServerDisconnectedError) as e:
			print('Error. url: %s; error: %r' % (url, e))
		except json.decoder.JSONDecodeError:
			print(resp)
			raise
		except asyncio.TimeoutError:
			print(resp) 
			raise
		finally:
			return data
			
	async def _fetchread(self, url, proxy_url):
		resp = None
		try:
			async with self.session.get(url, timeout=30, proxy=proxy_url) as resp:
				data = await resp.read()
		except (aiohttp.errors.ClientOSError, aiohttp.errors.ClientResponseError,
				aiohttp.errors.ServerDisconnectedError) as e:
			print('Error. url: %s; error: %r' % (url, e))
		except asyncio.TimeoutError:
			print(resp) 
			raise
		finally:
			return (url, data)
			
	async def _fetch_tourney(self):
		"""Fetch tournament data. Run sparingly"""
		url = "{}".format('http://statsroyale.com/tournaments?appjson=1')
		proxy = await self._get_proxy()
		data = await self._fetch(url, proxy, {})
		
		return data
		
	async def _API_tourney(self, hashtag):
		"""Fetch API tourney from hashtag"""
		url = "{}{}".format('http://api.cr-api.com/tournaments/',hashtag)
		proxy = await self._get_proxy()
		data = await self._fetch(url, proxy, self.getAuth())
		
		return data
	
	async def _get_proxy(self):
		host = random.choice(self.proxylist)
		port = 80
		proxy = 'http://{}:{}'.format(host, port)
		
		return proxy  # Return host for now, will return proxy later
		
	async def _proxyBroker(self):
		self.broker.find(types=['HTTP', 'HTTPS'], limit=10)
		await self.bot.send_message(discord.Object(id="390927071553126402"), "Self.broker.find triggered")
		await asyncio.sleep(120)
	
	async def _brokerResult(self):
		await asyncio.sleep(120)
		while True:
			proxy = await self.queue.get()
			await self.bot.send_message(discord.Object(id="390927071553126402"), "Proxy attempt: {}".format(proxy))
			if proxy is None: break
			self.proxylist.append(proxy)
		
	
	async def _expire_cache(self):
		await asyncio.sleep(900)
		self.cacheUpdated = False
		await self.bot.send_message(discord.Object(id="390927071553126402"), "Cache expired")
	
	async def _update_cache(self):
		# try:
		newdata = await self._fetch_tourney()
		# except:  # On error: Don't retry, but don't mark cache as updated
			# return False
		
		if not newdata['success']:
			return False  # On error: Don't retry, but don't mark cache as updated
		
		newdata = newdata['tournaments']
		
		newdata = [tourney for tourney in newdata if not tourney['full']]  # Only keep not-full tourneys
		
		for tourney in newdata:
			if tourney["hashtag"] not in self.tourneyCache:  # Tourney the cache hasn't seen before
				timeLeft = timedelta(seconds=tourney['timeLeft'])
				endtime = datetime.utcnow() + timeLeft
				tourney["endtime"] = time_str(endtime, True)
				self.tourneyCache[tourney["hashtag"]] = tourney
			else:  # Already cached, update everything except endtime
				tourney["endtime"] = self.tourneyCache[tourney["hashtag"]]["endtime"]  # Keep endtime
				self.tourneyCache[tourney["hashtag"]] = tourney
		
		self.save_cache()
		self.cacheUpdated=True
		
		await self._topTourney(newdata)  # Posts all best tourneys when cache is updated
		
		return True
		
	
	async def _get_tourney(self, minPlayers):
		"""self.tourneyCache is dict of tourneys with hashtag as key"""
		if not self.cacheUpdated:	
			if not await self._update_cache(): 
				await self.bot.send_message(discord.Object(id="390927071553126402"), "Cache update failed")

		now = datetime.utcnow()
		
		tourneydata = [t1 for tkey, t1 in self.tourneyCache.items()
						if not t1['full'] and time_str(t1['endtime'], False) - now >= timedelta(seconds=600) and t1['maxPlayers']>=minPlayers]
		
		if not tourneydata:
			return None
		return random.choice(tourneydata)


	async def _topTourney(self, newdata):
		"""newdata is a list of tourneys"""
		now = datetime.utcnow()
		tourneydata = [t1 for t1 in newdata
						if not t1['full'] and time_str(t1['endtime'], False) - now >= timedelta(seconds=600) and t1['maxPlayers']>50]
						
		# Adjust parameters for what qualifies as a "top" tourney here ^^^^
		
		for data in tourneydata:
			embed = await self._get_embed(data)
				
			for serverid in self.settings.keys():
				if self.settings[serverid]:
					server = self.bot.get_server(serverid)
					channel = server.get_channel(self.settings[serverid])
					await self.bot.send_message(channel, embed=embed) # Family
					
			#await self.bot.send_message(discord.Object(id='363728974821457923'), embed=embed) # testing

	@commands.command(pass_context=True, no_pm=True)
	@checks.is_owner()
	async def proxytest(self, ctx):
		for page in pagify(
			str(self.proxylist), shorten_by=50):
			
			await self.bot.say(page)
		
		
	@commands.command(pass_context=True, no_pm=True)
	@checks.is_owner()
	async def showcache(self, ctx):
		"""Displays current cache pagified"""

		for page in pagify(
			str(self.tourneyCache), shorten_by=50):
			
			await self.bot.say(page)
	
	@commands.command(pass_context=True, no_pm=True)
	@checks.is_owner()
	async def clearcache(self, ctx):
		"""Clears all tourneys in cache"""

		self.tourneyCache = {}
		self.save_cache()
			
	@commands.command(pass_context=True, no_pm=True)
	async def tourney(self, ctx, minPlayers: int=0):
		"""Check an open tournament in clash royale instantly"""

		author = ctx.message.author

		await self.bot.send_typing(ctx.message.channel)

		allowed = await self._is_allowed(author)
		if not allowed:
			await self.bot.say("Error, this command is only available for Legend Members and Guests.")
			return
		
		tourney = await self._get_tourney(minPlayers)
		
		if tourney:
			embed = await self._get_embed(tourney)
			await self.bot.say(embed=embed)
		else:
			await self.bot.say("No tourney found")

	@commands.command(pass_context=True, no_pm=True)
	@checks.admin_or_permissions(administrator=True)
	async def tourneychannel(self, ctx, channel: discord.Channel=None):
		serverid = ctx.message.server.id
		if not channel:
			self.settings[serverid] = None
			await self.bot.say("Tournament channel for this server cleared")
		else:
			self.settings[serverid] = channel.id
			await self.bot.say("Tournament channel for this server set to "+channel.mention)
		self.save_data()
		
	@commands.command(pass_context=True, no_pm=True)
	@checks.admin_or_permissions(administrator=True)
	async def tourneywipe(self, ctx, channel: discord.Channel=None):
		
		self.settings = {}
		await self.bot.say("Tournament channel for all servers cleared")

		self.save_data()
		
	async def _get_embed(self, aTourney):
		"""Builds embed for tourney
		Uses cr-api.com if available"""
		
		hashlesstag = aTourney['hashtag'].lstrip('# ')
		try:
			bTourney = await self._API_tourney(hashlesstag)
		except:
			bTourney = None
			
		now = datetime.utcnow()
		
		embedtitle = "Open Tournament"
		
		if bTourney:
			title = bTourney['name']
			totalPlayers = bTourney['capacity']
			maxPlayers = bTourney['maxCapacity']
			full = bTourney['capacity'] >= bTourney['maxCapacity']
			
			if bTourney['type'] == "passwordProtected":
				embedtitle = "Locked Tournament"
			
			if bTourney['status'] == "ended":
				embedtitle = "Ended Tournament"
			
		else:
			title = aTourney['title']
			totalPlayers = aTourney['totalPlayers']
			maxPlayers = aTourney['maxPlayers']
			full = aTourney['full']
			
		timeLeft = time_str(aTourney['endtime'], False) - now
		timeLeft = timeLeft.total_seconds()
		if timeLeft < 0:
			timeLeft = 0
			embedtitle = "Ended Tournament"
			
		hashtag = aTourney['hashtag']
		cards = getCards(maxPlayers)
		coins = getCoins(maxPlayers)
		
		embed=discord.Embed(title="Open Tournament", color=0xFAA61A)
		embed.set_thumbnail(url='https://statsroyale.com/images/tournament.png')
		embed.add_field(name="Title", value=title, inline=True)
		embed.add_field(name="Tag", value="#"+hashtag, inline=True)
		embed.add_field(name="Players", value=str(totalPlayers) + "/" + str(maxPlayers), inline=True)
		embed.add_field(name="Ends In", value=sec2tme(timeLeft), inline=True)
		embed.add_field(name="Top prize", value="<:coin:380832316932489268> " + str(cards) + "     <:tournamentcards:380832770454192140> " +  str(coins), inline=True)
		embed.set_footer(text=credits, icon_url=creditIcon)
		return embed
		

def check_folders():
	if not os.path.exists("data/tourney"):
		print("Creating data/tourney folder...")
		os.makedirs("data/tourney")

def check_files():
	f = "data/tourney/settings.json"
	if not dataIO.is_valid_json(f):
		dataIO.save_json(f, {})
	
	f = "data/tourney/tourneycache.json"
	if not dataIO.is_valid_json(f):
		dataIO.save_json(f, {})

def setup(bot):
	check_folders()
	check_files()
	n = tournament(bot)
	loop = asyncio.get_event_loop()
	loop.create_task(n._expire_cache())
	loop.create_task(n._proxyBroker())
	loop.create_task(n._brokerResult())
	bot.add_cog(n)
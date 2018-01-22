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

import multiprocessing
from proxybroker import Broker
from queue import Empty
from ssl import _create_unverified_context

import aiohttp

from cogs.utils.chat_formatting import pagify

lastTag = '0'
creditIcon = "https://i.imgur.com/TP8GXZb.png"
credits = "Cog by GR8 | Titan"

proxies_list = [
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

class ProxyFinder(object):
	"""
		Wrapper for ProxyFinderProcess. Enables running proxybroker.Broker.find() in
		the background, so it's possible to do other (possibly synchronous) stuff in 
		the main process without being forced to use asyncio library.
		Usage:
			1. Call start() to spawn separate process and start grabbing proxies
			2. Do your work while proxy grabbing is taking place in the background
			3. To access found proxies, use ProxyFinder.proxies list of proxybroker.Proxy 
			   objects (call update_proxies() before doing so, otherwise you will get only
			   the ones since last update_proxies() call)
			4. After you finish doing your work, call stop() to exit gracefully
	"""
	
	def __init__(self, types=None, data=None, countries=None,
				post=False, strict=False, dnsbl=None, limit=0):
		"""
			Creates ProxyFinder class instance. All keyword arguments are in the end
			passed down to proxybroker.Broker.find()
			Note: if limit = 0, proxy grabbing will last forever
		"""
		try:
			multiprocessing.set_start_method('spawn')
		except RuntimeError:
			if multiprocessing.get_start_method() is not 'spawn':
				raise RuntimeError("Multiprocessing method of starting child processes has to be 'spawn'")
			
		self._results_queue = multiprocessing.Queue()
		self._poison_pill = multiprocessing.Event()
		self._proxy_finder = ProxyFinderProcess(self._results_queue, self._poison_pill, types=types, data=data, 
											countries=countries, post=post, strict=strict, dnsbl=dnsbl, limit=limit)
		self._proxy_finder.daemon = True
		self.proxies = []
		
	def start(self):
		"""
			Spawn separate proxy finder process and start grabbing proxies.
		"""
		self._proxy_finder.start()
		print("ProxyFinder process started")
		
	def stop(self):
		"""
			Gracefully terminate proxy finder process.
		"""
		self._poison_pill.set()
		self._proxy_finder.join()
		print("ProxyFinder process stopped")
		
	def update_proxies(self):
		"""
			Pull proxies which have been put in queue from separated process
			and append them to a ProxyFinder.proxies list.
		"""
		while True:
			try:
				proxy = self._results_queue.get_nowait()
			except Empty:
				break
			else:
				# restore SSLContext, see ProxyFinderProcess.async_to_result
				proxy = self._restore_ssl_context(proxy)
				self.proxies.append(proxy)
				
	def wait_for_proxy(self, timeout=None):
		try:
			proxy = self._results_queue.get(True, timeout)
		except Empty:
			return
		else:
			proxy = self._restore_ssl_context(proxy)
			self.proxies.append(proxy)
			
	def _restore_ssl_context(self, proxy):
		if proxy._ssl_context is None:
			proxy._ssl_context = _create_unverified_context()
			return proxy
				
class ProxyFinderProcess(multiprocessing.Process):
	"""
		Wrapper for proxybroker.Broker.find() which runs it in a separate process 
		so it runs in background.
		Note: if limit = 0, proxy grabbing will last forever
	"""
	
	def __init__(self, proxy_queue, poison_pill, types=None, data=None, countries=None,
				post=False, strict=False, dnsbl=None, limit=0):
		"""
			Creates ProxyFinderProcess class instance. All keyword arguments are in the end
			passed down to proxybroker.Broker.find()
			proxy_queue is a multiprocessing.Queue object which enables access of proxies outside of the process
			poison_pill is a multiprocessing.Event object which enables graceful termination of process if set()
			Note: if limit = 0, proxy grabbing will last forever
		"""
		multiprocessing.Process.__init__(self)
		self.results_queue = proxy_queue # multiprocessing.Queue to access proxies outside of the process
		self.poison_pill = poison_pill	# multiprocessing.Event which terminates process gracefully if set()
		self.types = types or ['HTTP']
		self.data = data or []
		self.countries = countries or []
		self.post = post
		self.strict = strict
		self.dnsbl = dnsbl or []
		self.limit = limit

	async def async_to_results(self):
		"""
			Coroutine that transfers proxybroker.Proxy object from internal asyncio.Queue 
			to multiprocessing.Queue, so it can be accessed outside of the process
		"""
		while not self.poison_pill.is_set():
			proxy = await self.async_queue.get()
			if proxy is None:	# note: if proxy is None, it's a ProxyBroker way of signaling poison pill
				break
			else:
				# because _ssl_context isn't pickable when it's a SSLContext object (it can be a boolean
				# value as well), we have to throw it away (we can reinstate it later by calling 
				# ssl._create_unverified_context(), just like it is done in the ProxyBroker library)
				if proxy._ssl_context != True or proxy._ssl_context != False:	
					proxy._ssl_context = None
				self.results_queue.put(proxy)
		self.broker.stop()	# if we got poison pill, exit gracefully
			
	def run(self):	
		"""
			Starts proxybroker.Broker.find() in a separate process
		"""
		self.async_queue = asyncio.Queue()
		self.broker = Broker(self.async_queue)
		self.tasks = asyncio.gather(self.broker.find(types=self.types, data=self.data, countries=self.countries,
													post=self.post, strict=self.strict, dnsbl=self.dnsbl, limit=self.limit),
									self.async_to_results())
		self.loop = asyncio.get_event_loop()
		self.loop.run_until_complete(self.tasks)

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
		
		self.finder = ProxyFinder(types=['HTTP', 'HTTPS'], limit=100) 
		self.finder.start()
			
		
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
	
	async def _fetch(url, proxy_url):
		resp = None
		try:
			async with aiohttp.ClientSession() as session:
				async with session.get(url, timeout=30, proxy=proxy_url) as resp:
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
			return (url, data)
			
	async def _fetch_tourney(self):
		"""Fetch tournament data. Run sparingly"""
		url = "{}".format('http://statsroyale.com/tournaments?appjson=1')
		return await self._gather_proxy(url)
		
	async def _API_tourney(self, hashtag):
		"""Fetch API tourney from hashtag"""
		url = "{}{}".format('http://api.cr-api.com/tournaments/',hashtag)
		return await self._gather_proxy(url)
	
	async def _gather_proxy(self, url):
		self.finder.update_proxies()
		print(self.finder.proxies)
		proxy = 'http://{}:{}'.format(self.host, self.port)
		urlOut, data = await self._fetch(url, proxy)

		return data
	
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
		
		for tourney in newdata:
			if tourney["hashtag"] not in self.tourneyCache:
				timeLeft = timedelta(seconds=tourney['timeLeft'])
				endtime = datetime.utcnow() + timeLeft
				tourney["endtime"] = time_str(endtime, True)
				self.tourneyCache[tourney["hashtag"]] = tourney
			else:
				tourney["endtime"] = self.tourneyCache[tourney["hashtag"]]["endtime"]  # Keep endtime
				self.tourneyCache[tourney["hashtag"]] = tourney
		
		self.save_cache()
		self.cacheUpdated=True
		
		await self._topTourney(newdata)  # Posts all best tourneys when cache is updated
		
		return True
		
	
	async def _get_tourney(self, minPlayers):
		"""tourneyCache is dict of tourneys with hashtag as key"""
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
	async def showcache(self, ctx):
		"""Displays current cache pagified"""

		for page in pagify(
			str(self.tourneyCache), shorten_by=50):
			
			await self.bot.say(page)
			
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
		
		try:
			bTourney = await self._API_tourney(aTourney['hashtag'])
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
		timeLeft = timeLeft.seconds
		if timeLeft < 0:
			timeLeft = 0
			embedtitle = "Ended Tournament"
			
		hashtag = aTourney['hashtag']
		cards = getCards(maxPlayers)
		coins = getCoins(maxPlayers)
		
		embed=discord.Embed(title="Open Tournament", color=randint(0, 0xffffff))
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
	bot.add_cog(n)
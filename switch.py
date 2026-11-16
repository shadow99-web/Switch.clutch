import os
import asyncio
import io
import time
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
# Ensure no trailing slash so endpoints format correctly
HF_API_URL = os.getenv("HF_API_URL", "").rstrip("/") 
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# ==========================================
# CACHING SYSTEM (10 Minute TTL)
# ==========================================
CACHE = {}
CACHE_TTL = 600  # 10 minutes in seconds

# ==========================================
# AIOHTTP KEEP-ALIVE (For Render)
# ==========================================
async def start_web_server():
    async def handle(request):
        return web.Response(text="OSINT Bot is online and active 24/7!")
    
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[Keep-Alive] Web server listening on port {port}")

# ==========================================
# BOT SETUP
# ==========================================
class APISyncOSINTBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.web_session = None

    async def setup_hook(self):
        # 1. Start global aiohttp session
        self.web_session = aiohttp.ClientSession()
        
        # 2. Start web server
        await start_web_server()

        # 3. Start self-ping loop
        if RENDER_EXTERNAL_URL:
            self.loop.create_task(self.keep_alive_ping())
            print(f"[Keep-Alive] Self-ping task initialized for: {RENDER_EXTERNAL_URL}")

        # 4. Sync slash commands
        await self.tree.sync()
        print(f"[+] Bot synchronized and online as {self.user}")

    async def keep_alive_ping(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                async with self.web_session.get(RENDER_EXTERNAL_URL) as resp:
                    pass
            except Exception:
                pass
            await asyncio.sleep(180) # 3 minutes

    async def close(self):
        if self.web_session:
            await self.web_session.close()
        await super().close()

bot = APISyncOSINTBot()
osint_group = app_commands.Group(name="osint", description="Distributed OSINT Intelligence Suite")

# ==========================================
# ERROR HANDLER (For Cooldowns)
# ==========================================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ **Slow down!** You can use this command again in `{error.retry_after:.1f}s`.", 
            ephemeral=True
        )
    else:
        print(f"[ERROR] {type(error).__name__}: {error}")
        try:
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        except:
            pass

# ==========================================
# HELPER FUNCTION (Handles Cache & API Fetching)
# ==========================================
async def fetch_osint(endpoint: str, params: dict, timeout: int):
    """Fetches data from HF Space with caching."""
    cache_key = f"{endpoint}:{str(params)}"
    
    # 1. Check Cache
    if cache_key in CACHE:
        if time.time() - CACHE[cache_key]["time"] < CACHE_TTL:
            print(f"[CACHE] Hit for {cache_key}")
            return CACHE[cache_key]["result"], None

    # 2. Fetch from API
    try:
        async with bot.web_session.get(f"{HF_API_URL}{endpoint}", params=params, timeout=timeout) as resp:
            if resp.status != 200:
                return None, f"❌ API Error: HTTP {resp.status}"
            
            if "application/json" not in resp.headers.get("Content-Type", ""):
                return None, "❌ API returned invalid format (HF Space might be offline)."
            
            data = await resp.json()
            if "error" in data:
                return None, f"❌ Error: {data['error']}"
            
            result = data.get("result", "No data returned.")
            
            # 3. Save to Cache
            CACHE[cache_key] = {"result": result, "time": time.time()}
            return result, None
            
    except asyncio.TimeoutError:
        return None, "❌ API Timeout. The Hugging Face Space might be waking up."
    except Exception as e:
        return None, f"❌ Connection error: {str(e)}"

# ==========================================
# COMMANDS
# ==========================================
@osint_group.command(name="username", description="Scan username via Maigret")
@app_commands.describe(username="Target username", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_username(interaction: discord.Interaction, username: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/username", {"username": username}, 320)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"🕵️ Username: {username}", color=discord.Color.dark_purple())
    embed.description = f"```ansi\n{result[:3900]}\n```" 
    embed.set_footer(text="Full results attached in file.")
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"username_{username}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="email", description="Scan email registrations via Holehe")
@app_commands.describe(email="Target email", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_email(interaction: discord.Interaction, email: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/email", {"email": email}, 60)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"📧 Email: {email}", color=discord.Color.blue())
    embed.description = f"```ansi\n{result[:3900]}\n```"
    embed.set_footer(text="Full results attached in file.")
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"email_{email}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="phone", description="Analyze phone number (Basic metadata)")
@app_commands.describe(phone="Target phone (+15555555555)", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_phone(interaction: discord.Interaction, phone: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/phone", {"phone": phone}, 20)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"📱 Phone: {phone}", color=discord.Color.green())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    embed.set_footer(text="For deeper OSINT, use /osint phoneinfoga")
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"phone_{phone}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="domain", description="Analyze domain & DNS")
@app_commands.describe(domain="Target domain", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_domain(interaction: discord.Interaction, domain: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/domain", {"domain": domain}, 60)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"🌐 Domain: {domain}", color=discord.Color.orange())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"domain_{domain}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="ip", description="Geolocate an IP address")
@app_commands.describe(ip="Target IP", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, time=1, key=lambda i: i.user.id)
async def osint_ip(interaction: discord.Interaction, ip: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/ip", {"ip": ip}, 15)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"📍 IP: {ip}", color=discord.Color.gold())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"ip_{ip}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="headers", description="Scan HTTP headers for security flaws")
@app_commands.describe(url="Target URL (e.g., example.com)", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_headers(interaction: discord.Interaction, url: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/headers", {"url": url}, 20)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"🛡️ Headers: {url}", color=discord.Color.teal())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"headers_{url.replace('https://','').replace('http://','')}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="github", description="Scan a GitHub profile")
@app_commands.describe(username="Target GitHub username", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_github(interaction: discord.Interaction, username: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/github", {"username": username}, 20)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"🐙 GitHub: {username}", color=discord.Color.dark_grey())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"github_{username}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

# ==========================================
# NEW TOOLS COMMANDS
# ==========================================
@osint_group.command(name="harvester", description="Gather emails, hosts, and subdomains")
@app_commands.describe(domain="Target domain (e.g., example.com)", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_harvester(interaction: discord.Interaction, domain: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/harvester", {"domain": domain}, 120)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"🌾 theHarvester: {domain}", color=discord.Color.dark_gold())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"harvester_{domain}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="phoneinfoga", description="Advanced phone OSINT")
@app_commands.describe(phone="Target phone number (+1234567890)", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_phoneinfoga(interaction: discord.Interaction, phone: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/phoneinfoga", {"phone": phone}, 60)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"📞 PhoneInfoga: {phone}", color=discord.Color.dark_green())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"phoneinfoga_{phone}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

@osint_group.command(name="sublist3r", description="Enumerate subdomains")
@app_commands.describe(domain="Target domain (e.g., example.com)", invisible="Only you can see the results")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def osint_sublist3r(interaction: discord.Interaction, domain: str, invisible: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=invisible)
    result, error = await fetch_osint("/api/sublist3r", {"domain": domain}, 120)
    if error: return await interaction.followup.send(error, ephemeral=invisible)

    embed = discord.Embed(title=f"🌐 Sublist3r: {domain}", color=discord.Color.dark_blue())
    embed.description = f"```yaml\n{result[:3900]}\n```"
    
    file = discord.File(io.BytesIO(result.encode("utf-8")), filename=f"sublist3r_{domain}.txt")
    await interaction.followup.send(embed=embed, file=file, ephemeral=invisible)

# ==========================================
# HELP MENU
# ==========================================
@osint_group.command(name="help", description="Display the OSINT toolkit help menu")
async def osint_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🕵️‍♂️ OSINT Suite",
        description="*Tip: Add `invisible: True` to any command to hide results from others.*\n*Bot has a 10-minute cache to prevent spamming.*",
        color=discord.Color.gold()
    )
    embed.add_field(name="👤 Identity", value="`/osint username` - Platform scan via Maigret\n`/osint email` - Email registrations via Holehe\n`/osint github` - GitHub profile recon", inline=False)
    embed.add_field(name="🌐 Infrastructure", value="`/osint domain` - WHOIS, DNS, Subdomains\n`/osint ip` - IP Geolocation & Proxy check\n`/osint headers` - HTTP Header security analysis\n`/osint harvester` - Emails, hosts & subdomains\n`/osint sublist3r` - Subdomain enumeration", inline=False)
    embed.add_field(name="📱 Phone", value="`/osint phone` - Basic phone metadata\n`/osint phoneinfoga` - Advanced phone OSINT", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Add the group to the tree
bot.tree.add_command(osint_group)

if __name__ == "__main__":
    if not TOKEN or not HF_API_URL:
        print("[!] CRITICAL: DISCORD_TOKEN or HF_API_URL is missing from environment variables.")
    else:
        bot.run(TOKEN)

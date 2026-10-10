import os
import threading
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import phonenumbers
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
HF_API_URL = os.getenv("HF_API_URL")  # e.g., https://your-space-name.hf.space

# 1. Initialize Flask web server for 24/7 keep-alive pings
app = Flask("")

@app.route("/")
def home():
    return "OSINT Bot is online and active 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# 2. Discord Bot Class Setup
class APISyncOSINTBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"[+] Bot synchronized and online as {self.user}")

bot = APISyncOSINTBot()
osint_group = app_commands.Group(name="osint", description="Distributed OSINT Intelligence Suite")

@osint_group.command(name="username", description="Scan username via Hugging Face Maigret API")
@app_commands.describe(username="Target username")
async def osint_username(interaction: discord.Interaction, username: str):
    await interaction.response.defer(thinking=True)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{HF_API_URL}/api/username", params={"username": username}, timeout=50) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Error connecting to OSINT backend service.")
                    return
                data = await resp.json()
                result_text = data.get("result", "No data returned.")
        except Exception as e:
            await interaction.followup.send(f"❌ Connection timeout or error: {str(e)}")
            return

    embed = discord.Embed(
        title=f"Username Intelligence: {username}",
        color=discord.Color.dark_purple(),
        timestamp=discord.utils.utcnow()
    )
    
    if len(result_text) > 3900:
        result_text = result_text[:3900] + "\n... [Output truncated]"
        
    embed.description = f"```ansi\n{result_text}\n```"
    embed.set_footer(text="OSINT Bot • Powered by Hugging Face API")
    await interaction.followup.send(embed=embed)

@osint_group.command(name="email", description="Scan email registrations via Hugging Face Holehe API")
@app_commands.describe(email="Target email address")
async def osint_email(interaction: discord.Interaction, email: str):
    await interaction.response.defer(thinking=True)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{HF_API_URL}/api/email", params={"email": email}, timeout=50) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Error connecting to OSINT backend service.")
                    return
                data = await resp.json()
                result_text = data.get("result", "No registrations found.")
        except Exception as e:
            await interaction.followup.send(f"❌ Connection timeout or error: {str(e)}")
            return

    embed = discord.Embed(
        title=f"Email Footprint Analysis: {email}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    if len(result_text) > 3900:
        result_text = result_text[:3900] + "\n... [Output truncated]"
        
    embed.description = f"```ansi\n{result_text}\n```"
    embed.set_footer(text="OSINT Bot • Powered by Hugging Face API")
    await interaction.followup.send(embed=embed)

@osint_group.command(name="phone", description="Analyze phone number via Hugging Face API")
@app_commands.describe(phone="Target phone number with country code (e.g., +15555555555)")
async def osint_phone(interaction: discord.Interaction, phone: str):
    await interaction.response.defer(thinking=True)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{HF_API_URL}/api/phone", params={"phone": phone}, timeout=20) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Error connecting to phone intelligence endpoint.")
                    return
                data = await resp.json()
                if "error" in data:
                    await interaction.followup.send(f"❌ Error: {data['error']}")
                    return
                result_text = data.get("result", "No data returned.")
        except Exception as e:
            await interaction.followup.send(f"❌ Connection timeout or error: {str(e)}")
            return

    embed = discord.Embed(
        title=f"Phone Intelligence: {phone}",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )
    embed.description = f"```yaml\n{result_text}\n```"
    embed.set_footer(text="OSINT Bot • Powered by Hugging Face API")
    await interaction.followup.send(embed=embed)

@osint_group.command(name="help", description="Display the OSINT toolkit help menu")
async def osint_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🕵️‍♂️ OSINT Intelligence Suite - Help Menu",
        description="Here are all the available reconnaissance commands powered by your distributed architecture.",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="/osint username", 
        value="Scans a target username across hundreds of online platforms using the Maigret engine.", 
        inline=False
    )
    embed.add_field(
        name="/osint email", 
        value="Checks account registrations associated with an email address using the Holehe engine.", 
        inline=False
    )
    embed.add_field(
        name="/osint phone", 
        value="Analyzes metadata, carrier details, and regional attributes for a given phone number.", 
        inline=False
    )
    embed.set_footer(text="OSINT Bot • 24/7 Keep-Alive Active")
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.tree.add_command(osint_group)

if __name__ == "__main__":
    if not TOKEN or not HF_API_URL:
        print("[!] CRITICAL: DISCORD_TOKEN or HF_API_URL is missing from environment variables.")
    else:
        keep_alive()
        bot.run(TOKEN)

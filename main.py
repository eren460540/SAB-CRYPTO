import os
import discord
from discord import app_commands
from discord.ext import tasks
import requests
from supabase import create_client, Client
from dotenv import load_dotenv
import cloudscraper
from bs4 import BeautifulSoup
import asyncio

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("BOT_TOKEN")

ADMIN_ROLE_ID = int(os.environ.get("ADMIN_ROLE_ID", 0))
TICKET_CATEGORY_ID = int(os.environ.get("TICKET_CATEGORY_ID", 0))

# --- DATABASE SETUP ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CONSTANTS & CONFIG ---
SAB_EMOJI = "<:SAB:1495012520510099577>"

COINS = {
    "ELEPHANT": {"name": "Strawberry Elephant", "ref": "bitcoin", "emoji": "<:ELEPHANT:1494995440213688340>"},
    "MEOWL": {"name": "Meowl", "ref": "ethereum", "emoji": "<:MEOWL:1494995595222454366>"},
    "GARAMA": {"name": "Garama and Madundung", "ref": "binancecoin", "emoji": "<:GARAMA:1494995007910842418>"},
    "SKIBIDI": {"name": "Skibidi Toilet", "ref": "solana", "emoji": "<:SKIBIDI:1494995556030746714>"},
    "DRAG": {"name": "Dragon Cannelloni", "ref": "ripple", "emoji": "<:DRAG:1494995236068397127>"},
    "KETCHURU": {"name": "Ketchuru and Musturu", "ref": "tron", "emoji": "<:KETCHURU:1494996298733191308>"},
    "TICTAC": {"name": "Tictac Sahur", "ref": "cardano", "emoji": "<:TICTAC:1494996594473308190>"},
    "SUPREME": {"name": "La Supreme Combinasion", "ref": "dogecoin", "emoji": "<:SUPREME:1494997175531470960>"},
    "KETUPAT": {"name": "Ketupat Kepat", "ref": "shiba-inu", "emoji": "<:KETUPAT:1494996070303006793>"},
    "TANG": {"name": "Tang Tang Keletang", "ref": "pepe", "emoji": "<:TANG:1494995850831728701>"}
}

def get_or_create_profile(user_id: str):
    # Fixed table name reference to match SQL editor
    res = supabase.table("profiles").select("*").eq("user_id", user_id).execute()
    if not res.data:
        default_portfolio = {key: 0.0 for key in COINS.keys()}
        new_user = {"user_id": user_id, "sab_balance": 0.0, "portfolio": default_portfolio}
        supabase.table("profiles").insert(new_user).execute()
        return new_user
    return res.data[0]

def update_profile(user_id: str, updates: dict):
    supabase.table("profiles").update(updates).eq("user_id", user_id).execute()

class SAB_Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.market_prices = {}

    async def setup_hook(self):
        self.update_prices.start()
        await self.tree.sync()

    @tasks.loop(seconds=60) # Increased to 60s to avoid API rate limits
    async def update_prices(self):
        try:
            ids = ",".join([c["ref"] for c in COINS.values()])
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur&include_24hr_change=true"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                self.market_prices = response.json()
        except Exception as e:
            print(f"Price update failed: {e}")

client = SAB_Bot()

# --- MARKET COMMAND ---
@client.tree.command(name="coins", description="View live SAB Market prices")
async def coins(interaction: discord.Interaction):
    if not client.market_prices:
        return await interaction.response.send_message("⏳ Loading market data...", ephemeral=True)
    
    embed = discord.Embed(title="📈 SAB Market Ticker", color=0x2b2d31)
    sorted_coins = sorted(COINS.items(), key=lambda x: client.market_prices.get(x[1]['ref'], {}).get('eur', 0), reverse=True)
    
    desc = ""
    for i, (sym, data) in enumerate(sorted_coins, 1):
        p = client.market_prices.get(data['ref'], {"eur": 0, "eur_24h_change": 0})
        price = p['eur']
        change = p.get('eur_24h_change') or 0.0
        trend = "🟢" if change >= 0 else "🔴"
        price_str = f"€{price:.8f}" if price < 0.1 else f"€{price:,.2f}"
        desc += f"`{i}.` {data['emoji']} **{sym}** ➔ **{price_str}** | {trend} `{change:+.2f}%`\n"
    
    embed.description = desc
    embed.set_footer(text="Updates every 60 seconds • Prices in EUR")
    await interaction.response.send_message(embed=embed)

# --- PROFILE COMMAND ---
@client.tree.command(name="profile", description="Check your balance and holdings")
async def profile(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    p = get_or_create_profile(str(target.id))
    
    embed = discord.Embed(title=f"🏦 Vault: {target.display_name}", color=0xFFD700)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Wallet Balance", value=f"**{p['sab_balance']:,.2f}** {SAB_EMOJI}", inline=False)
    
    holdings = []
    for k, v in p['portfolio'].items():
        if v > 0:
            price = client.market_prices.get(COINS[k]['ref'], {}).get('eur', 0)
            value = price * v
            holdings.append(f"{COINS[k]['emoji']} **{k}:** {v:,.4f} *(€{value:,.2f})*")
    
    embed.add_field(name="Current Holdings", value="\n".join(holdings) if holdings else "*No coins owned*", inline=False)
    await interaction.response.send_message(embed=embed)

# --- TRADE COMMANDS ---
@client.tree.command(name="buy", description="Purchase coins with SAB")
async def buy(interaction: discord.Interaction, coin: str, amount: float):
    coin = coin.upper()
    if coin not in COINS or amount <= 0:
        return await interaction.response.send_message("❌ Invalid coin or amount.", ephemeral=True)
    
    price = client.market_prices.get(COINS[coin]['ref'], {}).get('eur', 0)
    cost = price * amount
    p = get_or_create_profile(str(interaction.user.id))
    
    if p['sab_balance'] < cost:
        return await interaction.response.send_message(f"❌ Insufficient SAB. Need {cost:,.2f} {SAB_EMOJI}.", ephemeral=True)

    p['portfolio'][coin] = p['portfolio'].get(coin, 0) + amount
    update_profile(str(interaction.user.id), {"sab_balance": p['sab_balance'] - cost, "portfolio": p['portfolio']})
    await interaction.response.send_message(f"✅ Successfully bought **{amount} {coin}** for {cost:,.2f} {SAB_EMOJI}!")

@client.tree.command(name="sell", description="Sell coins for SAB")
async def sell(interaction: discord.Interaction, coin: str, amount: float):
    coin = coin.upper()
    if coin not in COINS or amount <= 0:
        return await interaction.response.send_message("❌ Invalid coin or amount.", ephemeral=True)
    
    p = get_or_create_profile(str(interaction.user.id))
    current_holding = p['portfolio'].get(coin, 0)
    
    if current_holding < amount:
        return await interaction.response.send_message(f"❌ You only have **{current_holding} {coin}**.", ephemeral=True)

    price = client.market_prices.get(COINS[coin]['ref'], {}).get('eur', 0)
    gain = price * amount
    
    p['portfolio'][coin] = current_holding - amount
    update_profile(str(interaction.user.id), {"sab_balance": p['sab_balance'] + gain, "portfolio": p['portfolio']})
    await interaction.response.send_message(f"✅ Sold **{amount} {coin}** for {gain:,.2f} {SAB_EMOJI}!")

# --- UTILITY COMMANDS ---
@client.tree.command(name="chart", description="View live chart of a coin")
async def chart(interaction: discord.Interaction, coin: str):
    coin = coin.upper()
    if coin not in COINS:
        return await interaction.response.send_message("❌ Invalid coin.", ephemeral=True)
    
    ref = COINS[coin]['ref']
    url = f"https://www.coingecko.com/en/coins/{ref}"
    embed = discord.Embed(title=f"📊 {COINS[coin]['name']} ({coin})", url=url, color=0x3498db)
    embed.description = f"Click the link above to view the live price chart for **{COINS[coin]['name']}**."
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="withdraw", description="Request to withdraw SAB balance")
async def withdraw(interaction: discord.Interaction, amount: float):
    p = get_or_create_profile(str(interaction.user.id))
    if amount <= 0 or p['sab_balance'] < amount:
        return await interaction.response.send_message("❌ Invalid amount or insufficient balance.", ephemeral=True)
    
    guild = interaction.guild
    cat = guild.get_channel(TICKET_CATEGORY_ID)
    if not cat:
        return await interaction.response.send_message("❌ Ticket category not found. Contact staff.", ephemeral=True)

    # Pre-deduct to prevent double spending
    update_profile(str(interaction.user.id), {"sab_balance": p['sab_balance'] - amount})
    
    chan = await guild.create_text_channel(f"withdraw-{interaction.user.name}", category=cat)
    await chan.send(f"⚠️ **WITHDRAWAL REQUEST**\nUser: {interaction.user.mention}\nAmount: **{amount} {SAB_EMOJI}**\nStaff: Process this request manually.")
    await interaction.response.send_message(f"✅ Request sent. Ticket: {chan.mention}", ephemeral=True)

@client.tree.command(name="deposit", description="Open a deposit ticket")
async def deposit(interaction: discord.Interaction):
    guild = interaction.guild
    cat = guild.get_channel(TICKET_CATEGORY_ID)
    admin = guild.get_role(ADMIN_ROLE_ID)
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        admin: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    
    chan = await guild.create_text_channel(f"deposit-{interaction.user.name}", category=cat, overwrites=overwrites)
    await interaction.response.send_message(f"✅ Deposit Ticket: {chan.mention}", ephemeral=True)
    await chan.send(f"{interaction.user.mention} Please provide proof of your deposit here for staff review.")

# --- ADMIN COMMANDS ---
@client.tree.command(name="add_sab", description="Admin Only: Add SAB to a user")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def add_sab(interaction: discord.Interaction, user: discord.Member, amount: float):
    p = get_or_create_profile(str(user.id))
    update_profile(str(user.id), {"sab_balance": p['sab_balance'] + amount})
    await interaction.response.send_message(f"✅ Added {amount} {SAB_EMOJI} to {user.name}'s vault.")

if __name__ == "__main__":
    client.run(TOKEN)

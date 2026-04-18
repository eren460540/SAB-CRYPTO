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

# IDs need to be integers. We use a fallback of 0 to prevent crashes if missing during setup.
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

# --- DATABASE HELPER ---
def get_or_create_profile(user_id: str):
    """Fetches user profile or creates a default one if it doesn't exist."""
    res = supabase.table("profiles").select("*").eq("user_id", user_id).execute()
    if not res.data:
        default_portfolio = {key: 0.0 for key in COINS.keys()}
        new_user = {
            "user_id": user_id,
            "sab_balance": 0.0,
            "portfolio": default_portfolio
        }
        supabase.table("profiles").insert(new_user).execute()
        return new_user
    return res.data[0]

def update_profile(user_id: str, updates: dict):
    """Updates a user's database record."""
    supabase.table("profiles").update(updates).eq("user_id", user_id).execute()

# --- BOT CLASS ---
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
        print(f"Logged in as {self.user} | Commands Synced")

    @tasks.loop(seconds=15)
    async def update_prices(self):
        """High-speed 15s market ticker fetching real EUR values."""
        try:
            ids = ",".join([c["ref"] for c in COINS.values()])
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur&include_24hr_change=true"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                self.market_prices = response.json()
        except Exception as e:
            print(f"Market API Error: {e}")

    @update_prices.before_loop
    async def before_update_prices(self):
        await self.wait_until_ready()

client = SAB_Bot()

# --- CORE MARKET COMMANDS ---

@client.tree.command(name="coins", description="View the live SAB Market leaderboard")
async def coins_cmd(interaction: discord.Interaction):
    if not client.market_prices:
        await interaction.response.send_message("⏳ Market data is currently booting up. Please try again in 15 seconds.", ephemeral=True)
        return

    embed = discord.Embed(title="📈 SAB Market Ticker", color=0x2b2d31)
    
    # Sort coins from most expensive to least
    sorted_coins = sorted(
        COINS.items(), 
        key=lambda x: client.market_prices.get(x[1]['ref'], {}).get('eur', 0), 
        reverse=True
    )
    
    desc = ""
    for i, (sym, data) in enumerate(sorted_coins, 1):
        p_data = client.market_prices.get(data['ref'], {"eur": 0, "eur_24h_change": 0})
        price = p_data['eur']
        change = p_data.get('eur_24h_change') or 0.0
        
        trend = "🟢" if change >= 0 else "🔴"
        price_str = f"€{price:.8f}" if price < 0.1 else f"€{price:,.2f}"
        
        desc += f"`{i}.` {data['emoji']} **{sym}** ➔ **{price_str}** | {trend} `{change:+.2f}%`\n\n"
    
    embed.description = desc
    embed.set_footer(text="Live Real-World Market Data • Refreshes every 15s")
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="profile", description="Check your SAB COIN balance and crypto portfolio")
async def profile_cmd(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    profile = get_or_create_profile(str(target.id))
    
    embed = discord.Embed(title=f"🏦 Vault: {target.display_name}", color=0xFFD700)
    embed.set_thumbnail(url=target.display_avatar.url)
    
    sab_bal = profile['sab_balance']
    embed.add_field(name="Base Currency", value=f"**{sab_bal:,.2f}** {SAB_EMOJI}", inline=False)
    
    portfolio_text = ""
    for sym, amount in profile.get('portfolio', {}).items():
        if amount > 0:
            emoji = COINS[sym]['emoji']
            portfolio_text += f"{emoji} **{sym}:** {amount:,.4f}\n"
            
    if not portfolio_text:
        portfolio_text = "*Your crypto wallet is empty. Use /buy to start trading!*"
        
    embed.add_field(name="Crypto Holdings", value=portfolio_text, inline=False)
    await interaction.response.send_message(embed=embed)


# --- TRADING COMMANDS ---

@client.tree.command(name="buy", description="Buy a SAB coin using your SAB COIN balance")
async def buy_cmd(interaction: discord.Interaction, coin: str, amount: float):
    coin = coin.upper()
    if coin not in COINS:
        await interaction.response.send_message("❌ Invalid coin symbol. Check `/coins`.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
        return

    ref_id = COINS[coin]['ref']
    current_price = client.market_prices.get(ref_id, {}).get('eur', 0)
    if current_price == 0:
        await interaction.response.send_message("❌ Market data unavailable. Try again later.", ephemeral=True)
        return

    cost = current_price * amount
    profile = get_or_create_profile(str(interaction.user.id))
    
    if profile['sab_balance'] < cost:
        await interaction.response.send_message(f"❌ **Nah Uh.** You need **{cost:,.2f}** {SAB_EMOJI} for this trade, but you only have **{profile['sab_balance']:,.2f}**.", ephemeral=True)
        return

    # Process Transaction
    new_sab = profile['sab_balance'] - cost
    new_coin_bal = profile['portfolio'].get(coin, 0) + amount
    
    updates = {
        "sab_balance": new_sab,
        "portfolio": {**profile['portfolio'], coin: new_coin_bal}
    }
    update_profile(str(interaction.user.id), updates)

    embed = discord.Embed(title="✅ Trade Successful", color=0x00FF00)
    embed.description = f"You bought **{amount} {COINS[coin]['emoji']} {coin}** for **{cost:,.2f} {SAB_EMOJI}**."
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="sell", description="Sell a SAB coin for SAB COINS")
async def sell_cmd(interaction: discord.Interaction, coin: str, amount: float):
    coin = coin.upper()
    if coin not in COINS:
        await interaction.response.send_message("❌ Invalid coin symbol.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
        return

    profile = get_or_create_profile(str(interaction.user.id))
    current_coin_bal = profile['portfolio'].get(coin, 0)

    if current_coin_bal < amount:
        await interaction.response.send_message(f"❌ **Nah Uh.** {COINS['DRAG']['emoji']} You don't have enough {coin}. You only have **{current_coin_bal:,.4f}**.", ephemeral=True)
        return

    ref_id = COINS[coin]['ref']
    current_price = client.market_prices.get(ref_id, {}).get('eur', 0)
    revenue = current_price * amount

    # Process Transaction
    new_sab = profile['sab_balance'] + revenue
    new_coin_bal = current_coin_bal - amount

    updates = {
        "sab_balance": new_sab,
        "portfolio": {**profile['portfolio'], coin: new_coin_bal}
    }
    update_profile(str(interaction.user.id), updates)

    embed = discord.Embed(title="✅ Sale Successful", color=0x00FF00)
    embed.description = f"You sold **{amount} {COINS[coin]['emoji']} {coin}** and received **{revenue:,.2f} {SAB_EMOJI}**."
    await interaction.response.send_message(embed=embed)


# --- TICKET SYSTEM ---

async def create_ticket(interaction: discord.Interaction, ticket_type: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    category = guild.get_channel(TICKET_CATEGORY_ID)
    
    if not category:
        await interaction.followup.send("❌ Ticket category not configured correctly. Contact an Admin.")
        return

    admin_role = guild.get_role(ADMIN_ROLE_ID)
    
    # Set permissions: Everyone block, Admin allow, User allow
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
    }
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel_name = f"sab-{ticket_type}-{interaction.user.name}"
    ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)

    # Save to Supabase
    supabase.table("tickets").insert({
        "channel_id": str(ticket_channel.id),
        "user_id": str(interaction.user.id),
        "ticket_type": ticket_type,
        "status": "open"
    }).execute()

    embed = discord.Embed(title=f"🏦 SAB BANK: {ticket_type.capitalize()}", color=0x2b2d31)
    embed.description = f"Hello {interaction.user.mention},\n\nPlease state the amount you wish to {ticket_type} and provide any necessary proof/details. An admin will assist you shortly."
    await ticket_channel.send(content=f"{interaction.user.mention}", embed=embed)
    await interaction.followup.send(f"✅ Ticket created: {ticket_channel.mention}")

@client.tree.command(name="deposit", description="Open a secure ticket to deposit funds into your SAB Vault")
async def deposit_cmd(interaction: discord.Interaction):
    await create_ticket(interaction, "deposit")

@client.tree.command(name="withdraw", description="Open a secure ticket to withdraw funds from your SAB Vault")
async def withdraw_cmd(interaction: discord.Interaction):
    await create_ticket(interaction, "withdraw")

@client.tree.command(name="close", description="Close the current ticket (Admin Only)")
@app_commands.checks.has_role(int(os.environ.get("ADMIN_ROLE_ID", 0)))
async def close_cmd(interaction: discord.Interaction):
    res = supabase.table("tickets").select("*").eq("channel_id", str(interaction.channel.id)).execute()
    if not res.data:
        await interaction.response.send_message("❌ This is not an active ticket channel.", ephemeral=True)
        return

    supabase.table("tickets").update({"status": "closed"}).eq("channel_id", str(interaction.channel.id)).execute()
    await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
    await asyncio.sleep(5)
    await interaction.channel.delete()


# --- ADMIN ECONOMY COMMANDS ---

@client.tree.command(name="add_sab", description="Add SAB COINS to a user (Admin Only)")
@app_commands.checks.has_role(int(os.environ.get("ADMIN_ROLE_ID", 0)))
async def add_sab(interaction: discord.Interaction, user: discord.Member, amount: float):
    profile = get_or_create_profile(str(user.id))
    new_bal = profile['sab_balance'] + amount
    update_profile(str(user.id), {"sab_balance": new_bal})
    
    embed = discord.Embed(title="💰 Funds Added", color=0x00FF00)
    embed.description = f"Added **{amount:,.2f}** {SAB_EMOJI} to {user.mention}'s vault.\nNew Balance: **{new_bal:,.2f}** {SAB_EMOJI}"
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="remove_sab", description="Remove SAB COINS from a user (Admin Only)")
@app_commands.checks.has_role(int(os.environ.get("ADMIN_ROLE_ID", 0)))
async def remove_sab(interaction: discord.Interaction, user: discord.Member, amount: float):
    profile = get_or_create_profile(str(user.id))
    new_bal = max(0.0, profile['sab_balance'] - amount)
    update_profile(str(user.id), {"sab_balance": new_bal})
    
    embed = discord.Embed(title="📉 Funds Removed", color=0xFF0000)
    embed.description = f"Removed **{amount:,.2f}** {SAB_EMOJI} from {user.mention}'s vault.\nNew Balance: **{new_bal:,.2f}** {SAB_EMOJI}"
    await interaction.response.send_message(embed=embed)


# --- UTILITY COMMANDS ---

@client.tree.command(name="value", description="Scrape Eldorado to find an item's real EUR value")
async def value_cmd(interaction: discord.Interaction, item_name: str):
    await interaction.response.defer()
    
    # Run scraper in a background thread to prevent blocking the async loop
    loop = asyncio.get_event_loop()
    
    def scrape():
        scraper = cloudscraper.create_scraper()
        query = item_name.replace(" ", "%20")
        url = f"https://www.eldorado.gg/search?q={query}"
        
        try:
            req = scraper.get(url, timeout=10)
            soup = BeautifulSoup(req.text, 'html.parser')
            # Look for pricing tags (Class names may need adjustment based on Eldorado's dynamic UI updates)
            price_element = soup.find('div', class_='price') or soup.find('span', text=lambda t: t and '€' in t)
            
            if price_element:
                return price_element.text.strip()
            return None
        except Exception:
            return None

    result = await loop.run_in_executor(None, scrape)

    if result:
        embed = discord.Embed(title="🔍 Market Value Search", color=0x3498DB)
        embed.description = f"**Item:** {item_name}\n**Estimated Value:** {result}"
        embed.set_footer(text="Data scraped from Eldorado.gg")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ Could not retrieve pricing for `{item_name}` right now. The site structure may have changed or the item doesn't exist.")

# --- ERROR HANDLER ---
@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    else:
        print(f"Command Error: {error}")

# Launch Bot
if __name__ == "__main__":
    client.run(TOKEN)

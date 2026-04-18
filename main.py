import os
import discord
from discord import app_commands
from discord.ext import tasks
import requests
import cloudscraper
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv
import asyncio

# --- SETUP ---
load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", 0))
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

# --- HELPERS ---
async def coin_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=f"{v['emoji']} {k}", value=k) 
            for k, v in COINS.items() if current.lower() in k.lower()][:25]

def get_profile(user_id: str):
    res = supabase.table("profiles").select("*").eq("user_id", user_id).execute()
    if not res.data:
        p = {"user_id": user_id, "sab_balance": 0.0, "portfolio": {k: 0.0 for k in COINS}}
        supabase.table("profiles").insert(p).execute()
        return p
    return res.data[0]

# --- CHART BUTTONS ---
class ChartView(discord.ui.View):
    def __init__(self, coin_key, prices):
        super().__init__(timeout=60)
        self.coin_key = coin_key
        self.prices = prices

    def create_embed(self, timeframe):
        data = COINS[self.coin_key]
        p_data = self.prices.get(data['ref'], {"eur": 0, "eur_24h_change": 0})
        embed = discord.Embed(title=f"{data['emoji']} {data['name']} Market ({timeframe})", color=0x2b2d31)
        embed.add_field(name="Current Price", value=f"€{p_data['eur']:,.4f}", inline=True)
        embed.add_field(name="24h Change", value=f"{p_data.get('eur_24h_change', 0):+.2f}%", inline=True)
        # Using Sparkline as a dynamic chart placeholder
        embed.set_image(url=f"https://www.coingecko.com/coins/{data['ref']}/sparkline.png")
        embed.set_footer(text=f"Last updated via API • Timeframe: {timeframe}")
        return embed

    @discord.ui.button(label="24H", style=discord.ButtonStyle.blurple)
    async def h24(self, it, btn): await it.response.edit_message(embed=self.create_embed("24H"))
    @discord.ui.button(label="7D", style=discord.ButtonStyle.gray)
    async def d7(self, it, btn): await it.response.edit_message(embed=self.create_embed("7D"))
    @discord.ui.button(label="1M", style=discord.ButtonStyle.gray)
    async def m1(self, it, btn): await it.response.edit_message(embed=self.create_embed("1M"))
    @discord.ui.button(label="1Y", style=discord.ButtonStyle.gray)
    async def y1(self, it, btn): await it.response.edit_message(embed=self.create_embed("1Y"))

class SAB_Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)
        self.market_prices = {}

    async def setup_hook(self):
        self.update_prices.start()
        await self.tree.sync()

    @tasks.loop(seconds=60)
    async def update_prices(self):
        try:
            ids = ",".join([c["ref"] for c in COINS.values()])
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur&include_24hr_change=true")
            if r.status_code == 200: self.market_prices = r.json()
        except: pass

client = SAB_Bot()

# --- THE ELDORADO SEARCH (/value) ---
@client.tree.command(name="value", description="Find average Eldorado price for a Brainrot item")
async def value(interaction: discord.Interaction, item_name: str):
    await interaction.response.defer() # Scaping takes time
    
    search_query = item_name.replace(" ", "+")
    url = f"https://www.eldorado.gg/steal-a-brainrot-brainrots/i/259?searchQuery={search_query}&gamePageOfferIndex=1&gamePageOfferSize=25"
    
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # This selector targets the price elements on Eldorado
        price_elements = soup.select('.price-amount')[:25]
        
        if not price_elements:
            return await interaction.followup.send(f"❌ No listings found for `{item_name}`.")
            
        prices = [float(p.get_text().replace('$', '').replace(',', '')) for p in price_elements]
        avg_price = sum(prices) / len(prices)
        
        embed = discord.Embed(title="🔎 Eldorado Value Search", color=0x2b2d31)
        embed.add_field(name="Item", value=f"`{item_name}`", inline=True)
        embed.add_field(name="Listings Analyzed", value=len(prices), inline=True)
        embed.add_field(name="Average Market Price", value=f"**${avg_price:,.2f}**", inline=False)
        embed.set_footer(text="Data scraped from Eldorado.gg")
        
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error scraping Eldorado: {str(e)}")

# --- TRADING WITH AUTOCOMPLETE ---
@client.tree.command(name="buy", description="Buy coins with SAB balance")
@app_commands.autocomplete(coin=coin_autocomplete)
async def buy(interaction: discord.Interaction, coin: str, amount: float):
    if coin not in COINS: return await interaction.response.send_message("❌ Pick a coin from the list!", ephemeral=True)
    p = get_profile(str(interaction.user.id))
    price = client.market_prices.get(COINS[coin]['ref'], {}).get('eur', 0)
    cost = price * amount
    
    if p['sab_balance'] < cost: return await interaction.response.send_message(f"❌ You need {cost:,.2f} SAB.", ephemeral=True)
    
    p['portfolio'][coin] = p['portfolio'].get(coin, 0) + amount
    supabase.table("profiles").update({"sab_balance": p['sab_balance'] - cost, "portfolio": p['portfolio']}).eq("user_id", str(interaction.user.id)).execute()
    await interaction.response.send_message(f"✅ Bought **{amount} {coin}** for {cost:,.2f} {SAB_EMOJI}")

@client.tree.command(name="sell", description="Sell your coins for SAB")
@app_commands.autocomplete(coin=coin_autocomplete)
async def sell(interaction: discord.Interaction, coin: str, amount: float):
    if coin not in COINS: return await interaction.response.send_message("❌ Pick a coin from the list!", ephemeral=True)
    p = get_profile(str(interaction.user.id))
    if p['portfolio'].get(coin, 0) < amount: return await interaction.response.send_message("❌ Not enough coins.", ephemeral=True)
    
    price = client.market_prices.get(COINS[coin]['ref'], {}).get('eur', 0)
    gain = price * amount
    
    p['portfolio'][coin] -= amount
    supabase.table("profiles").update({"sab_balance": p['sab_balance'] + gain, "portfolio": p['portfolio']}).eq("user_id", str(interaction.user.id)).execute()
    await interaction.response.send_message(f"✅ Sold **{amount} {coin}** for {gain:,.2f} {SAB_EMOJI}")

# --- CHART WITH BUTTONS ---
@client.tree.command(name="chart", description="Show coin info with interactive chart buttons")
@app_commands.autocomplete(coin=coin_autocomplete)
async def chart(interaction: discord.Interaction, coin: str):
    if coin not in COINS: return await interaction.response.send_message("❌ Pick a coin from the list!", ephemeral=True)
    view = ChartView(coin, client.market_prices)
    await interaction.response.send_message(embed=view.create_embed("24H"), view=view)

# --- STANDARDS ---
@client.tree.command(name="profile", description="View your vault")
async def profile(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    p = get_profile(str(target.id))
    embed = discord.Embed(title=f"🏦 Vault: {target.display_name}", color=0xFFD700)
    embed.add_field(name="SAB Balance", value=f"{p['sab_balance']:,.2f} {SAB_EMOJI}", inline=False)
    holdings = [f"{COINS[k]['emoji']} {k}: {v:,.2f}" for k,v in p['portfolio'].items() if v > 0]
    embed.add_field(name="Portfolio", value="\n".join(holdings) if holdings else "Empty", inline=False)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="withdraw", description="Request withdrawal")
async def withdraw(interaction: discord.Interaction, amount: float):
    p = get_profile(str(interaction.user.id))
    if p['sab_balance'] < amount: return await interaction.response.send_message("❌ Low balance.", ephemeral=True)
    supabase.table("profiles").update({"sab_balance": p['sab_balance'] - amount}).eq("user_id", str(interaction.user.id)).execute()
    chan = await interaction.guild.create_text_channel(f"withdraw-{interaction.user.name}", category=interaction.guild.get_channel(TICKET_CATEGORY_ID))
    await chan.send(f"⚠️ **Request:** {interaction.user.mention} wants to withdraw {amount} {SAB_EMOJI}")
    await interaction.response.send_message("✅ Ticket created.", ephemeral=True)

client.run(TOKEN)

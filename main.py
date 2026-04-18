import os, discord, requests, cloudscraper, json, asyncio
from discord import app_commands, ui
from discord.ext import tasks
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
TOKEN = os.getenv("BOT_TOKEN")
SAB_EMOJI = "<:SAB:1495012520510099577>"

# Coin Config with official API IDs
COINS = {
    "ELEPHANT": {"name": "Elephant", "ref": "bitcoin", "color": "rgb(247, 147, 26)"},
    "MEOWL": {"name": "Meowl", "ref": "ethereum", "color": "rgb(98, 126, 234)"},
    "GARAMA": {"name": "Garama", "ref": "binancecoin", "color": "rgb(243, 186, 47)"},
    "SKIBIDI": {"name": "Skibidi", "ref": "solana", "color": "rgb(20, 241, 149)"},
    "DRAG": {"name": "Dragon", "ref": "ripple", "color": "rgb(35, 41, 47)"},
    "KETCHURU": {"name": "Ketchuru", "ref": "tron", "color": "rgb(255, 0, 19)"},
    "TICTAC": {"name": "Tictac", "ref": "cardano", "color": "rgb(0, 51, 173)"},
    "SUPREME": {"name": "Supreme", "ref": "dogecoin", "color": "rgb(194, 166, 51)"},
    "KETUPAT": {"name": "Ketupat", "ref": "shiba-inu", "color": "rgb(255, 0, 0)"},
    "TANG": {"name": "Tang", "ref": "pepe", "color": "rgb(61, 148, 33)"}
}

# --- DATABASE HELPERS ---
def get_profile(uid: str):
    res = supabase.table("profiles").select("*").eq("user_id", uid).execute()
    if not res.data:
        p = {"user_id": uid, "sab_balance": 1000.0, "portfolio": {k: 0.0 for k in COINS}}
        supabase.table("profiles").insert(p).execute()
        return p
    return res.data[0]

# --- TRADING MODAL ---
class TradeModal(ui.Modal):
    amount_input = ui.TextInput(label="Amount (SAB or %)", placeholder="e.g. 500 or 25%", required=True)

    def __init__(self, coin, mode, price, profile):
        super().__init__(title=f"{mode} {coin}")
        self.coin, self.mode, self.price, self.p = coin, mode, price, profile

    async def on_submit(self, it: discord.Interaction):
        val = self.amount_input.value.strip()
        is_pct = "%" in val
        try:
            num = float(val.replace("%", ""))
        except: return await it.response.send_message("❌ Invalid number.", ephemeral=True)

        if self.mode == "BUY":
            sab_to_spend = (self.p['sab_balance'] * (num/100)) if is_pct else num
            if sab_to_spend > self.p['sab_balance'] or sab_to_spend <= 0:
                return await it.response.send_message("❌ Insufficient SAB balance.", ephemeral=True)
            
            coin_amt = sab_to_spend / self.price
            self.p['sab_balance'] -= sab_to_spend
            self.p['portfolio'][self.coin] = self.p['portfolio'].get(self.coin, 0) + coin_amt
            msg = f"✅ Spent **{sab_to_spend:,.2f} SAB** to buy **{coin_amt:,.6f} {self.coin}**"

        else: # SELL
            current_coins = self.p['portfolio'].get(self.coin, 0)
            # Sell % of coins or sell specific SAB worth of coins
            if is_pct:
                coins_to_sell = current_coins * (num/100)
                sab_gain = coins_to_sell * self.price
            else:
                sab_gain = num
                coins_to_sell = num / self.price
            
            if coins_to_sell > current_coins or coins_to_sell <= 0:
                return await it.response.send_message("❌ You don't have enough coins.", ephemeral=True)
            
            self.p['sab_balance'] += sab_gain
            self.p['portfolio'][self.coin] -= coins_to_sell
            msg = f"✅ Sold **{coins_to_sell:,.4f} {self.coin}** for **{sab_gain:,.2f} SAB**"

        supabase.table("profiles").update(self.p).eq("user_id", str(it.user.id)).execute()
        await it.response.send_message(msg, ephemeral=True)

# --- REAL-TIME CHART VIEW ---
class ChartView(ui.View):
    def __init__(self, coin, price_data, history):
        super().__init__(timeout=None)
        self.coin, self.price_data, self.history = coin, price_data, history

    def generate_chart_url(self):
        # Format history data for QuickChart
        prices = [p[1] for p in self.history]
        labels = ["" for _ in prices] # Hide labels for cleaner look
        
        config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "data": prices,
                    "borderColor": COINS[self.coin]["color"],
                    "borderWidth": 4,
                    "pointRadius": 0,
                    "fill": True,
                    "backgroundColor": "rgba(0,0,0,0.1)"
                }]
            },
            "options": {
                "scales": {"xAxes": [{"display": False}], "yAxes": [{"display": True, "gridLines": {"color": "rgba(255,255,255,0.05)"}}]},
                "legend": {"display": False}
            }
        }
        return f"https://quickchart.io/chart?bkg=rgb(43,45,49)&width=600&height=300&c={json.dumps(config)}"

    @ui.button(label="BUY", style=discord.ButtonStyle.green)
    async def buy_btn(self, it, btn):
        p = get_profile(str(it.user.id))
        await it.response.send_modal(TradeModal(self.coin, "BUY", self.price_data['eur'], p))

    @ui.button(label="SELL", style=discord.ButtonStyle.red)
    async def sell_btn(self, it, btn):
        p = get_profile(str(it.user.id))
        await it.response.send_modal(TradeModal(self.coin, "SELL", self.price_data['eur'], p))

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

bot = SAB_Bot()

@bot.tree.command(name="chart", description="Professional market chart and trade terminal")
@app_commands.autocomplete(coin=lambda it, cur: [app_commands.Choice(name=k, value=k) for k in COINS if cur.lower() in k.lower()])
async def chart(it: discord.Interaction, coin: str):
    coin = coin.upper()
    if coin not in COINS: return await it.response.send_message("❌ Unknown coin.", ephemeral=True)
    await it.response.defer()

    # Fetch real 7-day history for the "Up/Down" detailed look
    ref = COINS[coin]['ref']
    hist_r = requests.get(f"https://api.coingecko.com/api/v3/coins/{ref}/market_chart?vs_currency=eur&days=7")
    
    if hist_r.status_code != 200:
        return await it.followup.send("❌ Market API busy. Try again in 10s.")
    
    history = hist_r.json()['prices']
    price_data = bot.market_prices.get(ref, {"eur": 0, "eur_24h_change": 0})
    
    view = ChartView(coin, price_data, history)
    embed = discord.Embed(title=f"📈 {COINS[coin]['name']} / EUR", color=0x2b2d31)
    embed.add_field(name="Live Price", value=f"**€{price_data['eur']:,.8f}**", inline=True)
    embed.add_field(name="24h Change", value=f"`{price_data['eur_24h_change']:+.2f}%`", inline=True)
    embed.set_image(url=view.generate_chart_url())
    
    await it.followup.send(embed=embed, view=view)

@bot.tree.command(name="value", description="Average Eldorado.gg price scraper")
async def value(it: discord.Interaction, search: str):
    await it.response.defer()
    # Improved scraper logic for items like '50m/s'
    query = search.replace(" ", "+").replace("/", "%2F")
    url = f"https://www.eldorado.gg/steal-a-brainrot-brainrots/i/259?searchQuery={query}"
    
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','mobile': False,'platform': 'windows'})
    r = scraper.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Target listing prices
    price_tags = soup.select('.price-amount')
    if not price_tags:
        return await it.followup.send(f"❌ Nothing found on Eldorado for `{search}`.")
        
    prices = []
    for p in price_tags[:25]:
        try: prices.append(float(p.text.replace('$','').replace(',','').strip()))
        except: continue
        
    avg = sum(prices) / len(prices)
    embed = discord.Embed(title=f"🔎 Market Value: {search}", color=0x5865F2)
    embed.add_field(name="Average Price (Top 25)", value=f"**${avg:,.2f}**", inline=False)
    embed.set_footer(text="Live scraping from Eldorado.gg")
    await it.followup.send(embed=embed)

bot.run(TOKEN)

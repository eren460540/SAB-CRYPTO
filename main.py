import os, discord, requests, cloudscraper, json
from discord import app_commands, ui
from discord.ext import tasks
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
TOKEN = os.getenv("BOT_TOKEN")
SAB_EMOJI = "<:SAB:1495012520510099577>"

COINS = {
    "ELEPHANT": {"name": "Elephant", "ref": "bitcoin", "color": "rgb(247, 147, 26)", "emoji": "<:ELEPHANT:1494995440213688340>"},
    "MEOWL": {"name": "Meowl", "ref": "ethereum", "color": "rgb(98, 126, 234)", "emoji": "<:MEOWL:1494995595222454366>"},
    "GARAMA": {"name": "Garama", "ref": "binancecoin", "color": "rgb(243, 186, 47)", "emoji": "<:GARAMA:1494995007910842418>"},
    "SKIBIDI": {"name": "Skibidi", "ref": "solana", "color": "rgb(20, 241, 149)", "emoji": "<:SKIBIDI:1494995556030746714>"},
    "DRAG": {"name": "Dragon", "ref": "ripple", "color": "rgb(35, 41, 47)", "emoji": "<:DRAG:1494995236068397127>"},
    "KETCHURU": {"name": "Ketchuru", "ref": "tron", "color": "rgb(255, 0, 19)", "emoji": "<:KETCHURU:1494996298733191308>"},
    "TICTAC": {"name": "Tictac", "ref": "cardano", "color": "rgb(0, 51, 173)", "emoji": "<:TICTAC:1494996594473308190>"},
    "SUPREME": {"name": "La Supreme", "ref": "dogecoin", "color": "rgb(194, 166, 51)", "emoji": "<:SUPREME:1494997175531470960>"},
    "KETUPAT": {"name": "Ketupat", "ref": "shiba-inu", "color": "rgb(255, 0, 0)", "emoji": "<:KETUPAT:1494996070303006793>"},
    "TANG": {"name": "Tang", "ref": "pepe", "color": "rgb(61, 148, 33)", "emoji": "<:TANG:1494995850831728701>"}
}

# --- HELPERS ---
def get_profile(uid: str):
    res = supabase.table("profiles").select("*").eq("user_id", uid).execute()
    if not res.data:
        p = {"user_id": uid, "sab_balance": 1000.0, "portfolio": {k: 0.0 for k in COINS}}
        supabase.table("profiles").insert(p).execute()
        return p
    return res.data[0]

async def coin_autocomplete(it: discord.Interaction, current: str):
    # EMOJIS REMOVED FROM PICKER
    return [app_commands.Choice(name=k, value=k) for k in COINS if current.lower() in k.lower()][:25]

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
        except: return await it.response.send_message("❌ Invalid input.", ephemeral=True)

        if self.mode == "BUY":
            sab_to_spend = (self.p['sab_balance'] * (num/100)) if is_pct else num
            if sab_to_spend > self.p['sab_balance'] or sab_to_spend <= 0:
                return await it.response.send_message("❌ Insufficient SAB.", ephemeral=True)
            
            coin_amt = sab_to_spend / self.price
            self.p['sab_balance'] -= sab_to_spend
            self.p['portfolio'][self.coin] = self.p['portfolio'].get(self.coin, 0) + coin_amt
            msg = f"✅ Bought **{coin_amt:,.6f} {self.coin}** for **{sab_to_spend:,.2f} SAB**"

        else: # SELL
            current_coins = self.p['portfolio'].get(self.coin, 0)
            if is_pct:
                coins_to_sell = current_coins * (num/100)
                sab_gain = coins_to_sell * self.price
            else:
                sab_gain = num
                coins_to_sell = num / self.price
            
            if coins_to_sell > current_coins or coins_to_sell <= 0:
                return await it.response.send_message("❌ Not enough coins.", ephemeral=True)
            
            self.p['sab_balance'] += sab_gain
            self.p['portfolio'][self.coin] -= coins_to_sell
            msg = f"✅ Sold for **{sab_gain:,.2f} SAB**"

        supabase.table("profiles").update(self.p).eq("user_id", str(it.user.id)).execute()
        await it.response.send_message(msg, ephemeral=True)

# --- CHART VIEW ---
class ChartView(ui.View):
    def __init__(self, coin, price_data, history):
        super().__init__(timeout=None)
        self.coin, self.price_data, self.history = coin, price_data, history

    def generate_chart_url(self):
        # FIX: Sample the data (every 4th point) to prevent URL being too long
        prices = [p[1] for p in self.history[::4]] 
        
        config = {
            "type": "line",
            "data": {
                "labels": ["" for _ in prices],
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
        # Final URL safety check
        url = f"https://quickchart.io/chart?bkg=rgb(43,45,49)&width=500&height=250&c={json.dumps(config)}"
        return url

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
@app_commands.autocomplete(coin=coin_autocomplete)
async def chart(it: discord.Interaction, coin: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid coin.", ephemeral=True)
    await it.response.defer()

    ref = COINS[coin_key]['ref']
    hist_r = requests.get(f"https://api.coingecko.com/api/v3/coins/{ref}/market_chart?vs_currency=eur&days=7")
    
    if hist_r.status_code != 200:
        return await it.followup.send("❌ Market API busy. Try again shortly.")
    
    history = hist_r.json()['prices']
    price_data = bot.market_prices.get(ref, {"eur": 0, "eur_24h_change": 0})
    
    view = ChartView(coin_key, price_data, history)
    embed = discord.Embed(title=f"{COINS[coin_key]['emoji']} {COINS[coin_key]['name']} Market", color=0x2b2d31)
    embed.add_field(name="Price", value=f"**€{price_data['eur']:,.8f}**", inline=True)
    embed.add_field(name="24h Change", value=f"`{price_data['eur_24h_change']:+.2f}%`", inline=True)
    
    chart_url = view.generate_chart_url()
    embed.set_image(url=chart_url)
    
    await it.followup.send(embed=embed, view=view)

@bot.tree.command(name="value", description="Eldorado Average Price Scraper")
async def value(it: discord.Interaction, search: str):
    await it.response.defer()
    query = search.replace(" ", "+").replace("/", "%2F")
    url = f"https://www.eldorado.gg/steal-a-brainrot-brainrots/i/259?searchQuery={query}"
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','mobile': False,'platform': 'windows'})
    r = scraper.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    prices = [float(x.text.replace('$','').replace(',','')) for x in soup.select('.price-amount')[:25]]
    if not prices: return await it.followup.send(f"❌ Nothing found for `{search}`.")
    avg = sum(prices)/len(prices)
    await it.followup.send(embed=discord.Embed(title=f"🔎 Search: {search}", description=f"**Average Price: ${avg:,.2f}**", color=0x5865F2))

bot.run(TOKEN)

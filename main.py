import os, discord, requests, json, urllib.parse
from discord import app_commands, ui
from discord.ext import tasks
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", 0))
SAB_EMOJI = "<:SAB:1495012520510099577>"

# Updated References for CryptoCompare Symbols
COINS = {
    "ELEPHANT": {"symbol": "BTC", "color": "#f7931a", "emoji": "<:ELEPHANT:1494995440213688340>", "name": "Elephant"},
    "MEOWL": {"symbol": "ETH", "color": "#627eea", "emoji": "<:MEOWL:1494995595222454366>", "name": "Meowl"},
    "GARAMA": {"symbol": "BNB", "color": "#f3ba2f", "emoji": "<:GARAMA:1494995007910842418>", "name": "Garama"},
    "SKIBIDI": {"symbol": "SOL", "color": "#14f195", "emoji": "<:SKIBIDI:1494995556030746714>", "name": "Skibidi"},
    "DRAG": {"symbol": "XRP", "color": "#23292f", "emoji": "<:DRAG:1494995236068397127>", "name": "Dragon"},
    "KETCHURU": {"symbol": "TRX", "color": "#ff0013", "emoji": "<:KETCHURU:1494996298733191308>", "name": "Ketchuru"},
    "TICTAC": {"symbol": "ADA", "color": "#0033ad", "emoji": "<:TICTAC:1494996594473308190>", "name": "Tictac"},
    "SUPREME": {"symbol": "DOGE", "color": "#c2a633", "emoji": "<:SUPREME:1494997175531470960>", "name": "La Supreme"},
    "KETUPAT": {"symbol": "SHIB", "color": "#ff0000", "emoji": "<:KETUPAT:1494996070303006793>", "name": "Ketupat"},
    "TANG": {"symbol": "PEPE", "color": "#3d9421", "emoji": "<:TANG:1494995850831728701>", "name": "Tang"}
}

def get_profile(uid: str):
    res = supabase.table("profiles").select("*").eq("user_id", uid).execute()
    if not res.data:
        p = {"user_id": uid, "sab_balance": 1000.0, "portfolio": {k: 0.0 for k in COINS}}
        supabase.table("profiles").insert(p).execute()
        return p
    return res.data[0]

def format_price(val):
    return f"{val:,.8f}".rstrip('0').rstrip('.')

async def coin_autocomplete(it: discord.Interaction, current: str):
    return [app_commands.Choice(name=k, value=k) for k in COINS if current.lower() in k.lower()][:25]

class ChartView(ui.View):
    def __init__(self, coin, bot_instance, current_days=7):
        super().__init__(timeout=None)
        self.coin, self.bot, self.current_days = coin, bot_instance, current_days

    async def update_chart(self, it: discord.Interaction, days: int, label: str):
        if not it.response.is_done(): await it.response.defer()
        self.current_days = days
        symbol = COINS[self.coin]['symbol']
        
        # Determine API endpoint based on timeframe
        if days <= 1:
            url = f"https://min-api.cryptocompare.com/data/v2/histohour?fsym={symbol}&tsym=EUR&limit=24"
        elif days <= 30:
            url = f"https://min-api.cryptocompare.com/data/v2/histoday?fsym={symbol}&tsym=EUR&limit={days}"
        else:
            url = f"https://min-api.cryptocompare.com/data/v2/histoday?fsym={symbol}&tsym=EUR&limit={days}"

        try:
            r = requests.get(url).json()
            if r.get('Response') == "Success":
                data_points = r['Data']['Data']
                prices = [round(d['close'], 8) for d in data_points]
                
                # Sample to 25 points to ensure URL stays short
                step = max(1, len(prices) // 25)
                sampled_prices = prices[::step]

                config = {
                    "type": "line",
                    "data": {"labels": ["" for _ in sampled_prices], "datasets": [{"data": sampled_prices, "borderColor": COINS[self.coin]["color"], "borderWidth": 4, "pointRadius": 0, "fill": False}]},
                    "options": {"scales": {"xAxes": [{"display": False}], "yAxes": [{"display": False}]}, "legend": {"display": False}}
                }
                
                params = urllib.parse.quote(json.dumps(config))
                chart_url = f"https://quickchart.io/chart?bkg=rgb(43,45,49)&w=500&h=200&c={params}"
                
                # Fetch Current Price Detail
                curr_url = f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={symbol}&tsyms=EUR"
                curr_r = requests.get(curr_url).json()
                raw_data = curr_r['RAW'][symbol]['EUR']
                
                embed = discord.Embed(title=f"{COINS[self.coin]['emoji']} {COINS[self.coin]['name']} Market ({label})", color=0x2b2d31)
                embed.add_field(name="Detailed Price", value=f"**€{format_price(raw_data['PRICE'])}**", inline=True)
                embed.add_field(name="24h Change", value=f"`{raw_data['CHANGEPCT24HOUR']:+.2f}%`", inline=True)
                embed.set_image(url=chart_url)
                await it.edit_original_response(embed=embed, view=self)
            else:
                await it.followup.send("⚠️ CryptoCompare limit reached. Wait 1 min.", ephemeral=True)
        except Exception as e:
            await it.followup.send(f"❌ Chart Error: {str(e)}", ephemeral=True)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary, row=0)
    async def btn_refresh(self, it, btn):
        await self.update_chart(it, self.current_days, f"{self.current_days}D" if self.current_days > 1 else "24H")

    @ui.button(label="24H", style=discord.ButtonStyle.secondary, row=1)
    async def btn_24h(self, it, btn): await self.update_chart(it, 1, "24H")
    @ui.button(label="7D", style=discord.ButtonStyle.secondary, row=1)
    async def btn_7d(self, it, btn): await self.update_chart(it, 7, "7D")
    @ui.button(label="1M", style=discord.ButtonStyle.secondary, row=1)
    async def btn_1m(self, it, btn): await self.update_chart(it, 30, "1M")
    @ui.button(label="3M", style=discord.ButtonStyle.secondary, row=1)
    async def btn_3m(self, it, btn): await self.update_chart(it, 90, "3M")
    @ui.button(label="1Y", style=discord.ButtonStyle.secondary, row=1)
    async def btn_1y(self, it, btn): await self.update_chart(it, 365, "1Y")

class SAB_Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)
        self.market_prices = {}

    async def setup_hook(self):
        self.update_prices.start()
        await self.tree.sync()

    @tasks.loop(seconds=15)
    async def update_prices(self):
        try:
            fsyms = ",".join([c["symbol"] for c in COINS.values()])
            r = requests.get(f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={fsyms}&tsyms=EUR")
            if r.status_code == 200:
                data = r.json().get('RAW', {})
                # Standardize format for the rest of the bot
                new_prices = {}
                for coin_name, info in COINS.items():
                    symbol = info['symbol']
                    if symbol in data:
                        new_prices[symbol] = {
                            "eur": data[symbol]['EUR']['PRICE'],
                            "eur_24h_change": data[symbol]['EUR']['CHANGEPCT24HOUR']
                        }
                self.market_prices = new_prices
        except: pass

bot = SAB_Bot()

@bot.tree.command(name="chart")
@app_commands.autocomplete(coin=coin_autocomplete)
async def chart(it: discord.Interaction, coin: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid", ephemeral=True)
    view = ChartView(coin_key, bot)
    await view.update_chart(it, 7, "7D")

@bot.tree.command(name="buy")
@app_commands.autocomplete(coin=coin_autocomplete)
async def buy(it: discord.Interaction, coin: str, amount: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid", ephemeral=True)
    price = bot.market_prices.get(COINS[coin_key]['symbol'], {}).get('eur', 0)
    if price == 0: return await it.response.send_message("❌ Syncing...", ephemeral=True)
    p = get_profile(str(it.user.id))
    try:
        val = amount.strip()
        num = float(val.replace("%", ""))
        spend = (p['sab_balance'] * (num/100)) if "%" in val else num
        if spend > p['sab_balance'] or spend <= 0: return await it.response.send_message("❌ Poor", ephemeral=True)
        c_amt = spend / price
        p['sab_balance'] -= spend
        p['portfolio'][coin_key] = p['portfolio'].get(coin_key, 0) + c_amt
        supabase.table("profiles").update(p).eq("user_id", str(it.user.id)).execute()
        await it.response.send_message(f"✅ Bought {c_amt:,.6f} {coin_key}")
    except: await it.response.send_message("❌ Error", ephemeral=True)

@bot.tree.command(name="sell")
@app_commands.autocomplete(coin=coin_autocomplete)
async def sell(it: discord.Interaction, coin: str, amount: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid", ephemeral=True)
    price = bot.market_prices.get(COINS[coin_key]['symbol'], {}).get('eur', 0)
    p = get_profile(str(it.user.id))
    try:
        val, cur = amount.strip(), p['portfolio'].get(coin_key, 0)
        num = float(val.replace("%", ""))
        s_amt = (cur * (num/100)) if "%" in val else num
        if s_amt > cur or s_amt <= 0: return await it.response.send_message("❌ Not enough", ephemeral=True)
        gain = s_amt * price
        p['sab_balance'] += gain
        p['portfolio'][coin_key] -= s_amt
        supabase.table("profiles").update(p).eq("user_id", str(it.user.id)).execute()
        await it.response.send_message(f"✅ Sold for {gain:,.2f} SAB")
    except: await it.response.send_message("❌ Error", ephemeral=True)

@bot.tree.command(name="wallet")
async def wallet(it: discord.Interaction, user: discord.Member = None):
    t = user or it.user
    p = get_profile(str(t.id))
    emb = discord.Embed(title=f"🏦 Vault: {t.display_name}", color=0xFFD700)
    emb.add_field(name="Balance", value=f"**{p['sab_balance']:,.2f}** {SAB_EMOJI}", inline=False)
    port, net = [], p['sab_balance']
    for c, a in p['portfolio'].items():
        if a > 0:
            pr = bot.market_prices.get(COINS[c]['symbol'], {}).get('eur', 0)
            val = a * pr
            net += val
            port.append(f"{COINS[c]['emoji']} **{c}**: {a:,.6f} (≈ {val:,.2f} SAB)")
    emb.add_field(name="Holdings", value="\n".join(port) if port else "Empty", inline=False)
    emb.add_field(name="Net Worth", value=f"**{net:,.2f} SAB**", inline=False)
    await it.response.send_message(embed=emb)

@bot.tree.command(name="add_sab")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def add_sab(it, user: discord.Member, amount: float):
    p = get_profile(str(user.id))
    p['sab_balance'] += amount
    supabase.table("profiles").update(p).eq("user_id", str(user.id)).execute()
    await it.response.send_message(f"✅ Added {amount}")

@bot.tree.command(name="deposit")
async def deposit(it):
    g, cat, adm = it.guild, it.guild.get_channel(TICKET_CATEGORY_ID), it.guild.get_role(ADMIN_ROLE_ID)
    ov = {g.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True), adm: discord.PermissionOverwrite(view_channel=True)}
    ch = await g.create_text_channel(f"dep-{it.user.name}", category=cat, overwrites=ov)
    await it.response.send_message(f"✅ {ch.mention}", ephemeral=True)

@bot.tree.command(name="withdraw")
async def withdraw(it):
    g, cat, adm = it.guild, it.guild.get_channel(TICKET_CATEGORY_ID), it.guild.get_role(ADMIN_ROLE_ID)
    ov = {g.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True), adm: discord.PermissionOverwrite(view_channel=True)}
    ch = await g.create_text_channel(f"wit-{it.user.name}", category=cat, overwrites=ov)
    await it.response.send_message(f"✅ {ch.mention}", ephemeral=True)

bot.run(TOKEN)

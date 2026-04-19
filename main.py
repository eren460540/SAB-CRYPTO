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

COINS = {
    "ELEPHANT": {"symbol": "BTC", "color": "241, 147, 26", "emoji": "<:ELEPHANT:1494995440213688340>", "name": "Elephant"},
    "MEOWL": {"symbol": "ETH", "color": "98, 126, 234", "emoji": "<:MEOWL:1494995595222454366>", "name": "Meowl"},
    "GARAMA": {"symbol": "BNB", "color": "243, 186, 47", "emoji": "<:GARAMA:1494995007910842418>", "name": "Garama"},
    "SKIBIDI": {"symbol": "SOL", "color": "20, 241, 149", "emoji": "<:SKIBIDI:1494995556030746714>", "name": "Skibidi"},
    "DRAG": {"symbol": "XRP", "color": "35, 41, 47", "emoji": "<:DRAG:1494995236068397127>", "name": "Dragon"},
    "KETCHURU": {"symbol": "TRX", "color": "255, 0, 19", "emoji": "<:KETCHURU:1494996298733191308>", "name": "Ketchuru"},
    "TICTAC": {"symbol": "ADA", "color": "0, 51, 173", "emoji": "<:TICTAC:1494996594473308190>", "name": "Tictac"},
    "SUPREME": {"symbol": "DOGE", "color": "194, 166, 51", "emoji": "<:SUPREME:1494997175531470960>", "name": "La Supreme"},
    "KETUPAT": {"symbol": "SHIB", "color": "255, 0, 0", "emoji": "<:KETUPAT:1494996070303006793>", "name": "Ketupat"},
    "TANG": {"symbol": "PEPE", "color": "61, 148, 33", "emoji": "<:TANG:1494995850831728701>", "name": "Tang"}
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
    def __init__(self, coin, bot_instance, user_id, current_days=7):
        super().__init__(timeout=None)
        self.coin, self.bot, self.user_id, self.current_days = coin, bot_instance, user_id, current_days

    async def update_chart(self, it: discord.Interaction, days: int, label: str):
        if not it.response.is_done(): await it.response.defer()
        self.current_days = days
        symbol = COINS[self.coin]['symbol']
        
        # HistData Fetching
        limit = 24 if days <= 1 else days
        endpoint = "histohour" if days <= 1 else "histoday"
        url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}?fsym={symbol}&tsym=EUR&limit={limit}"

        try:
            r = requests.get(url).json()
            if r.get('Response') == "Success":
                data_points = r['Data']['Data']
                prices = [d['close'] for d in data_points]
                
                # Logic for Red/Green based on performance in the selected range
                start_price = prices[0]
                end_price = prices[-1]
                diff = end_price - start_price
                pct_change = (diff / start_price) * 100
                
                # Colors: Green if +, Red if -
                theme_color = "rgb(0, 200, 81)" if diff >= 0 else "rgb(255, 68, 68)"
                fill_color = "rgba(0, 200, 81, 0.1)" if diff >= 0 else "rgba(255, 68, 68, 0.1)"
                embed_color = 0x00c851 if diff >= 0 else 0xff4444

                # QuickChart Config (Area Chart Style)
                config = {
                    "type": "line",
                    "data": {
                        "labels": ["" for _ in prices],
                        "datasets": [{
                            "data": prices,
                            "borderColor": theme_color,
                            "borderWidth": 3,
                            "pointRadius": 0,
                            "fill": True,
                            "backgroundColor": fill_color,
                            "lineTension": 0.3
                        }]
                    },
                    "options": {
                        "scales": {"xAxes": [{"display": False}], "yAxes": [{"display": False}]},
                        "legend": {"display": False},
                        "elements": {"line": {"tension": 0.4}}
                    }
                }
                
                chart_url = f"https://quickchart.io/chart?bkg=rgb(43,45,49)&w=500&h=250&c={urllib.parse.quote(json.dumps(config))}"
                
                # Portfolio Info
                p = get_profile(str(self.user_id))
                amt_owned = p['portfolio'].get(self.coin, 0)
                current_val_sab = amt_owned * end_price
                
                embed = discord.Embed(title=f"{COINS[self.coin]['emoji']} {COINS[self.coin]['name']} Market", color=embed_color)
                embed.add_field(name="Current Price", value=f"**€{format_price(end_price)}**", inline=True)
                embed.add_field(name=f"{label} Change", value=f"`{pct_change:+.2f}%`", inline=True)
                
                # Portfolio Overlay (Right Middleish)
                port_text = f"💰 **Owned:** `{amt_owned:,.4f}`\n"
                port_text += f"💎 **Value:** `{current_val_sab:,.2f} SAB`"
                embed.add_field(name="Your Position", value=port_text, inline=False)
                
                embed.set_image(url=chart_url)
                await it.edit_original_response(embed=embed, view=self)
            else:
                await it.followup.send("⚠️ API Limit reached.", ephemeral=True)
        except Exception as e:
            await it.followup.send(f"❌ Chart Error: {str(e)}", ephemeral=True)

    @ui.button(label="24H", style=discord.ButtonStyle.secondary)
    async def btn_24h(self, it, btn): await self.update_chart(it, 1, "24h")
    @ui.button(label="7D", style=discord.ButtonStyle.secondary)
    async def btn_7d(self, it, btn): await self.update_chart(it, 7, "7d")
    @ui.button(label="1M", style=discord.ButtonStyle.secondary)
    async def btn_1m(self, it, btn): await self.update_chart(it, 30, "1m")
    @ui.button(label="1Y", style=discord.ButtonStyle.secondary)
    async def btn_1y(self, it, btn): await self.update_chart(it, 365, "1y")

class AllChartsView(ui.View):
    def __init__(self, bot_instance, user_id, current_days=7):
        super().__init__(timeout=None)
        self.bot, self.user_id, self.current_days = bot_instance, user_id, current_days

    async def update_all_charts(self, it: discord.Interaction, days: int, label: str):
        if not it.response.is_done(): await it.response.defer()
        self.current_days = days
        limit = 24 if days <= 1 else days
        endpoint = "histohour" if days <= 1 else "histoday"
        profile = get_profile(str(it.user.id))
        rows = []

        for coin_key, coin_data in COINS.items():
            symbol = coin_data['symbol']
            url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}?fsym={symbol}&tsym=EUR&limit={limit}"
            try:
                r = requests.get(url).json()
                if r.get('Response') != "Success": continue
                data_points = r.get('Data', {}).get('Data', [])
                prices = [d.get('close', 0) for d in data_points if d.get('close') is not None]
                if len(prices) < 2: continue
                start_price, end_price = prices[0], prices[-1]
                if start_price == 0: continue
                pct_change = ((end_price - start_price) / start_price) * 100
                amt_owned = profile['portfolio'].get(coin_key, 0)
                current_val_sab = amt_owned * end_price
                rows.append({
                    "coin_key": coin_key,
                    "end_price": end_price,
                    "pct_change": pct_change,
                    "amt_owned": amt_owned,
                    "current_val_sab": current_val_sab
                })
            except: continue

        rows.sort(key=lambda x: x['end_price'], reverse=True)
        embed = discord.Embed(title="All Coin Markets", color=0x5865F2)

        if not rows:
            embed.description = "⚠️ Could not load market data right now."
        else:
            for row in rows[:10]:
                c = COINS[row["coin_key"]]
                field_name = f"{c['emoji']} {c['name']} ({c['symbol']})"
                field_val = (
                    f"Price: **€{format_price(row['end_price'])}**\n"
                    f"{label} Change: `{row['pct_change']:+.2f}%`\n"
                    f"Owned: `{row['amt_owned']:,.4f}`\n"
                    f"Value: `{row['current_val_sab']:,.2f} SAB`"
                )
                embed.add_field(name=field_name, value=field_val, inline=False)

        try:
            await it.edit_original_response(embed=embed, view=self)
        except Exception as e:
            if it.response.is_done():
                await it.followup.send(f"❌ All charts error: {str(e)}", ephemeral=True)
            else:
                await it.response.send_message(f"❌ All charts error: {str(e)}", ephemeral=True)

    @ui.button(label="24H", style=discord.ButtonStyle.secondary)
    async def btn_24h(self, it, btn): await self.update_all_charts(it, 1, "24h")
    @ui.button(label="7D", style=discord.ButtonStyle.secondary)
    async def btn_7d(self, it, btn): await self.update_all_charts(it, 7, "7d")
    @ui.button(label="1M", style=discord.ButtonStyle.secondary)
    async def btn_1m(self, it, btn): await self.update_all_charts(it, 30, "1m")
    @ui.button(label="1Y", style=discord.ButtonStyle.secondary)
    async def btn_1y(self, it, btn): await self.update_all_charts(it, 365, "1y")

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
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid Coin", ephemeral=True)
    view = ChartView(coin_key, bot, it.user.id)
    await view.update_chart(it, 7, "7d")

@bot.tree.command(name="all_charts")
async def all_charts(it: discord.Interaction):
    view = AllChartsView(bot, it.user.id)
    await view.update_all_charts(it, 7, "7d")

@bot.tree.command(name="buy")
@app_commands.autocomplete(coin=coin_autocomplete)
async def buy(it: discord.Interaction, coin: str, amount: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid", ephemeral=True)
    price = bot.market_prices.get(COINS[coin_key]['symbol'], {}).get('eur', 0)
    if price == 0: return await it.response.send_message("❌ Syncing prices...", ephemeral=True)
    p = get_profile(str(it.user.id))
    try:
        val = amount.strip()
        num = float(val.replace("%", ""))
        spend = (p['sab_balance'] * (num/100)) if "%" in val else num
        if spend > p['sab_balance'] or spend <= 0: return await it.response.send_message("❌ Insufficient SAB balance.", ephemeral=True)
        c_amt = spend / price
        p['sab_balance'] -= spend
        p['portfolio'][coin_key] = p['portfolio'].get(coin_key, 0) + c_amt
        supabase.table("profiles").update(p).eq("user_id", str(it.user.id)).execute()
        await it.response.send_message(f"✅ Purchased {c_amt:,.6f} {coin_key} for {spend:,.2f} SAB")
    except: await it.response.send_message("❌ Enter a valid number or percentage (e.g. 50%)", ephemeral=True)

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
        if s_amt > cur or s_amt <= 0: return await it.response.send_message(f"❌ You only have {cur:,.6f} {coin_key}", ephemeral=True)
        gain = s_amt * price
        p['sab_balance'] += gain
        p['portfolio'][coin_key] -= s_amt
        supabase.table("profiles").update(p).eq("user_id", str(it.user.id)).execute()
        await it.response.send_message(f"✅ Sold {s_amt:,.6f} {coin_key} for {gain:,.2f} SAB")
    except: await it.response.send_message("❌ Error processing sale.", ephemeral=True)

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
    emb.add_field(name="Holdings", value="\n".join(port) if port else "No assets held.", inline=False)
    emb.add_field(name="Net Worth", value=f"**{net:,.2f} SAB**", inline=False)
    await it.response.send_message(embed=emb)

@bot.tree.command(name="add_sab")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def add_sab(it, user: discord.Member, amount: float):
    p = get_profile(str(user.id))
    p['sab_balance'] += amount
    supabase.table("profiles").update(p).eq("user_id", str(user.id)).execute()
    await it.response.send_message(f"✅ Added {amount} SAB to {user.display_name}")

@bot.tree.command(name="deposit")
async def deposit(it):
    g, cat, adm = it.guild, it.guild.get_channel(TICKET_CATEGORY_ID), it.guild.get_role(ADMIN_ROLE_ID)
    ov = {g.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True), adm: discord.PermissionOverwrite(view_channel=True)}
    ch = await g.create_text_channel(f"dep-{it.user.name}", category=cat, overwrites=ov)
    await it.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)

@bot.tree.command(name="withdraw")
async def withdraw(it):
    g, cat, adm = it.guild, it.guild.get_channel(TICKET_CATEGORY_ID), it.guild.get_role(ADMIN_ROLE_ID)
    ov = {g.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True), adm: discord.PermissionOverwrite(view_channel=True)}
    ch = await g.create_text_channel(f"wit-{it.user.name}", category=cat, overwrites=ov)
    await it.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)

bot.run(TOKEN)

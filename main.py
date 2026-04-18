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
    "ELEPHANT": {"name": "Elephant", "ref": "bitcoin", "color": "#f7931a", "emoji": "<:ELEPHANT:1494995440213688340>"},
    "MEOWL": {"name": "Meowl", "ref": "ethereum", "color": "#627eea", "emoji": "<:MEOWL:1494995595222454366>"},
    "GARAMA": {"name": "Garama", "ref": "binancecoin", "color": "#f3ba2f", "emoji": "<:GARAMA:1494995007910842418>"},
    "SKIBIDI": {"name": "Skibidi", "ref": "solana", "color": "#14f195", "emoji": "<:SKIBIDI:1494995556030746714>"},
    "DRAG": {"name": "Dragon", "ref": "ripple", "color": "#23292f", "emoji": "<:DRAG:1494995236068397127>"},
    "KETCHURU": {"name": "Ketchuru", "ref": "tron", "color": "#ff0013", "emoji": "<:KETCHURU:1494996298733191308>"},
    "TICTAC": {"name": "Tictac", "ref": "cardano", "color": "#0033ad", "emoji": "<:TICTAC:1494996594473308190>"},
    "SUPREME": {"name": "La Supreme", "ref": "dogecoin", "color": "#c2a633", "emoji": "<:SUPREME:1494997175531470960>"},
    "KETUPAT": {"name": "Ketupat", "ref": "shiba-inu", "color": "#ff0000", "emoji": "<:KETUPAT:1494996070303006793>"},
    "TANG": {"name": "Tang", "ref": "pepe", "color": "#3d9421", "emoji": "<:TANG:1494995850831728701>"}
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
    return [app_commands.Choice(name=k, value=k) for k in COINS if current.lower() in k.lower()][:25]

# --- CHART TIMEFRAME VIEW ---
class ChartView(ui.View):
    def __init__(self, coin, bot_instance):
        super().__init__(timeout=None)
        self.coin = coin
        self.bot = bot_instance

    async def update_chart(self, it: discord.Interaction, days: int, label: str):
        await it.response.defer()
        ref = COINS[self.coin]['ref']
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/{ref}/market_chart?vs_currency=eur&days={days}")
            if r.status_code == 200:
                history = r.json()['prices']
                
                # Dynamic sampling: We only keep ~50 points so the URL never breaks Discord limits
                step = max(1, len(history) // 50) 
                prices = [round(p[1], 8) for p in history[::step]]
                
                config = {
                    "type": "line",
                    "data": {"labels": ["" for _ in prices], "datasets": [{"data": prices, "borderColor": COINS[self.coin]["color"], "borderWidth": 3, "pointRadius": 0, "fill": False}]},
                    "options": {"scales": {"xAxes": [{"display": False}], "yAxes": [{"display": True}]}, "legend": {"display": False}}
                }
                params = urllib.parse.quote(json.dumps(config))
                chart_url = f"https://quickchart.io/chart?bkg=rgb(43,45,49)&w=500&h=250&c={params}"
                
                price_data = self.bot.market_prices.get(ref, {"eur": 0, "eur_24h_change": 0})
                embed = discord.Embed(title=f"{COINS[self.coin]['emoji']} {COINS[self.coin]['name']} Market ({label})", color=0x2b2d31)
                embed.add_field(name="Current Price", value=f"**€{price_data['eur']:,.8f}**", inline=True)
                embed.add_field(name="24h Change", value=f"`{price_data['eur_24h_change']:+.2f}%`", inline=True)
                embed.set_image(url=chart_url)
                
                await it.edit_original_response(embed=embed, view=self)
            else:
                await it.followup.send("⚠️ API busy, try clicking again in a few seconds.", ephemeral=True)
        except Exception as e:
            await it.followup.send(f"❌ Error fetching chart: {str(e)}", ephemeral=True)

    @ui.button(label="24H", style=discord.ButtonStyle.blurple)
    async def btn_24h(self, it: discord.Interaction, btn: ui.Button): await self.update_chart(it, 1, "24H")

    @ui.button(label="7D", style=discord.ButtonStyle.blurple)
    async def btn_7d(self, it: discord.Interaction, btn: ui.Button): await self.update_chart(it, 7, "7D")

    @ui.button(label="1M", style=discord.ButtonStyle.blurple)
    async def btn_1m(self, it: discord.Interaction, btn: ui.Button): await self.update_chart(it, 30, "1M")

    @ui.button(label="3M", style=discord.ButtonStyle.blurple)
    async def btn_3m(self, it: discord.Interaction, btn: ui.Button): await self.update_chart(it, 90, "3M")

    @ui.button(label="1Y", style=discord.ButtonStyle.blurple)
    async def btn_1y(self, it: discord.Interaction, btn: ui.Button): await self.update_chart(it, 365, "1Y")


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
            ids = ",".join([c["ref"] for c in COINS.values()])
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur&include_24hr_change=true")
            if r.status_code == 200: self.market_prices = r.json()
        except: pass

bot = SAB_Bot()

@bot.tree.command(name="chart", description="Professional market chart terminal")
@app_commands.autocomplete(coin=coin_autocomplete)
async def chart(it: discord.Interaction, coin: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid coin.", ephemeral=True)
    
    view = ChartView(coin_key, bot)
    # Default to 7D chart on first open
    await view.update_chart(it, 7, "7D")

# --- SECURE TRADING COMMANDS (Always uses Live Memory Price) ---
@bot.tree.command(name="buy", description="Buy a coin using SAB or % of your balance (e.g. 500 or 25%)")
@app_commands.autocomplete(coin=coin_autocomplete)
async def buy(it: discord.Interaction, coin: str, amount: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid coin.", ephemeral=True)
    
    price = bot.market_prices.get(COINS[coin_key]['ref'], {}).get('eur', 0)
    if price == 0: return await it.response.send_message("❌ Live market data syncing. Try again in 10s.", ephemeral=True)

    p = get_profile(str(it.user.id))
    val = amount.strip()
    is_pct = "%" in val
    try: num = float(val.replace("%", ""))
    except: return await it.response.send_message("❌ Invalid format. Use e.g. 500 or 25%", ephemeral=True)

    sab_to_spend = (p['sab_balance'] * (num/100)) if is_pct else num
    if sab_to_spend > p['sab_balance'] or sab_to_spend <= 0:
        return await it.response.send_message("❌ Insufficient SAB balance.", ephemeral=True)
    
    coin_amt = sab_to_spend / price
    p['sab_balance'] -= sab_to_spend
    p['portfolio'][coin_key] = p['portfolio'].get(coin_key, 0) + coin_amt
    
    supabase.table("profiles").update(p).eq("user_id", str(it.user.id)).execute()
    await it.response.send_message(f"✅ Executed Market Buy!\nSpent: **{sab_to_spend:,.2f} SAB**\nReceived: **{coin_amt:,.6f} {coin_key}**\n*Locked in at €{price:,.8f}*")

@bot.tree.command(name="sell", description="Sell a coin using quantity or % of your holdings (e.g. 50 or 100%)")
@app_commands.autocomplete(coin=coin_autocomplete)
async def sell(it: discord.Interaction, coin: str, amount: str):
    coin_key = coin.upper()
    if coin_key not in COINS: return await it.response.send_message("❌ Invalid coin.", ephemeral=True)
    
    price = bot.market_prices.get(COINS[coin_key]['ref'], {}).get('eur', 0)
    if price == 0: return await it.response.send_message("❌ Live market data syncing. Try again in 10s.", ephemeral=True)

    p = get_profile(str(it.user.id))
    current_coins = p['portfolio'].get(coin_key, 0)
    
    val = amount.strip()
    is_pct = "%" in val
    try: num = float(val.replace("%", ""))
    except: return await it.response.send_message("❌ Invalid format. Use e.g. 50 or 100%", ephemeral=True)

    if is_pct:
        coins_to_sell = current_coins * (num/100)
    else:
        coins_to_sell = num
    
    if coins_to_sell > current_coins or coins_to_sell <= 0:
        return await it.response.send_message(f"❌ You don't have enough {coin_key} to sell.", ephemeral=True)
    
    sab_gain = coins_to_sell * price
    p['sab_balance'] += sab_gain
    p['portfolio'][coin_key] -= coins_to_sell
    
    supabase.table("profiles").update(p).eq("user_id", str(it.user.id)).execute()
    await it.response.send_message(f"✅ Executed Market Sell!\nSold: **{coins_to_sell:,.6f} {coin_key}**\nReceived: **{sab_gain:,.2f} SAB**\n*Locked in at €{price:,.8f}*")


@bot.tree.command(name="wallet", description="View your balances, holdings, and net worth")
async def wallet(it: discord.Interaction, user: discord.Member = None):
    target = user or it.user
    p = get_profile(str(target.id))
    
    embed = discord.Embed(title=f"🏦 Vault: {target.display_name}", color=0xFFD700)
    embed.add_field(name="Liquid SAB Balance", value=f"**{p['sab_balance']:,.2f}** {SAB_EMOJI}", inline=False)
    
    portfolio_text = []
    net_worth = p['sab_balance']
    
    for c, amount in p['portfolio'].items():
        if amount > 0:
            price = bot.market_prices.get(COINS[c]['ref'], {}).get('eur', 0)
            value_in_sab = amount * price
            net_worth += value_in_sab
            portfolio_text.append(f"{COINS[c]['emoji']} **{c}**: {amount:,.4f} (≈ {value_in_sab:,.2f} SAB)")
            
    embed.add_field(name="Coin Holdings", value="\n".join(portfolio_text) if portfolio_text else "*No coins*", inline=False)
    embed.add_field(name="Total Net Worth", value=f"**{net_worth:,.2f} SAB**", inline=False)
    await it.response.send_message(embed=embed)

@bot.tree.command(name="add_sab", description="Admin Only: Add SAB to a user")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def add_sab(it: discord.Interaction, user: discord.Member, amount: float):
    p = get_profile(str(user.id))
    p['sab_balance'] += amount
    supabase.table("profiles").update({"sab_balance": p['sab_balance']}).eq("user_id", str(user.id)).execute()
    await it.response.send_message(f"✅ Added **{amount:,.2f} SAB** to {user.mention}.", ephemeral=True)

@bot.tree.command(name="deposit", description="Open a deposit ticket")
async def deposit(it: discord.Interaction):
    guild = it.guild
    cat = guild.get_channel(TICKET_CATEGORY_ID)
    admin = guild.get_role(ADMIN_ROLE_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        it.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        admin: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    chan = await guild.create_text_channel(f"deposit-{it.user.name}", category=cat, overwrites=overwrites)
    await it.response.send_message(f"✅ Ticket created: {chan.mention}", ephemeral=True)
    await chan.send(f"{it.user.mention} Welcome! Please state how much you want to deposit.")

@bot.tree.command(name="withdraw", description="Open a withdrawal ticket")
async def withdraw(it: discord.Interaction):
    guild = it.guild
    cat = guild.get_channel(TICKET_CATEGORY_ID)
    admin = guild.get_role(ADMIN_ROLE_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        it.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        admin: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    chan = await guild.create_text_channel(f"withdraw-{it.user.name}", category=cat, overwrites=overwrites)
    await it.response.send_message(f"✅ Ticket created: {chan.mention}", ephemeral=True)
    await chan.send(f"{it.user.mention} Welcome! Please state how much you want to withdraw.")

bot.run(TOKEN)

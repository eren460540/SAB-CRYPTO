import discord
from discord import app_commands
import httpx

# Helper function to fetch data and sort by most valuable (highest price)
async def fetch_coin_data(timeframe: str):
    # Using CoinGecko as an example to fetch live crypto data
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc", # Fetches top market cap coins first
        "per_page": 20, 
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": timeframe
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            # Sort explicitly from most valuable (highest price) to least valuable
            sorted_data = sorted(data, key=lambda x: x.get('current_price', 0), reverse=True)
            return sorted_data[:10] # Return only the top 10
        return None

# Helper function to construct the embed
def build_embed(data, timeframe_label, timeframe_key):
    embed = discord.Embed(
        title=f"🏆 Top 10 Most Valuable Coins ({timeframe_label})",
        description="Detailed stats for the top 10 coins by unit price.",
        color=discord.Color.gold()
    )
    
    if not data:
        embed.description = "⚠️ Failed to fetch data from the API. Please try again later."
        return embed

    for index, coin in enumerate(data, start=1):
        name = coin.get("name", "Unknown")
        symbol = coin.get("symbol", "").upper()
        price = coin.get("current_price", 0)
        market_cap = coin.get("market_cap", 0)
        volume = coin.get("total_volume", 0)

        # Map the requested timeframe to the correct API response key
        change_key = f"price_change_percentage_{timeframe_key}_in_currency"
        change = coin.get(change_key)
        
        # Fallback to 24h if specific timeframe is missing
        if change is None:
            change = coin.get("price_change_percentage_24h", 0)

        change_str = f"{change:+.2f}%" if change is not None else "N/A"

        # Formatted like your typical /chart info without the picture
        info = (
            f"**Price:** ${price:,.2f}\n"
            f"**Change:** {change_str}\n"
            f"**Market Cap:** ${market_cap:,.0f}\n"
            f"**Volume:** ${volume:,.0f}"
        )
        embed.add_field(name=f"{index}. {name} ({symbol})", value=info, inline=False)
        
    return embed

# UI View containing the 4 Timelapse Buttons
class TimelapseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def update_message(self, interaction: discord.Interaction, label: str, key: str):
        # Acknowledge the button press to prevent timeout
        await interaction.response.defer()
        
        # Fetch updated data and edit the embed
        data = await fetch_coin_data(key)
        embed = build_embed(data, label, key)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="1D", style=discord.ButtonStyle.primary, custom_id="all_charts_1d")
    async def btn_1d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_message(interaction, "1 Day", "24h")

    @discord.ui.button(label="1W", style=discord.ButtonStyle.primary, custom_id="all_charts_1w")
    async def btn_1w(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_message(interaction, "1 Week", "7d")

    @discord.ui.button(label="1M", style=discord.ButtonStyle.primary, custom_id="all_charts_1m")
    async def btn_1m(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_message(interaction, "1 Month", "30d")

    @discord.ui.button(label="1Y", style=discord.ButtonStyle.primary, custom_id="all_charts_1y")
    async def btn_1y(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_message(interaction, "1 Year", "1y")


# The actual Slash Command
@app_commands.command(name="all_charts", description="Shows info for the top 10 most valuable coins (No charts).")
async def all_charts(interaction: discord.Interaction):
    # Defer the response because API calls take longer than 3 seconds sometimes
    await interaction.response.defer()

    # Fetch initial 1-Day data
    data = await fetch_coin_data("24h")
    embed = build_embed(data, "1 Day", "24h")
    view = TimelapseView()

    # Send the follow-up message with the embed and buttons
    await interaction.followup.send(embed=embed, view=view)

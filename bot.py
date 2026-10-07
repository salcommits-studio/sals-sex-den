import os, time, secrets, html, asyncio
import aiohttp, discord
from aiohttp import web
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")  # e.g. https://verify.yourdomain.com
PORT = int(os.environ.get("PORT", 8080))

OWNER_ID = 1556386435643478047
ROLE_ID = 1557354880069410826
CHANNEL_ID = 1557354934201225256
BOT_NAME = "SAL'S SEX DEN"
BOT_BIO = "LOOKING OVER SAL'S SEX DEN"

API = "https://discord.com/api/v10"
REDIRECT_URI = f"{BASE_URL}/callback"
SCOPES = "identify"  # only reads username/ID; no joining servers, no DMs
states: dict[str, float] = {}  # state -> expiry

intents = discord.Intents.default()
intents.message_content = True  # needed for ? prefix commands
bot = commands.Bot(command_prefix="?", intents=intents, owner_id=OWNER_ID)


# ───────────────────────── website ─────────────────────────
CSS = """
*{box-sizing:border-box;margin:0}
body{min-height:100vh;display:grid;place-items:center;padding:24px;font-family:'Quicksand',sans-serif;color:#5a3a4a;
background:radial-gradient(circle at 15% 20%,#ffe3ee 0,transparent 45%),radial-gradient(circle at 85% 80%,#ffd1e3 0,transparent 45%),#fff8fb}
.card{width:100%;max-width:440px;background:rgba(255,255,255,.85);backdrop-filter:blur(14px);border:1.5px solid #ffd6e6;
border-radius:32px;padding:44px 36px;text-align:center;box-shadow:0 20px 60px rgba(255,105,160,.18)}
.logo{width:92px;height:92px;margin:0 auto 18px;border-radius:50%;display:grid;place-items:center;font-size:42px;
background:linear-gradient(135deg,#ffb3d1,#ff7eb3);box-shadow:0 10px 28px rgba(255,105,160,.35)}
h1{font-family:'Pacifico',cursive;font-weight:400;font-size:2.3rem;color:#ff5c9d;margin-bottom:6px}
.tag{font-size:.72rem;letter-spacing:.3em;color:#d98aab;font-weight:700;margin-bottom:22px}
p{line-height:1.6;color:#8a6577;margin-bottom:26px;font-size:.98rem}
.btn{display:inline-flex;align-items:center;gap:10px;padding:15px 34px;border-radius:999px;border:0;cursor:pointer;
font:700 1rem 'Quicksand',sans-serif;color:#fff;text-decoration:none;background:linear-gradient(135deg,#ff8fbf,#ff5c9d);
box-shadow:0 10px 26px rgba(255,92,157,.4);transition:.2s}
.btn:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(255,92,157,.5)}
.perms{margin-top:24px;font-size:.78rem;color:#c79bb0}
.hearts{margin-top:18px;letter-spacing:.4em;color:#ffb3d1}
.ok{background:linear-gradient(135deg,#ffd1e3,#ff8fbf)}
"""

def page(title, emoji, heading, body, button=""):
    return web.Response(content_type="text/html", text=f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Pacifico&family=Quicksand:wght@500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main class="card"><div class="logo">{emoji}</div>
<h1>{heading}</h1><div class="tag">LOOKING OVER SAL'S DEN</div><p>{body}</p>{button}
<div class="hearts">♡ ♡ ♡</div></main></body></html>""")


async def index(request):
    return page(
        "Verify · Sal's Den", "🎀", "Sal's Den",
        "Welcome, cutie! Authorize with Discord to prove you're a real person and unlock the den.",
        '<a class="btn" href="/login">🌸 Verify with Discord</a>'
        '<div class="perms">We only see your Discord username &amp; ID. Nothing else.</div>',
    )


async def login(request):
    now = time.time()
    for k in [k for k, v in states.items() if v < now]:
        states.pop(k, None)
    state = secrets.token_urlsafe(24)
    states[state] = now + 600
    url = (f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code"
           f"&redirect_uri={aiohttp.helpers.quote(REDIRECT_URI, safe='')}&scope={SCOPES}&state={state}&prompt=none")
    raise web.HTTPFound(url)


def fail(msg):
    return page("Oops · Sal's Den", "🥀", "Oops!", html.escape(msg),
                '<a class="btn" href="/">Try again</a>')


async def callback(request):
    code, state = request.query.get("code"), request.query.get("state")
    if not code or states.pop(state, 0) < time.time():
        return fail("That link expired or was invalid. Please start again.")

    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API}/oauth2/token", data={
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code",
            "code": code, "redirect_uri": REDIRECT_URI}) as r:
            if r.status != 200:
                return fail("Discord rejected the authorization. Please try again.")
            token = (await r.json())["access_token"]
        async with s.get(f"{API}/users/@me", headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status != 200:
                return fail("Couldn't read your Discord profile.")
            user = await r.json()
        # we don't keep the token – verification only needs the user ID
        await s.post(f"{API}/oauth2/token/revoke", data={
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "token": token})

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return fail("The den is sleeping right now. Try again in a moment.")
    guild = channel.guild
    role = guild.get_role(ROLE_ID)
    try:
        member = await guild.fetch_member(int(user["id"]))
    except discord.NotFound:
        return fail("You need to be in Sal's Den server first, then verify again!")
    if role is None:
        return fail("Verified role not found. Please tell an admin.")
    try:
        await member.add_roles(role, reason="Verified via website")
    except discord.Forbidden:
        return fail("I can't give that role yet. An admin needs to move my role above it.")

    name = html.escape(user.get("global_name") or user["username"])
    return page("Verified · Sal's Den", "💖", "You're in!",
                f"Welcome, <b>{name}</b>! You're verified and your role is on its way. You can close this tab. ✨")


# ───────────────────────── bot ─────────────────────────
def verify_embed_and_view():
    embed = discord.Embed(
        title="🎀 Verify to enter Sal's Den",
        description="Press the button below, authorize with Discord, and you'll get your role instantly ♡",
        color=0xFF8FBF,
    )
    embed.set_footer(text="LOOKING OVER SAL'S DEN")
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Verify", emoji="🌸", style=discord.ButtonStyle.link, url=BASE_URL))
    return embed, view


async def post_verify_message():
    channel = bot.get_channel(CHANNEL_ID)
    embed, view = verify_embed_and_view()
    await channel.send(embed=embed, view=view)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="over Sal's Den"))
    # name (rate-limited by Discord, so only if different)
    if bot.user.name != BOT_NAME:
        try:
            await bot.user.edit(username=BOT_NAME)
        except discord.HTTPException as e:
            print("Couldn't rename bot:", e)
    # bio = application description
    async with aiohttp.ClientSession() as s:
        await s.patch(f"{API}/applications/@me", headers={"Authorization": f"Bot {TOKEN}"},
                      json={"description": BOT_BIO})
    # post the verify button once
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async for m in channel.history(limit=25):
            if m.author == bot.user and m.embeds:
                return
        await post_verify_message()


@bot.hybrid_command(name="verifybutton", description="Post the verification button (owner only)")
@commands.is_owner()
async def verifybutton(ctx):
    """Works as ?verifybutton and /verifybutton."""
    await post_verify_message()
    await ctx.send("Verify button posted ♡", ephemeral=True)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("Only Sal can use this command 🎀", ephemeral=True)
    else:
        print("Command error:", error)


async def setup_hook():
    await bot.tree.sync()  # registers the slash commands


bot.setup_hook = setup_hook


async def main():
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/login", login), web.get("/callback", callback)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"Website on :{PORT}")
    async with bot:
        await bot.start(TOKEN)


asyncio.run(main())

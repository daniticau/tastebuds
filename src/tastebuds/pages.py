"""The plain pages: privacy, terms, docs, and the icon.

The Muse connector form asks for each of them. Every claim on the privacy page
must match what the code does. When the code changes, change the page in the same commit.
"""

from html import escape
from pathlib import Path

from pydantic import ValidationError

from tastebuds.config import Settings, get_settings, public_base_url
from tastebuds.playbook import PLAYBOOK

_TEMPLATE = (Path(__file__).parent / "web" / "page.html").read_text(encoding="utf-8")
_UPDATED = "September 27, 2026"

ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#C7764F"/>
      <stop offset="1" stop-color="#93492E"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="116" fill="url(#bg)"/>
  <g fill="#FFF6EA">
    <path d="M256 300C150 300 86 236 86 130c106 0 170 64 170 170z"/>
    <path d="M256 300c0-106 64-170 170-170 0 106-64 170-170 170z"/>
    <path d="M235 280h42v122a21 21 0 0 1-42 0z"/>
  </g>
</svg>
"""


def _page(title: str, body: str) -> str:
    return _TEMPLATE.replace("__TITLE__", escape(title)).replace("__BODY__", body)


def _settings() -> Settings | None:
    """A page must render even when no database URL is configured."""
    try:
        return get_settings()
    except ValidationError:
        return None


def _support_email() -> str | None:
    settings = _settings()
    return settings.support_email if settings else None


def _contact() -> str:
    email = _support_email()
    if not email:
        return "<p>Ask your assistant, or reach us through the project page.</p>"
    safe = escape(email)
    return f'<p>Write to <a href="mailto:{safe}">{safe}</a>. We answer within a few days.</p>'


def privacy_page() -> str:
    return _page(
        "Privacy",
        f"""
<h1>Privacy</h1>
<p class="updated">Last updated {_UPDATED}</p>

<p>Tastebuds is a food memory for AI assistants. It is built so that it cannot say who you are.
You have no account. Your assistant holds one random token for you, and Tastebuds keeps your
food taste under that token.</p>

<h2>What Tastebuds stores</h2>
<ul>
  <li><strong>A random token.</strong> The server makes it. Your assistant keeps it.</li>
  <li><strong>Your food preferences,</strong> when your assistant sends them: home city, neighborhoods,
      dietary needs, allergies, cuisines you like and avoid, budget, spice level, the atmosphere you like,
      and a short note.</li>
  <li><strong>Your opinions on places.</strong> For each place: whether you liked it, the dishes you named,
      the occasion, the price level, and one short comment. Your assistant writes the comment without
      names or personal details. The server removes emails, phone numbers, links, and handles again.</li>
  <li><strong>Friend links.</strong> Two tokens, a closeness level from 1 to 3 for each side, each side's
      choice to share picks, and the invite code.</li>
  <li><strong>Circles.</strong> A group code and the tokens of its members.</li>
  <li><strong>What it recommended to you,</strong> so your assistant can ask how it went, and which
      finds from friends it already told you about.</li>
</ul>

<h2>What Tastebuds does not store</h2>
<ul>
  <li>Your name, email, phone number, or any account.</li>
  <li>Your messages, your contacts, or how often you message anyone.</li>
  <li>Your friends' names. A friend is a code. Your own assistant turns the code into a name.</li>
  <li>Your location history. A search may include a location. Tastebuds uses it for that one answer.</li>
</ul>

<h2>Who can see what</h2>
<ul>
  <li><strong>Everyone</strong> gets totals for a place: how many people liked it, which dishes people
      praise, and short comments with no author.</li>
  <li><strong>A linked friend</strong> sees which places you liked, the dishes you named, and your short
      comment, marked as yours. This happens only when you agreed to the link and chose to share picks.
      You can stop sharing with one friend, or end a link, at any time. Ask your assistant.</li>
  <li><strong>A circle</strong> sees counts only, never who said what, and only when the circle has
      three or more members.</li>
</ul>

<h2>Dietary needs and allergies</h2>
<p>These can say something about your health or your beliefs. Tastebuds keeps them under your random
token only, uses them to rank places for you, and shows them to no one else.</p>

<h2>Other companies that handle data</h2>
<ul>
  <li><strong>Neon</strong> hosts the database.</li>
  <li><strong>Railway</strong> runs the server. It keeps standard request logs, which include IP addresses,
      for a short time. The logs hold no request bodies and no tokens.</li>
  <li><strong>TypeSafe AI</strong>, when quick decisions are switched on. It receives place names, the city,
      and dish names, to tell whether two names are the same restaurant. It receives comments only when
      the comment check is switched on.</li>
  <li><strong>Google Fonts</strong> serves the fonts on this website to your browser.</li>
</ul>
<p>To limit abuse, the server keeps IP addresses in memory for about one minute. It never writes them
to the database.</p>
<p>Tastebuds does not sell data and shows no ads.</p>

<h2>Your choices</h2>
<ul>
  <li><strong>See it.</strong> Ask your assistant what it remembers about your food taste.</li>
  <li><strong>Change it.</strong> Tell your assistant what changed.</li>
  <li><strong>Delete it.</strong> Ask your assistant to forget your food taste. Tastebuds deletes your profile,
      your friend links, your circle memberships, and your follow-ups. Your past opinions stay in the
      totals for each place, with no token attached.</li>
</ul>

<h2>Children</h2>
<p>Tastebuds is not meant for children under 13.</p>

<h2>Changes</h2>
<p>When this page changes, the date at the top changes with it.</p>

<h2>Contact</h2>
{_contact()}
""",
    )


def terms_page() -> str:
    return _page(
        "Terms",
        f"""
<h1>Terms</h1>
<p class="updated">Last updated {_UPDATED}</p>

<p>These terms cover the Tastebuds service: the server, its tools for AI assistants, and this website.
If you use Tastebuds, you agree to them.</p>

<h2>What Tastebuds is</h2>
<p>Tastebuds stores food opinions and ranks places to eat. It works through your AI assistant.
A recommendation is an opinion, built from what people said. It is not a promise about any restaurant.</p>

<h2>Allergies and dietary needs</h2>
<p><strong>Tastebuds does not know menus or ingredients.</strong> It cannot tell you that a dish is safe
for you. Always check allergens and dietary needs with the restaurant.</p>

<h2>Your part</h2>
<ul>
  <li>Share opinions about meals you really had.</li>
  <li>Do not post fake opinions, and do not try to push a place up or down.</li>
  <li>Do not send names or personal details about other people.</li>
  <li>Do not overload the service, scrape it, or try to read another person's profile.</li>
  <li>Keep your token private. Anyone who holds it can read your food profile.</li>
</ul>

<h2>Our part</h2>
<ul>
  <li>We handle data as the <a href="/privacy">privacy page</a> says.</li>
  <li>We may remove opinions that break these terms, and we may block abuse.</li>
  <li>We may change or stop the service. We will try to give notice first.</li>
</ul>

<h2>Friends</h2>
<p>When you link with a friend and share picks, that friend sees which places you liked.
Link only with people you trust. You can end a link at any time.</p>

<h2>No warranty</h2>
<p>Tastebuds comes as it is. We do not promise that it is always available or always right.
As far as the law allows, we are not liable for losses that come from using it.</p>

<h2>Changes</h2>
<p>When these terms change, the date at the top changes with them. If you keep using Tastebuds
after a change, you accept the new terms.</p>

<h2>Contact</h2>
{_contact()}
""",
    )


def _tool_rows(tools: list) -> str:
    rows = []
    for tool in tools:
        hints = tool.annotations
        if hints and hints.read_only_hint:
            kind = "read"
        elif hints and hints.destructive_hint:
            kind = "delete"
        else:
            kind = "write"
        summary = (tool.description or "").split("\n", 1)[0]
        rows.append(
            f"<tr><td><code>{escape(tool.name)}</code></td><td>{kind}</td>"
            f"<td>{escape(summary)}</td></tr>",
        )
    return "\n".join(rows)


def docs_page(tools: list) -> str:
    base = escape(public_base_url())
    settings = _settings()
    per_minute = settings.rate_limit_per_minute if settings else 300
    per_day = settings.max_feedback_per_token_per_day if settings else 40
    return _page(
        "Docs",
        f"""
<h1>Docs</h1>
<p class="updated">For assistants, for developers, and for connector review. Last updated {_UPDATED}</p>

<p>Tastebuds gives an AI assistant a food memory. It remembers how one person eats, learns from each
meal they mention, and ranks places for them. Linked friends see where each other like to eat.
It is built for Muse first. Any MCP client works.</p>

<h2>Connect</h2>
<table>
  <tr><th>Surface</th><th>Address</th></tr>
  <tr><td>MCP, streamable HTTP</td><td><code>{base}/mcp</code></td></tr>
  <tr><td>REST, same tools</td><td><code>POST {base}/api/v1/&lt;tool_name&gt;</code></td></tr>
  <tr><td>OpenAPI</td><td><code>{base}/openapi.json</code></td></tr>
  <tr><td>Plain-text guide</td><td><code>{base}/llms.txt</code></td></tr>
</table>
<p>The MCP endpoint is stateless. It answers in plain JSON and accepts any <code>Accept</code> header.</p>

<h2>Sign-in</h2>
<p>There is none. A person has no account. The first call, <code>start_taste_profile</code>, returns a
random <code>taste_id</code>. The assistant keeps it and passes it on every call, as the
<code>taste_id</code> argument or as <code>Authorization: Bearer &lt;taste_id&gt;</code>.
On a connector form, this is auth type "Other".</p>

<h2>Reads and writes</h2>
<p>Every tool carries MCP hints. Reads look things up. Writes save the person's own food opinions and
preferences. One tool deletes. No tool sends a message, spends money, or acts outside Tastebuds.</p>
<div class="scroll">
<table>
  <tr><th>Tool</th><th>Kind</th><th>What it does</th></tr>
  {_tool_rows(tools)}
</table>
</div>

<h2>Testing, for reviewers</h2>
<ul>
  <li>No test account is needed. Call <code>start_taste_profile</code> to get a token.</li>
  <li>Writes take <code>dry_run=true</code>. A dry run checks the input and stores nothing.</li>
  <li><code>get_friend_finds</code> takes <code>peek=true</code>, which marks nothing as told.</li>
  <li><code>delete_taste_profile</code> does nothing without <code>confirm=true</code>.</li>
</ul>
<pre><code>curl -X POST {base}/api/v1/start_taste_profile \\
  -H 'Content-Type: application/json' \\
  -d '{{"home_city": "San Diego", "favorite_places": ["Tajima Ramen"], "dry_run": true}}'</code></pre>

<h2>Limits</h2>
<ul>
  <li>{per_minute} requests per minute per client.</li>
  <li>{per_day} opinions per person per day.</li>
  <li>A search returns at most 10 places.</li>
</ul>

<h2>Data</h2>
<p>See the <a href="/privacy">privacy page</a> and the <a href="/terms">terms</a>.</p>

<h2>Support</h2>
{_contact()}

<h2>The playbook</h2>
<p>This is the guide the assistant follows. The server also returns it from
<code>start_taste_profile</code> and as the MCP instructions.</p>
<pre><code>{escape(PLAYBOOK)}</code></pre>
""",
    )

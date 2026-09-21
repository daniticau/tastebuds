from fastmcp import FastMCP

from tastebuds.config import public_base_url
from tastebuds.playbook import PLAYBOOK

mcp = FastMCP(
    name="Tastebuds",
    instructions=PLAYBOOK,
    version="0.3.0",
    website_url=public_base_url(),
)

# Import tools so they register with the mcp instance
import tastebuds.tools.onboarding  # noqa: F401, E402
import tastebuds.tools.search  # noqa: F401, E402
import tastebuds.tools.feedback  # noqa: F401, E402
import tastebuds.tools.trending  # noqa: F401, E402
import tastebuds.tools.profile  # noqa: F401, E402
import tastebuds.tools.followups  # noqa: F401, E402
import tastebuds.tools.circles  # noqa: F401, E402
import tastebuds.tools.friends  # noqa: F401, E402

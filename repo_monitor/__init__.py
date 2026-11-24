"""GitHub Repository Monitor.

Deterministisk analys av GitHub-data som Claude Code hämtar via GitHub MCP.
Paketet gör aldrig egna anrop mot GitHub: MCP är den enda datakällan, och
paketet tar emot en "snapshot" (JSON) av det som MCP returnerade.
"""

__version__ = "1.0.0"

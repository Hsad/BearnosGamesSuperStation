import os
import json
from dataclasses import dataclass, field

ARCADE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_DIR = os.path.join(ARCADE_DIR, "games")

CALIBRATE_TEXTCARD = """\
  ██████╗ █████╗ ██╗
 ██╔════╝██╔══██╗██║
 ██║     ███████║██║
 ██║     ██╔══██║██║
 ╚██████╗██║  ██║███████╗
  ╚═════╝╚═╝  ╚═╝╚══════╝
   CONTROLLER CALIBRATE  """

@dataclass
class Game:
    title: str
    description: str
    players: str
    author: str
    slug: str
    directory: str
    textcard: str  # empty string if absent
    is_calibrate: bool = False

CALIBRATE_GAME = Game(
    title="Calibrate Controllers",
    description="Configure arcade controller mappings.",
    players="1",
    author="system",
    slug="_calibrate",
    directory=os.path.expanduser("~/Arcade"),
    textcard=CALIBRATE_TEXTCARD,
    is_calibrate=True,
)

def scan_games(games_dir: str = GAMES_DIR) -> list[Game]:
    games = []
    try:
        entries = os.listdir(games_dir)
    except FileNotFoundError:
        return games

    for slug in sorted(entries):
        game_dir = os.path.join(games_dir, slug)
        if not os.path.isdir(game_dir):
            continue
        launch_sh = os.path.join(game_dir, "launch.sh")
        meta_json = os.path.join(game_dir, "meta.json")
        if not os.path.isfile(launch_sh) or not os.path.isfile(meta_json):
            continue

        try:
            with open(meta_json) as f:
                meta = json.load(f)
        except Exception:
            continue

        if meta.get("hidden"):
            continue

        textcard = ""
        textcard_path = os.path.join(game_dir, "TextCard.txt")
        if os.path.isfile(textcard_path):
            try:
                with open(textcard_path) as f:
                    textcard = f.read()
            except Exception:
                pass

        games.append(Game(
            title=meta.get("title", slug),
            description=meta.get("description", ""),
            players=meta.get("players", "?"),
            author=meta.get("author", ""),
            slug=slug,
            directory=game_dir,
            textcard=textcard,
        ))

    games.sort(key=lambda g: g.title.lower())
    return games

"""
Pseudo-persistent in-memory storage for users and game rooms.
"""

import threading
from typing import Dict, List, Optional
import secrets
from passlib.context import CryptContext

from .models import UserCreate, UserPublic, GameRoom, LeaderboardEntry

# Password hashing (bcrypt by default)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InMemoryStore:
    """Singleton-like in-memory game/user/scoreboard storage."""

    def __init__(self):
        self.users: Dict[str, dict] = {}  # username: {id, username, hashed_pw}
        self.user_ids: Dict[int, str] = {}  # id : username
        self.games: Dict[str, GameRoom] = {}  # room_id : GameRoom
        self.scores: Dict[str, LeaderboardEntry] = {}  # username : LeaderboardEntry
        self._lock = threading.Lock()
        self._user_counter = 1

    # PUBLIC_INTERFACE
    def create_user(self, user: UserCreate) -> UserPublic:
        """Create user. Password is stored as hashed string."""
        with self._lock:
            if user.username in self.users:
                raise ValueError("Username already taken")
            hashed_pw = pwd_context.hash(user.password)
            user_obj = {
                "id": self._user_counter,
                "username": user.username,
                "hashed_pw": hashed_pw,
            }
            self.users[user.username] = user_obj
            self.user_ids[self._user_counter] = user.username
            self._user_counter += 1
            # Leaderboard entry creation
            self.scores[user.username] = LeaderboardEntry(username=user.username, wins=0, losses=0, draws=0, games_played=0)
            return UserPublic(username=user.username, id=user_obj["id"])

    # PUBLIC_INTERFACE
    def verify_user(self, username: str, password: str) -> Optional[UserPublic]:
        """Check credentials validity."""
        with self._lock:
            user_obj = self.users.get(username)
            if not user_obj:
                return None
            if not pwd_context.verify(password, user_obj["hashed_pw"]):
                return None
            return UserPublic(username=username, id=user_obj["id"])

    # PUBLIC_INTERFACE
    def get_user(self, username: str) -> Optional[UserPublic]:
        with self._lock:
            user_obj = self.users.get(username)
            if user_obj:
                return UserPublic(username=username, id=user_obj["id"])
            return None

    # PUBLIC_INTERFACE
    def create_game(self, user: UserPublic) -> GameRoom:
        """Create a new game room, put user as player X, waiting for O to join."""
        with self._lock:
            room_id = secrets.token_hex(4)
            board = [["" for _ in range(3)] for _ in range(3)]
            game = GameRoom(
                room_id=room_id,
                players=[user],
                board=board,
                next_turn=user.username,
                finished=False,
                winner=None,
                moves=[]
            )
            self.games[room_id] = game
            return game

    # PUBLIC_INTERFACE
    def join_game(self, room_id: str, player: UserPublic) -> GameRoom:
        """Let player join room if not full and not finished. Returns updated room."""
        with self._lock:
            game = self.games.get(room_id)
            if not game:
                raise ValueError("Game room not found")
            if len(game.players) >= 2:
                raise ValueError("Game already has two players")
            if player.username in [p.username for p in game.players]:
                raise ValueError("Player already in game")
            if game.finished:
                raise ValueError("Game already finished")
            game.players.append(player)
            return game

    # PUBLIC_INTERFACE
    def list_games(self) -> List[GameRoom]:
        """List all game rooms."""
        with self._lock:
            return list(self.games.values())

    # PUBLIC_INTERFACE
    def get_game(self, room_id: str) -> Optional[GameRoom]:
        with self._lock:
            return self.games.get(room_id)

    # PUBLIC_INTERFACE
    def save_game(self, game: GameRoom):
        """Update game in store (call after any mutation!)."""
        with self._lock:
            self.games[game.room_id] = game

    # PUBLIC_INTERFACE
    def update_scoreboard(self, winner: Optional[str], players: List[UserPublic], draw: bool = False):
        """Update win/loss/draw counts."""
        with self._lock:
            for player in players:
                entry = self.scores.setdefault(player.username, LeaderboardEntry(username=player.username, wins=0, draws=0, losses=0, games_played=0))
                entry.games_played += 1
                if draw:
                    entry.draws += 1
                elif player.username == winner:
                    entry.wins += 1
                else:
                    entry.losses += 1

    # PUBLIC_INTERFACE
    def get_leaderboard(self) -> List[LeaderboardEntry]:
        with self._lock:
            return sorted(list(self.scores.values()), key=lambda e: (-e.wins, e.losses, -e.draws, e.username))

STORE = InMemoryStore()

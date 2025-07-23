"""
Models for the Tic Tac Toe backend (FastAPI).
"""

from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class PlayerColor(str, Enum):
    X = "X"
    O = "O"


# PUBLIC_INTERFACE
class UserCreate(BaseModel):
    """Incoming user registration."""
    username: str = Field(..., min_length=3, max_length=32, description="Player's username.")
    password: str = Field(..., min_length=6, max_length=64, description="Player's password (hashed before storing in prod).")


# PUBLIC_INTERFACE
class UserLogin(BaseModel):
    """Login credentials."""
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)


# PUBLIC_INTERFACE
class UserPublic(BaseModel):
    """Minimal public user info."""
    username: str = Field(..., description="Player's username.")
    id: int = Field(..., description="Player id")


# PUBLIC_INTERFACE
class GameCreateRequest(BaseModel):
    """To create a new game room."""
    nickname: str = Field(..., description="Player username for the first player.")


# PUBLIC_INTERFACE
class JoinGameRequest(BaseModel):
    """To join an existing game."""
    room_id: str = Field(..., description="Game room identifier")
    nickname: str = Field(..., description="Player username for joining player.")


# PUBLIC_INTERFACE
class MoveRequest(BaseModel):
    """Make a move in a game."""
    room_id: str = Field(..., description="Game room identifier")
    row: int = Field(..., ge=0, le=2, description="Row index (0-2)")
    col: int = Field(..., ge=0, le=2, description="Column index (0-2)")
    player: str = Field(..., description="Player's username making the move.")


# PUBLIC_INTERFACE
class GameState(BaseModel):
    """Representation of the current board and turn."""
    board: List[List[str]] = Field(..., description="3x3 tic tac toe board, values are 'X', 'O', or ''.")
    next_turn: Optional[str] = Field(None, description="Username of the player whose turn is next.")
    winner: Optional[str] = Field(None, description="Username of the winner, if any.")
    finished: bool = Field(..., description="Whether the game is over.")


# PUBLIC_INTERFACE
class GameRoom(BaseModel):
    """In-memory object for game room."""
    room_id: str
    players: List[UserPublic] = Field(..., min_items=1, max_items=2, description="List of players.")
    board: List[List[str]]
    next_turn: str
    finished: bool
    winner: Optional[str] = None
    moves: List[Dict[str, int]] = Field(default_factory=list)


# PUBLIC_INTERFACE
class GameSummary(BaseModel):
    """High-level summary for scoreboard/history."""
    room_id: str
    players: List[str]
    winner: Optional[str]
    finished: bool


# PUBLIC_INTERFACE
class LeaderboardEntry(BaseModel):
    """Leaderboard/player statistics summary."""
    username: str
    wins: int
    losses: int
    draws: int
    games_played: int


# PUBLIC_INTERFACE
class TokenResponse(BaseModel):
    """JWT/token or session for authenticated player."""
    access_token: str
    token_type: str = "bearer"

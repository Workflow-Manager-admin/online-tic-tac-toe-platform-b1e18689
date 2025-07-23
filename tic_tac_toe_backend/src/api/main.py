from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Dict
from .models import (
    UserCreate, UserPublic, GameCreateRequest, JoinGameRequest,
    MoveRequest, GameRoom, GameState, GameSummary, LeaderboardEntry, TokenResponse
)
from .store import STORE
from .game_logic import make_move
from .auth import create_access_token, get_current_user

openapi_tags = [
    {"name": "auth", "description": "User sign-up and login"},
    {"name": "game", "description": "Start, join, play, and view games"},
    {"name": "scoreboard", "description": "Leaderboard and statistics"},
    {"name": "ws", "description": "Websocket for live game experience"},
]

app = FastAPI(
    title="Tic Tac Toe Backend",
    description="REST and WebSocket API for online Tic Tac Toe game. Supports player authentication, rooms, moves, history, and leaderboard.",
    version="1.0.0",
    openapi_tags=openapi_tags
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}

# ---------------- Authentication ---------------- #

# PUBLIC_INTERFACE
@app.post("/auth/register", response_model=UserPublic, tags=["auth"], summary="Register user")
async def register_user(user: UserCreate):
    """Creates a new player account."""
    try:
        return STORE.create_user(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# PUBLIC_INTERFACE
@app.post("/auth/login", response_model=TokenResponse, tags=["auth"], summary="Login user/get token")
async def login_user(form_data: OAuth2PasswordRequestForm = Depends()):
    """Obtain access token by providing credentials."""
    user = STORE.verify_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


# ---------------- Game API ---------------- #

# PUBLIC_INTERFACE
@app.post("/game/create", response_model=GameRoom, tags=["game"], summary="Create a new game room")
async def create_game(req: GameCreateRequest, user: UserPublic = Depends(get_current_user)):
    """Create a room; player will be the only participant until another joins."""
    if req.nickname != user.username:
        raise HTTPException(status_code=403, detail="You can only create a game as yourself.")
    game = STORE.create_game(user)
    return game

# PUBLIC_INTERFACE
@app.post("/game/join", response_model=GameRoom, tags=["game"], summary="Join an existing game room")
async def join_game(req: JoinGameRequest, user: UserPublic = Depends(get_current_user)):
    """Join a room as second player."""
    if req.nickname != user.username:
        raise HTTPException(status_code=403, detail="You can only join a game as yourself.")
    try:
        game = STORE.join_game(req.room_id, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    STORE.save_game(game)
    return game

# PUBLIC_INTERFACE
@app.get("/game/list", response_model=List[GameRoom], tags=["game"], summary="List all game rooms")
async def list_games():
    """List all rooms."""
    return STORE.list_games()

# PUBLIC_INTERFACE
@app.get("/game/{room_id}", response_model=GameRoom, tags=["game"], summary="Get room state")
async def get_game(room_id: str):
    """Room/game full state."""
    game = STORE.get_game(room_id)
    if not game:
        raise HTTPException(status_code=404, detail="Room not found.")
    return game

# PUBLIC_INTERFACE
@app.post("/game/move", response_model=GameState, tags=["game"], summary="Make a move in a game")
async def make_a_move(req: MoveRequest, user: UserPublic = Depends(get_current_user)):
    """Make a move in a joined game. Checks legality, applies, and returns updated state."""
    game = STORE.get_game(req.room_id)
    if not game:
        raise HTTPException(status_code=404, detail="No such room")
    if user.username not in [p.username for p in game.players]:
        raise HTTPException(status_code=403, detail="You are not a player in this room")
    try:
        state = make_move(game, user.username, req.row, req.col)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    STORE.save_game(game)
    # Update the leaderboard/scoreboard
    if state.finished:
        draw = state.winner is None
        STORE.update_scoreboard(state.winner, game.players, draw=draw)
    return state

# PUBLIC_INTERFACE
@app.get("/game/state/{room_id}", response_model=GameState, tags=["game"], summary="Get game board/state only")
async def get_game_state(room_id: str):
    """Returns only the board (for lightweight polling or refresh)."""
    game = STORE.get_game(room_id)
    if not game:
        raise HTTPException(status_code=404, detail="Room not found.")
    winner, finished = None, False
    if game.finished:
        winner = game.winner
        finished = True
    return GameState(
        board=[list(r) for r in game.board],
        next_turn=game.next_turn if not finished else None,
        winner=winner,
        finished=finished
    )

# ----------------- Past Games/History ------------------ #

# PUBLIC_INTERFACE
@app.get("/game/history", response_model=List[GameSummary], tags=["game"], summary="List finished games for ALL users")
async def get_game_history():
    """History of all completed games ever."""
    games = STORE.list_games()
    return [
        GameSummary(
            room_id=g.room_id,
            players=[p.username for p in g.players],
            winner=g.winner,
            finished=g.finished
        )
        for g in games if g.finished
    ]

# ----------------- Scoreboard/Leaderboard ---------------- #

# PUBLIC_INTERFACE
@app.get("/scoreboard", response_model=List[LeaderboardEntry], tags=["scoreboard"], summary="Sorted leaderboard")
async def get_scoreboard():
    """Leaderboard table sorted by wins/records."""
    return STORE.get_leaderboard()

# --------------- WebSocket Real-time Game Updates --------------- #

class ConnectionManager:
    """Manages active websocket connections in rooms."""
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, room_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(room_id, []).append(websocket)

    def disconnect(self, room_id: str, websocket: WebSocket):
        if room_id in self.active_connections:
            self.active_connections[room_id] = [
                ws for ws in self.active_connections[room_id]
                if ws != websocket
            ]

    async def broadcast(self, room_id: str, message: dict):
        """Send JSON to all clients of this room."""
        if room_id in self.active_connections:
            disconnected = []
            for ws in self.active_connections[room_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                await self.disconnect(room_id, ws)

manager = ConnectionManager()

# PUBLIC_INTERFACE
@app.websocket("/ws/game/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """
    Real-time updates for a given game room.

    Connect, receive moves or requests, push out new game state to all clients in room after each move.
    See /docs or /openapi.json for websocket schema/usage.
    """
    await manager.connect(room_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # This expects: {"action":"move", "row":int, "col":int, "player":username}
            if isinstance(data, dict) and data.get("action") == "move":
                username = data.get("player")
                row = data.get("row")
                col = data.get("col")
                game = STORE.get_game(room_id)
                if not game or username not in [p.username for p in game.players] or game.finished:
                    await websocket.send_json({"error": "Invalid move or game"})
                    continue
                try:
                    state = make_move(game, username, row, col)
                    STORE.save_game(game)
                    # Update the leaderboard if finished
                    if state.finished:
                        draw = state.winner is None
                        STORE.update_scoreboard(state.winner, game.players, draw=draw)
                    # Broadcast new state
                    await manager.broadcast(room_id, {
                        "type": "game_state",
                        "state": state.model_dump()
                    })
                except ValueError as err:
                    await websocket.send_json({"error": str(err)})
            else:
                await websocket.send_json({"error": "Invalid command"})
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)

# PUBLIC_INTERFACE
@app.get("/ws/docs", tags=["ws"], summary="Websocket API usage help")
def websocket_usage():
    """
    API docs for websocket:
    - Endpoint: /ws/game/{room_id}
    - Protocol: JSON messages from client must have:
        - { "action": "move", "row": 0, "col": 1, "player": "<username>" }
    - Responses are { "type": "game_state", "state": {...GameState...}}
    - Errors { "error": "<string>" }
    """
    return {
        "endpoint": "/ws/game/{room_id}",
        "message": {
            "action": "move",
            "row": 0,
            "col": 1,
            "player": "<username>",
        },
        "response": {
            "type": "game_state",
            "state": "GameState schema"
        }
    }

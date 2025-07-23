"""
Game logic functions for Tic Tac Toe (board validation, move making, win/draw detection).
"""

from typing import Tuple, Optional
from .models import GameRoom, GameState


# PUBLIC_INTERFACE
def make_move(game: GameRoom, username: str, row: int, col: int) -> GameState:
    """
    Attempt to make a move for a player (username) at (row, col).
    Returns updated GameState, or raises ValueError if invalid.
    """
    if game.finished:
        raise ValueError("Game already finished.")
    if username != game.next_turn:
        raise ValueError("Not your turn.")
    if not (0 <= row < 3 and 0 <= col < 3):
        raise ValueError("Invalid board position.")
    if game.board[row][col] != "":
        raise ValueError("Cell already occupied.")

    symbol = "X" if username == game.players[0].username else "O"
    game.board[row][col] = symbol
    game.moves.append({"player": username, "row": row, "col": col})

    winner, is_finished = check_winner(game.board)
    if is_finished:
        game.finished = True
        game.winner = winner
        next_turn = None
    else:
        # Alternate next turn
        usernames = [p.username for p in game.players]
        next_turn = [u for u in usernames if u != username]
        game.next_turn = next_turn[0] if next_turn else username  # If only one player, stay
        game.winner = None

    if is_finished:
        game.finished = True
        game.winner = winner

    return GameState(
        board=[list(row) for row in game.board],
        next_turn=game.next_turn if not is_finished else None,
        winner=winner,
        finished=is_finished
    )


# PUBLIC_INTERFACE
def check_winner(board: list) -> Tuple[Optional[str], bool]:
    """
    Examines board. Returns (winner_symbol, finished) tuples.
    """
    lines = []
    # rows and columns
    for i in range(3):
        lines.append(board[i])
        lines.append([board[0][i], board[1][i], board[2][i]])
    # diagonals
    lines.append([board[0][0], board[1][1], board[2][2]])
    lines.append([board[0][2], board[1][1], board[2][0]])

    for l in lines:
        if l[0] and l.count(l[0]) == 3:
            return l[0], True

    # Draw: full board/no winner
    if all(cell for row in board for cell in row):
        return None, True  # Draw!

    return None, False

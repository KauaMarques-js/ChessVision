"""Chess.com DOM snapshots -> consistent python-chess state.

Prefer a SAN history only if it exactly reproduces the rendered board.
Otherwise synchronize with one- or two-ply legal move searches, then fall back
with an explicit warning that historical state was reconstructed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import chess

PLACEMENT_RE = re.compile(r'^[1-8prnbqkPRNBQK/]+$')


@dataclass
class Snapshot:
    board: chess.Board
    mode: str
    warning: str
    changed: bool


def parse_placement(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) > 100 or not PLACEMENT_RE.fullmatch(raw):
        raise ValueError('Tabuleiro malformado')
    ranks = raw.split('/')
    if len(ranks) != 8:
        raise ValueError('O tabuleiro precisa de oito linhas')
    for rank in ranks:
        total = sum(int(c) if c.isdigit() else 1 for c in rank)
        if total != 8:
            raise ValueError('Linha com numero de casas diferente de oito')
    # Also rejects overlapping kings and illegal basic piece placement.
    temp = chess.Board(f'{raw} w - - 0 1')
    if temp.king(chess.WHITE) is None or temp.king(chess.BLACK) is None:
        raise ValueError('Reis ausentes')
    return raw


def estimated_castling(placement: str) -> str:
    b = chess.Board(f'{placement} w - - 0 1')
    rights = ''
    for name, king, rook, k, r in (
        ('K', chess.E1, chess.H1, 'K', 'R'),
        ('Q', chess.E1, chess.A1, 'K', 'R'),
        ('k', chess.E8, chess.H8, 'k', 'r'),
        ('q', chess.E8, chess.A8, 'k', 'r'),
    ):
        if b.piece_at(king) and b.piece_at(rook):
            if b.piece_at(king).symbol() == k and b.piece_at(rook).symbol() == r:
                rights += name
    return rights or '-'


class BoardTracker:
    def __init__(self):
        self.board: Optional[chess.Board] = None
        self.mode = 'aguardando'
        self.warning = ''

    def _build_history(self, moves: list[str], placement: str) -> Optional[chess.Board]:
        if not moves or len(moves) > 400:
            return None
        b = chess.Board()
        try:
            for san in moves:
                if not isinstance(san, str) or len(san) > 22:
                    return None
                san = san.strip().replace('0-0', 'O-O')
                b.push_san(san)
            return b if b.board_fen() == placement else None
        except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            return None

    def _walk(self, state: chess.Board, placement: str, count: int):
        if count == 0:
            return state if state.board_fen() == placement else None
        for move in state.legal_moves:
            state.push(move)
            result = self._walk(state, placement, count - 1)
            if result:
                out = result.copy(stack=True)
                state.pop()
                return out
            state.pop()
        return None

    def _reconstruct(self, placement: str, turn: Optional[str]) -> chess.Board:
        candidates = ([turn] if turn in ('w', 'b') else ['w', 'b'])
        for color in candidates + [c for c in ('w', 'b') if c not in candidates]:
            fen = f'{placement} {color} {estimated_castling(placement)} - 0 1'
            board = chess.Board(fen)
            if board.is_valid():
                return board
        raise ValueError('Posicao temporaria/impossivel; aguarde o fim da animacao')

    def update(self, placement: str, moves: Optional[list[str]] = None,
               turn: Optional[str] = None) -> Snapshot:
        placement = parse_placement(placement)
        if self.board and self.board.board_fen() == placement:
            # An authoritative reconstructed SAN line may still provide a
            # complete state for an otherwise estimated position.
            history = self._build_history(moves or [], placement)
            if history and (self.mode != 'historico' or
                            history.fen() != self.board.fen() or
                            len(history.move_stack) != len(self.board.move_stack)):
                # Critical: reversible sequences may return to the same pieces
                # with the OTHER side to move, so placement-only caching is unsafe.
                self.board = history
                self.mode = 'historico'
                self.warning = ''
                return Snapshot(history.copy(), self.mode, self.warning, True)
            return Snapshot(self.board.copy(), self.mode, self.warning, False)

        history = self._build_history(moves or [], placement)
        if history:
            self.board = history
            self.mode = 'historico'
            self.warning = ''
            return Snapshot(history.copy(), self.mode, self.warning, True)

        if placement == chess.STARTING_BOARD_FEN:
            self.board = chess.Board()
            self.mode = 'inicio'
            self.warning = ''
            return Snapshot(self.board.copy(), self.mode, '', True)

        if self.board:
            for plies in (1, 2):
                follow = self._walk(self.board.copy(stack=True), placement, plies)
                if follow:
                    self.board = follow
                    self.mode = 'movimentos legais'
                    self.warning = ''
                    return Snapshot(follow.copy(), self.mode, '', True)

        board = self._reconstruct(placement, turn)
        self.board = board
        self.mode = 'estimado'
        self.warning = ('Partida iniciada no meio ou lances perdidos: turno/roque '
                        'podem estar incorretos. Reinicie desde a posicao inicial.')
        return Snapshot(board.copy(), self.mode, self.warning, True)

    def force_turn(self, color: str):
        if not self.board or color not in ('w', 'b'):
            return None
        new = self.board.copy(stack=False)
        new.turn = chess.WHITE if color == 'w' else chess.BLACK
        new.clear_stack()
        if not new.is_valid():
            raise ValueError('Turno escolhido gera posicao invalida')
        self.board = new
        self.mode = 'turno manual'
        self.warning = 'Turno ajustado manualmente; direitos historicos podem ser estimados.'
        return new.copy()

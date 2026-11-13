"""Persistent local piece banks, including the supplied cburnett classifier."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import chess
from screen_reader import ScreenBoardReader


class ReaderProfiles:
    def __init__(self, directory, bundled=None):
        self.directory = Path(directory)
        base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
        self.bundled = Path(bundled) if bundled else base/'profiles'

    def save(self, reader):
        self.directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(reader.profile_name.encode('utf-8')).hexdigest()[:24]
        path = self.directory / (key + '.json')
        reader.save(path, allow_incomplete=True)
        return path

    def list(self):
        profiles = {}
        for directory in (self.bundled, self.directory):
            if not directory.exists():
                continue
            for path in sorted(directory.glob('*.json')):
                try:
                    reader = ScreenBoardReader.load(path, allow_incomplete=True)
                except (OSError, ValueError, TypeError, KeyError):
                    continue
                profiles[reader.profile_name] = (path, reader)
        return profiles

    def ready(self):
        return [reader for _, reader in self.list().values() if not reader.missing_symbols]

    def save_game(self, reader, board):
        self.directory.mkdir(parents=True, exist_ok=True)
        key=hashlib.sha256(reader.profile_name.encode('utf-8')).hexdigest()[:24]
        path=self.directory/(key+'.game')
        data={'profile':reader.profile_name,'initial':board.root().fen(),
              'moves':[move.uci() for move in board.move_stack], 'fen':board.fen()}
        temporary=path.with_suffix('.game.tmp')
        temporary.write_text(json.dumps(data),encoding='utf-8')
        temporary.replace(path)

    def load_game(self, reader):
        key=hashlib.sha256(reader.profile_name.encode('utf-8')).hexdigest()[:24]
        path=self.directory/(key+'.game')
        if path.stat().st_size>100000:raise ValueError('Histórico salvo inválido')
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('profile')!=reader.profile_name:raise ValueError('Perfil do histórico incompatível')
        moves=data.get('moves')
        if not isinstance(moves,list) or len(moves)>1000:raise ValueError('Histórico salvo inválido')
        board=chess.Board(data['initial'])
        if not board.is_valid():raise ValueError('Posição inicial inválida')
        for move in moves:board.push_uci(move)
        if board.fen()!=data.get('fen'):raise ValueError('Histórico salvo inconsistente')
        return board

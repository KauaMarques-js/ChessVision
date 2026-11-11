"""Verificação executável do ChessVision Lab (sem precisar do navegador)."""
from __future__ import annotations

import json
import sys
import traceback
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def main():
    result = []
    def record(ok, title, message=''):
        status = 'OK' if ok else 'FALHA'
        result.append((ok, title, message))
        print(f'[{status}] {title}' + (f': {message}' if message else ''))

    # Tkinter can import successfully even without the Tcl/Tk data files.
    # Reproduce the exact operation that failed on Windows: Tk().
    try:
        import tkinter as tk
        win = tk.Tk()
        win.withdraw()
        win.update_idletasks()
        win.destroy()
        record(True, 'Interface Tkinter/Tcl', 'Janela criada e encerrada')
    except Exception as exc:
        record(False, 'Interface Tkinter/Tcl (init.tcl)', str(exc))

    try:
        import chess
        import chess.engine
        from PIL import ImageGrab, ImageTk
        from screen_reader import ScreenBoardReader
        from tracker import BoardTracker
        from app import AnalysisState, LocalHandler, find_stockfish
        record(True, 'Biblioteca de xadrez', getattr(chess, '__version__', 'instalada'))
    except Exception as exc:
        record(False, 'Dependencias Python', str(exc))
        return save(result)

    try:
        tracker = BoardTracker()
        tracker.update(chess.STARTING_BOARD_FEN)
        expected = chess.Board()
        for move in ('e4', 'e5', 'Nf3', 'Nc6'):
            expected.push_san(move)
            last = tracker.update(expected.board_fen())
            assert last.board.fen() == expected.fen()
        assert last.board.turn == chess.WHITE
        record(True, 'Reconstrucao legal dos movimentos', expected.fen())
    except Exception as exc:
        record(False, 'Reconstrucao dos movimentos', str(exc))

    try:
        state = AnalysisState()
        LocalHandler.state = state
        server = ThreadingHTTPServer(('127.0.0.1', 0), LocalHandler)
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            data = json.dumps({'placement': chess.STARTING_BOARD_FEN,
                               'moves':[], 'source':'/play/computer', 'orientation':'white'}).encode()
            req = urllib.request.Request(url+'/position', data=data,
                                         headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=4) as response:
                received = json.load(response)
            with urllib.request.urlopen(url+'/health', timeout=4) as response:
                health = json.load(response)
            assert received['ok'] and health['board_ready'] and state.board.fen() == chess.STARTING_FEN
            record(True, 'Extensao simulada -> servidor localhost -> tabuleiro', f'porta teste {server.server_port}')
        finally:
            server.shutdown()
            server.server_close()
    except Exception as exc:
        record(False, 'Ponte HTTP local', str(exc))

    path = find_stockfish()
    if not path:
        record(False, 'Stockfish 19', 'Executavel nao encontrado na pasta engine ou no PATH')
    else:
        engine = None
        try:
            engine = chess.engine.SimpleEngine.popen_uci(path, timeout=15)
            name = engine.id.get('name', '')
            assert 'Stockfish 19' in name, f'Motor encontrado nao e Stockfish 19: {name}'
            # A real UCI search, not just checking that the file exists.
            board = chess.Board()
            infos = engine.analyse(board, chess.engine.Limit(depth=7), multipv=5,
                                   info=chess.engine.INFO_ALL)
            assert len(infos) == 5, f'Esperadas 5 variantes, recebidas {len(infos)}'
            for info in infos:
                assert info.get('pv') and info['pv'][0] in board.legal_moves
                assert info.get('depth', 0) >= 7
            record(True, 'Stockfish UCI + busca real de 5 variantes',
                   f'{name}, depth {infos[0]["depth"]}, {Path(path).name}')
        except Exception as exc:
            record(False, 'Stockfish UCI + busca real', str(exc))
        finally:
            if engine:
                try: engine.quit()
                except Exception: pass
    return save(result)


def save(result):
    good = sum(ok for ok, _, _ in result)
    summary = f'RESULTADO: {good}/{len(result)} testes aprovados'
    print('\n'+summary)
    path = Path(__file__).with_name('diagnostico_resultado.txt')
    try:
        path.write_text('\n'.join(f'{"OK" if ok else "FALHA"}: {name} - {message}'
                                  for ok, name, message in result)+'\n'+summary+'\n', encoding='utf-8')
    except OSError:
        pass
    return 0 if good == len(result) else 1


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)

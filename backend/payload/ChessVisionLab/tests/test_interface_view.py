"""Regressão do modo compacto e da seta, sem iniciar servidor ou motor."""

import tempfile
import time
import unittest
from pathlib import Path
from tkinter import Tk, TclError
from unittest.mock import patch

import chess
import app


class InterfaceViewTests(unittest.TestCase):
    def test_board_only_and_selected_variation(self):
        try:
            root = Tk()
        except TclError as exc:
            self.skipTest(f'Janela Tk indisponível: {exc}')
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as temp, patch.object(app, 'CONFIG', Path(temp) / 'config.json'):
                state = app.AnalysisState()
                ui = app.ChessVisionUI(root, state)
                lines = [
                    {'rank': rank, 'uci': move, 'first': san, 'score': '+0.20',
                     'depth': 12, 'seldepth': 16, 'san': f'1. {san}'}
                    for rank, move, san in [(1, 'e2e4', 'e4'),
                                            (2, 'd2d4', 'd4'),
                                            (3, 'g1f3', 'Nf3')]
                ]

                ui.set_board_only(True)
                self.assertTrue(ui.board_only)
                self.assertEqual(ui.full_view.winfo_manager(), '')
                self.assertEqual(ui.compact_view.winfo_manager(), 'pack')

                ui.lines = lines
                ui.display_key.set('third')
                ui.change_display_mode()
                self.assertEqual(ui.best_uci, 'g1f3')
                self.assertIn('3º MELHOR LANCE', ui.moves_text.get('1.0', 'end'))
                self.assertNotIn('1º MELHOR LANCE', ui.moves_text.get('1.0', 'end'))
                self.assertEqual(state.config['display_mode'], 'third')

                ui.lines = lines[:2]
                ui.refresh_variation()
                self.assertIsNone(ui.best_uci)

                ui.lines = lines
                ui.display_key.set('alternate')
                ui.change_display_mode()
                self.assertEqual(ui.best_uci, 'e2e4')
                ui.cycle_at = time.monotonic() - app.CYCLE_SECONDS - 1
                ui.poll()
                self.assertEqual(ui.best_uci, 'd2d4')

                state.ui_events.put(('board', chess.Board(), 'inicio', ''))
                ui.poll()
                self.assertIsNone(ui.best_uci)
                self.assertEqual(ui.lines, [])

                ui.set_board_only(False)
                self.assertFalse(ui.board_only)
                self.assertEqual(ui.full_view.winfo_manager(), 'pack')
                self.assertFalse(state.config['board_only'])
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()

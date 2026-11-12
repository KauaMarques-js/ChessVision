"""Regressão do modo compacto e da seta, sem iniciar servidor ou motor."""

import tempfile
import time
import unittest
from pathlib import Path
from tkinter import Tk, TclError
from unittest.mock import patch
from PIL import Image

import chess
import app
from test_screen_reader import render


class InterfaceViewTests(unittest.TestCase):
    def test_teaching_clicks_undo_and_validation_before_using_profile(self):
        from screen_reader import PIECE_LABELS,square_at
        root=Tk()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.object(app,'CONFIG',Path(temp)/'config.json'):
                ui=app.ChessVisionUI(root,app.AnalysisState())
                board=chess.Board()
                for move in ('e4','d5','Nc3','Nf6'):board.push_san(move)
                accepted=[]
                trainer=ui.teach_piece_profile(render(board),'white',accepted.append)
                root.update()
                def find(widget,text):
                    for child in widget.winfo_children():
                        if child.winfo_class()=='TButton' and child.cget('text')==text:return child
                        result=find(child,text)
                        if result:return result
                find(trainer,'Usar perfil').invoke()
                self.assertEqual(accepted,[])
                for symbol in PIECE_LABELS:
                    ui.teaching_choice.set(PIECE_LABELS[symbol])
                    cells=[(row,col) for row in range(8) for col in range(8)
                           if (board.piece_at(square_at(row,col,'white')).symbol()
                               if board.piece_at(square_at(row,col,'white')) else '.')==symbol]
                    row,col=cells[0]
                    ui.teaching_canvas.event_generate('<Button-1>',x=col*35+17,y=row*35+17)
                    root.update()
                self.assertEqual(ui.teaching_reader.missing_symbols,[])
                find(trainer,'Desfazer').invoke()
                self.assertEqual(ui.teaching_reader.missing_symbols,['k'])
                # Use another king click after the intentional double-click guard.
                time.sleep(.36)
                ui.teaching_canvas.event_generate('<Button-1>',x=4*35+17,y=17)
                root.update()
                find(trainer,'Usar perfil').invoke()
                self.assertEqual(len(accepted),1)
                self.assertEqual(accepted[0].read(render(board)),board.board_fen())
                self.assertIsNone(ui.state.board)
                self.assertFalse((Path(temp)/'.reader_templates.json').exists())
        finally:root.destroy()

    def test_reopening_loads_saved_theme_and_starts_cancellable_background_search(self):
        from screen_reader import ScreenBoardReader
        root=Tk()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.object(app,'CONFIG',Path(temp)/'config.json'):
                ScreenBoardReader(render(chess.Board())).save(Path(temp)/'.reader_templates.json')
                with patch.object(app.threading,'Thread') as thread:
                    ui=app.ChessVisionUI(root,app.AnalysisState())
                    self.assertIsNotNone(ui.screen_reader)
                    self.assertIsNone(ui.state.board)
                    deadline=time.monotonic()+2
                    while not ui.search_active and time.monotonic()<deadline:
                        root.update()
                        time.sleep(.02)
                    self.assertTrue(ui.search_active)
                    self.assertEqual(root.state(),'normal')
                    self.assertEqual(thread.call_args.kwargs['target'],ui.search_game)
                    old_generation=ui.capture_generation
                    ui.stop_screen()
                    self.assertTrue(ui.search_stop.is_set())
                    with patch.object(ui,'review_screen_board') as review:
                        ui.state.ui_events.put(('search_ready',old_generation,render(chess.Board()),[(0,0,480,480)]))
                        ui.poll()
                        review.assert_not_called()
        finally:root.destroy()

    def test_midgame_review_waits_for_confirmation_then_restores_assistance(self):
        from screen_reader import ScreenBoardReader
        root=Tk()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.object(app,'CONFIG',Path(temp)/'config.json'):
                ui=app.ChessVisionUI(root,app.AnalysisState())
                ui.screen_reader=ScreenBoardReader(render(chess.Board()))
                board=chess.Board()
                for move in ('e4','e5','Nf3'):board.push_san(move)
                photo=Image.new('RGB',(700,600),'#202433')
                photo.paste(render(board),(17,23))
                with patch('PIL.ImageGrab.grab',return_value=photo):
                    ui.begin_background_search()
                    deadline=time.monotonic()+10
                    while ui.search_active and time.monotonic()<deadline:
                        root.update()
                        time.sleep(.02)
                self.assertFalse(ui.search_active)
                dialog=ui.screen_dialog
                self.assertIsNotNone(dialog)
                self.assertIsNone(ui.state.board)
                self.assertIsNone(ui.best_uci)
                self.assertEqual(ui.confirm_turn_var.get(),'Confirme a vez')
                def find(widget):
                    for child in widget.winfo_children():
                        if child.winfo_class()=='TButton' and child.cget('text')=='Confirmar e continuar':return child
                        result=find(child)
                        if result:return result
                button=find(dialog)
                button.invoke()
                self.assertTrue(dialog.winfo_exists())
                self.assertIsNone(ui.state.board)
                ui.confirm_turn_var.set('Pretas jogam')
                for var in ui.confirm_castling_vars.values():var.set(True)
                with patch.object(app.threading,'Thread'),patch.object(ui,'dock_capture_window'):
                    button.invoke()
                self.assertEqual(ui.state.board.board_fen(),board.board_fen())
                self.assertEqual(ui.state.board.turn,chess.BLACK)
                self.assertEqual(ui.state.mode,'tela confirmada')
                self.assertFalse(ui.state.screen_paused)
                cached=ScreenBoardReader.load(Path(temp)/'.reader_templates.json')
                self.assertEqual(cached.read(render(board)),board.board_fen())
                ui.poll()
                self.assertEqual(ui.board.board_fen(),board.board_fen())
        finally:root.destroy()

    def test_retry_recaptures_uncovered_screen_and_compact_layout_keeps_board_size(self):
        root=Tk()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.object(app,'CONFIG',Path(temp)/'config.json'):
                ui=app.ChessVisionUI(root,app.AnalysisState())
                root.update()
                self.assertLessEqual(root.winfo_width(),900)
                self.assertLessEqual(root.winfo_height(),560)
                self.assertEqual(ui.canvas.winfo_width(),440)
                bad=Image.new('RGB',(700,600),'#888888')
                good=bad.copy()
                good.paste(render(chess.Board()),(17,23))
                def find(widget,text):
                    for child in widget.winfo_children():
                        if child.winfo_class()=='TButton' and child.cget('text')==text:return child
                        found=find(child,text)
                        if found:return found
                with patch.object(ui,'start_screen_capture') as start:
                    dialog=ui.review_screen_board(bad,[(17,23,497,503)])
                    root.update()
                    self.assertLessEqual(ui.screen_preview.winfo_width(),280)
                    find(dialog,'Confirmar e continuar').invoke()
                    start.assert_not_called()
                    def grab():
                        self.assertEqual(root.state(),'withdrawn')
                        self.assertEqual(dialog.state(),'withdrawn')
                        return good
                    with patch('PIL.ImageGrab.grab',side_effect=grab) as capture:
                        find(dialog,'Tentar novamente').invoke()
                        deadline=time.monotonic()+2
                        while not capture.called and time.monotonic()<deadline:
                            root.update()
                            time.sleep(.02)
                        capture.assert_called_once()
                    find(dialog,'Confirmar e continuar').invoke()
                    self.assertEqual(start.call_args.args[1],(17,23,497,503))
                ui.set_board_only(True)
                root.update()
                self.assertEqual(root.winfo_width(),440)
                self.assertEqual(ui.compact_canvas.winfo_width(),440)
                self.assertLessEqual(root.winfo_height(),520)
                reader=object()
                ui.screen_reader=reader
                ui.capture_mode.set('Manual')
                ui.screen_bbox=(17,23,497,503)
                ui.state.set_fen(chess.STARTING_FEN)
                tracker=ui.state.tracker
                with patch.object(ui,'dock_capture_window'),patch.object(app.threading,'Thread') as thread:
                    ui.retry_screen()
                    self.assertIs(thread.call_args.kwargs['args'][0],reader)
                    self.assertIs(ui.state.tracker,tracker)
        finally:root.destroy()

    def test_region_review_validates_pixel_bounds_before_starting(self):
        try:
            root = Tk()
        except TclError as exc:
            self.skipTest(f'Janela Tk indisponível: {exc}')
        try:
            with tempfile.TemporaryDirectory() as temp, patch.object(app, 'CONFIG', Path(temp) / 'config.json'):
                ui = app.ChessVisionUI(root, app.AnalysisState())
                screenshot = Image.new('RGB', (700,600), '#202433')
                screenshot.paste(render(chess.Board()), (17,23))

                def find_button(widget, text):
                    for child in widget.winfo_children():
                        if child.winfo_class()=='TButton' and child.cget('text')==text:
                            return child
                        found = find_button(child,text)
                        if found:return found
                    return None

                with patch.object(ui, 'start_screen_capture') as start:
                    dialog = ui.review_screen_board(screenshot, [(17,23,497,503),(18,24,498,504)])
                    root.update()
                    find_button(dialog,'Outra região').invoke()
                    self.assertEqual([v.get() for v in ui.screen_review_vars], [17,23,480,480])
                    find_button(dialog,'Outra região').invoke()
                    ui.screen_review_vars[2].set(159)
                    find_button(dialog,'Confirmar e continuar').invoke()
                    start.assert_not_called()
                    ui.screen_review_vars[2].set(480)
                    ui.screen_review_vars[0].set(300)
                    find_button(dialog,'Confirmar e continuar').invoke()
                    start.assert_not_called()
                    ui.screen_review_vars[0].set(17)
                    find_button(dialog,'Confirmar e continuar').invoke()
                    self.assertEqual(start.call_args.args[1], (17,23,497,503))

                with patch.object(ui, 'review_screen_board') as review:
                    ui.locate_screen_boards(screenshot, ui.capture_generation)
                    ui.poll()
                    self.assertEqual(review.call_args.args[1], [(17,23,497,503)])
                    review.reset_mock()
                    ui.state.ui_events.put(('detected_boards',ui.capture_generation-1,
                                            screenshot,[(17,23,497,503)],''))
                    ui.poll()
                    review.assert_not_called()
                ui.locate_screen_boards(screenshot, ui.capture_generation, (17,23,497,503))
                event=ui.state.ui_events.get_nowait()
                self.assertEqual(event[0],'detected_boards')
                self.assertEqual(event[3], [])
        finally:
            root.destroy()

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
                                            (3, 'g1f3', 'Nf3'),
                                            (4, 'c2c4', 'c4'),
                                            (5, 'g2g3', 'g3')]
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

                ui.display_key.set('fifth')
                ui.change_display_mode()
                revision = state.revision
                ui.cycle_at = time.monotonic() - 100
                ui.poll()
                self.assertEqual(ui.best_uci, 'g2g3')
                self.assertEqual(state.revision, revision)
                self.assertIn('5ª melhor', ui.compact_description.get())
                ui.display_key.set('third')
                ui.change_display_mode()

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

                ui.set_board_only(False)
                ui.set_board_only(True)
                self.assertEqual(ui.display_key.get(), 'first')

                state.ui_events.put(('board', chess.Board(), 'inicio', ''))
                ui.poll()
                self.assertIsNone(ui.best_uci)
                self.assertEqual(ui.lines, [])

                ui.set_board_only(False)
                self.assertFalse(ui.board_only)
                self.assertEqual(ui.full_view.winfo_manager(), 'pack')
                self.assertFalse(state.config['board_only'])

                ui.profile_label.set('Humanizado (treino)')
                ui.human_skill.set(20)
                previous_revision=state.revision
                with patch.object(app.messagebox,'showerror') as error:
                    ui.apply_profile()
                    error.assert_called_once()
                self.assertEqual(state.revision,previous_revision)
                self.assertFalse(state.config['human_enabled'])
                ui.profile_label.set('Humanizado (treino)')
                ui.human_skill.set(7)
                ui.apply_profile()
                self.assertTrue(state.config['human_enabled'])
                self.assertEqual(ui.display_key.get(),'human')
                self.assertIsNone(ui.best_uci)
                ui.lines=lines
                ui.human_line={**lines[2],'skill':7}
                ui.refresh_variation()
                self.assertEqual(ui.best_uci,'g1f3')
                self.assertIn('Sugestão do perfil: Nf3',ui.moves_text.get('1.0','end'))
                self.assertIn('1º MELHOR LANCE: e4',ui.moves_text.get('1.0','end'))
                ui.set_board_only(True)
                self.assertEqual(ui.display_key.get(),'human')
                state.ui_events.put(('human_line',state.revision-1,chess.STARTING_FEN,
                                     {**lines[0],'skill':7}))
                ui.poll()
                self.assertEqual(ui.best_uci,'g1f3')
                state.ui_events.put(('board',chess.Board(),'inicio',''))
                ui.poll()
                self.assertIsNone(ui.human_line)
                self.assertIsNone(ui.best_uci)
                ui.profile_label.set('Análise máxima')
                ui.apply_profile()
                self.assertFalse(state.config['human_enabled'])
                self.assertEqual(ui.display_key.get(),'first')
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import chess
from PIL import Image, ImageDraw, ImageFont, ImageChops

import app
from screen_reader import ScreenBoardReader, square_at, detect_boards, outside_position, refine_board_region


def render(board, orientation='white', highlight=None, highlights=None):
    image = Image.new('RGB', (480, 480))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    for row in range(8):
        for col in range(8):
            square = square_at(row, col, orientation)
            bg = (150, 180, 140) if (row+col) % 2 else (220, 210, 180)
            if square == highlight:
                bg = (190, 200, 120)
            if highlights and square in highlights:
                bg = highlights[square]
            draw.rectangle((col*60, row*60, (col+1)*60-1, (row+1)*60-1), fill=bg)
            piece = board.piece_at(square)
            if piece:
                draw.text((col*60+13, row*60+6), piece.symbol().upper(), font=font,
                          fill=(255, 255, 255) if piece.color else (10, 10, 10))
    return image


class ScreenReaderTests(unittest.TestCase):
    def test_red_gradient_and_yellow_highlight_keep_piece_identity(self):
        board=chess.Board();board.push_san('e4')
        reader=ScreenBoardReader(render(chess.Board()))
        image=render(board,highlights={chess.E2:(245,220,60),chess.E4:(245,220,60)})
        # The check effect covers the background, not the piece itself.
        tile=image.crop((240,420,300,480))
        draw=ImageDraw.Draw(tile)
        for radius in range(42,0,-1):
            t=1-radius/42
            color=(int(220+(255-220)*t),int(210*(1-t)),int(180*(1-t)))
            draw.ellipse((30-radius,30-radius,30+radius,30+radius),fill=color)
        draw.text((13,6),'K',font=ImageFont.load_default(size=42),fill='white')
        image.paste(tile,(240,420))
        self.assertEqual(reader.read(image),board.board_fen())

    def test_cached_profile_reads_captured_types_and_only_rechecks_changed_squares(self):
        reader=ScreenBoardReader(render(chess.Board()))
        board=chess.Board('4k3/8/8/8/8/8/4P3/4K3 w - - 0 1')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'profile.json';reader.save(path)
            restored=ScreenBoardReader.load(path)
            self.assertEqual(restored.read(render(board)),board.board_fen())
            with patch.object(restored,'_matches',wraps=restored._matches) as match:
                self.assertEqual(restored.read(render(board)),board.board_fen())
                match.assert_not_called()
                board.push_san('e4')
                self.assertEqual(restored.read(render(board)),board.board_fen())
                self.assertEqual(match.call_count,2)

    def test_partial_piece_bank_can_be_saved_before_any_board_is_recognized(self):
        reader=ScreenBoardReader.new_profile((480,480),name='Meu cadastro')
        reader.add_example(render(chess.Board()),0,0,'r')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'draft.json';reader.save(path,allow_incomplete=True)
            loaded=ScreenBoardReader.load(path,allow_incomplete=True)
            self.assertEqual(len(loaded.templates['r']),1)
            self.assertEqual(len(loaded.missing_symbols),12)
            with self.assertRaises(ValueError):loaded.read(render(chess.Board()))
            with self.assertRaises(ValueError):ScreenBoardReader.load(path)

    def test_black_rooks_keep_identity_with_small_raster_offsets(self):
        board=chess.Board();board.push_san('e4')
        image=render(board,'black')
        reader=ScreenBoardReader.new_profile(image.size,'black')
        for row in range(8):
            for col in range(8):
                piece=board.piece_at(square_at(row,col,'black'))
                symbol=piece.symbol() if piece else '.'
                if symbol in reader.missing_symbols:reader.add_example(image,row,col,symbol)
        for dx,dy in ((2,0),(-2,0),(0,2),(0,-2)):
            shifted=image.copy()
            for col in (0,7):
                tile=image.crop((col*60,420,(col+1)*60,480))
                shifted.paste(ImageChops.offset(tile,dx,dy),(col*60,420))
            with self.subTest(offset=(dx,dy)):
                self.assertEqual(reader.read(shifted),board.board_fen())

    def test_manual_examples_learn_midgame_without_initial_position(self):
        board=chess.Board()
        for move in ('e4','d5','Nc3','Nf6'):board.push_san(move)
        for orientation in ('white','black'):
            image=render(board,orientation)
            reader=ScreenBoardReader.new_profile(image.size,orientation,'Meu estilo')
            with self.assertRaisesRegex(ValueError,'incompleto'):reader.read(image)
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'profile.json'
                with self.assertRaises(ValueError):reader.save(path)
                for row in range(8):
                    for col in range(8):
                        piece=board.piece_at(square_at(row,col,orientation))
                        symbol=piece.symbol() if piece else '.'
                        if symbol in reader.missing_symbols:reader.add_example(image,row,col,symbol)
                self.assertEqual(reader.missing_symbols,[])
                self.assertEqual(reader.read(image),board.board_fen())
                reader.save(path)
                loaded=ScreenBoardReader.load(path)
                self.assertEqual(loaded.profile_name,'Meu estilo')
                self.assertEqual(loaded.read(image),board.board_fen())

    def test_manual_rectangle_snaps_to_grid_and_preserves_unknown_regions(self):
        image=Image.new('RGB',(900,650),'#202433')
        image.paste(render(chess.Board()),(113,79))
        self.assertEqual(refine_board_region(image,(108,76,596,562)),(113,79,593,559))
        self.assertEqual(refine_board_region(image,(650,20,850,220)),(650,20,850,220))

    def test_unknown_piece_style_still_opens_background_confirmation(self):
        image=Image.new('RGB',(700,600),'#202433')
        image.paste(render(chess.Board()),(17,23))
        ui=app.ChessVisionUI.__new__(app.ChessVisionUI)
        ui.state=app.AnalysisState()
        ui.screen_reader=ScreenBoardReader.new_profile((480,480))
        ui.search_exclusions=[]
        class Stop:
            count=0
            stopped=False
            def is_set(self):return self.stopped or self.count>=4
            def set(self):self.stopped=True
            def wait(self,_):self.count+=1
        with patch('PIL.ImageGrab.grab',return_value=image):ui.search_game(12,Stop())
        events=[]
        while not ui.state.ui_events.empty():events.append(ui.state.ui_events.get_nowait())
        ready=[event for event in events if event[0]=='search_ready']
        self.assertEqual(len(ready),1)
        self.assertEqual(ready[0][3],[(17,23,497,503)])
        self.assertIsNone(ui.state.board)

    def test_repeated_lost_frames_request_background_relocation(self):
        ui=app.ChessVisionUI.__new__(app.ChessVisionUI)
        ui.state=app.AnalysisState()
        ui.state.screen_active=True
        ui.capture_generation=9
        reader=ScreenBoardReader(render(chess.Board()))
        class Stop:
            count=0
            def is_set(self):return self.count>=5
            def wait(self,_):self.count+=1
        with patch('PIL.ImageGrab.grab',side_effect=OSError('window moved')):
            ui.read_screen(reader,(0,0,480,480),Stop())
        events=[]
        while not ui.state.ui_events.empty():events.append(ui.state.ui_events.get_nowait())
        self.assertIn(('relocalize',9),events)
        self.assertTrue(ui.state.screen_paused)
        self.assertIsNone(ui.state.board)

    def test_missed_moves_request_confirmation_instead_of_staying_stuck(self):
        ui=app.ChessVisionUI.__new__(app.ChessVisionUI)
        ui.state=app.AnalysisState()
        ui.state.screen_active=True
        ui.state.receive({'source':'Captura de tela','placement':chess.STARTING_BOARD_FEN})
        ui.capture_generation=11
        reader=ScreenBoardReader(render(chess.Board()))
        board=chess.Board()
        for move in ('e4','e5','Nf3'):board.push_san(move)
        class Stop:
            count=0
            def is_set(self):return self.count>=12
            def wait(self,_):self.count+=1
        with patch('PIL.ImageGrab.grab',return_value=render(board)):
            ui.read_screen(reader,(0,0,480,480),Stop())
        events=[]
        while not ui.state.ui_events.empty():events.append(ui.state.ui_events.get_nowait())
        self.assertIn(('relocalize',11),events)
        self.assertEqual(ui.state.tracker.board.board_fen(),chess.STARTING_BOARD_FEN)
        self.assertEqual(ui.state.pending_screen,board.board_fen())

    def test_saved_references_read_midgame_after_restart_and_relocation(self):
        initial=ScreenBoardReader(render(chess.Board()))
        board=chess.Board()
        for move in ('e4','e5','Nf3','Nc6','Bb5','a6'):board.push_san(move)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'reader_templates.json'
            initial.save(path)
            restored=ScreenBoardReader.load(path)
            self.assertEqual(restored.read(render(board)),board.board_fen())
            resized=render(board).resize((384,384),Image.Resampling.LANCZOS)
            self.assertEqual(restored.for_region(resized.size).read(resized),board.board_fen())
            path.write_text('[]',encoding='utf-8')
            with self.assertRaises(ValueError):ScreenBoardReader.load(path)

    def test_background_search_ignores_own_board_and_waits_for_real_game(self):
        own=(10,20,490,500)
        before=Image.new('RGB',(1100,650),'#202433')
        before.paste(render(chess.Board()),own[:2])
        game=chess.Board()
        for move in ('e4','e5','Nf3'):game.push_san(move)
        after=before.copy()
        after.paste(render(game),(580,130))
        ui=app.ChessVisionUI.__new__(app.ChessVisionUI)
        ui.state=app.AnalysisState()
        ui.screen_reader=ScreenBoardReader(render(chess.Board()))
        ui.search_exclusions=[own]
        class Stop:
            stopped=False
            count=0
            def is_set(self):return self.stopped or self.count>6
            def set(self):self.stopped=True
            def wait(self,_):self.count+=1
        with patch('PIL.ImageGrab.grab',side_effect=[OSError('hidden'),before,after,after]):
            ui.search_game(7,Stop())
        events=[]
        while not ui.state.ui_events.empty():events.append(ui.state.ui_events.get_nowait())
        ready=[event for event in events if event[0]=='search_ready']
        self.assertEqual(len(ready),1)
        self.assertEqual(ready[0][1],7)
        self.assertEqual(ready[0][3],[(580,130,1060,610)])
        self.assertIsNone(ui.state.board)

    def test_midgame_confirmation_requires_turn_and_preserves_legal_history(self):
        state=app.AnalysisState()
        board=chess.Board()
        for move in ('e4','e5','Nf3'):board.push_san(move)
        placement=board.board_fen()
        with self.assertRaises(ValueError):state.confirm_screen_position(placement,None,'white')
        self.assertIsNone(state.board)
        state.confirm_screen_position(placement,'b','white','KQkq')
        self.assertEqual(state.board.board_fen(),placement)
        self.assertEqual(state.mode,'tela confirmada')
        self.assertEqual(state.board.castling_xfen(),'KQkq')
        state.set_fen(chess.STARTING_FEN)
        after=chess.Board();after.push_san('e4')
        state.confirm_screen_position(after.board_fen(),'b','white','-')
        self.assertEqual(state.board.fen(),after.fen())

    def test_calibration_does_not_mislabel_empty_starting_pawn_squares(self):
        board=chess.Board()
        board.push_san('c4')
        board.push_san('c6')
        with self.assertRaisesRegex(ValueError,'posição inicial'):
            ScreenBoardReader(render(board))

    def test_uncertain_snapshot_does_not_destroy_history_and_can_be_confirmed(self):
        state=app.AnalysisState()
        state.screen_active=True
        initial=chess.Board()
        state.receive({'source':'Captura de tela','placement':initial.board_fen()})
        observed=initial.copy()
        for san in ('e4','e5','Nf3'):observed.push_san(san)
        response=state.receive({'source':'Captura de tela','placement':observed.board_fen()})
        self.assertFalse(response['ok'])
        self.assertEqual(state.tracker.board.fen(),initial.fen())
        self.assertTrue(state.screen_paused)
        self.assertIsNotNone(state.pending_screen)
        self.assertTrue(state.receive({'source':'Captura de tela','placement':initial.board_fen()})['ok'])
        self.assertFalse(state.screen_paused)
        self.assertIsNone(state.pending_screen)
        state.receive({'source':'Captura de tela','placement':observed.board_fen()})
        state.force_turn('b')
        self.assertEqual(state.board.board_fen(),observed.board_fen())
        self.assertEqual(state.mode,'turno manual')
        self.assertFalse(state.screen_paused)
        trusted=state.tracker
        checking=chess.Board('4k3/8/8/8/8/8/4R3/K7 b - - 0 1')
        state.receive({'source':'Captura de tela','placement':checking.board_fen()})
        with self.assertRaises(ValueError):state.force_turn('w')
        self.assertIs(state.tracker,trusted)
        self.assertIsNotNone(state.pending_screen)
        state.force_turn('b')
        self.assertEqual(state.board.board_fen(),checking.board_fen())

    def test_outlined_chess_glyphs_survive_colored_highlights(self):
        try:font=ImageFont.truetype('C:/Windows/Fonts/seguisym.ttf',50)
        except OSError:self.skipTest('Windows chess font unavailable')
        glyphs={'k':'♚','q':'♛','r':'♜','b':'♝','n':'♞','p':'♟'}
        def picture(board,highlights=None):
            image=Image.new('RGB',(656,656))
            draw=ImageDraw.Draw(image)
            for row in range(8):
                for col in range(8):
                    square=chess.square(col,7-row)
                    bg=(highlights or {}).get(square,(240,217,181) if (row+col)%2==0 else (181,136,99))
                    draw.rectangle((col*82,row*82,(col+1)*82-1,(row+1)*82-1),fill=bg)
                    p=board.piece_at(square)
                    if p:draw.text((col*82+41,row*82+41),glyphs[p.symbol().lower()],font=font,anchor='mm',
                                   fill='white' if p.color else 'black',stroke_width=1,
                                   stroke_fill='black' if p.color else 'white')
            return image
        reader=ScreenBoardReader(picture(chess.Board()))
        board=chess.Board()
        board.push_san('c4')
        board.push_san('c6')
        for color in ((163,168,45),(75,145,205)):
            self.assertEqual(reader.read(picture(board,{chess.C7:color,chess.C6:color})),board.board_fen())

    def test_viewer_can_be_placed_outside_source_or_report_no_space(self):
        bbox=(51,229,707,885)
        position=outside_position(bbox,(456,540),(1657,1043))
        self.assertIsNotNone(position)
        x,y=position
        self.assertTrue(x>=bbox[2] or x+456<=bbox[0] or y>=bbox[3] or y+540<=bbox[1])
        self.assertIsNone(outside_position((0,0,1280,720),(456,540),(1280,720)))

    def test_live_reader_keeps_retrying_after_occlusion_and_resumes(self):
        initial=render(chess.Board())
        blocked=initial.copy()
        ImageDraw.Draw(blocked).rectangle((0,0,479,150),fill='red')
        moved=chess.Board()
        moved.push_san('e4')
        frames=[initial,initial,blocked,blocked,initial,initial,render(moved),render(moved)]
        reader=ScreenBoardReader(initial)
        state=app.AnalysisState()
        state.screen_active=True
        ui=app.ChessVisionUI.__new__(app.ChessVisionUI)
        ui.state=state
        class Stop:
            count=0
            def is_set(self):return self.count>=len(frames)
            def wait(self,_):self.count+=1
        with patch('PIL.ImageGrab.grab',side_effect=frames):
            ui.read_screen(reader,(0,0,480,480),Stop())
        self.assertTrue(state.screen_active)
        self.assertFalse(state.screen_paused)
        self.assertEqual(state.board.fen(),moved.fen())
        self.assertEqual(state.mode,'movimentos legais')
        events=[]
        while not state.ui_events.empty():events.append(state.ui_events.get_nowait())
        self.assertTrue(any(e[0]=='clear' for e in events))
        statuses=[e[1] for e in events if e[0]=='screen_status']
        self.assertTrue(any('tentando novamente' in s for s in statuses))
        self.assertIn('posição reconhecida',statuses[-1])
    def test_last_move_highlights_do_not_pause_reading(self):
        reader=ScreenBoardReader(render(chess.Board()))
        board=chess.Board()
        board.push_san('c4')
        board.push_san('c6')
        for color in ((163,168,45),(245,220,60),(75,145,205)):
            with self.subTest(color=color):
                image=render(board,highlights={chess.C7:color,chess.C6:color})
                self.assertEqual(reader.read(image),board.board_fen())

    def test_automatic_location_preserves_exact_pixel_boundaries(self):
        for size, position in ((480, (113, 79)), (328, (31, 21)), (481, (7, 13))):
            with self.subTest(size=size):
                image = Image.new('RGB', (900, 650), '#202433')
                image.paste(render(chess.Board()).resize((size,size), Image.Resampling.NEAREST), position)
                self.assertEqual(detect_boards(image),
                                 [(*position, position[0]+size, position[1]+size)])

    def test_automatic_location_returns_multiple_boards(self):
        image = Image.new('RGB', (1100, 650), '#202433')
        image.paste(render(chess.Board()), (10, 20))
        image.paste(render(chess.Board(), 'black'), (580, 130))
        self.assertEqual(detect_boards(image), [(10,20,490,500), (580,130,1060,610)])

    def test_automatic_location_rejects_missing_or_partial_board(self):
        image = Image.new('RGB', (900, 650), '#202433')
        self.assertEqual(detect_boards(image), [])
        image.paste(render(chess.Board()).crop((0,0,420,480)), (11,19))
        self.assertEqual(detect_boards(image), [])

    def test_both_orientations_and_legal_sequence(self):
        for orientation in ('white', 'black'):
            board = chess.Board()
            reader = ScreenBoardReader(render(board, orientation), orientation)
            self.assertEqual(reader.read(render(board, orientation)), board.board_fen())
            for san in ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Nf6', 'O-O'):
                board.push_san(san)
                self.assertEqual(reader.read(render(board, orientation)), board.board_fen())

    def test_highlight_and_promoted_piece(self):
        reader = ScreenBoardReader(render(chess.Board()))
        board = chess.Board('Q6k/8/8/8/8/8/8/7K w - - 0 1')
        self.assertEqual(reader.read(render(board, highlight=chess.A8)), board.board_fen())

    def test_bad_regions_and_occlusion_are_rejected(self):
        for size in ((80, 80), (480, 400)):
            with self.assertRaises(ValueError):
                ScreenBoardReader(Image.new('RGB', size))
        with self.assertRaises(ValueError):
            ScreenBoardReader(Image.new('RGB', (480, 480)))
        reader = ScreenBoardReader(render(chess.Board()))
        image = render(chess.Board())
        ImageDraw.Draw(image).rectangle((0, 0, 479, 100), fill='red')
        with self.assertRaises(ValueError):
            reader.read(image)

    def test_capture_and_extension_do_not_overwrite_each_other(self):
        with patch.object(app.AnalysisState, '_save_config'):
            state = app.AnalysisState()
            state.screen_active = True
            state.receive({'placement': chess.STARTING_BOARD_FEN, 'source': 'Captura de tela'})
            revision = state.revision
            state.pause_screen('Animação')
            self.assertGreater(state.revision, revision)
            self.assertEqual(state.mode, 'captura pausada')
            state.receive({'placement': chess.STARTING_BOARD_FEN, 'source': 'Captura de tela'})
            self.assertFalse(state.screen_paused)
            self.assertEqual(state.mode, 'inicio')
            board = chess.Board()
            board.push_san('e4')
            state.receive({'placement': board.board_fen(), 'source': 'chess.com'})
            self.assertEqual(state.board.board_fen(), chess.STARTING_BOARD_FEN)
            state.screen_active = False
            state.receive({'placement': board.board_fen(), 'source': 'chess.com'})
            self.assertEqual(state.board.board_fen(), board.board_fen())


if __name__ == '__main__':
    unittest.main()

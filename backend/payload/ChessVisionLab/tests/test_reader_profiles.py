import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chess
from PIL import Image

import app
from reader_profiles import ReaderProfiles
from screen_reader import ScreenBoardReader, UncertainSquareError
from test_screen_reader import render


class ReaderProfileTests(unittest.TestCase):
    def test_background_reader_observes_match_until_checkmate_and_saves_it(self):
        board=chess.Board()
        frames=[render(board),render(board)]
        for san in ('f3','e5','g4','Qh4#'):
            board.push_san(san)
            frames.extend([render(board),render(board)])
        ui=app.ChessVisionUI.__new__(app.ChessVisionUI)
        ui.state=app.AnalysisState();ui.state.screen_active=True
        reader=ScreenBoardReader(render(chess.Board()))
        class Stop:
            count=0
            def is_set(self):return self.count>=len(frames)
            def wait(self,_):self.count+=1
        with tempfile.TemporaryDirectory() as folder:
            ui.reader_profiles=ReaderProfiles(folder)
            with patch('PIL.ImageGrab.grab',side_effect=frames):
                ui.read_screen(reader,(0,0,480,480),Stop())
            self.assertTrue(ui.state.board.is_checkmate())
            self.assertEqual(ui.state.board.fen(),board.fen())
            self.assertEqual(ui.reader_profiles.load_game(reader).move_stack,board.move_stack)
            events=[]
            while not ui.state.ui_events.empty():events.append(ui.state.ui_events.get_nowait())
            self.assertTrue(any(event[0]=='screen_status' and 'Partida encerrada' in event[1] and '0-1' in event[1] for event in events))

    def test_multiple_profiles_and_partial_progress_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ReaderProfiles(folder,Path(folder)/'no-bundled')
            ready=ScreenBoardReader(render(chess.Board()))
            ready.profile_name='Meu tema / teste'
            store.save(ready)
            partial=ScreenBoardReader.new_profile((480,480),name='Outro tema')
            partial.add_example(render(chess.Board()),0,0,'r')
            store.save(partial)
            restored=ReaderProfiles(folder,Path(folder)/'no-bundled')
            self.assertEqual(set(restored.list()),{ready.profile_name,partial.profile_name})
            self.assertEqual(len(restored.ready()),1)
            self.assertEqual(len(restored.list()['Outro tema'][1].templates['r']),1)

    def test_corrupt_profile_does_not_hide_good_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ReaderProfiles(folder,Path(folder)/'none')
            store.save(ScreenBoardReader(render(chess.Board())))
            (Path(folder)/'bad.json').write_text('{',encoding='utf-8')
            self.assertEqual(len(store.ready()),1)

    def test_game_history_retains_rules_and_repetition_after_restart(self):
        board=chess.Board()
        for san in ('Nf3','Nf6','Ng1','Ng8','e4','a6','e5','d5'):
            board.push_san(san)
        with tempfile.TemporaryDirectory() as folder:
            store=ReaderProfiles(folder)
            reader=ScreenBoardReader(render(chess.Board()))
            store.save_game(reader,board)
            restored=store.load_game(reader)
            self.assertEqual(restored.fen(),board.fen())
            self.assertEqual(restored.move_stack,board.move_stack)
            self.assertIn(chess.Move.from_uci('e5d6'),restored.legal_moves)
            self.assertEqual(restored.castling_rights,board.castling_rights)
            reader.profile_name='another'
            with self.assertRaises(OSError):store.load_game(reader)

    def test_bundled_profile_is_ready_without_user_training(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ReaderProfiles(folder)
            reader=next(r for r in store.ready() if r.profile_name=='cburnett (pronto)')
            source=Path(__file__).parents[1]/'profiles'/'cburnett-source'/'initial.png'
            with Image.open(source) as image:
                self.assertEqual(reader.for_region(image.size).read(image),chess.STARTING_BOARD_FEN)
                small=image.resize((480,480))
                self.assertEqual(reader.for_region(small.size).read(small),chess.STARTING_BOARD_FEN)

    def test_legal_context_resolves_close_tie_but_never_overrides_visual_evidence(self):
        reader=ScreenBoardReader(render(chess.Board()))
        before=chess.Board()
        after=before.copy();after.push_san('e4')
        original=reader._matches
        reader.read(render(before))
        pawn=reader._tile(render(after),4,4)
        def ambiguous(tile):
            matches=original(tile)
            if reader._distance(tile,pawn)<.01:
                return sorted((2 if s=='P' else 1.5 if s=='N' else d+20,s) for d,s in matches)
            return matches
        with patch.object(reader,'_matches',side_effect=ambiguous):
            with self.assertRaises(UncertainSquareError):reader.read(render(after))
            self.assertEqual(reader.read(render(after),board=before),after.board_fen())
            self.assertEqual(reader.read(render(after),board=after),after.board_fen())
        self.assertEqual(before.fen(),chess.Board().fen())

    def test_rule_resolution_rejects_blocked_board_and_ambiguous_promotion(self):
        before=chess.Board()
        after=before.copy();after.push_san('e4')
        observations={s:[(0,p.symbol() if p else '.')] for s in chess.SQUARES for p in [after.piece_at(s)]}
        observations[chess.E4]=[(1,'N'),(2,'P')]
        self.assertEqual(ScreenBoardReader._resolve_move(before,observations,{chess.E4}),after.board_fen())
        self.assertIsNone(ScreenBoardReader._resolve_move(before,observations,{chess.E4,chess.E2,chess.A1}))
        observations[chess.A1]=[(0,'q')]
        self.assertIsNone(ScreenBoardReader._resolve_move(before,observations,{chess.E4}))
        board=chess.Board('4k3/P7/8/8/8/8/8/4K3 w - - 0 1')
        promoted=board.copy();promoted.push_uci('a7a8q')
        observations={s:[(0,p.symbol() if p else '.')] for s in chess.SQUARES for p in [promoted.piece_at(s)]}
        observations[chess.A8]=[(1,'Q'),(1.1,'R'),(1.2,'B'),(1.3,'N')]
        self.assertIsNone(ScreenBoardReader._resolve_move(board,observations,{chess.A8}))

    def test_camera_tracks_special_moves_using_legal_history(self):
        from tracker import BoardTracker
        reader=ScreenBoardReader(render(chess.Board()))
        cases=[
            ('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','e1g1'),
            ('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1','e5d6'),
            ('4k3/P7/8/8/8/8/8/4K3 w - - 0 1','a7a8n'),
            ('4k3/8/8/8/3p4/4P3/8/4K3 w - - 0 1','e3d4'),
        ]
        for fen,uci in cases:
            with self.subTest(move=uci):
                before=chess.Board(fen)
                after=before.copy();after.push_uci(uci)
                tracker=BoardTracker();tracker.board=before;tracker.mode='tela confirmada'
                observed=reader.read(render(after),board=before)
                result=tracker.update(observed)
                self.assertEqual(result.board.fen(),after.fen())
                self.assertEqual(result.mode,'movimentos legais')

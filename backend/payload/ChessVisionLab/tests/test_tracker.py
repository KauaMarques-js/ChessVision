import unittest
import chess
from tracker import BoardTracker, parse_placement


class TrackerTests(unittest.TestCase):
    def test_start_and_known_move(self):
        t = BoardTracker()
        st = t.update(chess.STARTING_BOARD_FEN)
        self.assertTrue(st.changed)
        target = chess.Board()
        target.push_san('e4')
        st = t.update(target.board_fen())
        self.assertEqual(st.board.fen(),target.fen())

    def test_history_overrides_late_join(self):
        b = chess.Board()
        for san in ['e4','c5','Nf3','d6','d4']:
            b.push_san(san)
        t = BoardTracker()
        out = t.update(b.board_fen(), ['e4','c5','Nf3','d6','d4'])
        self.assertEqual(out.mode,'historico')
        self.assertEqual(out.board.fen(),b.fen())

    def test_two_ply_jump(self):
        t = BoardTracker()
        t.update(chess.STARTING_BOARD_FEN)
        target=chess.Board()
        target.push_san('e4')
        target.push_san('e5')
        out=t.update(target.board_fen())
        self.assertEqual(out.board.fen(),target.fen())

    def test_reject_bad_placement(self):
        for val in ['0/8/8/8/8/8/8/8','8/8/8/8/8/8/8/8','xyz','8/8/8/8/8/8/8/7']:
            with self.assertRaises(ValueError): parse_placement(val)


if __name__=='__main__': unittest.main()

class RegressionTests(unittest.TestCase):
    def test_repetition_same_piece_placement_must_update_turn_and_counters(self):
        tracker = BoardTracker()
        tracker.update(chess.STARTING_BOARD_FEN)
        board = chess.Board()
        san = ['Nf3','Nf6','Ng1','Ng8']
        for move in san:
            board.push_san(move)
        result = tracker.update(board.board_fen(), san)
        self.assertEqual(result.mode,'historico')
        self.assertTrue(result.changed)
        self.assertEqual(result.board.fen(),board.fen())
        self.assertEqual(result.board.fullmove_number,3)

    def test_late_join_without_history_should_warn(self):
        board = chess.Board()
        for move in ['e4', 'c5', 'Nf3', 'd6']:
            board.push_san(move)
        t=BoardTracker()
        result=t.update(board.board_fen())
        self.assertEqual(result.mode, 'estimado')
        self.assertTrue(result.warning)

    def test_castling_and_en_passant_from_full_history(self):
        for line in (
            ['e4','e5','Nf3','Nc6','Bc4','Nf6','O-O'],
            ['e4','a5','e5','d5','exd6']
        ):
            board=chess.Board()
            for san in line: board.push_san(san)
            tracker=BoardTracker()
            result=tracker.update(board.board_fen(),line)
            self.assertEqual(result.board.fen(),board.fen())
            self.assertEqual(result.mode,'historico')

import unittest
from unittest.mock import patch

import chess
from PIL import Image, ImageDraw, ImageFont

import app
from screen_reader import ScreenBoardReader, square_at, detect_boards


def render(board, orientation='white', highlight=None):
    image = Image.new('RGB', (480, 480))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    for row in range(8):
        for col in range(8):
            square = square_at(row, col, orientation)
            bg = (150, 180, 140) if (row+col) % 2 else (220, 210, 180)
            if square == highlight:
                bg = (190, 200, 120)
            draw.rectangle((col*60, row*60, (col+1)*60-1, (row+1)*60-1), fill=bg)
            piece = board.piece_at(square)
            if piece:
                draw.text((col*60+13, row*60+6), piece.symbol().upper(), font=font,
                          fill=(255, 255, 255) if piece.color else (10, 10, 10))
    return image


class ScreenReaderTests(unittest.TestCase):
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

"""Local, calibrated 2D board recognition. Never sends images or plays moves."""
from __future__ import annotations

from PIL import Image, ImageChops, ImageStat
import chess


def _similar(a, b):
    return all(abs(x-y) <= 12 for x, y in zip(a, b))


def _grid_spans(colors):
    """Find eight alternating, equally sized runs without resizing pixels."""
    runs = []
    start, anchor = 0, colors[0]
    for position, color in enumerate(colors[1:], 1):
        if not _similar(color, anchor):
            runs.append((start, position, anchor))
            start, anchor = position, color
    runs.append((start, len(colors), anchor))
    spans = []
    for index in range(len(runs)-7):
        group = runs[index:index+8]
        lengths = [end-start for start, end, _ in group]
        if min(lengths) < 20 or max(lengths)-min(lengths) > 2:
            continue
        if sum(abs(a-b) for a, b in zip(group[0][2], group[1][2])) < 45:
            continue
        if all(_similar(item[2], group[n % 2][2]) for n, item in enumerate(group)):
            spans.append((group[0][0], group[-1][1]))
    return spans


def detect_boards(image):
    """Return pixel rectangles of visible, flat-color 8x8 checkerboards.

    Detection locates geometry, not pieces or the side to move. Ambiguous
    candidates must be reviewed by the user before calibration.
    """
    image = image.convert('RGB')
    w, h = image.size
    if min(w, h) < 160:
        return []
    pixels = image.load()
    horizontal = set()
    for y in range(0, h, max(1, h//200)):
        for left, right in _grid_spans([pixels[x, y] for x in range(w)]):
            horizontal.add((left, right, y))
    if not horizontal:
        return []
    vertical = []
    for x in range(0, w, max(1, w//240)):
        for top, bottom in _grid_spans([pixels[x, y] for y in range(h)]):
            vertical.append((top, bottom, x))
    candidates = set()
    for left, right, y in horizontal:
        for top, bottom, x in vertical:
            if left <= x < right and top <= y < bottom and abs((right-left)-(bottom-top)) <= 2:
                candidates.add((left, top, right, bottom))
    valid = []
    for bbox in sorted(candidates):
        left, top, right, bottom = bbox
        cell_w, cell_h = (right-left)/8, (bottom-top)/8
        samples = [[], []]
        tiles = []
        for row in range(8):
            for col in range(8):
                corners = [pixels[min(w-1, int(left+(col+dx)*cell_w)),
                                  min(h-1, int(top+(row+dy)*cell_h))]
                           for dx, dy in ((.12,.12),(.88,.12),(.12,.88),(.88,.88))]
                parity = (row+col) % 2
                samples[parity].extend(corners)
                tiles.append((parity, corners))
        backgrounds = [tuple(sorted(p[c] for p in group)[len(group)//2] for c in range(3))
                       for group in samples]
        if sum(abs(a-b) for a,b in zip(*backgrounds)) < 45:
            continue
        matching = sum(sum(_similar(p, backgrounds[parity]) for p in corners) >= 3
                       for parity, corners in tiles)
        if matching >= 60:
            valid.append(bbox)
    return valid


def square_at(row, col, orientation):
    return chess.square(7-col if orientation == 'black' else col,
                        row if orientation == 'black' else 7-row)


def feature(tile):
    # Subtract each square's background so highlights and board colors have
    # less influence. Keep both positive and negative edges for white/black.
    tile = tile.convert('RGB').resize((32, 32), Image.Resampling.LANCZOS)
    corners = [tile.getpixel(p) for p in ((2, 2), (29, 2), (2, 29), (29, 29))]
    background = tuple(sorted(p[c] for p in corners)[2] for c in range(3))
    bg = Image.new('RGB', tile.size, background)
    residual = ImageChops.subtract(tile, bg, scale=2, offset=128).crop((3, 3, 29, 29))
    amplitude = max(16, *(abs(v-128) for bounds in residual.getextrema() for v in bounds))
    return residual.point(lambda v: round(128+(v-128)*120/amplitude))


class ScreenBoardReader:
    """Templates come from the user's initial board, with all twelve pieces.

    Calibration is session-only. A changed theme, zoom or region requires a
    fresh calibration. Ambiguous squares reject the entire snapshot.
    """
    def __init__(self, image, orientation='white'):
        if orientation not in ('white', 'black'):
            raise ValueError('Orientação inválida')
        if min(image.size) < 160 or abs(image.width-image.height) > 4:
            raise ValueError('Selecione somente as 64 casas de um tabuleiro quadrado (mínimo 160 px).')
        self.orientation = orientation
        self.size = image.size
        self.templates = {}
        initial = chess.Board()
        for row in range(8):
            for col in range(8):
                piece = initial.piece_at(square_at(row, col, orientation))
                symbol = piece.symbol() if piece else '.'
                self.templates.setdefault(symbol, []).append(self._tile(image, row, col))
        # A wrong region or nearly identical pieces cannot be calibrated safely.
        samples = {s: ts[0] for s, ts in self.templates.items()}
        for symbol, tile in samples.items():
            if any(self._distance(tile, other) < 1.5
                   for s, other in samples.items() if s != symbol):
                raise ValueError('Peças indistinguíveis. Confira a região e use a posição inicial, sem animações.')

    def _tile(self, image, row, col):
        w, h = image.size
        return feature(image.crop((round(col*w/8), round(row*h/8),
                                   round((col+1)*w/8), round((row+1)*h/8))))

    @staticmethod
    def _distance(a, b):
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean)/3

    def read(self, image):
        if image.size != self.size:
            raise ValueError('Tamanho alterado; calibre o tabuleiro novamente.')
        board = chess.Board(None)
        for row in range(8):
            for col in range(8):
                tile = self._tile(image, row, col)
                matches = sorted((min(self._distance(tile, t) for t in templates), symbol)
                                 for symbol, templates in self.templates.items())
                (distance, symbol), (runner_up, _) = matches[:2]
                if distance > 10 or runner_up-distance < 1.2:
                    raise ValueError('Leitura incerta; deixe as peças visíveis e aguarde o fim da animação.')
                if symbol != '.':
                    board.set_piece_at(square_at(row, col, self.orientation), chess.Piece.from_symbol(symbol))
        if len(board.pieces(chess.KING, chess.WHITE)) != 1 or len(board.pieces(chess.KING, chess.BLACK)) != 1:
            raise ValueError('Reis não reconhecidos; confira a captura ou calibre novamente.')
        return board.board_fen()

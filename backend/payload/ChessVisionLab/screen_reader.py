"""Local, calibrated 2D board recognition. Never sends images or plays moves."""
from __future__ import annotations

import base64
import json
from PIL import Image, ImageChops, ImageStat, ImageDraw
import chess

PIECE_LABELS={'.':'Casa vazia','P':'Peão branco','N':'Cavalo branco','B':'Bispo branco',
              'R':'Torre branca','Q':'Dama branca','K':'Rei branco','p':'Peão preto',
              'n':'Cavalo preto','b':'Bispo preto','r':'Torre preta','q':'Dama preta','k':'Rei preto'}


class UncertainSquareError(ValueError):
    def __init__(self,row,col,orientation,matches):
        self.row,self.col=row,col
        self.matches=matches
        self.symbol=matches[0][1]
        square=chess.square_name(square_at(row,col,orientation))
        super().__init__(f'Casa {square}: peça incerta. Aguarde a área ficar visível.')


def outside_position(bbox, window_size, screen_size, margin=12):
    """Place the viewer outside the source without resizing its board."""
    left,top,right,bottom=bbox
    ww,wh=window_size
    sw,sh=screen_size
    if ww>sw or wh>sh:return None
    x=max(0,min(left,sw-ww))
    y=max(0,min(top,sh-wh))
    for px,py in ((right+margin,y),(left-margin-ww,y),(x,bottom+margin),(x,top-margin-wh)):
        if 0<=px<=sw-ww and 0<=py<=sh-wh:
            return px,py
    return None


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


def detect_boards(image, excluded_regions=()):
    """Return pixel rectangles of visible, flat-color 8x8 checkerboards.

    Detection locates geometry, not pieces or the side to move. Ambiguous
    candidates must be reviewed by the user before calibration.
    """
    image = image.convert('RGB')
    if excluded_regions:
        image=image.copy()
        draw=ImageDraw.Draw(image)
        for left,top,right,bottom in excluded_regions:
            if right>left and bottom>top:
                draw.rectangle((left,top,right-1,bottom-1),fill='#111723')
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


def refine_board_region(image,bbox):
    """Snap a slightly padded/manual rectangle to the observed grid edges."""
    left,top,right,bottom=bbox
    margin=max(12,round(min(right-left,bottom-top)/24))
    region=(max(0,left-margin),max(0,top-margin),min(image.width,right+margin),min(image.height,bottom+margin))
    if region[2]<=region[0] or region[3]<=region[1]:return bbox
    matches=[]
    for x,y,r,b in detect_boards(image.crop(region)):
        candidate=(x+region[0],y+region[1],r+region[0],b+region[1])
        if all(abs(a-z)<=margin*2 for a,z in zip(candidate,bbox)):
            matches.append(candidate)
    return min(matches,key=lambda candidate:sum(abs(a-b) for a,b in zip(candidate,bbox))) if matches else bbox


def square_at(row, col, orientation):
    return chess.square(7-col if orientation == 'black' else col,
                        row if orientation == 'black' else 7-row)


def feature(tile):
    # Preserve absolute foreground ink, masking the background. SVG pieces may
    # contain grey strokes whose polarity changes on light versus dark squares.
    if 'A' in tile.getbands() or 'transparency' in tile.info:
        rgba=tile.convert('RGBA')
        tile=Image.alpha_composite(Image.new('RGBA',rgba.size,(160,160,160,255)),rgba)
    tile = tile.convert('RGB').resize((32, 32), Image.Resampling.LANCZOS)
    corners = [tile.getpixel(p) for p in ((2, 2), (29, 2), (2, 29), (29, 29))]
    background=tuple(sorted(pixel[channel] for pixel in corners)[2] for channel in range(3))
    difference=ImageChops.difference(tile,Image.new('RGB',tile.size,background))
    red,green,blue=difference.split()
    mask=ImageChops.lighter(ImageChops.lighter(red,green),blue).point(lambda value:min(255,value*20))
    ink=Image.composite(tile.convert('L'),Image.new('L',tile.size,128),mask)
    mask,ink=mask.crop((3,3,29,29)),ink.crop((3,3,29,29))
    return Image.merge('RGB',(mask,ink,ink))


class ScreenBoardReader:
    """Templates come from the user's initial board, with all twelve pieces.

    Saved feature references can be reused on a mid-game board. A different
    theme still requires calibration. Ambiguous squares reject the snapshot.
    """
    def __init__(self, image, orientation='white'):
        if orientation not in ('white', 'black'):
            raise ValueError('Orientação inválida')
        if min(image.size) < 160 or abs(image.width-image.height) > 4:
            raise ValueError('Selecione somente as 64 casas de um tabuleiro quadrado (mínimo 160 px).')
        self.orientation = orientation
        self.profile_name='Calibração inicial'
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
        # Calibration must generalize across repeated pawns, rather than
        # "recognizing" an empty starting square as a pawn from its own sample.
        for symbol in ('P','p'):
            group=self.templates[symbol]
            for index,tile in enumerate(group):
                same=min(self._distance(tile,other) for i,other in enumerate(group) if i!=index)
                different=min(self._distance(tile,other) for key,values in self.templates.items()
                              if key!=symbol for other in values)
                if same+.8>=different:
                    raise ValueError('Peões iniciais inconsistentes. Volte à posição inicial e confira os limites da área.')

    def _tile(self, image, row, col):
        w, h = image.size
        return feature(image.crop((round(col*w/8), round(row*h/8),
                                   round((col+1)*w/8), round((row+1)*h/8))))

    def for_region(self,size,orientation=None):
        if min(size)<160 or abs(size[0]-size[1])>4:
            raise ValueError('Região inválida para o tabuleiro.')
        orientation=orientation or self.orientation
        if orientation not in ('white','black'):raise ValueError('Orientação inválida')
        reader=object.__new__(type(self))
        reader.orientation=orientation
        reader.size=tuple(size)
        reader.templates=self.templates
        reader.profile_name=getattr(self,'profile_name','Calibração inicial')
        return reader

    @classmethod
    def new_profile(cls,size,orientation='white',name='Tema personalizado'):
        reader=object.__new__(cls)
        reader.size=tuple(size)
        reader.orientation=orientation
        reader.profile_name=str(name).strip()[:80] or 'Tema personalizado'
        reader.templates={symbol:[] for symbol in PIECE_LABELS}
        return reader.for_region(size,orientation)

    @property
    def missing_symbols(self):
        return [symbol for symbol in PIECE_LABELS if not self.templates.get(symbol)]

    def add_example(self,image,row,col,symbol):
        if symbol not in PIECE_LABELS or not 0<=row<8 or not 0<=col<8:
            raise ValueError('Escolha uma peça e uma casa válida.')
        if image.size!=self.size:raise ValueError('A área mudou; reinicie o ensino deste perfil.')
        self.add_tile(symbol,image.crop((round(col*image.width/8),round(row*image.height/8),
                                        round((col+1)*image.width/8),round((row+1)*image.height/8))))

    def add_tile(self,symbol,image):
        if symbol not in PIECE_LABELS:raise ValueError('Escolha o tipo de peça.')
        if min(image.size)<12:raise ValueError('O exemplo precisa mostrar a casa inteira.')
        if len(self.templates[symbol])>=64 or sum(map(len,self.templates.values()))>=256:
            raise ValueError('Limite de exemplos atingido; remova um exemplo ou crie outro perfil.')
        self.templates[symbol].append(feature(image))

    def save(self,path):
        if self.missing_symbols:raise ValueError('Complete os exemplos de todas as peças antes de salvar.')
        # Only normalized piece features: never full desktop screenshots.
        data={'format':'foreground-ink-v2','size':self.size,'orientation':self.orientation,
              'profile_name':self.profile_name,
              'templates':{symbol:[base64.b64encode(tile.tobytes()).decode('ascii') for tile in tiles]
                           for symbol,tiles in self.templates.items()}}
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data),encoding='utf-8')
        temporary.replace(path)

    @classmethod
    def load(cls,path):
        if path.stat().st_size>1000000:raise ValueError('Referências salvas inválidas')
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict):raise ValueError('Referências salvas inválidas')
        if data.get('format')!='foreground-ink-v2':raise ValueError('Perfil antigo: ensine as peças novamente nesta versão.')
        templates=data.get('templates')
        if not isinstance(templates,dict) or set(templates)!=set('.KQRBNPkqrbnp'):
            raise ValueError('Referências de peças incompletas')
        decoded={}
        for symbol,tiles in templates.items():
            if not isinstance(tiles,list) or not 1<=len(tiles)<=64:raise ValueError('Referências inválidas')
            decoded[symbol]=[]
            for tile in tiles:
                raw=base64.b64decode(tile,validate=True)
                if len(raw)!=26*26*3:raise ValueError('Referência de peça inválida')
                decoded[symbol].append(Image.frombytes('RGB',(26,26),raw))
        reader=object.__new__(cls)
        reader.templates=decoded
        reader.profile_name=str(data.get('profile_name','Calibração inicial'))[:80]
        reader.orientation=data.get('orientation')
        reader.size=tuple(data.get('size',()))
        if len(reader.size)!=2 or not all(isinstance(v,int) for v in reader.size):
            raise ValueError('Tamanho das referências inválido')
        return reader.for_region(reader.size)

    @staticmethod
    def _distance(a, b):
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean)/3

    @staticmethod
    def _uncertain(matches):
        distance,runner_up=matches[0][0],matches[1][0]
        return distance>12 or runner_up-distance<1.2 or (distance>10 and runner_up<distance*1.8)

    def _matches(self,tile):
        matches=sorted((min(self._distance(tile,t) for t in templates),symbol)
                       for symbol,templates in self.templates.items())
        if self._uncertain(matches):
            # Subpixel rasterization and slightly offset crops can move an
            # outline by one normalized pixel. Compare every class with the
            # same bounded shifts, retaining the confidence/margin checks.
            shifted=[ImageChops.offset(tile,dx,dy) for dx,dy in
                     ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))]
            matches=sorted((min(distance,min(self._distance(other,t)
                           for other in shifted for t in self.templates[symbol])),symbol)
                           for distance,symbol in matches)
        return matches

    def read(self, image):
        if self.missing_symbols:
            missing=', '.join(PIECE_LABELS[symbol] for symbol in self.missing_symbols)
            raise ValueError('Perfil incompleto: cadastre '+missing)
        if image.size != self.size:
            raise ValueError('Tamanho alterado; calibre o tabuleiro novamente.')
        board = chess.Board(None)
        for row in range(8):
            for col in range(8):
                tile = self._tile(image, row, col)
                matches = self._matches(tile)
                (distance, symbol), (runner_up, _) = matches[:2]
                # Small light/dark-square variation is accepted only when the
                # winning piece remains well separated from the runner-up.
                if self._uncertain(matches):
                    raise UncertainSquareError(row,col,self.orientation,matches[:2])
                if symbol != '.':
                    board.set_piece_at(square_at(row, col, self.orientation), chess.Piece.from_symbol(symbol))
        if len(board.pieces(chess.KING, chess.WHITE)) != 1 or len(board.pieces(chess.KING, chess.BLACK)) != 1:
            raise ValueError('Reis não reconhecidos; confira a captura ou calibre novamente.')
        return board.board_fen()

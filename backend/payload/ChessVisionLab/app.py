"""ChessVision Lab: local desktop analysis GUI + localhost Chess.com board bridge.

Run: python app.py     (requires python-chess and an official Stockfish binary)
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import (Tk, Canvas, Text, StringVar, IntVar, BooleanVar, END,
                     filedialog, messagebox, ttk)
import tkinter as tk

import chess
import chess.engine

from tracker import BoardTracker
from variation_view import DISPLAY_LABELS, CYCLE_SECONDS, selected_line, next_cycle_rank

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
CONFIG = BASE / 'config.json'
HOST, PORT = '127.0.0.1', 8765
PIECE_GLYPHS = {'K':'♔','Q':'♕','R':'♖','B':'♗','N':'♘','P':'♙',
                'k':'♚','q':'♛','r':'♜','b':'♝','n':'♞','p':'♟'}


def find_stockfish():
    # Favor the bundled official v19 release over older engines on PATH.
    for directory in (BASE / 'engine', BASE / 'stockfish'):
        if directory.is_dir():
            matches = list(directory.rglob('stockfish*.exe')) if os.name == 'nt' else list(directory.rglob('stockfish*'))
            matches = [p for p in matches if p.is_file() and (os.name == 'nt' or os.access(p, os.X_OK))]
            if matches:
                return str(matches[0])
    for name in ('stockfish', 'stockfish.exe'):
        found = shutil.which(name)
        if found:
            return found
    return ''


def load_config():
    defaults = {'stockfish':find_stockfish(), 'depth':42, 'seconds':0,
                'threads':2, 'hash':128, 'multipv':3, 'always_on_top':False,
                'display_mode':'all', 'board_only':False}
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        return {**defaults, **{k:v for k,v in data.items() if k in defaults}}
    except (OSError, json.JSONDecodeError):
        return defaults


class AnalysisState:
    def __init__(self):
        self.lock = threading.RLock()
        self.tracker = BoardTracker()
        self.board = None
        self.source = ''
        self.orientation = 'white'
        self.warning = ''
        self.mode = ''
        self.connected_at = 0.0
        self.revision = 0
        self.config = load_config()
        self.ui_events = queue.Queue()
        self.wakeup = threading.Event()
        self.shutdown = threading.Event()
        self.last_payload = None

    def change_config(self, config):
        with self.lock:
            self.config = config.copy()
            self.revision += 1
            self.wakeup.set()
        self._save_config(config)

    def update_view_settings(self, **changes):
        """Preferências de exibição não devem reiniciar a busca do Stockfish."""
        with self.lock:
            self.config.update(changes)
            config = self.config.copy()
        self._save_config(config)

    @staticmethod
    def _save_config(config):
        try:
            CONFIG.write_text(json.dumps(config, indent=2), encoding='utf-8')
        except OSError:
            pass

    def receive(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('JSON esperado')
        placement = payload.get('placement')
        moves = payload.get('moves', [])
        if not isinstance(moves, list) or len(moves) > 400:
            raise ValueError('Lista de lances invalida')
        moves = [m for m in moves if isinstance(m, str)][:400]
        source = str(payload.get('source',''))[:120]
        orientation = payload.get('orientation', 'white')
        turn = payload.get('turn')
        if turn not in ('w', 'b', None):
            raise ValueError('Turno invalido')
        with self.lock:
            result = self.tracker.update(placement, moves, turn=turn)
            self.connected_at = time.monotonic()
            self.source = source
            self.orientation = orientation if orientation in ('white', 'black') else 'white'
            self.warning = result.warning
            self.mode = result.mode
            if result.changed or self.board is None:
                self.board = result.board
                self.revision += 1
                self.wakeup.set()
                self.ui_events.put(('board', self.board.copy(), self.mode, self.warning))
            self.last_payload = time.time()
            self.ui_events.put(('connection', self.source, self.orientation))
        return {'ok':True, 'mode':result.mode}

    def set_fen(self, fen):
        b = chess.Board(fen)
        if not b.is_valid():
            raise ValueError('Posicao FEN invalida')
        with self.lock:
            self.tracker = BoardTracker()
            self.tracker.board = b.copy()
            self.tracker.mode = 'FEN manual'
            self.board = b
            self.mode, self.warning = 'FEN manual', ''
            self.source = 'Entrada manual'
            self.revision += 1
            self.wakeup.set()
            self.ui_events.put(('board', b.copy(), self.mode, self.warning))

    def force_turn(self, color):
        with self.lock:
            b = self.tracker.force_turn(color)
            if b:
                self.board = b
                self.mode = self.tracker.mode
                self.warning = self.tracker.warning
                self.revision += 1
                self.wakeup.set()
                self.ui_events.put(('board', b.copy(), self.mode, self.warning))


class LocalHandler(BaseHTTPRequestHandler):
    state: AnalysisState

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/health':
            with self.state.lock:
                source = self.state.source
                mode = self.state.mode
                last_seen = self.state.last_payload
                ready = self.state.board is not None
            self._send(200, {'ok':True, 'app':'ChessVision Lab', 'version':'1.1.0',
                             'board_ready':ready, 'mode':mode, 'source':source,
                             'last_payload':last_seen})
        else:
            self._send(404, {'error':'not found'})

    def do_POST(self):
        if self.path != '/position':
            self._send(404, {'error':'not found'})
            return
        try:
            # Only extension-origin/locally originated requests are accepted.
            origin = self.headers.get('Origin', '')
            if origin and not (origin.startswith('chrome-extension://') or
                               origin.startswith('moz-extension://')):
                self._send(403, {'ok':False, 'error':'Origem nao permitida'})
                return
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                self._send(415, {'ok':False, 'error':'Content-Type invalido'})
                return
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size < 16000:
                raise ValueError('Tamanho de mensagem invalido')
            content = self.rfile.read(size)
            obj = json.loads(content.decode('utf-8'))
            output = self.state.receive(obj)
            self._send(200, output)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            self._send(400, {'ok':False, 'error':str(exc)[:200]})
        except Exception as exc:
            self._send(500, {'ok':False, 'error':'Erro ao processar tabuleiro'})
            self.state.ui_events.put(('error',str(exc)))


def serve_local(state: AnalysisState):
    LocalHandler.state = state
    try:
        server = ThreadingHTTPServer((HOST,PORT),LocalHandler)
        server.timeout = 0.6
        state.ui_events.put(('server', f'Leitor ativo em {HOST}:{PORT}'))
        while not state.shutdown.is_set():
            server.handle_request()
        server.server_close()
    except OSError as exc:
        state.ui_events.put(('error',f'Nao foi possivel abrir a porta {PORT}: {exc}'))


def score_label(score):
    if score is None:
        return '—'
    pov = score.white()
    mate = pov.mate()
    if mate is not None:
        return ('Mate das ' + ('brancas' if mate > 0 else 'pretas') + f' em {abs(mate)}') if mate else 'Xeque-mate'
    cp = pov.score()
    return f'{cp/100:+.2f}' if cp is not None else '—'


def engine_worker(state: AnalysisState):
    engine, path, last_opts = None, None, None
    last_idle = None
    try:
        while not state.shutdown.is_set():
            with state.lock:
                board = state.board.copy(stack=True) if state.board else None
                config = state.config.copy()
                revision = state.revision
            executable = str(config.get('stockfish') or find_stockfish())
            if not board or not executable or not Path(executable).is_file():
                why = ('Aguardando uma posicao...' if board is None else
                       'Motor nao encontrado. Execute instalar_windows.bat ou selecione stockfish.exe.')
                if why != last_idle:
                    state.ui_events.put(('engine', why))
                    last_idle = why
                state.wakeup.wait(0.5)
                state.wakeup.clear()
                continue
            if state.mode == 'estimado':
                why = 'Posicao nao confirmada: selecione o turno ou informe um FEN completo.'
                if why != last_idle:
                    state.ui_events.put(('engine', why))
                    last_idle = why
                state.wakeup.wait(0.5)
                state.wakeup.clear()
                continue
            last_idle = None
            try:
                if engine is None or path != executable:
                    if engine:
                        engine.quit()
                    engine = chess.engine.SimpleEngine.popen_uci(executable, timeout=15)
                    path, last_opts = executable, None
                    state.ui_events.put(('engine',f'Motor ativo: {engine.id.get("name", "Stockfish")}'))
                opts = {
                    'Threads':max(1,min(64,int(config.get('threads',2)))),
                    'Hash':max(16,min(4096,int(config.get('hash',128))))
                }
                if opts != last_opts:
                    engine.configure({k:v for k,v in opts.items() if k in engine.options})
                    last_opts = opts
                depth = max(1, min(99, int(config.get('depth',40))))
                seconds = max(0, min(86400, int(config.get('seconds',15))))
                multi = max(1, min(5, int(config.get('multipv',3))))
                if board.is_game_over(claim_draw=True):
                    state.ui_events.put(('engine',f'Partida finalizada: {board.result(claim_draw=True)}'))
                    state.wakeup.wait(0.5)
                    state.wakeup.clear()
                    continue
                state.ui_events.put(('engine',f'Analisando: limite depth {depth} | {seconds}s' if seconds else f'Analisando: depth {depth} sem limite de tempo'))
                state.ui_events.put(('clear',revision))
                limit = chess.engine.Limit(depth=depth, time=seconds if seconds else None)
                lines = {}
                last_report = 0.0
                with engine.analysis(board, limit, multipv=multi, info=chess.engine.INFO_ALL) as analysis:
                    for info in analysis:
                        with state.lock:
                            stale = state.shutdown.is_set() or revision != state.revision
                        if stale:
                            analysis.stop()
                            break
                        pv = info.get('pv',[])
                        if not pv:
                            continue
                        rank = int(info.get('multipv',1))
                        if rank < 1 or rank > multi:
                            continue
                        try:
                            san = board.variation_san(pv[:60])
                            first = board.san(pv[0])
                        except (ValueError, AssertionError):
                            continue
                        lines[rank] = {'rank':rank, 'depth':int(info.get('depth',0)),
                                       'seldepth':int(info.get('seldepth',0)),
                                       'score':score_label(info.get('score')),
                                       'san':san, 'first':first,
                                       'uci':pv[0].uci(), 'nodes':int(info.get('nodes',0))}
                        now = time.monotonic()
                        if now - last_report >= 0.15:
                            state.ui_events.put(('lines',revision,board.fen(),[lines[n] for n in sorted(lines)]))
                            last_report = now
                if lines:
                    state.ui_events.put(('lines',revision,board.fen(),[lines[n] for n in sorted(lines)]))
            except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError,
                    ValueError, TimeoutError) as exc:
                state.ui_events.put(('error',f'Falha no motor: {exc}'))
                if engine:
                    try: engine.quit()
                    except Exception: pass
                engine, path, last_opts = None, None, None
                last_idle = None
                state.wakeup.wait(1.0)
                state.wakeup.clear()
            # Wait until position or configuration changes; no redundant analysis.
            while not state.shutdown.is_set():
                with state.lock:
                    if revision != state.revision:
                        break
                state.wakeup.wait(0.4)
                state.wakeup.clear()
    finally:
        if engine:
            try: engine.quit()
            except Exception: pass


class ChessVisionUI:
    CELL = 55
    def __init__(self, root, state):
        self.root, self.state = root, state
        self.board = chess.Board()
        self.best_uci = None
        self.lines = []
        self.cycle_rank = 1
        self.cycle_at = time.monotonic()
        self.board_only = False
        self.normal_geometry = '1030x730'
        self.normal_minsize = (850, 630)
        self.config = state.config
        root.title('ChessVision Lab • Stockfish 19')
        root.geometry('1030x730')
        root.minsize(850,630)
        root.configure(bg='#111723')
        root.protocol('WM_DELETE_WINDOW',self.close)

        style = ttk.Style()
        try:style.theme_use('clam')
        except tk.TclError:pass
        style.configure('TFrame',background='#111723')
        style.configure('TLabel',background='#111723', foreground='#edf2fb', font=('Segoe UI',10))
        style.configure('H1.TLabel',background='#111723',foreground='#fbfbfc',font=('Segoe UI',19,'bold'))
        style.configure('Hint.TLabel',background='#111723',foreground='#a8b6ca',font=('Segoe UI',9))
        style.configure('TButton',font=('Segoe UI',10))
        style.configure('TCheckbutton',background='#111723',foreground='#edf2fb')

        self.full_view=ttk.Frame(root)
        self.full_view.pack(fill='both',expand=True)
        header=ttk.Frame(self.full_view)
        header.pack(fill='x',padx=22,pady=(16,10))
        ttk.Label(header,text='♞  ChessVision Lab',style='H1.TLabel').pack(side='left')
        ttk.Label(header,text='ANÁLISE LOCAL • UCI • NNUE',style='Hint.TLabel').pack(side='right')
        self.status=StringVar(value='Aguardando tabuleiro do navegador…')
        ttk.Label(self.full_view,textvariable=self.status).pack(anchor='w',padx=25)
        content=ttk.Frame(self.full_view)
        content.pack(fill='both', expand=True,padx=20,pady=12)
        left=ttk.Frame(content)
        left.pack(side='left',fill='y')
        self.canvas=Canvas(left,width=self.CELL*8,height=self.CELL*8,bg='#242d3c',highlightthickness=0)
        self.canvas.pack()
        ttk.Label(left,text='O leitor acompanha a posição; nunca executa lances.',style='Hint.TLabel').pack(anchor='w',pady=7)
        self.fenvar=StringVar(value=chess.STARTING_FEN)
        fenframe=ttk.Frame(left)
        fenframe.pack(fill='x',pady=(9,0))
        ttk.Label(fenframe,text='FEN').pack(side='left')
        ttk.Entry(fenframe,textvariable=self.fenvar,width=48).pack(side='left',padx=7,fill='x',expand=True)
        ttk.Button(left,text='Analisar FEN digitado',command=self.manual_fen).pack(anchor='w',pady=7)

        right=ttk.Frame(content)
        right.pack(side='left',fill='both',expand=True,padx=(20,0))
        self.enginevar=StringVar(value='Stockfish não iniciado')
        self.sourcevar=StringVar(value='Origem: aguardando extensão…')
        self.warningvar=StringVar(value='')
        ttk.Label(right,textvariable=self.enginevar,wraplength=470).pack(anchor='w',pady=(0,6))
        ttk.Label(right,textvariable=self.sourcevar,style='Hint.TLabel',wraplength=470).pack(anchor='w')
        ttk.Label(right,textvariable=self.warningvar,style='Hint.TLabel',wraplength=470).pack(anchor='w',pady=6)
        self.moves_text=Text(right,bg='#192233',fg='#e9eff8',insertbackground='white',
            wrap='word',font=('Consolas',11),borderwidth=0,padx=12,pady=12,height=12)
        self.moves_text.pack(fill='both',expand=True,pady=(8,9))
        self.moves_text.insert('1.0','As 3 melhores variantes aparecerão aqui.\n\n'+
            'Abra o Chrome ou Edge no Chess.com com a extensão instalada.\n'+
            'O programa recebe as posições automaticamente, sem serviços em nuvem.')
        self.moves_text.configure(state='disabled')

        controls=ttk.Frame(right)
        controls.pack(fill='x')
        self.pathvar=StringVar(value=self.config['stockfish'])
        ttk.Label(controls,text='Stockfish.exe').grid(row=0,column=0,sticky='w',pady=4)
        ttk.Entry(controls,textvariable=self.pathvar,width=38).grid(row=0,column=1,columnspan=4,sticky='ew',padx=5)
        ttk.Button(controls,text='Escolher',command=self.choose_stockfish).grid(row=0,column=5)
        self.depthvar=IntVar(value=self.config['depth'])
        self.secondsvar=IntVar(value=self.config['seconds'])
        self.threadsvar=IntVar(value=self.config['threads'])
        self.hashvar=IntVar(value=self.config['hash'])
        controls.columnconfigure(1,weight=1)
        for col,(label,var,lo,hi) in enumerate((('Depth',self.depthvar,1,99),
                                               ('Tempo (s)',self.secondsvar,0,86400),
                                               ('CPU threads',self.threadsvar,1,64),
                                               ('Hash MB',self.hashvar,16,4096))):
            ttk.Label(controls,text=label).grid(row=1,column=col+1,sticky='w',pady=(10,3))
            tk.Spinbox(controls,from_=lo,to=hi,textvariable=var,width=8).grid(row=2,column=col+1,sticky='w')
        ttk.Button(controls,text='Aplicar e reanalisar',command=self.apply).grid(row=3,column=1,columnspan=3,sticky='w',pady=(12,2))
        ttk.Button(controls,text='Reanalisar',command=self.reanalyse).grid(row=3,column=4,columnspan=2,sticky='e',pady=(12,2))
        row=ttk.Frame(right)
        row.pack(fill='x',pady=10)
        self.ontop=BooleanVar(value=bool(self.config.get('always_on_top')))
        ttk.Checkbutton(row,text='Sempre visível',variable=self.ontop,command=self.set_on_top).pack(side='left')
        ttk.Button(row,text='Vez: brancas',command=lambda:self.change_turn('w')).pack(side='left',padx=6)
        ttk.Button(row,text='Vez: pretas',command=lambda:self.change_turn('b')).pack(side='left')

        display=ttk.Frame(right)
        display.pack(fill='x',pady=(0,8))
        ttk.Label(display,text='Mostrar:').pack(side='left',padx=(0,5))
        initial_mode=self.config.get('display_mode','all')
        if initial_mode not in DISPLAY_LABELS:initial_mode='all'
        self.display_key=StringVar(value=initial_mode)
        self.display_label=StringVar(value=DISPLAY_LABELS[initial_mode])
        self.display_combo=ttk.Combobox(display,textvariable=self.display_label,
            values=list(DISPLAY_LABELS.values()),state='readonly',width=24)
        self.display_combo.pack(side='left',fill='x',expand=True,padx=(0,7))
        self.display_combo.bind('<<ComboboxSelected>>',self.on_display_selected)
        ttk.Button(display,text='◧  Só tabuleiro (F11)',command=lambda:self.set_board_only(True)).pack(side='left')

        self.compact_view=ttk.Frame(root)
        self.compact_canvas=Canvas(self.compact_view,width=self.CELL*8,height=self.CELL*8,
                                  bg='#242d3c',highlightthickness=0)
        self.compact_canvas.pack(fill='both',expand=True)
        self.compact_canvas.bind('<Button-3>',self.show_compact_menu)
        self.compact_canvas.bind('<Double-Button-1>',lambda _:self.set_board_only(False))
        self.compact_menu=tk.Menu(root,tearoff=False)
        for key,label in DISPLAY_LABELS.items():
            self.compact_menu.add_radiobutton(label=label,variable=self.display_key,
                value=key,command=self.change_display_mode)
        self.compact_menu.add_separator()
        self.compact_menu.add_checkbutton(label='Sempre visível',variable=self.ontop,
                                         command=self.set_on_top)
        self.compact_menu.add_command(label='Voltar ao painel (Esc / F11)',
                                      command=lambda:self.set_board_only(False))
        self.root.bind('<F11>',lambda _:self.set_board_only(not self.board_only))
        self.root.bind('<Escape>',lambda _:self.set_board_only(False) if self.board_only else None)
        self.root.bind('<KeyPress>',self.on_compact_key)
        self.root.attributes('-topmost',self.ontop.get())
        if self.config.get('board_only'):
            self.set_board_only(True,remember=False)
        self.draw_board()
        self.poll()

    def set_text(self, text):
        self.moves_text.configure(state='normal')
        self.moves_text.delete('1.0',END)
        self.moves_text.insert('1.0',text)
        self.moves_text.configure(state='disabled')

    def refresh_variation(self):
        mode=self.display_key.get()
        chosen=selected_line(self.lines,mode,self.cycle_rank)
        if mode=='alternate' and chosen:
            self.cycle_rank=chosen['rank']
        self.best_uci=chosen['uci'] if chosen else None

        visible=self.lines if mode=='all' else ([chosen] if chosen else [])
        if visible:
            out=[]
            for item in visible:
                out.append(f'{item["rank"]}º MELHOR LANCE: {item["first"]}    Avaliação: {item["score"]}')
                out.append(f'Profundidade {item["depth"]} • seletiva {item["seldepth"]}')
                out.append(item['san'])
                out.append('')
            self.set_text('\n'.join(out))
        elif mode in ('second','third') and self.lines:
            rank=2 if mode=='second' else 3
            self.set_text(f'Aguardando a {rank}ª variante desta posição…')
        else:
            self.set_text('Calculando variantes…')

        if chosen:
            description=f'{chosen["rank"]}ª melhor: {chosen["first"]} ({chosen["score"]})'
        elif mode in ('second','third'):
            description=f'Aguardando {2 if mode=="second" else 3}ª variante'
        else:
            description='Aguardando análise'
        self.root.title(('ChessVision Lab • Tabuleiro • ' if self.board_only else
                         'ChessVision Lab • Stockfish 19 • ') + description)
        self.draw_board()

    def draw_board(self):
        c = self.compact_canvas if self.board_only else self.canvas
        c.delete('all')
        size = self.CELL
        rotate = self.state.orientation == 'black'
        for row in range(8):
            for col in range(8):
                file = 7-col if rotate else col
                rank = row if rotate else 7-row
                square=chess.square(file,rank)
                x,y=col*size,row*size
                light=(file+rank)%2 != 0
                color='#e8d7ba' if light else '#8098ad'
                c.create_rectangle(x,y,x+size,y+size,fill=color,outline=color)
                if row==7:
                    c.create_text(x+6,y+size-7,anchor='sw',text=chess.FILE_NAMES[file],fill='#293244',font=('Segoe UI',8))
                if col==0:
                    c.create_text(x+5,y+5,anchor='nw',text=str(rank+1),fill='#293244',font=('Segoe UI',8))
                piece=self.board.piece_at(square)
                if piece:
                    sym=PIECE_GLYPHS[piece.symbol()]
                    ink='#fcfcfa' if piece.color else '#161c27'
                    c.create_text(x+size/2,y+size/2, text=sym, font=('Segoe UI Symbol',36),
                                  fill=ink)
        if self.best_uci:
            try:
                move=chess.Move.from_uci(self.best_uci)
                def center(sq):
                    file, rank=chess.square_file(sq),chess.square_rank(sq)
                    return ((7-file if rotate else file)*size+size/2,
                            (rank if rotate else 7-rank)*size+size/2)
                sx,sy=center(move.from_square)
                ex,ey=center(move.to_square)
                c.create_line(sx,sy,ex,ey,fill='#25d3a5',width=6,arrow='last',arrowshape=(15,19,7))
            except ValueError:pass

    def poll(self):
        for _ in range(80):
            try: event=self.state.ui_events.get_nowait()
            except queue.Empty:break
            what=event[0]
            if what=='board':
                _,board,mode,warning=event
                self.board=board
                self.lines=[]
                self.cycle_rank=1
                self.cycle_at=time.monotonic()
                self.fenvar.set(board.fen())
                self.warningvar.set(f'Leitura: {mode}. {warning}')
                self.status.set(f'Posição reconhecida • {"brancas" if board.turn else "pretas"} jogam')
                self.refresh_variation()
            elif what=='connection':
                self.sourcevar.set('Chess.com: '+event[1])
                self.draw_board()
            elif what=='engine':self.enginevar.set(event[1])
            elif what=='server':self.status.set(event[1])
            elif what=='error':self.enginevar.set('Aviso: '+event[1])
            elif what=='clear':
                if event[1]==self.state.revision:
                    self.lines=[]
                    self.refresh_variation()
            elif what=='lines':
                _,rev,fen,lines=event
                if rev!=self.state.revision or fen != self.board.fen():continue
                self.lines=lines
                self.refresh_variation()
        if self.display_key.get()=='alternate' and time.monotonic()-self.cycle_at>=CYCLE_SECONDS:
            self.cycle_at=time.monotonic()
            next_rank=next_cycle_rank(self.lines,self.cycle_rank)
            if next_rank!=self.cycle_rank:
                self.cycle_rank=next_rank
                self.refresh_variation()
        # A visible connection indicator must not stay green after closing the tab.
        with self.state.lock:
            last = self.state.connected_at
            source = self.state.source
        if source and source != 'Entrada manual':
            age = time.monotonic() - last
            if age > 8:
                self.sourcevar.set('Extensao sem comunicacao recente (verifique a aba e o navegador).')
        self.root.after(100,self.poll)

    def choose_stockfish(self):
        path=filedialog.askopenfilename(title='Selecione stockfish.exe',filetypes=[('Executáveis','*.exe'),('Todos','*.*')])
        if path:self.pathvar.set(path)

    def apply(self):
        try:
            data = {**self.state.config, 'stockfish':self.pathvar.get().strip(),
                    'depth':int(self.depthvar.get()), 'seconds':int(self.secondsvar.get()),
                    'threads':int(self.threadsvar.get()), 'hash':int(self.hashvar.get()),
                    'multipv':3, 'always_on_top':self.ontop.get()}
            if not 1 <= data['depth'] <= 99 or not 0 <= data['seconds'] <= 86400:
                raise ValueError('Depth ou tempo fora dos limites')
            if not data['stockfish'] or not Path(data['stockfish']).is_file():
                raise ValueError('Selecione o executável do Stockfish 19')
            self.state.change_config(data)
            self.enginevar.set('Carregando Stockfish…')
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror('Configuração',str(exc))

    def reanalyse(self):
        with self.state.lock:
            self.state.revision+=1
            self.state.wakeup.set()

    def change_turn(self,color):
        try:self.state.force_turn(color)
        except ValueError as exc:messagebox.showerror('Turno',str(exc))

    def manual_fen(self):
        try:self.state.set_fen(self.fenvar.get().strip())
        except ValueError as exc:messagebox.showerror('FEN inválido',str(exc))

    def set_on_top(self):
        self.root.attributes('-topmost',self.ontop.get())
        self.state.update_view_settings(always_on_top=self.ontop.get())

    def on_display_selected(self, _event):
        label=self.display_label.get()
        mode=next((key for key,value in DISPLAY_LABELS.items() if value==label),'all')
        self.display_key.set(mode)
        self.change_display_mode()

    def change_display_mode(self):
        mode=self.display_key.get()
        self.display_label.set(DISPLAY_LABELS[mode])
        self.cycle_rank=1
        self.cycle_at=time.monotonic()
        self.state.update_view_settings(display_mode=mode)
        self.refresh_variation()

    def on_compact_key(self, event):
        if not self.board_only:return
        mode={'1':'first','2':'second','3':'third','a':'alternate','t':'all'}.get(event.keysym.lower())
        if mode:
            self.display_key.set(mode)
            self.change_display_mode()
            return 'break'

    def show_compact_menu(self, event):
        try:self.compact_menu.tk_popup(event.x_root,event.y_root)
        finally:self.compact_menu.grab_release()

    def set_board_only(self, enabled, remember=True):
        if enabled==self.board_only:return
        if enabled:
            self.normal_geometry=self.root.geometry()
            self.normal_minsize=self.root.minsize()
            self.normal_maxsize=self.root.maxsize()
            self.full_view.pack_forget()
            self.compact_view.pack(fill='both',expand=True)
            size=self.CELL*8
            self.root.minsize(size,size)
            self.root.maxsize(size,size)
            self.root.geometry(f'{size}x{size}')
            self.compact_canvas.focus_set()
        else:
            self.compact_view.pack_forget()
            self.full_view.pack(fill='both',expand=True)
            self.root.maxsize(*self.normal_maxsize)
            self.root.minsize(*self.normal_minsize)
            self.root.geometry(self.normal_geometry)
        self.board_only=enabled
        if remember:self.state.update_view_settings(board_only=enabled)
        self.refresh_variation()

    def close(self):
        self.state.shutdown.set()
        self.state.wakeup.set()
        self.root.destroy()


def main():
    # Validate Tcl/Tk before starting the analysis threads and local bridge.
    # Importing tkinter alone does not check for init.tcl or tk.tcl.
    try:
        root = Tk()
    except tk.TclError as exc:
        details = (
            'Falha ao abrir a interface do ChessVision Lab.\n\n'
            'O Python nao encontrou o Tcl/Tk necessario (init.tcl / tk.tcl).\n'
            'Execute o instalador ChessVision Lab 2.1 para criar um Python local valido.\n'
            'Nao e preciso desinstalar seu Python atual.\n\n'
            f'Python: {sys.executable}\nBase: {sys.base_prefix}\nErro: {exc}\n'
        )
        try:
            (BASE / 'erro_interface_tkinter.txt').write_text(details, encoding='utf-8')
        except OSError:
            pass
        print(details, file=sys.stderr)
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, details, 'ChessVision Lab - Tcl/Tk', 0x10)
            except (AttributeError, OSError):
                pass
        raise SystemExit(2)
    state=AnalysisState()
    threading.Thread(target=serve_local,args=(state,),daemon=True).start()
    threading.Thread(target=engine_worker,args=(state,),daemon=True).start()
    ChessVisionUI(root,state)
    root.mainloop()


if __name__=='__main__':main()

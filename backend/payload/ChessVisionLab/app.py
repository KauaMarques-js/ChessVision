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
from variation_view import DISPLAY_LABELS, RANK_MODES, CYCLE_SECONDS, selected_line, next_cycle_rank

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
                'threads':2, 'hash':128, 'multipv':5, 'always_on_top':False,
                'display_mode':'first', 'board_only':False, 'capture_mode':'automatic',
                'human_enabled':False, 'human_skill':12, 'auto_recover':True,
                'auto_start_search':True}
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
        self.screen_active = False
        self.screen_paused = False
        self.pending_screen = None

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
            if self.screen_active and source != 'Captura de tela':
                return {'ok': True, 'mode': 'Captura de tela ativa; extensão ignorada'}
            tracker=self.tracker
            if source=='Captura de tela' and tracker.board is not None:
                candidate=BoardTracker()
                candidate.board=tracker.board.copy(stack=True)
                candidate.mode,candidate.warning=tracker.mode,tracker.warning
                result=candidate.update(placement,moves,turn=turn)
                if result.mode=='estimado' and tracker.mode!='estimado':
                    self.pending_screen=placement
                    warning='Posição ainda incompatível com o histórico. Aguarde; se perdeu vários lances, confirme o turno em Leitura.'
                    self.pause_screen(warning)
                    return {'ok':False,'mode':'aguardando leitura','error':warning}
                self.tracker=candidate
            else:result=tracker.update(placement,moves,turn=turn)
            self.pending_screen=None
            self.connected_at = time.monotonic()
            self.source = source
            self.orientation = orientation if orientation in ('white', 'black') else 'white'
            self.warning = result.warning
            self.mode = result.mode
            if result.changed or self.board is None or self.screen_paused:
                self.board = result.board
                self.screen_paused = False
                self.revision += 1
                self.wakeup.set()
                self.ui_events.put(('board', self.board.copy(), self.mode, self.warning))
            self.last_payload = time.time()
            self.ui_events.put(('connection', self.source, self.orientation))
        return {'ok':True, 'mode':result.mode}

    def pause_screen(self, warning):
        with self.lock:
            if not self.screen_active:
                return
            self.warning = warning
            if self.screen_paused:return
            self.screen_paused = True
            self.mode = 'captura pausada'
            self.revision += 1
            self.wakeup.set()
            self.ui_events.put(('clear', self.revision))
            self.ui_events.put(('engine', warning))

    def set_fen(self, fen):
        b = chess.Board(fen)
        if not b.is_valid():
            raise ValueError('Posicao FEN invalida')
        with self.lock:
            self.tracker = BoardTracker()
            self.pending_screen=None
            self.tracker.board = b.copy()
            self.tracker.mode = 'FEN manual'
            self.board = b
            self.screen_paused=False
            self.mode, self.warning = 'FEN manual', ''
            self.source = 'Entrada manual'
            self.revision += 1
            self.wakeup.set()
            self.ui_events.put(('board', b.copy(), self.mode, self.warning))

    def force_turn(self, color):
        with self.lock:
            tracker=self.tracker
            if self.pending_screen is not None:
                candidate=BoardTracker()
                candidate.update(self.pending_screen,turn=color)
                tracker=candidate
            b = tracker.force_turn(color)
            if b:
                self.tracker=tracker
                self.pending_screen=None
                self.board = b
                self.screen_paused=False
                self.mode = self.tracker.mode
                self.warning = self.tracker.warning
                self.revision += 1
                self.wakeup.set()
                self.ui_events.put(('board', b.copy(), self.mode, self.warning))

    def preview_screen_position(self,placement):
        with self.lock:
            candidate=BoardTracker()
            if self.tracker.board is not None:
                candidate.board=self.tracker.board.copy(stack=True)
                candidate.mode,candidate.warning=self.tracker.mode,self.tracker.warning
            return candidate.update(placement)

    def confirm_screen_position(self,placement,turn,orientation,castling='-'):
        snapshot=self.preview_screen_position(placement)
        board=snapshot.board
        if snapshot.mode=='estimado':
            if turn not in ('w','b'):raise ValueError('Confirme de quem é a vez.')
            if castling!='-' and (not castling or any(c not in 'KQkq' for c in castling) or len(set(castling))!=len(castling)):
                raise ValueError('Direitos de roque inválidos.')
            board=chess.Board(f'{placement} {turn} {castling} - 0 1')
            if not board.is_valid():raise ValueError('A vez ou os direitos de roque não combinam com as peças lidas.')
            mode='tela confirmada'
            warning='Posição confirmada sem histórico completo; roques conforme confirmação, en passant e repetições não recuperados.'
        else:mode,warning=snapshot.mode,snapshot.warning
        with self.lock:
            self.tracker=BoardTracker()
            self.tracker.board=board.copy(stack=True)
            self.tracker.mode,self.tracker.warning=mode,warning
            self.board=board
            self.mode,self.warning=mode,warning
            self.orientation=orientation
            self.source='Captura de tela'
            self.connected_at=time.monotonic()
            self.last_payload=time.time()
            self.pending_screen=None
            self.screen_active=True
            self.screen_paused=False
            self.revision+=1
            self.wakeup.set()
            self.ui_events.put(('board',board.copy(stack=True),mode,warning))
            self.ui_events.put(('connection',self.source,orientation))


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
                warning = self.state.warning
                capture_running = self.state.screen_active
            self._send(200, {'ok':True, 'app':'ChessVision Lab', 'version':'1.1.0',
                             'board_ready':ready, 'mode':mode, 'source':source,
                             'last_payload':last_seen,'warning':warning,
                             'capture_running':capture_running})
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
            if state.mode in ('estimado', 'captura pausada'):
                why = ('Leitura ativa; aguardando imagem legível para analisar.' if state.mode == 'captura pausada'
                       else 'Posicao nao confirmada: selecione o turno ou informe um FEN completo.')
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
                human=bool(config.get('human_enabled',False))
                skill=int(config.get('human_skill',12))
                if human and not 0 <= skill <= 19:
                    raise ValueError('Nível humanizado deve estar entre 0 e 19')
                if human and 'Skill Level' not in engine.options:
                    raise ValueError('Este motor não oferece controle de força. Selecione o Stockfish 19.')
                opts.update({'Skill Level':skill if human else 20, 'UCI_LimitStrength':False})
                if opts != last_opts:
                    engine.configure({k:v for k,v in opts.items() if k in engine.options})
                    last_opts = opts
                depth = max(1, min(99, int(config.get('depth',40))))
                seconds = max(0, min(86400, int(config.get('seconds',15))))
                if human:seconds=min(seconds or 2,2)
                multi = 5
                if board.is_game_over(claim_draw=True):
                    state.ui_events.put(('engine',f'Partida finalizada: {board.result(claim_draw=True)}'))
                    state.wakeup.wait(0.5)
                    state.wakeup.clear()
                    continue
                profile=f'Humanizado • nível {skill}/19 • ' if human else 'Análise máxima • '
                state.ui_events.put(('engine',profile+(f'limite depth {depth} | {seconds}s' if seconds else f'depth {depth} sem limite de tempo')))
                state.ui_events.put(('clear',revision))
                limit = chess.engine.Limit(depth=depth, time=seconds if seconds else None)
                lines = {}
                last_report = 0.0
                selected_move=None
                stale=False
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
                    if human and not stale:
                        selected_move=analysis.wait().move
                if lines:
                    state.ui_events.put(('lines',revision,board.fen(),[lines[n] for n in sorted(lines)]))
                if human and selected_move:
                    if selected_move not in board.legal_moves:
                        raise ValueError('O motor retornou uma sugestão ilegal')
                    chosen=next((item.copy() for item in lines.values()
                                 if item['uci']==selected_move.uci()),None)
                    if chosen is None:
                        # A move picked at an earlier depth may leave the final
                        # top five. Do not invent a score or continuation.
                        chosen={'rank':None,'uci':selected_move.uci(),'first':board.san(selected_move),
                                'score':'—','depth':0,'seldepth':0,
                                'san':board.variation_san([selected_move])}
                    chosen['skill']=skill
                    state.ui_events.put(('human_line',revision,board.fen(),chosen))
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
    COMPACT_HEIGHT = 510
    def __init__(self, root, state):
        self.root, self.state = root, state
        self.board = chess.Board()
        self.best_uci = None
        self.lines = []
        self.human_line = None
        self.cycle_rank = 1
        self.cycle_at = time.monotonic()
        self.board_only = False
        self.screen_stop = threading.Event()
        self.screen_thread = None
        self.capture_generation = 0
        self.locating_screen = False
        self.screen_reader = None
        self.screen_bbox = None
        self.screen_dialog = None
        self.poll_job = None
        self.search_stop = threading.Event()
        self.search_active = False
        self.search_exclusions = []
        self.auto_search_job = None
        self.normal_geometry = '880x550'
        self.normal_minsize = (850, 530)
        self.config = state.config
        from screen_reader import ScreenBoardReader
        from reader_profiles import ReaderProfiles
        self.reader_profiles=ReaderProfiles(CONFIG.with_name('reader_profiles'))
        try:
            self.screen_reader=ScreenBoardReader.load(CONFIG.with_name('.reader_templates.json'))
            self.reader_cache_message=f'Perfil {self.screen_reader.profile_name} disponível para retomar a partida.'
            try:self.reader_profiles.save(self.screen_reader)
            except OSError:self.reader_cache_message+=' Não foi possível copiar para a biblioteca de perfis.'
        except (OSError,ValueError,TypeError,KeyError):
            self.reader_cache_message='Use Ensinar tema na conferência para cadastrar as peças, ou calibre na posição inicial.'
            ready=self.reader_profiles.ready()
            if ready:
                self.screen_reader=ready[0]
                self.reader_cache_message=f'Perfil {ready[0].profile_name} pronto. Outros estilos podem ser ensinados e ficam salvos.'
        if self.screen_reader is not None:
            try:
                self.state.tracker.board=self.reader_profiles.load_game(self.screen_reader)
                self.state.tracker.mode='histórico local'
                self.reader_cache_message+=' Histórico disponível; confira o jogo antes de continuar.'
            except (OSError,ValueError,TypeError,KeyError,AttributeError):pass
        root.title('ChessVision Lab • Stockfish 19')
        root.geometry(self.normal_geometry)
        root.minsize(*self.normal_minsize)
        root.configure(bg='#111723')
        root.protocol('WM_DELETE_WINDOW',self.close)

        style = ttk.Style()
        try:style.theme_use('clam')
        except tk.TclError:pass
        style.configure('TFrame',background='#111723')
        style.configure('TLabel',background='#111723', foreground='#edf2fb', font=('Segoe UI',9))
        style.configure('H1.TLabel',background='#111723',foreground='#fbfbfc',font=('Segoe UI',14,'bold'))
        style.configure('Hint.TLabel',background='#111723',foreground='#a8b6ca',font=('Segoe UI',9))
        style.configure('TButton',font=('Segoe UI',9),padding=(5,2))
        style.configure('TMenubutton',font=('Segoe UI',9),padding=(4,2))
        style.configure('TNotebook',background='#111723',borderwidth=0)
        style.configure('TNotebook.Tab',padding=(8,4),font=('Segoe UI',9))
        style.configure('TCheckbutton',background='#111723',foreground='#edf2fb')
        style.configure('TRadiobutton',background='#192233',foreground='#edf2fb',
                        font=('Segoe UI',9),padding=(4,2))
        style.map('TRadiobutton',background=[('selected','#255b57'),('active','#243448')],
                  foreground=[('selected','#ffffff'),('active','#ffffff')])

        self.full_view=ttk.Frame(root)
        self.full_view.pack(fill='both',expand=True)
        header=ttk.Frame(self.full_view)
        header.pack(fill='x',padx=10,pady=(6,2))
        ttk.Label(header,text='♞ ChessVision Lab',style='H1.TLabel').pack(side='left')
        ttk.Button(header,text='F11 · compacto',command=lambda:self.set_board_only(True)).pack(side='right')
        self.status=StringVar(value='Escolha Leitura, extensão ou FEN para começar.')
        ttk.Label(self.full_view,textvariable=self.status).pack(anchor='w',padx=10)
        content=ttk.Frame(self.full_view)
        content.pack(fill='both',expand=True,padx=10,pady=5)
        left=ttk.Frame(content)
        left.pack(side='left',fill='y')
        self.canvas=Canvas(left,width=self.CELL*8,height=self.CELL*8,bg='#242d3c',highlightthickness=0)
        self.canvas.pack()
        ttk.Label(left,text='Tabuleiro de análise · 440 × 440',style='Hint.TLabel').pack(anchor='w',pady=3)
        self.tabs=ttk.Notebook(content,width=380)
        self.tabs.pack(side='left',fill='both',expand=True,padx=(10,0))
        analysis_tab=ttk.Frame(self.tabs,padding=6)
        self.reading_tab=ttk.Frame(self.tabs,padding=8)
        settings=ttk.Frame(self.tabs,padding=8)
        self.tabs.add(analysis_tab,text='Análise')
        self.tabs.add(self.reading_tab,text='Leitura')
        self.tabs.add(settings,text='Ajustes')
        self.enginevar=StringVar(value='Aguardando posição…')
        self.sourcevar=StringVar(value='Origem: aguardando posição…')
        self.warningvar=StringVar(value='')
        ttk.Label(analysis_tab,textvariable=self.enginevar,wraplength=360).pack(anchor='w')
        profilebar=ttk.Frame(analysis_tab)
        profilebar.pack(fill='x',pady=5)
        self.profile_label=StringVar(value='Humanizado (treino)' if self.config.get('human_enabled') else 'Análise máxima')
        self.human_skill=IntVar(value=self.config.get('human_skill',12))
        profile_combo=ttk.Combobox(profilebar,textvariable=self.profile_label,state='readonly',width=18,
                                  values=['Análise máxima','Humanizado (treino)'])
        profile_combo.pack(side='left')
        profile_combo.bind('<<ComboboxSelected>>',lambda _:self.apply_profile())
        ttk.Label(profilebar,text=' Nível').pack(side='left')
        tk.Spinbox(profilebar,from_=0,to=19,textvariable=self.human_skill,width=3).pack(side='left',padx=3)
        ttk.Button(profilebar,text='Aplicar',command=self.apply_profile).pack(side='left')
        moves_frame=ttk.Frame(analysis_tab)
        moves_frame.pack(fill='both',expand=True,pady=3)
        self.moves_text=Text(moves_frame,bg='#192233',fg='#e9eff8',insertbackground='white',wrap='word',
                             font=('Consolas',10),borderwidth=0,padx=8,pady=8,height=10,width=32)
        moves_scroll=ttk.Scrollbar(moves_frame,orient='vertical',command=self.moves_text.yview)
        moves_scroll.pack(side='right',fill='y')
        self.moves_text.configure(yscrollcommand=moves_scroll.set)
        self.moves_text.pack(side='left',fill='both',expand=True)
        self.moves_text.insert('1.0','As sugestões aparecerão aqui.\n\nLeitura: selecione a área do tabuleiro.\nAjustes: motor e FEN manual.\n\nF11 mantém o tabuleiro e reduz os controles.')
        self.moves_text.configure(state='disabled')
        display=ttk.Frame(analysis_tab)
        display.pack(fill='x',pady=(4,0))
        initial_mode=self.config.get('display_mode','first')
        if initial_mode not in DISPLAY_LABELS:initial_mode='first'
        self.display_key=StringVar(value=initial_mode)
        self.display_label=StringVar(value=DISPLAY_LABELS[initial_mode])
        self.display_combo=ttk.Combobox(display,textvariable=self.display_label,
            values=list(DISPLAY_LABELS.values()),state='readonly',width=22)
        self.display_combo.pack(side='left',fill='x',expand=True)
        self.display_combo.bind('<<ComboboxSelected>>',self.on_display_selected)
        ttk.Button(display,text='Recalcular',command=self.reanalyse).pack(side='left',padx=(4,0))
        ttk.Label(self.reading_tab,text='Captura do tabuleiro',font=('Segoe UI',10,'bold')).pack(anchor='w')
        ttk.Label(self.reading_tab,text='Automático: procura o jogo em segundo plano e pede sua confirmação antes de analisar.',
                  style='Hint.TLabel',wraplength=350).pack(anchor='w',pady=(3,8))
        self.screen_orientation=StringVar(value='Pretas embaixo' if self.screen_reader and self.screen_reader.orientation=='black' else 'Brancas embaixo')
        ttk.Combobox(self.reading_tab,textvariable=self.screen_orientation,state='readonly',width=22,
                     values=['Brancas embaixo','Pretas embaixo']).pack(anchor='w',pady=2)
        self.capture_mode=StringVar(value='Automático' if self.config.get('capture_mode')=='automatic' else 'Manual')
        capture_combo=ttk.Combobox(self.reading_tab,textvariable=self.capture_mode,state='readonly',width=22,
                                  values=['Manual','Automático'])
        capture_combo.pack(anchor='w',pady=2)
        capture_combo.bind('<<ComboboxSelected>>',lambda _:self.state.update_view_settings(
            capture_mode='automatic' if self.capture_mode.get()=='Automático' else 'manual'))
        self.auto_recover=BooleanVar(value=self.config.get('auto_recover',True))
        self.auto_start_search=BooleanVar(value=self.config.get('auto_start_search',True))
        ttk.Checkbutton(self.reading_tab,text='Reencontrar ao perder a área',variable=self.auto_recover,
            command=lambda:self.state.update_view_settings(auto_recover=self.auto_recover.get())).pack(anchor='w',pady=2)
        ttk.Checkbutton(self.reading_tab,text='Procurar jogo ao abrir o programa',variable=self.auto_start_search,
            command=lambda:self.state.update_view_settings(auto_start_search=self.auto_start_search.get())).pack(anchor='w')
        self.cache_status=StringVar(value=self.reader_cache_message)
        ttk.Label(self.reading_tab,textvariable=self.cache_status,style='Hint.TLabel',wraplength=350).pack(anchor='w',pady=3)
        actions=ttk.Frame(self.reading_tab)
        actions.pack(fill='x',pady=8)
        ttk.Button(actions,text='Iniciar',command=self.select_screen_board).pack(side='left')
        ttk.Button(actions,text='Tentar novamente',command=self.retry_screen).pack(side='left',padx=4)
        ttk.Button(actions,text='Parar',command=self.stop_screen).pack(side='left')
        profiles_row=ttk.Frame(self.reading_tab);profiles_row.pack(fill='x')
        ttk.Button(profiles_row,text='Cadastro de peças',command=lambda:self.teach_piece_profile(
            None,'black' if self.screen_orientation.get()=='Pretas embaixo' else 'white',lambda reader:None)).pack(side='left')
        ttk.Button(profiles_row,text='Perfis salvos',command=self.choose_reader_profile).pack(side='left',padx=4)
        self.screen_status=StringVar(value='Captura não iniciada.')
        ttk.Label(self.reading_tab,textvariable=self.screen_status,wraplength=350).pack(anchor='w',pady=5)
        ttk.Label(self.reading_tab,textvariable=self.sourcevar,style='Hint.TLabel',wraplength=350).pack(anchor='w')
        ttk.Label(self.reading_tab,textvariable=self.warningvar,style='Hint.TLabel',wraplength=350).pack(anchor='w',pady=5)
        ttk.Button(self.reading_tab,text='Copiar FEN reconhecido',command=self.copy_fen).pack(anchor='w',pady=5)
        turnrow=ttk.Frame(self.reading_tab)
        turnrow.pack(fill='x',pady=5)
        self.turn_label=StringVar(value='Brancas')
        ttk.Combobox(turnrow,textvariable=self.turn_label,state='readonly',width=10,
                     values=['Brancas','Pretas']).pack(side='left')
        ttk.Button(turnrow,text='Confirmar turno',command=lambda:self.change_turn(
            'w' if self.turn_label.get()=='Brancas' else 'b')).pack(side='left',padx=4)
        self.ontop=BooleanVar(value=bool(self.config.get('always_on_top')))
        ttk.Checkbutton(settings,text='Sempre visível',variable=self.ontop,command=self.set_on_top).pack(anchor='w')
        self.pathvar=StringVar(value=self.config['stockfish'])
        ttk.Label(settings,text='Motor Stockfish').pack(anchor='w',pady=(8,2))
        pathrow=ttk.Frame(settings)
        pathrow.pack(fill='x')
        ttk.Entry(pathrow,textvariable=self.pathvar,width=26).pack(side='left',fill='x',expand=True)
        ttk.Button(pathrow,text='…',width=3,command=self.choose_stockfish).pack(side='left',padx=3)
        self.depthvar=IntVar(value=self.config['depth'])
        self.secondsvar=IntVar(value=self.config['seconds'])
        self.threadsvar=IntVar(value=self.config['threads'])
        self.hashvar=IntVar(value=self.config['hash'])
        controls=ttk.Frame(settings)
        controls.pack(fill='x',pady=8)
        for index,(label,var,lo,hi) in enumerate((('Profundidade',self.depthvar,1,99),
                                                 ('Tempo (s)',self.secondsvar,0,86400),
                                                 ('CPU',self.threadsvar,1,64),('Memória MB',self.hashvar,16,4096))):
            row,col=divmod(index,2)
            ttk.Label(controls,text=label).grid(row=row*2,column=col,sticky='w',padx=(0,18),pady=(3,1))
            tk.Spinbox(controls,from_=lo,to=hi,textvariable=var,width=9).grid(row=row*2+1,column=col,sticky='w')
        ttk.Button(settings,text='Aplicar ajustes',command=self.apply).pack(anchor='w',pady=4)
        self.fenvar=StringVar(value=chess.STARTING_FEN)
        ttk.Label(settings,text='FEN manual').pack(anchor='w',pady=(8,2))
        ttk.Entry(settings,textvariable=self.fenvar,width=32).pack(fill='x')
        ttk.Button(settings,text='Analisar FEN',command=self.manual_fen).pack(anchor='w',pady=4)
        self.compact_view=ttk.Frame(root)
        self.compact_canvas=Canvas(self.compact_view,width=self.CELL*8,height=self.CELL*8,
                                  bg='#242d3c',highlightthickness=0)
        self.compact_canvas.pack()
        toolbar=ttk.Frame(self.compact_view)
        toolbar.pack(fill='x',padx=4,pady=3)
        ttk.Label(toolbar,text='Opções:').pack(side='left',padx=(0,3))
        for rank,mode in enumerate(RANK_MODES,1):
            ttk.Radiobutton(toolbar,text=f'{rank}ª',variable=self.display_key,value=mode,
                            command=self.change_display_mode).pack(side='left',padx=1)
        ttk.Radiobutton(toolbar,text='Hum.',variable=self.display_key,value='human',
                        command=self.change_display_mode).pack(side='left',padx=1)
        self.compact_description=StringVar(value='Aguardando análise')
        self.compact_status=StringVar()
        tk.Label(self.compact_view,textvariable=self.compact_status,bg='#111723',fg='#c5d2e4',
                 font=('Segoe UI',9),height=2,anchor='nw',justify='left',wraplength=430).pack(fill='x',padx=5)
        self.compact_description.trace_add('write',lambda *_:self.update_compact_status())
        self.screen_status.trace_add('write',lambda *_:self.update_compact_status())
        self.compact_menu=tk.Menu(root,tearoff=False)
        self.compact_menu.add_command(label='Painel (F11)',command=lambda:self.set_board_only(False))
        self.compact_menu.add_command(label='Nova área de leitura',command=self.select_screen_board)
        self.compact_menu.add_command(label='Buscar jogo em segundo plano',command=self.begin_background_search)
        self.compact_menu.add_command(label='Tentar leitura novamente',command=self.retry_screen)
        self.compact_menu.add_command(label='Parar leitura',command=self.stop_screen)
        self.compact_menu.add_command(label='Copiar FEN',command=self.copy_fen)
        self.compact_menu.add_checkbutton(label='Sempre visível',variable=self.ontop,command=self.set_on_top)
        self.compact_menu.add_separator()
        for key,label in DISPLAY_LABELS.items():
            self.compact_menu.add_radiobutton(label=label,variable=self.display_key,value=key,
                                             command=self.change_display_mode)
        ttk.Menubutton(toolbar,text='Mais',menu=self.compact_menu).pack(side='right')
        self.compact_canvas.bind('<Button-3>',self.show_compact_menu)
        self.compact_canvas.bind('<Double-Button-1>',lambda _:self.set_board_only(False))
        self.root.bind('<F11>',lambda _:self.set_board_only(not self.board_only))
        self.root.bind('<Escape>',lambda _:self.set_board_only(False) if self.board_only else None)
        self.root.bind('<KeyPress>',self.on_compact_key)
        self.root.bind('<Destroy>',lambda event:self.destroy_jobs() if event.widget==self.root else None,add='+')
        self.root.attributes('-topmost',self.ontop.get())
        if self.config.get('board_only'):
            self.set_board_only(True,remember=False)
        self.draw_board()
        self.poll()
        if self.screen_reader is not None and self.config.get('auto_start_search',True):
            self.auto_search_job=self.root.after(400,self.begin_background_search)

    def set_text(self, text):
        self.moves_text.configure(state='normal')
        self.moves_text.delete('1.0',END)
        self.moves_text.insert('1.0',text)
        self.moves_text.configure(state='disabled')

    def refresh_variation(self):
        mode=self.display_key.get()
        chosen=selected_line(self.lines,mode,self.cycle_rank,self.human_line)
        if mode=='alternate' and chosen:
            self.cycle_rank=chosen['rank']
        self.best_uci=chosen['uci'] if chosen else None

        visible=self.lines if mode in ('all','human') else ([chosen] if chosen else [])
        human_text=[]
        if mode=='human':
            if chosen:
                human_text=[f'HUMANIZADO • nível {chosen["skill"]}/19',
                            f'Sugestão do perfil: {chosen["first"]} • avaliação {chosen["score"]}',
                            chosen['san'],'','PRÉVIAS DA ANÁLISE PARA COMPARAÇÃO:','']
                if not chosen['depth']:
                    human_text.insert(3,'Sem avaliação ou continuação disponível para este lance.')
            else:
                human_text=['Calculando a sugestão humanizada…','','PRÉVIAS DA ANÁLISE:','']
        if visible:
            out=human_text
            for item in visible:
                out.append(f'{item["rank"]}º MELHOR LANCE: {item["first"]}    Avaliação: {item["score"]}')
                out.append(f'Profundidade {item["depth"]} • seletiva {item["seldepth"]}')
                out.append(item['san'])
                out.append('')
            self.set_text('\n'.join(out))
        elif mode=='human':
            self.set_text('Calculando a sugestão humanizada…')
        elif mode in RANK_MODES and self.lines:
            rank=RANK_MODES.index(mode)+1
            self.set_text(f'Aguardando a {rank}ª variante desta posição…')
        else:
            self.set_text('Calculando variantes…')

        if chosen and mode=='human':
            description=f'Humanizado {chosen["skill"]}/19: {chosen["first"]} ({chosen["score"]})'
        elif chosen:
            description=f'{chosen["rank"]}ª melhor: {chosen["first"]} ({chosen["score"]})'
        elif mode in RANK_MODES:
            rank=RANK_MODES.index(mode)+1
            unavailable = len(self.lines) >= self.board.legal_moves.count() > 0
            description=f'{rank}ª opção indisponível nesta posição' if unavailable else f'Aguardando {rank}ª variante'
        else:
            description='Aguardando análise'
        self.compact_description.set(description)
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
        self.cancel_poll()
        self.search_exclusions=[]
        for window in (self.root,self.screen_dialog):
            if window is not None and window.winfo_exists() and window.state() not in ('withdrawn','iconic'):
                x,y=window.winfo_rootx(),window.winfo_rooty()
                self.search_exclusions.append((x,y,x+window.winfo_width(),y+window.winfo_height()))
        for _ in range(80):
            try: event=self.state.ui_events.get_nowait()
            except queue.Empty:break
            what=event[0]
            if what=='board':
                _,board,mode,warning=event
                self.board=board
                self.lines=[]
                self.human_line=None
                self.cycle_rank=1
                self.cycle_at=time.monotonic()
                self.fenvar.set(board.fen())
                self.warningvar.set(f'Leitura: {mode}. {warning}')
                self.status.set(f'Posição reconhecida • {"brancas" if board.turn else "pretas"} jogam')
                self.refresh_variation()
            elif what=='connection':
                self.sourcevar.set('Origem: '+event[1])
                self.draw_board()
            elif what=='screen_status':self.screen_status.set(event[1])
            elif what=='search_status':
                if event[1]==self.capture_generation and self.search_active:self.screen_status.set(event[2])
            elif what=='search_ready':
                _,generation,screenshot,candidates=event
                if generation!=self.capture_generation:continue
                self.search_active=False
                self.locating_screen=False
                self.set_board_only(True)
                self.root.deiconify()
                self.screen_status.set('Jogo encontrado. Confira as peças e confirme para retomar.')
                self.review_screen_board(screenshot,candidates)
            elif what=='relocalize':
                if event[1]==self.capture_generation and not self.search_active:
                    self.begin_background_search()
            elif what=='detected_boards':
                _,generation,screenshot,candidates,error=event
                if generation!=self.capture_generation:continue
                self.locating_screen=False
                if error or not candidates:
                    self.screen_status.set('Não foi possível localizar o tabuleiro. Use o modo Manual.')
                    messagebox.showwarning('Identificação automática',error or
                        'Não encontrei uma grade 8×8 completa. Deixe o tabuleiro 2D visível ou selecione Manual.')
                else:
                    self.review_screen_board(screenshot,candidates)
            elif what=='engine':self.enginevar.set(event[1])
            elif what=='server':self.status.set(event[1])
            elif what=='error':self.enginevar.set('Aviso: '+event[1])
            elif what=='clear':
                if event[1]==self.state.revision:
                    self.lines=[]
                    self.human_line=None
                    self.refresh_variation()
            elif what=='lines':
                _,rev,fen,lines=event
                if rev!=self.state.revision or fen != self.board.fen():continue
                self.lines=lines
                self.refresh_variation()
            elif what=='human_line':
                _,rev,fen,line=event
                if rev!=self.state.revision or fen!=self.board.fen():continue
                self.human_line=line
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
                self.sourcevar.set('Sem leitura recente: verifique a tela ou a extensão.')
        self.poll_job=self.root.after(100,self.poll)

    def cancel_poll(self):
        if self.poll_job is not None:
            try:self.root.after_cancel(self.poll_job)
            except tk.TclError:pass
            self.poll_job=None

    def destroy_jobs(self):
        self.cancel_poll()
        self.search_stop.set()
        self.screen_stop.set()
        if self.auto_search_job is not None:
            try:self.root.after_cancel(self.auto_search_job)
            except tk.TclError:pass
            self.auto_search_job=None

    def choose_stockfish(self):
        path=filedialog.askopenfilename(title='Selecione stockfish.exe',filetypes=[('Executáveis','*.exe'),('Todos','*.*')])
        if path:self.pathvar.set(path)

    def stop_screen(self):
        if self.auto_search_job is not None:
            try:self.root.after_cancel(self.auto_search_job)
            except tk.TclError:pass
            self.auto_search_job=None
        self.capture_generation += 1
        self.locating_screen = False
        self.search_active=False
        self.search_stop.set()
        self.screen_stop.set()
        with self.state.lock:
            self.state.screen_active = False
        self.screen_status.set('Captura parada. A extensão pode receber posições novamente.')

    def cancel_start_search(self):
        if self.auto_search_job is not None:
            self.root.after_cancel(self.auto_search_job)
            self.auto_search_job=None

    def update_compact_status(self):
        self.compact_status.set(self.compact_description.get()+'\n'+self.screen_status.get()[:76])

    def copy_fen(self):
        with self.state.lock:
            fen=self.state.board.fen() if self.state.board is not None else None
        if fen is None:
            self.screen_status.set('Ainda não há uma posição reconhecida para copiar.')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(fen)
        self.screen_status.set('Último FEN reconhecido copiado.')

    def retry_screen(self):
        if self.capture_mode.get()=='Automático':
            self.begin_background_search()
            return
        if self.screen_thread and self.screen_thread.is_alive():
            self.stop_screen()
            self.root.after(100,self.retry_screen)
            return
        if self.screen_reader is None or self.screen_bbox is None:
            if self.screen_bbox:
                self.fresh_screen(lambda photo:self.review_screen_board(photo,[self.screen_bbox]))
            else:self.select_screen_board()
            return
        # Reuse calibration and legal-move history, including in mid-game.
        self.screen_stop=threading.Event()
        with self.state.lock:self.state.screen_active=True
        self.state.pause_screen('Repetindo leitura; aguardando imagem estável.')
        self.dock_capture_window(self.screen_bbox)
        self.screen_status.set('Tentando novamente com a calibração existente…')
        self.screen_thread=threading.Thread(target=self.read_screen,
            args=(self.screen_reader,self.screen_bbox,self.screen_stop),daemon=True)
        self.screen_thread.start()

    def fresh_screen(self, callback, on_error=None):
        """Let the compositor uncover the source before taking a new image."""
        from PIL import ImageGrab
        generation=self.capture_generation
        windows=[self.root]
        if self.screen_dialog is not None and self.screen_dialog.winfo_exists():
            windows.append(self.screen_dialog)
        states=[(window,window.state()) for window in windows]
        for window,_ in states:window.withdraw()
        def grab():
            photo=None
            error=None
            try:photo=ImageGrab.grab()
            except OSError as exc:error=str(exc)
            finally:
                for window,state in states:
                    if window.winfo_exists() and state!='withdrawn':
                        if state=='iconic':window.iconify()
                        else:window.deiconify()
            if generation!=self.capture_generation:return
            if error:
                self.screen_status.set('Falha ao capturar: '+error)
                if on_error:on_error('Falha ao capturar: '+error)
                return
            callback(photo)
        self.root.after(180,grab)

    def dock_capture_window(self,bbox):
        self.set_board_only(True)
        from screen_reader import outside_position
        width,height=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
        position=outside_position(bbox,(self.CELL*8+16,self.COMPACT_HEIGHT+40),(width,height))
        if position is None:
            self.root.iconify()
            self.screen_status.set('Leitura ativa. Janela minimizada para não cobrir o tabuleiro.')
        else:
            self.root.geometry(f'{self.CELL*8}x{self.COMPACT_HEIGHT}+{position[0]}+{position[1]}')

    def select_screen_board(self):
        try:
            from PIL import ImageGrab, ImageTk
        except ImportError:
            messagebox.showerror('Captura', 'Instale as dependências de requirements.txt (Pillow).')
            return
        if self.locating_screen:return
        if self.capture_mode.get()=='Automático':
            self.begin_background_search()
            return
        if self.screen_thread and self.screen_thread.is_alive():
            self.stop_screen()
            self.root.after(100, self.select_screen_board)
            return
        self.stop_screen()
        self.fresh_screen(self.select_from_image)

    def begin_background_search(self):
        self.auto_search_job=None
        self.stop_screen()
        self.capture_mode.set('Automático')
        self.state.update_view_settings(capture_mode='automatic')
        self.search_stop=threading.Event()
        self.search_active=True
        self.locating_screen=True
        with self.state.lock:self.state.screen_active=True
        self.state.pause_screen('Procurando o jogo; aguardando confirmação antes de analisar.')
        self.screen_status.set('Procurando tabuleiro em segundo plano… Abra a janela do jogo.')
        self.root.title('ChessVision Lab • Procurando jogo em segundo plano')
        self.set_board_only(True)
        self.root.deiconify()
        self.root.update_idletasks()
        width=self.root.winfo_screenwidth()
        self.root.geometry(f'{self.CELL*8}x{self.COMPACT_HEIGHT}+{max(0,width-self.CELL*8-24)}+12')
        self.root.update_idletasks()
        x,y=self.root.winfo_rootx(),self.root.winfo_rooty()
        self.search_exclusions=[(x,y,x+self.root.winfo_width(),y+self.root.winfo_height())]
        threading.Thread(target=self.search_game,args=(self.capture_generation,self.search_stop),daemon=True).start()

    def search_game(self,generation,stop):
        from PIL import ImageGrab
        from screen_reader import detect_boards
        previous=None
        last_status=None
        attempts=0
        while not stop.is_set() and not self.state.shutdown.is_set():
            try:
                attempts+=1
                photo=ImageGrab.grab()
                candidates=detect_boards(photo,tuple(self.search_exclusions))
                verified=[]
                for bbox in candidates:
                    placement=None
                    if self.screen_reader is not None:
                        try:
                            reader=self.screen_reader.for_region((bbox[2]-bbox[0],bbox[3]-bbox[1]))
                            placement=reader.read(photo.crop(bbox))
                        except ValueError:pass
                    verified.append((bbox,placement))
                # Locating an 8x8 grid must not require already knowing its
                # pieces: unknown styles are taught in the confirmation UI.
                signature=tuple(item[0] for item in verified)
                if signature and signature==previous:
                    if not stop.is_set():
                        stop.set()
                        self.state.ui_events.put(('search_ready',generation,photo,[item[0] for item in verified]))
                    return
                previous=signature or None
                status=(f'Busca {attempts}: grade encontrada; preparando conferência das peças.' if verified
                        else f'Busca {attempts}: aguardando tabuleiro visível. Mova o painel se estiver por cima do jogo.')
            except (OSError,ValueError) as exc:
                previous=None
                status=f'Busca continua aguardando uma imagem legível: {exc}'
            if status!=last_status and not stop.is_set():
                self.state.ui_events.put(('search_status',generation,status))
                last_status=status
            stop.wait(1.2)

    def select_from_image(self,screenshot):
        from PIL import ImageTk
        if self.capture_mode.get()=='Automático':
            self.locating_screen=True
            self.screen_status.set('Localizando grades 8×8 na tela…')
            threading.Thread(target=self.locate_screen_boards,
                args=(screenshot,self.capture_generation),daemon=True).start()
            return
        overlay=tk.Toplevel(self.root)
        overlay.attributes('-fullscreen', True)
        overlay.attributes('-topmost', True)
        photo=ImageTk.PhotoImage(screenshot)
        canvas=Canvas(overlay,highlightthickness=0,cursor='crosshair')
        canvas.pack(fill='both',expand=True)
        canvas.create_image(0,0,image=photo,anchor='nw')
        canvas.image=photo
        canvas.create_text(20,20,anchor='nw',text='Selecione as 64 casas • Esc cancela',
                           fill='#ff3030',font=('Segoe UI',18,'bold'))
        start=[]
        rectangle=[None]
        def press(event):
            start[:]=[event.x,event.y]
            if rectangle[0]:canvas.delete(rectangle[0])
            rectangle[0]=canvas.create_rectangle(*start,*start,outline='#00ff99',width=3)
        def drag(event):
            if start:canvas.coords(rectangle[0],*start,event.x,event.y)
        def release(event):
            if not start:return
            bbox=(max(0,min(start[0],event.x)),max(0,min(start[1],event.y)),
                  min(screenshot.width,max(start[0],event.x)),
                  min(screenshot.height,max(start[1],event.y)))
            overlay.destroy()
            self.screen_bbox=bbox
            self.review_screen_board(screenshot,[bbox])
        canvas.bind('<ButtonPress-1>',press)
        canvas.bind('<B1-Motion>',drag)
        canvas.bind('<ButtonRelease-1>',release)
        overlay.bind('<Escape>',lambda _:overlay.destroy())
        overlay.focus_force()

    def locate_screen_boards(self, screenshot, generation, own_bbox=None):
        from screen_reader import detect_boards
        try:
            candidates=detect_boards(screenshot)
            if own_bbox is not None:
                candidates=[bbox for bbox in candidates
                            if any(abs(a-b)>2 for a,b in zip(bbox,own_bbox))]
            error=''
        except (ValueError,OSError) as exc:
            candidates=[]
            error=str(exc)
        if not self.state.shutdown.is_set():
            self.state.ui_events.put(('detected_boards',generation,screenshot,candidates,error))

    def review_screen_board(self, screenshot, candidates):
        from PIL import ImageTk
        self.cancel_start_search()
        with self.state.lock:self.state.screen_active=True
        self.state.pause_screen('Confira as peças lidas; assistência aguardando sua confirmação.')
        dialog=tk.Toplevel(self.root)
        self.screen_dialog=dialog
        photo_source=[screenshot]
        dialog.title('Conferir região do tabuleiro')
        dialog.resizable(False,False)
        dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=8)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Confira a imagem e as peças lidas antes de confirmar.').pack(anchor='w')
        ttk.Label(frame,text='Tema conhecido permite retomar no meio da partida.',style='Hint.TLabel').pack(anchor='w')
        regionrow=ttk.Frame(frame)
        regionrow.pack(fill='x',pady=3)
        candidate_label=ttk.Label(regionrow)
        candidate_label.pack(side='left')
        ttk.Button(regionrow,text='Ensinar tema',command=lambda:teach()).pack(side='right')
        ttk.Button(regionrow,text='Alinhar grade',command=lambda:align_region()).pack(side='right',padx=3)
        controls=ttk.Frame(frame)
        controls.pack(fill='x',pady=5)
        bounds=[IntVar() for _ in range(4)]
        self.screen_review_vars=bounds
        for column,(label,var) in enumerate(zip(('X','Y','Largura','Altura'),bounds)):
            ttk.Label(controls,text=label).grid(row=0,column=column*2,padx=(5,2))
            tk.Spinbox(controls,from_=0,to=max(screenshot.size),textvariable=var,width=5,
                       command=lambda:update_preview()).grid(row=0,column=column*2+1)
        views=ttk.Notebook(frame)
        views.pack(pady=4)
        preview=Canvas(views,width=280,height=280,bg='#111723',highlightthickness=0)
        self.screen_preview=preview
        pieces=Canvas(views,width=280,height=280,bg='#111723',highlightthickness=0)
        self.recognized_preview=pieces
        views.add(preview,text='Imagem do jogo')
        views.add(pieces,text='Peças lidas')
        confirmrow=ttk.Frame(frame)
        confirmrow.pack(fill='x',pady=3)
        preview_orientation=StringVar(value=self.screen_orientation.get())
        orientation_combo=ttk.Combobox(confirmrow,textvariable=preview_orientation,state='readonly',width=17,
            values=['Brancas embaixo','Pretas embaixo'])
        orientation_combo.pack(side='left')
        turn_choice=StringVar(value='Confirme a vez')
        self.confirm_turn_var=turn_choice
        turn_combo=ttk.Combobox(confirmrow,textvariable=turn_choice,state='readonly',width=14,
                               values=['Brancas jogam','Pretas jogam'])
        turn_combo.pack(side='left',padx=4)
        rightsrow=ttk.Frame(frame)
        rightsrow.pack(fill='x',pady=2)
        ttk.Label(rightsrow,text='Roques:').pack(side='left')
        rights={key:BooleanVar(value=False) for key in 'KQkq'}
        self.confirm_castling_vars=rights
        rights_buttons=[]
        for key in rights:
            button=ttk.Checkbutton(rightsrow,text=key,variable=rights[key])
            button.pack(side='left')
            rights_buttons.append(button)
        ttk.Label(frame,text='K/Q: roques das brancas; k/q: das pretas. Sem histórico, confirme os permitidos.',
                  style='Hint.TLabel',wraplength=390).pack(anchor='w')
        warning=StringVar()
        ttk.Label(frame,textvariable=warning,wraplength=390).pack(anchor='w')
        current=[0]
        recognized={'reader':None,'placement':None,'orientation':None}
        taught=[None]

        def recognize(crop):
            from screen_reader import ScreenBoardReader
            orientation='black' if preview_orientation.get()=='Pretas embaixo' else 'white'
            reader=None
            error=None
            reference=taught[0] or self.screen_reader
            if reference is not None:
                try:
                    reader=reference.for_region(crop.size,orientation)
                    placement=reader.read(crop)
                except ValueError as exc:reader=None;error=exc
            if reader is None and taught[0] is None:
                for saved in self.reader_profiles.ready():
                    if reference and saved.profile_name==reference.profile_name:continue
                    try:
                        reader=saved.for_region(crop.size,orientation)
                        placement=reader.read(crop)
                        break
                    except ValueError:reader=None
            if reader is None and taught[0] is None:
                try:
                    reader=ScreenBoardReader(crop,orientation)
                    placement=reader.read(crop)
                except ValueError as exc:
                    recognized['reader']=None
                    pieces.delete('all')
                    warning.set('Peças ainda não identificadas. Use Ensinar tema para cadastrar exemplos. '+str(error or exc))
                    return
            if reader is None:
                recognized['reader']=None
                pieces.delete('all')
                warning.set('O perfil precisa de outro exemplo: '+str(error))
                return
            snapshot=self.state.preview_screen_position(placement)
            changed=placement!=recognized['placement'] or orientation!=recognized['orientation']
            first=recognized['placement'] is None
            recognized.update(reader=reader,placement=placement,orientation=orientation)
            if first:views.select(pieces)
            known=snapshot.mode!='estimado'
            turn_combo.configure(state='disabled' if known else 'readonly')
            for button in rights_buttons:button.configure(state='disabled' if known else 'normal')
            if known:
                turn_choice.set('Brancas jogam' if snapshot.board.turn else 'Pretas jogam')
                for key,var in rights.items():var.set(key in snapshot.board.castling_xfen())
            elif changed:
                turn_choice.set('Confirme a vez')
                for var in rights.values():var.set(False)
            pieces.delete('all')
            for row in range(8):
                for col in range(8):
                    square=chess.square(7-col if orientation=='black' else col,row if orientation=='black' else 7-row)
                    pieces.create_rectangle(col*35,row*35,(col+1)*35,(row+1)*35,
                        fill='#e8d7ba' if (chess.square_file(square)+chess.square_rank(square))%2 else '#8098ad',outline='')
                    piece=snapshot.board.piece_at(square)
                    if piece:pieces.create_text(col*35+17.5,row*35+17.5,text=PIECE_GLYPHS[piece.symbol()],
                        fill='#ffffff' if piece.color else '#111723',font=('Segoe UI Symbol',25))
                    if row==7:pieces.create_text(col*35+3,278,anchor='sw',text=chess.FILE_NAMES[chess.square_file(square)],fill='#293244',font=('Segoe UI',7))
                    if col==0:pieces.create_text(2,row*35+2,anchor='nw',text=str(chess.square_rank(square)+1),fill='#293244',font=('Segoe UI',7))
            warning.set('Peças identificadas. Confira a aba Peças lidas.'+(' Confirme a vez e os roques; o histórico anterior não está disponível.' if not known else ' Histórico compatível.'))

        def update_preview():
            preview.delete('all')
            try:
                screenshot=photo_source[0]
                x,y,w,h=(v.get() for v in bounds)
                if min(x,y)<0 or min(w,h)<160 or abs(w-h)>4:
                    raise ValueError('Use uma região quadrada, com pelo menos 160 pixels de lado.')
                if x+w>screenshot.width or y+h>screenshot.height:
                    raise ValueError('A região precisa ficar inteiramente dentro da tela.')
                crop=screenshot.crop((x,y,x+w,y+h))
                crop.thumbnail((280,280))
                photo=ImageTk.PhotoImage(crop)
                preview.image=photo
                preview.configure(width=crop.width,height=crop.height)
                preview.create_image(0,0,image=photo,anchor='nw')
                for n in range(9):
                    px=min(crop.width-1,n*crop.width/8)
                    py=min(crop.height-1,n*crop.height/8)
                    preview.create_line(px,0,px,crop.height,fill='#00d9a3')
                    preview.create_line(0,py,crop.width,py,fill='#00d9a3')
                warning.set(f'Região: ({x}, {y}) até ({x+w}, {y+h}) • {w} × {h} px')
                self.screen_bbox=(x,y,x+w,y+h)
                recognize(screenshot.crop((x,y,x+w,y+h)))
                return x,y,x+w,y+h
            except (ValueError,tk.TclError) as exc:
                warning.set(str(exc))
                return None

        def choose(index):
            current[0]=index % len(candidates)
            left,top,right,bottom=candidates[current[0]]
            from screen_reader import refine_board_region
            left,top,right,bottom=refine_board_region(photo_source[0],(left,top,right,bottom))
            for var,value in zip(bounds,(left,top,right-left,bottom-top)):var.set(value)
            candidate_label.configure(text=f'Região {current[0]+1} de {len(candidates)}')
            update_preview()

        def align_region():
            bbox=update_preview()
            if bbox is None:return None
            from screen_reader import refine_board_region
            aligned=refine_board_region(photo_source[0],bbox)
            left,top,right,bottom=aligned
            for var,value in zip(bounds,(left,top,right-left,bottom-top)):var.set(value)
            update_preview()
            return aligned

        def teach():
            bbox=align_region()
            if bbox is None:return
            crop=photo_source[0].crop(bbox)
            orientation='black' if preview_orientation.get()=='Pretas embaixo' else 'white'
            def accept(reader):
                taught[0]=reader
                update_preview()
                views.select(pieces)
            self.teach_piece_profile(crop,orientation,accept,parent=dialog)

        def start():
            bbox=update_preview()
            if bbox is None:return
            if recognized['reader'] is None:return
            turn={'Brancas jogam':'w','Pretas jogam':'b'}.get(turn_choice.get())
            if turn is None:
                warning.set('Confirme de quem é a vez antes de continuar.')
                return
            castling=''.join(key for key,var in rights.items() if var.get()) or '-'
            confirmation={'placement':recognized['placement'],'turn':turn,
                          'orientation':recognized['orientation'],'castling':castling}
            try:
                # Validate metadata before dismissing the confirmation UI.
                probe=self.state.preview_screen_position(confirmation['placement'])
                if probe.mode=='estimado' and not chess.Board(
                    f'{confirmation["placement"]} {turn} {castling} - 0 1').is_valid():
                    raise ValueError('A vez ou os roques não combinam com as peças lidas.')
            except ValueError as exc:warning.set(str(exc));return
            dialog.destroy()
            self.screen_dialog=None
            self.screen_orientation.set(preview_orientation.get())
            self.start_screen_capture(recognized['reader'],bbox,confirmation=confirmation)

        def recapture():
            warning.set('Recapturando a tela…')
            def replace(photo):
                if not dialog.winfo_exists():return
                photo_source[0]=photo
                update_preview()
            self.fresh_screen(replace,on_error=warning.set)

        def new_area():
            dialog.destroy()
            self.screen_dialog=None
            self.select_screen_board()

        def cancel():
            self.screen_dialog=None
            self.stop_screen()
            self.screen_status.set('Calibração cancelada.')
            dialog.destroy()

        buttons=ttk.Frame(frame)
        buttons.pack(fill='x',pady=8)
        if len(candidates)>1:
            ttk.Button(buttons,text='Outra região',command=lambda:choose(current[0]+1)).pack(side='left')
        ttk.Button(buttons,text='Tentar novamente',command=recapture).pack(side='left',padx=2)
        ttk.Button(buttons,text='Nova área',command=new_area).pack(side='left',padx=2)
        ttk.Button(buttons,text='Cancelar',command=cancel).pack(side='right')
        ttk.Button(buttons,text='Confirmar e continuar',command=start).pack(side='right',padx=4)
        orientation_combo.bind('<<ComboboxSelected>>',lambda _:update_preview())
        dialog.bind('<Return>',lambda _:update_preview())
        dialog.bind('<Escape>',lambda _:cancel())
        dialog.protocol('WM_DELETE_WINDOW',cancel)
        choose(0)
        dialog.grab_set()
        return dialog

    def teach_piece_profile(self,crop,orientation,on_ready,parent=None):
        from PIL import Image,ImageTk
        from screen_reader import ScreenBoardReader,PIECE_LABELS,square_at,UncertainSquareError
        self.cancel_start_search()
        parent=parent or self.root
        standalone=crop is None
        if standalone:crop=Image.new('RGB',(480,480),'#283445')
        trainer=tk.Toplevel(parent)
        trainer.title('Ensinar estilo das peças')
        trainer.transient(parent)
        trainer.resizable(False,False)
        panel=ttk.Frame(trainer,padding=8)
        panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Escolha o tipo e clique na casa que mostra essa peça.',wraplength=380).pack(anchor='w')
        ttk.Label(panel,text='São 12 tipos + casa vazia. Para torres e outras peças, adicione exemplos em casas claras e escuras.',
                  style='Hint.TLabel',wraplength=380).pack(anchor='w',pady=3)
        reference=None
        try:reference=ScreenBoardReader.load(CONFIG.with_name('.reader_draft.json'),allow_incomplete=True)
        except (OSError,ValueError):
            reference=self.screen_reader
            if reference and reference.profile_name=='cburnett (pronto)':reference=None
        name=StringVar(value=reference.profile_name if reference else 'Meu tema')
        namerow=ttk.Frame(panel);namerow.pack(fill='x',pady=3)
        ttk.Label(namerow,text='Perfil:').pack(side='left')
        ttk.Entry(namerow,textvariable=name,width=25).pack(side='left',padx=4)
        choice=StringVar(value=PIECE_LABELS['.'])
        palette=ttk.Combobox(panel,textvariable=choice,values=list(PIECE_LABELS.values()),state='readonly',width=27)
        palette.pack(anchor='w',pady=3)
        self.teaching_choice=choice
        reader=ScreenBoardReader.new_profile(crop.size,orientation)
        if reference is not None:
            reader.templates={symbol:list(tiles) for symbol,tiles in reference.templates.items()}
        self.teaching_reader=reader
        image_row=ttk.Frame(panel);image_row.pack(fill='x',pady=4)
        canvas=Canvas(image_row,width=280,height=280,highlightthickness=0,bg='#111723')
        canvas.pack(side='left')
        detail=Canvas(image_row,width=72,height=72,highlightthickness=0,bg='#111723')
        detail.pack(side='left',anchor='n',padx=(5,0))
        self.teaching_canvas=canvas
        thumbnail=crop.copy();thumbnail.thumbnail((280,280))
        photo=ImageTk.PhotoImage(thumbnail)
        canvas.image=photo
        canvas.create_image(0,0,image=photo,anchor='nw')
        for n in range(9):
            canvas.create_line(n*thumbnail.width/8,0,n*thumbnail.width/8,thumbnail.height,fill='#00d9a3')
            canvas.create_line(0,n*thumbnail.height/8,thumbnail.width,n*thumbnail.height/8,fill='#00d9a3')
        progress=StringVar()
        ttk.Label(panel,textvariable=progress,wraplength=380).pack(anchor='w')
        status=StringVar(value='Importe imagens de casas, uma peça por vez. Cada exemplo é salvo automaticamente.' if standalone
                         else 'Clique nas peças ou importe exemplos. O cadastro é salvo automaticamente.')
        ttk.Label(panel,textvariable=status,style='Hint.TLabel',wraplength=380).pack(anchor='w',pady=3)
        undo=[]
        last_click=[None,0.0]

        def refresh():
            missing=reader.missing_symbols
            progress.set(f'{13-len(missing)}/13 tipos cadastrados'+(' • próximo: '+PIECE_LABELS[missing[0]] if missing else ' • pronto para conferir'))
            if missing:choice.set(PIECE_LABELS[missing[0]])

        def selected_symbol():
            return next(symbol for symbol,label in PIECE_LABELS.items() if label==choice.get())

        def register(symbol,tile,location):
            previous=list(reader.templates[symbol])
            reader.add_tile(symbol,tile)
            undo.append((symbol,previous))
            status.set(f'{PIECE_LABELS[symbol]}: {len(reader.templates[symbol])} exemplo(s), último: {location}.')
            refresh()
            save_profile()

        def show_square(row,col):
            tile=crop.crop((round(col*crop.width/8),round(row*crop.height/8),
                            round((col+1)*crop.width/8),round((row+1)*crop.height/8)))
            detail.image=ImageTk.PhotoImage(tile.resize((72,72),Image.Resampling.LANCZOS))
            detail.delete('all');detail.create_image(0,0,image=detail.image,anchor='nw')
            canvas.delete('selected')
            canvas.create_rectangle(col*thumbnail.width/8,row*thumbnail.height/8,
                (col+1)*thumbnail.width/8,(row+1)*thumbnail.height/8,outline='#ffcc55',width=3,tags='selected')
            return tile

        def click(event):
            col=int(event.x*8/thumbnail.width);row=int(event.y*8/thumbnail.height)
            if not 0<=row<8 or not 0<=col<8:return
            cell=(row,col)
            now=time.monotonic()
            if cell==last_click[0] and now-last_click[1]<.35:return
            last_click[:]=[cell,now]
            symbol=selected_symbol()
            tile=show_square(row,col)
            try:register(symbol,tile,chess.square_name(square_at(row,col,orientation)))
            except ValueError as exc:status.set(str(exc))

        def undo_last():
            if not undo:return
            symbol,previous=undo.pop()
            reader.templates[symbol]=previous
            refresh();choice.set(PIECE_LABELS[symbol])
            status.set('Exemplo desfeito. Clique novamente na peça correta.')
            save_profile()

        def clear_type():
            symbol=selected_symbol()
            previous=list(reader.templates[symbol])
            if previous:
                undo.append((symbol,previous))
                reader.templates[symbol]=[]
            refresh();choice.set(PIECE_LABELS[symbol])
            status.set('Exemplos desse tipo removidos. Clique na peça correta.')
            save_profile()

        def import_tile():
            filename=filedialog.askopenfilename(parent=trainer,title='Escolha a imagem de uma casa inteira',
                filetypes=[('Imagens','*.png *.jpg *.jpeg *.webp'),('Todos','*.*')])
            if not filename:return
            try:
                with Image.open(filename) as image:
                    if max(image.size)>2048:raise ValueError('Importe o recorte de uma casa, com a peça e suas margens.')
                    register(selected_symbol(),image.copy(),'imagem importada')
            except (OSError,ValueError) as exc:status.set(str(exc))

        def close():
            if not save_profile():return False
            trainer.destroy()
            if parent is not self.root and parent.winfo_exists():parent.grab_set()
            return True

        def save_profile():
            reader.profile_name=name.get().strip()[:80] or 'Meu tema'
            try:
                self.reader_profiles.save(reader)
                reader.save(CONFIG.with_name('.reader_draft.json'),allow_incomplete=True)
                if not reader.missing_symbols:
                    reader.save(CONFIG.with_name('.reader_templates.json'))
                    self.screen_reader=reader.for_region(reader.size)
                    self.cache_status.set(f'Perfil {reader.profile_name} salvo. Pronto para conferir uma partida.')
                    status.set('Cadastro completo salvo. Pode fechar e usar em outra partida.')
                else:status.set(f'Progresso salvo. Faltam {len(reader.missing_symbols)} tipos; pode completar depois.')
                return True
            except OSError as exc:status.set('Não foi possível salvar: '+str(exc));return False

        def learn_initial():
            try:
                learned=ScreenBoardReader(crop,orientation)
                undo.extend((symbol,list(reader.templates[symbol])) for symbol in reader.templates)
                reader.templates={symbol:list(tiles) for symbol,tiles in learned.templates.items()}
                refresh()
                save_profile()
            except ValueError as exc:status.set(str(exc))

        def use():
            if standalone:
                if reader.missing_symbols:save_profile()
                elif close():on_ready(reader)
                return
            try:
                reader.profile_name=name.get().strip()[:80] or 'Meu tema'
                placement=reader.read(crop)
                self.state.preview_screen_position(placement)
            except UncertainSquareError as exc:
                show_square(exc.row,exc.col)
                choice.set(PIECE_LABELS[exc.symbol])
                square=chess.square_name(square_at(exc.row,exc.col,orientation))
                status.set(f'Confira {square} destacada. Escolha o tipo correto e clique nela para adicionar outro exemplo; depois use o perfil.')
                return
            except ValueError as exc:
                status.set('Revise os exemplos: '+str(exc))
                return
            if close():on_ready(reader)

        if not standalone:canvas.bind('<Button-1>',click)
        actions=ttk.Frame(panel);actions.pack(fill='x',pady=4)
        ttk.Button(actions,text='Importar casa…',command=import_tile).pack(side='left')
        ttk.Button(actions,text='Desfazer',command=undo_last).pack(side='left',padx=3)
        ttk.Button(actions,text='Usar perfil',command=use).pack(side='right')
        ttk.Button(actions,text='Fechar',command=close).pack(side='right',padx=3)
        correction=ttk.Frame(panel);correction.pack(fill='x')
        ttk.Button(correction,text='Limpar tipo selecionado',command=clear_type).pack(side='left')
        ttk.Button(correction,text='Salvar cadastro',command=save_profile).pack(side='right')
        if not standalone:
            ttk.Button(panel,text='Aprender todas: tabuleiro na posição inicial',command=learn_initial).pack(anchor='w',pady=3)
        refresh()
        trainer.protocol('WM_DELETE_WINDOW',close)
        trainer.bind('<Escape>',lambda _:close())
        trainer.grab_set()
        return trainer

    def choose_reader_profile(self):
        self.cancel_start_search()
        profiles=self.reader_profiles.list()
        dialog=tk.Toplevel(self.root)
        dialog.title('Perfis de reconhecimento')
        dialog.transient(self.root)
        panel=ttk.Frame(dialog,padding=12);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Escolha um perfil salvo. Cadastros incompletos podem ser continuados.').pack(anchor='w')
        names=list(profiles)
        selected=StringVar(value=self.screen_reader.profile_name if self.screen_reader and self.screen_reader.profile_name in profiles else (names[0] if names else ''))
        combo=ttk.Combobox(panel,textvariable=selected,values=names,state='readonly',width=38)
        combo.pack(fill='x',pady=6)
        detail=StringVar()
        def describe(*_):
            item=profiles.get(selected.get())
            if item:
                reader=item[1]
                detail.set(f'{13-len(reader.missing_symbols)}/13 tipos • {sum(map(len,reader.templates.values()))} exemplos salvos')
            else:detail.set('Nenhum perfil salvo. Abra Cadastro de peças para começar.')
        selected.trace_add('write',describe);describe()
        ttk.Label(panel,textvariable=detail).pack(anchor='w')
        def use():
            item=profiles.get(selected.get())
            if not item:return
            reader=item[1]
            try:
                self.reader_profiles.save(reader)
                reader.save(CONFIG.with_name('.reader_draft.json'),allow_incomplete=True)
                if reader.missing_symbols:
                    dialog.destroy()
                    self.teach_piece_profile(None,reader.orientation,lambda _:None)
                    return
                reader.save(CONFIG.with_name('.reader_templates.json'))
            except OSError as exc:
                detail.set('Não foi possível salvar: '+str(exc));return
            self.stop_screen()
            self.screen_reader=reader
            self.screen_orientation.set('Pretas embaixo' if reader.orientation=='black' else 'Brancas embaixo')
            self.cache_status.set(f'Perfil {reader.profile_name} selecionado. Clique em Iniciar para conferir o jogo.')
            dialog.destroy()
        ttk.Button(panel,text='Usar / continuar cadastro',command=use).pack(anchor='e',pady=8)
        def create():
            from screen_reader import ScreenBoardReader
            number=1
            while f'Meu tema {number}' in profiles:number+=1
            reader=ScreenBoardReader.new_profile((480,480),name=f'Meu tema {number}')
            try:reader.save(CONFIG.with_name('.reader_draft.json'),allow_incomplete=True)
            except OSError as exc:
                detail.set('Não foi possível criar: '+str(exc));return
            dialog.destroy()
            self.teach_piece_profile(None,'white',lambda _:None)
        ttk.Button(panel,text='Novo perfil',command=create).pack(anchor='w')
        return dialog

    def start_screen_capture(self, reader, bbox, confirmation=None):
        self.screen_reader=reader
        self.screen_bbox=bbox
        self.screen_stop=threading.Event()
        stop=self.screen_stop
        if confirmation is not None:self.state.confirm_screen_position(**confirmation)
        else:
            with self.state.lock:
                self.state.screen_active=True
                self.state.tracker=BoardTracker()
                self.state.tracker.update(chess.STARTING_BOARD_FEN)
                self.state.pending_screen=None
                self.state.board=None
                self.state.revision+=1
                self.state.wakeup.set()
                self.state.ui_events.put(('clear', self.state.revision))
        try:
            self.reader_profiles.save(reader)
            reader.save(CONFIG.with_name('.reader_templates.json'))
            self.cache_status.set(f'Perfil {reader.profile_name} salvo. Pode retomar no meio da partida neste tema.')
        except OSError:self.cache_status.set('Referências disponíveis só nesta sessão; não foi possível salvar.')
        self.screen_status.set('Captura ativa: mantenha o tabuleiro visível.')
        self.dock_capture_window(bbox)
        self.screen_thread=threading.Thread(target=self.read_screen,args=(reader,bbox,stop),daemon=True)
        self.screen_thread.start()

    def read_screen(self, reader, bbox, stop):
        from PIL import ImageGrab
        previous=None
        last_status=None
        failures=0
        saved_fen=None
        generation=getattr(self,'capture_generation',0)
        while not stop.is_set() and not self.state.shutdown.is_set():
            try:
                with self.state.lock:
                    known=self.state.tracker.board.copy(stack=True) if self.state.tracker.board is not None else None
                placement=reader.read(ImageGrab.grab(bbox=bbox),board=known)
                # Require two matching frames to avoid moving pieces/animations.
                if placement==previous:
                    with self.state.lock:
                        if stop.is_set() or not self.state.screen_active:return
                        accepted=self.state.receive({'placement':placement,'moves':[],
                            'source':'Captura de tela','orientation':reader.orientation})
                        if not accepted['ok']:raise ValueError(accepted['error'])
                    with self.state.lock:
                        current=self.state.tracker.board
                        outcome=current.outcome() if current else None
                        turn='brancas' if current and current.turn else 'pretas'
                        last=current.peek().uci() if current and current.move_stack else 'início'
                    status=(f'Partida encerrada • {outcome.result()}' if outcome else
                            f'Leitura ativa • posição reconhecida • vez das {turn} • último lance: {last}')
                    if current and current.fen()!=saved_fen and hasattr(self,'reader_profiles'):
                        try:
                            self.reader_profiles.save_game(reader,current)
                            saved_fen=current.fen()
                        except OSError as exc:status+=' • falha ao salvar histórico: '+str(exc)
                    failures=0
                else:
                    status='Aguardando posição estável; a leitura continua…'
                    self.state.pause_screen(status)
                previous=placement
            except (ValueError,OSError) as exc:
                failures+=1
                previous=None
                status=f'Aguardando imagem legível; tentando novamente: {exc}'
                self.state.pause_screen(status)
                # Allow visual animations/brief obstruction to settle before
                # abandoning this region. Capture I/O failures recover sooner.
                limit=4 if isinstance(exc,OSError) else 12
                if failures>=limit and self.state.config.get('auto_recover',True) and not stop.is_set():
                    self.state.ui_events.put(('relocalize',generation))
                    return
            if status!=last_status and not stop.is_set():
                self.state.ui_events.put(('screen_status',status))
                last_status=status
            stop.wait(0.2)

    def apply(self):
        try:
            data = {**self.state.config, 'stockfish':self.pathvar.get().strip(),
                    'depth':int(self.depthvar.get()), 'seconds':int(self.secondsvar.get()),
                    'threads':int(self.threadsvar.get()), 'hash':int(self.hashvar.get()),
                    'multipv':5, 'always_on_top':self.ontop.get(),
                    'human_enabled':self.profile_label.get()=='Humanizado (treino)',
                    'human_skill':int(self.human_skill.get())}
            if not 1 <= data['depth'] <= 99 or not 0 <= data['seconds'] <= 86400:
                raise ValueError('Depth ou tempo fora dos limites')
            if not data['stockfish'] or not Path(data['stockfish']).is_file():
                raise ValueError('Selecione o executável do Stockfish 19')
            if not 0 <= data['human_skill'] <= 19:
                raise ValueError('Nível humanizado deve estar entre 0 e 19')
            self.state.change_config(data)
            self.lines=[]
            self.human_line=None
            self.refresh_variation()
            self.enginevar.set('Carregando Stockfish…')
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror('Configuração',str(exc))

    def apply_profile(self):
        try:
            skill=int(self.human_skill.get())
            if not 0 <= skill <= 19:
                raise ValueError('Nível humanizado deve estar entre 0 e 19')
            enabled=self.profile_label.get()=='Humanizado (treino)'
            mode='human' if enabled else 'first'
            with self.state.lock:
                config={**self.state.config,'human_enabled':enabled,
                        'human_skill':skill,'display_mode':mode}
            self.state.change_config(config)
            self.display_key.set(mode)
            self.display_label.set(DISPLAY_LABELS[mode])
            self.lines=[]
            self.human_line=None
            self.refresh_variation()
            self.enginevar.set(f'Perfil humanizado • nível {skill}/19' if enabled else 'Perfil de análise máxima')
        except (ValueError,tk.TclError) as exc:
            mode=self.state.config.get('display_mode','first')
            self.display_key.set(mode)
            self.display_label.set(DISPLAY_LABELS[mode])
            self.profile_label.set('Humanizado (treino)' if self.state.config.get('human_enabled') else 'Análise máxima')
            messagebox.showerror('Perfil',str(exc))

    def reanalyse(self):
        with self.state.lock:
            self.state.revision+=1
            self.state.wakeup.set()

    def change_turn(self,color):
        try:self.state.force_turn(color)
        except ValueError as exc:messagebox.showerror('Turno',str(exc))

    def manual_fen(self):
        try:
            fen=self.fenvar.get().strip()
            if not chess.Board(fen).is_valid():raise ValueError('Posição FEN inválida')
            self.stop_screen()
            self.state.set_fen(fen)
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
        if mode=='human' and not self.state.config.get('human_enabled'):
            self.profile_label.set('Humanizado (treino)')
            self.apply_profile()
            return
        self.display_label.set(DISPLAY_LABELS[mode])
        self.cycle_rank=1
        self.cycle_at=time.monotonic()
        self.state.update_view_settings(display_mode=mode)
        self.refresh_variation()

    def on_compact_key(self, event):
        if not self.board_only:return
        mode={'1':'first','2':'second','3':'third','4':'fourth','5':'fifth','a':'alternate','t':'all','h':'human'}.get(event.keysym.lower())
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
            # Compact mode always starts with a manually selected rank, even
            # when an old configuration had automatic cycling enabled.
            if self.display_key.get() not in (*RANK_MODES,'human'):
                self.display_key.set('first')
                self.change_display_mode()
            self.normal_geometry=self.root.geometry()
            self.normal_minsize=self.root.minsize()
            self.normal_maxsize=self.root.maxsize()
            self.full_view.pack_forget()
            self.compact_view.pack(fill='both',expand=True)
            size=self.CELL*8
            self.root.minsize(size,self.COMPACT_HEIGHT)
            self.root.maxsize(size,self.COMPACT_HEIGHT)
            self.root.geometry(f'{size}x{self.COMPACT_HEIGHT}')
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
        self.screen_stop.set()
        self.state.shutdown.set()
        self.state.wakeup.set()
        self.root.destroy()


def main():
    if os.name == 'nt':
        # Keep Tk selection coordinates aligned with screenshot pixels on HiDPI.
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
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

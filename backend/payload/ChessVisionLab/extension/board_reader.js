"use strict";
(() => {
  // Robust DOM adapter: dynamic game boards may be replaced after navigation.
  // The engine never reads pixels and never accesses account credentials.
  const SELECTORS = ["wc-chess-board", "chess-board", ".board-layout-chessboard .board", ".board"];
  const PIECES = new Set(["wp","wn","wb","wr","wq","wk","bp","bn","bb","br","bq","bk"]);
  const HEARTBEAT_MS = 4500;
  let lastSent = "", lastTime = 0, scheduled = 0;

  function rootOf(element) {
    return element?.shadowRoot || element;
  }

  function piecesOf(board) {
    let pieces = Array.from(rootOf(board).querySelectorAll('.piece, [data-piece][data-square]'));
    if (!pieces.length && board.shadowRoot) pieces = Array.from(board.querySelectorAll('.piece, [data-piece][data-square]'));
    return pieces;
  }

  function findBoard() {
    for (const selector of SELECTORS) {
      for (const board of document.querySelectorAll(selector)) {
        if (piecesOf(board).length >= 2) return board;
      }
    }
    return null;
  }

  function readPlacement(board) {
    const squares = Array.from({length:8}, () => Array(8).fill(null));
    const seen = new Set(), kings = {w:0,b:0};
    for (const element of piecesOf(board)) {
      let piece = null, square = null;
      for (const cls of element.classList) {
        if (PIECES.has(cls)) piece = cls;
        const match = /^square-([1-8])([1-8])$/.exec(cls);
        if (match) square = [Number(match[1]), Number(match[2])];
      }
      // Optional DOM format used by some custom board components.
      if (!piece) {
        const label = element.getAttribute?.('data-piece') || '';
        const alias = {'white-pawn':'wp','white-knight':'wn','white-bishop':'wb',
          'white-rook':'wr','white-queen':'wq','white-king':'wk',
          'black-pawn':'bp','black-knight':'bn','black-bishop':'bb',
          'black-rook':'br','black-queen':'bq','black-king':'bk'};
        piece = alias[label] || (PIECES.has(label) ? label : null);
      }
      if (!square) {
        const label = element.getAttribute?.('data-square') || '';
        if (/^[a-h][1-8]$/.test(label)) square = [label.charCodeAt(0)-96, Number(label[1])];
      }
      if (!piece || !square) continue;
      const [file, rank] = square, key = file + ':' + rank;
      if (seen.has(key)) return null; // animation during a capture
      seen.add(key);
      if (piece[1] === 'k') kings[piece[0]]++;
      squares[8-rank][file-1] = piece[0] === 'w' ? piece[1].toUpperCase() : piece[1];
    }
    if (seen.size < 2 || kings.w !== 1 || kings.b !== 1) return null;
    return squares.map(rank => {
      let result = '', empty = 0;
      for (const piece of rank) {
        if (piece) { if (empty) result += empty; empty = 0; result += piece; }
        else empty++;
      }
      return result + (empty || '');
    }).join('/');
  }

  function readMoveHistory() {
    const list = document.querySelector('wc-simple-move-list') ||
                 document.querySelector('.move-list') ||
                 document.querySelector('[data-cy="move-list"]');
    if (!list) return [];
    const moves = [];
    const san = /^(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)(?:[+#])?[!?]*$/;
    for (const node of rootOf(list).querySelectorAll('.node, [data-node="mainline-ply"]')) {
      if (node.closest?.('[data-node="variation-ply"], .variation, .variation-line')) continue;
      let text = node.getAttribute('data-san') || node.getAttribute('data-move') ||
                 (node.innerText || node.textContent || '');
      text = text.trim().replace(/^(?:\d+\.{1,3}\s*)/, '').replace(/\s+/g,'');
      if (san.test(text)) moves.push(text);
    }
    return moves;
  }

  function readOrientation(board) {
    const attr = board.getAttribute?.('orientation') || board.getAttribute?.('data-orientation');
    if (attr === 'black' || attr === 'white') return attr;
    if (board.classList.contains('flipped') || board.closest?.('.flipped')) return 'black';
    return 'white';
  }

  function readTurn(board, placement) {
    // Never guess the turn from which color is at the bottom.
    const fen = board.getAttribute?.('data-fen') || board.getAttribute?.('fen');
    if (fen) {
      const parts = fen.trim().split(/\s+/);
      if (parts[0] === placement && ['w', 'b'].includes(parts[1])) return parts[1];
    }
    const turn = board.getAttribute?.('data-turn');
    if (turn === 'white' || turn === 'w') return 'w';
    if (turn === 'black' || turn === 'b') return 'b';
    return null;
  }

  function publish() {
    const board = findBoard();
    if (!board) return;
    const placement = readPlacement(board);
    if (!placement) return;
    const moves = readMoveHistory();
    const payload = {placement, moves, turn: readTurn(board,placement),
      orientation: readOrientation(board), source: location.pathname, timestamp: Date.now()};
    const digest = [placement, moves.join(','), payload.turn, payload.orientation, location.pathname].join('|');
    const now = Date.now();
    if (digest === lastSent && now - lastTime < HEARTBEAT_MS) return;
    lastSent = digest;
    lastTime = now;
    try {
      chrome.runtime.sendMessage({type:'chessvision-position',payload}, response => {
        if (chrome.runtime.lastError || !response?.ok) {
          lastSent = '';
          lastTime = 0;
        }
      });
    } catch (_) { lastSent = ''; lastTime = 0; }
  }

  function schedule() {
    clearTimeout(scheduled);
    scheduled = setTimeout(publish, 300);
  }
  new MutationObserver(schedule).observe(document.documentElement, {
    subtree:true,childList:true,attributes:true,attributeFilter:['class','data-node','data-fen','data-turn']
  });
  setInterval(publish, 1500);
  schedule();
})();

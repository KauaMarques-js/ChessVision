"""Verify that the UCI worker requests and delivers all five ranked lines."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import chess.engine
import app


class EngineVariantsTests(unittest.TestCase):
    def test_worker_emits_five_lines_for_current_position(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / 'engine'
            executable.touch()
            with patch.object(app, 'CONFIG', Path(temp) / 'config.json'):
                state = app.AnalysisState()
                state.set_fen(chess.STARTING_FEN)
                state.config['stockfish'] = str(executable)
                engine = MagicMock()
                engine.options = {'Skill Level':None,'UCI_LimitStrength':None}
                engine.id = {'name': 'Test UCI'}

                def infos():
                    for rank, move in enumerate(('e2e4','d2d4','g1f3','c2c4','g2g3'), 1):
                        yield {'multipv': rank, 'pv': [chess.Move.from_uci(move)],
                               'depth': 12, 'score': chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE)}
                    state.shutdown.set()

                engine.analysis.return_value.__enter__.return_value = infos()
                with patch.object(app.chess.engine.SimpleEngine, 'popen_uci', return_value=engine):
                    app.engine_worker(state)
                self.assertEqual(engine.analysis.call_args.kwargs['multipv'], 5)
                engine.configure.assert_called_with({'Skill Level':20,'UCI_LimitStrength':False})
                events = []
                while not state.ui_events.empty():
                    events.append(state.ui_events.get_nowait())
                lines = [event for event in events if event[0] == 'lines'][-1]
                self.assertEqual(lines[1], state.revision)
                self.assertEqual([line['rank'] for line in lines[3]], [1,2,3,4,5])
                engine.quit.assert_called_once()

    def test_human_profile_uses_native_bestmove_not_first_variation(self):
        for uci,rank in [('d2d4',2),('e2e3',None)]:
            with self.subTest(uci=uci), tempfile.TemporaryDirectory() as temp:
                executable=Path(temp)/'engine'
                executable.touch()
                with patch.object(app,'CONFIG',Path(temp)/'config.json'):
                    state=app.AnalysisState()
                    state.set_fen(chess.STARTING_FEN)
                    state.config.update(stockfish=str(executable),human_enabled=True,human_skill=7,seconds=0)
                    engine=MagicMock()
                    engine.options={'Skill Level':None,'UCI_LimitStrength':None}
                    engine.id={'name':'Test UCI'}
                    result=MagicMock()
                    def infos():
                        for index,move in enumerate(('e2e4','d2d4','g1f3','c2c4','g2g3'),1):
                            yield {'multipv':index,'pv':[chess.Move.from_uci(move)],'depth':12}
                        state.shutdown.set()
                    result.__iter__.side_effect=infos
                    result.wait.return_value=chess.engine.BestMove(chess.Move.from_uci(uci),None)
                    engine.analysis.return_value.__enter__.return_value=result
                    with patch.object(app.chess.engine.SimpleEngine,'popen_uci',return_value=engine):
                        app.engine_worker(state)
                    engine.configure.assert_called_with({'Skill Level':7,'UCI_LimitStrength':False})
                    self.assertEqual(engine.analysis.call_args.args[1].time,2)
                    events=[]
                    while not state.ui_events.empty():events.append(state.ui_events.get_nowait())
                    chosen=next(event[3] for event in events if event[0]=='human_line')
                    self.assertEqual(chosen['uci'],uci)
                    self.assertEqual(chosen['rank'],rank)
                    self.assertEqual(chosen['skill'],7)
                    self.assertNotEqual(chosen['uci'],'e2e4')
                    if rank is None:
                        self.assertEqual(chosen['score'],'—')
                        self.assertEqual(chosen['depth'],0)


if __name__ == '__main__':
    unittest.main()

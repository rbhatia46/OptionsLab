import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.options_lab import server

class HistoryTests(unittest.TestCase):
    def test_delete_and_clear_are_recoverable_and_keep_active_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs=Path(tmp)/'runs';runs.mkdir()
            jobs={'finished':{'status':'completed'},'active':{'status':'running'},'failed':{'status':'failed'}}
            for id,job in jobs.items():(runs/(id+'.json')).write_text(json.dumps(job))
            with patch.object(server,'RUNS',runs),patch.object(server,'JOBS',jobs):
                self.assertEqual(server.delete_runs(['finished'])['deleted'],['finished'])
                self.assertFalse((runs/'finished.json').exists())
                self.assertTrue((runs.parent/'deleted_runs/finished.json').exists())
                result=server.delete_runs()
                self.assertEqual(result['deleted'],['failed'])
                self.assertEqual(result['active_runs_kept'],1)
                self.assertTrue((runs/'active.json').exists())
                self.assertEqual(server.delete_runs(['missing'])['deleted'],[])

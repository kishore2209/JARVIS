import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from core.recovery import backup, restore
from core.knowledge import KnowledgeService
from core.tasks import TaskService
from core.jobs import JobService
from personal.service import PersonalService
from market.persistence import SQLiteStore
from market.durable_paper import DurablePaperEngine


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.store = SQLiteStore(str(self.root/'source.db'))
        self.key = Fernet.generate_key()
        KnowledgeService(self.store).ingest(title='Plan', text='Private position sizing evidence', source='local:plan', readers=['owner'])
        self.engine = DurablePaperEngine(self.store); self.engine.set_kill_switch(False)

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def test_restore_drill_preserves_data_and_blocks_actions(self):
        task = TaskService(self.store); task.handlers['READ'] = lambda p, c: {}
        submitted = task.submit('READ', {}, idempotency_key='test', correlation_id='restore-test')
        jobs = JobService(self.store, PersonalService(self.store))
        jobs.register('morning', 'DAILY_PLAN', datetime.now(timezone.utc))
        manifest = backup(self.store, self.root/'snapshot.enc', self.key)
        self.assertNotIn(b'Private position', (self.root/'snapshot.enc').read_bytes())
        result = restore(self.root/'snapshot.enc', self.root/'recovered.db', self.key)
        recovered = SQLiteStore(str(self.root/'recovered.db'))
        try:
            self.assertTrue(DurablePaperEngine(recovered).kill_switch)
            self.assertEqual(TaskService(recovered).get(submitted['id'])['state'], 'FAILED')
            self.assertFalse(JobService(recovered, PersonalService(recovered)).list()[0]['enabled'])
            self.assertFalse(KnowledgeService(recovered).retrieve('sizing', principal='owner')['empty'])
            self.assertEqual(result['source_snapshot_at'], manifest['created_at'])
            self.assertEqual(recovered.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            recovered.close()

    def test_tamper_and_wrong_key_leave_no_plaintext(self):
        backup(self.store, self.root/'snapshot.enc', self.key)
        with self.assertRaises(ValueError):
            restore(self.root/'snapshot.enc', self.root/'bad.db', Fernet.generate_key())
        raw = bytearray((self.root/'snapshot.enc').read_bytes()); raw[80] ^= 1
        (self.root/'snapshot.enc').write_bytes(raw)
        with self.assertRaises(ValueError):
            restore(self.root/'snapshot.enc', self.root/'bad.db', self.key)
        self.assertFalse((self.root/'bad.db').exists())

    def test_never_overwrite_existing_files(self):
        backup(self.store, self.root/'snapshot.enc', self.key)
        with self.assertRaises(FileExistsError):
            backup(self.store, self.root/'snapshot.enc', self.key)
        (self.root/'existing.db').write_text('keep me')
        with self.assertRaises(FileExistsError):
            restore(self.root/'snapshot.enc', self.root/'existing.db', self.key)
        self.assertEqual((self.root/'existing.db').read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()

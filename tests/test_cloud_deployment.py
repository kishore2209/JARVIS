import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import subprocess
from threading import Event
import unittest
from jarvis_cloud import configure_environment, supervise


class FakeProcess:
    def __init__(self, exited=False):
        self.exited=exited;self.terminated=False;self.killed=False
    def poll(self): return 1 if self.exited else None
    def terminate(self): self.terminated=True;self.exited=True
    def wait(self,timeout): return 1
    def kill(self): self.killed=True;self.exited=True


class CloudTests(unittest.TestCase):
    def env(self):
        return {'RENDER_EXTERNAL_HOSTNAME':'jarvis-test.onrender.com', 'JARVIS_API_TOKEN':'test-owner-'*4}

    def test_platform_origin_and_persistent_settings(self):
        env=self.env();env['PORT']='12345'
        self.assertEqual(configure_environment(env),'https://jarvis-test.onrender.com')
        self.assertEqual(env['JARVIS_PORT'],'12345')
        self.assertEqual(env['JARVIS_DB_PATH'],'/var/data/jarvis.db')
        self.assertEqual(env['JARVIS_CORS_ORIGINS'],'https://jarvis-test.onrender.com')
        self.assertNotIn('*',env['JARVIS_ALLOWED_HOSTS'])
        self.assertEqual(env['JARVIS_MARKET_PROVIDER'],'MOCK')

    def test_custom_domain_keeps_platform_health_hostname(self):
        env=self.env();env['JARVIS_PUBLIC_URL']='https://jarvis.example.com/'
        configure_environment(env)
        self.assertIn('jarvis.example.com',env['JARVIS_ALLOWED_HOSTS'])
        self.assertIn('jarvis-test.onrender.com',env['JARVIS_ALLOWED_HOSTS'])

    def test_cloud_rejects_missing_auth_http_and_ephemeral_settings(self):
        for override in ({'JARVIS_API_TOKEN':''},{'JARVIS_PUBLIC_URL':'http://jarvis.example'},
                         {'JARVIS_PUBLIC_URL':'https://user:pass@jarvis.example'},
                         {'JARVIS_DB_ENABLED':'false'},{'JARVIS_DB_PATH':'data/local.db'}):
            with self.subTest(override=override),self.assertRaises(ValueError):
                configure_environment({**self.env(),**override})

    def test_child_failure_stops_sibling(self):
        dead=FakeProcess(True);alive=FakeProcess();children=iter([dead,alive])
        status=supervise(Event(),commands=[['server'],['worker']],popen=lambda _:next(children))
        self.assertEqual(status,1);self.assertTrue(alive.terminated)

    def test_clean_shutdown_stops_both(self):
        children=[FakeProcess(),FakeProcess()];iterator=iter(children);stop=Event();stop.set()
        self.assertEqual(supervise(stop,commands=[['server'],['worker']],popen=lambda _:next(iterator)),0)
        self.assertTrue(all(p.terminated for p in children))

    def test_partial_launch_failure_stops_existing_child(self):
        first=FakeProcess();calls=[]
        def spawn(_):
            if calls: raise OSError('Cannot start worker')
            calls.append(1);return first
        with self.assertRaises(OSError):supervise(Event(),commands=[['server'],['worker']],popen=spawn)
        self.assertTrue(first.terminated)


if __name__=='__main__':unittest.main()

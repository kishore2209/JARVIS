"""Explicit-start worker for allowlisted, read-only durable jobs."""
import argparse
import signal
from threading import Event
from core.runtime import RuntimeConfig, create_runtime
from core.jobs import JobService


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true',help='Run one tick then exit')
    args=parser.parse_args()
    config=RuntimeConfig.from_environment()
    if not config.db_enabled:parser.error('Set JARVIS_DB_ENABLED=true to run durable jobs')
    runtime=create_runtime(config);jobs=JobService(runtime.store,runtime.personal);stop=Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    try:
        while not stop.is_set():
            jobs.tick()
            runtime.tasks.run_next()
            if args.once:break
            stop.wait(5)
    finally:runtime.close()

if __name__=='__main__':main()

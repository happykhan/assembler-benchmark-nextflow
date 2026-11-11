"""Measure a command's resident process tree without retrying its execution."""
import subprocess
import time


def measured_run(command, stdout, stderr, cwd, interval=0.02):
    import psutil

    start = time.monotonic()
    peak = 0
    with stdout.open('wb') as out, stderr.open('wb') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err, cwd=cwd)
        parent = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                members = [parent] + parent.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                members = []
            rss = 0
            for member in members:
                try:
                    rss += member.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            peak = max(peak, rss)
            time.sleep(interval)
        code = process.wait()
    return {'exit_code': code, 'elapsed_seconds': time.monotonic() - start,
            'process_tree_peak_rss_bytes': peak or None,
            'memory_method': 'Peak sampled sum of process-tree RSS; shared pages may be counted more than once',
            'memory_sampling_interval_seconds': interval}

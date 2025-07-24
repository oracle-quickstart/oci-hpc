#!/usr/bin/env python3
import os
import glob
import json
import time
import argparse
import logging
import orjson
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_INT64_MIN = -2**63
_INT64_MAX =  2**63 - 1

def lookup_slurm_job_id(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/environ", "rb") as envf:
            for var in envf.read().split(b"\0"):
                if var.startswith(b"SLURM_JOB_ID="):
                    return var.split(b"=", 1)[1].decode()
    except Exception:
        pass
    return "unknown"

def load_events_from_file(path: str):
    # with open(path, "r") as f:    
    #     data = json.load(f)
    with open(path, "rb") as f: 
        data = orjson.loads(f.read())    
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data

def group_events(events):
    spans = {}
    for ev in events:
        name = ev.get("name")
        phase = ev.get("ph")
        eid = ev.get("id")
        if name not in ("Group", "AllGather", "Broadcast", "AllReduce"):
            continue
        spans.setdefault(eid, {}).setdefault(name, {})[phase] = ev
    return spans

def safe_set_attr(span, key, value):
    if isinstance(value, int):
        if _INT64_MIN <= value <= _INT64_MAX:
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value))
    else:
        span.set_attribute(key, value)

def process_file(path: str, tempo_endpoint: str):
    logger.info(f"Processing file: {path}")
    events = load_events_from_file(path)
    if not events:
        logger.warning(f"{path} is empty, skipping")
        return

    pid = next(
        (ev.get("pid") or ev.get("args", {}).get("pid") for ev in events if "pid" in ev or "args" in ev),
        None
    )
    slurm_job_id = lookup_slurm_job_id(pid) if pid else "unknown"
    service_name = f"slurm-job-{slurm_job_id}"

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=tempo_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    spans_data = group_events(events)
    ts_vals = [ev["ts"] for ev in events if "ts" in ev]
    start_us = min(ts_vals)
    end_us = max(ts_vals)
    total_ns = int((end_us - start_us) * 1_000)

    base_ns = time.time_ns()
    trace_start = base_ns
    trace_end = base_ns + total_ns

    file_name = os.path.basename(path)
    root = tracer.start_span(f"file-trace-{file_name}", start_time=trace_start)
    safe_set_attr(root, "file.name", file_name)
    safe_set_attr(root, "slurm.job_id", slurm_job_id)
    if pid is not None:
        safe_set_attr(root, "process.pid", pid)

    for eid, group in spans_data.items():
        for op in ("Group", "AllGather", "Broadcast", "AllReduce"):
            b = group.get(op, {}).get("b")
            e = group.get(op, {}).get("e")
            if not b or not e:
                continue

            offset_ns = int((b["ts"] - start_us) * 1_000)
            span_dur_ns = int((e["ts"] - b["ts"]) * 1_000)
            span_start = trace_start + offset_ns
            span_end = span_start + span_dur_ns

            span = tracer.start_span(
                f"{op}-{eid}",
                start_time=span_start,
                context=trace.set_span_in_context(root)
            )

            pid_child = b.get("pid") or b.get("args", {}).get("pid")
            if pid_child is not None:
                safe_set_attr(span, "process.pid", pid_child)
            for k, v in b.get("args", {}).items():
                safe_set_attr(span, f"arg.{k}", v)
            span.end(end_time=span_end)

    root.end(end_time=trace_end)
    provider.shutdown()
    logger.info(f"[OK] pushed trace for {file_name} under service {service_name}")

class JsonFileHandler(FileSystemEventHandler):
    def __init__(self, pattern, endpoint):
        self.pattern = pattern
        self.endpoint = endpoint

    def on_created(self, event):
        if event.is_directory or not glob.fnmatch.fnmatch(event.src_path, self.pattern):
            return
        try:
            process_file(event.src_path, self.endpoint)
        except Exception as e:
            logger.error(f"[ERROR] Failed to process {event.src_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Export NCCL traces to Tempo using OTLP")
    parser.add_argument("-d", "--input-dir", default="/tmp", help="Directory to watch")
    parser.add_argument("-p", "--pattern", default="*.txt", help="File pattern to match")
    parser.add_argument("-e", "--tempo-endpoint", default="localhost:4317", help="Tempo OTLP/gRPC endpoint")
    args = parser.parse_args()

    event_handler = JsonFileHandler(pattern=args.pattern, endpoint=args.tempo_endpoint)
    observer = Observer()
    observer.schedule(event_handler, args.input_dir, recursive=False)
    observer.start()

    logger.info(f"Watching {args.input_dir} for {args.pattern} files")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
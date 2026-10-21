"""Experimental loopback gateway for OpenVINO GenAI; no product dependency.

Runs one CPU pipeline and one request at a time. Stateless generate calls never
start a chat or preserve a previous request's KV state. Logs contain no prompts.
"""

import argparse
import json
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--request-timeout", type=float, default=300)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.threads < 1 or args.request_timeout <= 0:
        parser.error("invalid resource limits")
    import openvino_genai as genai
    pipeline = genai.LLMPipeline(args.model, "CPU", INFERENCE_NUM_THREADS=args.threads, NUM_STREAMS=1)
    tokenizer = pipeline.get_tokenizer()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, value, code=200):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                self.send({"status": "ok", "runtime": "openvino", "version": genai.__version__,
                           "device": "CPU", "prompt_state": "stateless"})
            elif path == "/slots":
                self.send([{"id": 0, "is_processing": lock.locked()}])
            else:
                self.send({"error": "NOT_FOUND"}, 404)

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8 * 1024 * 1024:
                    self.send({"error": "INVALID_BODY_SIZE"}, 413)
                    return
                body = json.loads(self.rfile.read(size))
                path = urlsplit(self.path).path
                with lock:
                    if path == "/slots/0":
                        # There is no persisted chat/KV state to erase.
                        self.send({"id_slot": 0, "stateless": True})
                    elif path == "/tokenize":
                        tokens = tokenizer.encode(body["content"], add_special_tokens=body.get("add_special", False))
                        self.send({"tokens": tokens.input_ids.data[0].tolist()})
                    elif path == "/v1/chat/completions":
                        self.generate(body)
                    else:
                        self.send({"error": "NOT_FOUND"}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                # Exception messages can contain source text: emit only a type.
                self.send({"error": type(exc).__name__}, 500)

        def generate(self, body):
            if body.get("stream") or body.get("temperature", 0) != 0:
                self.send({"error": "UNSUPPORTED_EXPERIMENT_SETTINGS"}, 422)
                return
            prompt = tokenizer.apply_chat_template(body["messages"], True,
                                                   extra_context={"enable_thinking": False})
            limit = int(body.get("max_tokens", 4096))
            input_tokens = tokenizer.encode(prompt, add_special_tokens=False).input_ids.data.shape[1]
            if limit < 1 or input_tokens + limit + 256 > 16384:
                self.send({"error": "CONTEXT_LIMIT"}, 422)
                return
            config = genai.GenerationConfig()
            config.max_new_tokens = limit
            config.do_sample = False
            config.rng_seed = int(body.get("seed", 42))
            config.apply_chat_template = False
            if "json_schema" in body:
                config.structured_output_config = genai.StructuredOutputConfig(json_schema=json.dumps(body["json_schema"]))
            started = time.monotonic()
            cancelled = False
            def stream(_):
                nonlocal cancelled
                disconnected = bool(select.select([self.connection], [], [], 0)[0]) and not self.connection.recv(1, socket.MSG_PEEK)
                cancelled = disconnected or time.monotonic() - started > args.request_timeout
                return genai.StreamingStatus.CANCEL if cancelled else genai.StreamingStatus.RUNNING
            result = pipeline.generate(prompt, config, streamer=stream)
            if cancelled:
                self.send({"error": "REQUEST_CANCELLED_OR_TIMEOUT"}, 504)
                return
            metrics = result.perf_metrics
            generated = metrics.get_num_generated_tokens()
            self.send({"model": "latency-generation", "choices": [{"message": {
                "role": "assistant", "content": result.texts[0]},
                "finish_reason": "length" if generated >= limit else "stop"}],
                "usage": {"prompt_tokens": input_tokens, "completion_tokens": generated,
                          "total_tokens": input_tokens + generated}})

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

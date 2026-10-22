import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
SERVICE = os.getenv("SERVICE_NAME", "api")
PRODUCTS = [{"id":"sku-100","name":"Everyday Backpack","price":39.99},{"id":"sku-200","name":"Ceramic Mug","price":12.50}]
class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == "/health": self.send_json(200, {"status":"ok","service":SERVICE})
        elif self.path == "/products" and SERVICE == "catalog": self.send_json(200, {"items":PRODUCTS})
        elif self.path == "/cart" and SERVICE == "cart": self.send_json(200, {"items":[],"count":0,"note":"demo only"})
        else: self.send_json(200, {"service":SERVICE,"message":"Retail Shop demo API"})
    def do_POST(self):
        if self.path != "/checkout" or SERVICE != "checkout":
            self.send_json(404, {"error":"not_found"}); return
        size = int(self.headers.get("Content-Length","0"))
        try: body = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError: self.send_json(400, {"error":"invalid_json"}); return
        self.send_json(202, {"status":"accepted","demo_order_id":"demo-001","received":body,"note":"No payment or persistent order created"})
    def log_message(self, fmt, *args): print(fmt % args, flush=True)
if __name__ == "__main__": ThreadingHTTPServer(("0.0.0.0",8000),Handler).serve_forever()

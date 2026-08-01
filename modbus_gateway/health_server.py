from flask import Flask
from simulators import base_machine
from simulators.hipot_tester import HiPotTester
import threading
import time
import urllib.request



def create_health_app(machine,lock):
    app = Flask(__name__)
    # routes
    @app.route("/ping")
    def ping():
        return {"status": "ok"}
    
    @app.route("/health")
    def health():
        try:
            with lock:
                return machine.sample_health().to_dict()
        except Exception as e:
            return ({"error": "failed to read machine health", "detail": str(e)}, 500)
    
    return app




if __name__ == "__main__":
    
    tester = HiPotTester(station_id="HIPOT-HEALTH SMOKE")
    lock = threading.Lock()
    app = create_health_app(tester, lock)

    server_thread = threading.Thread(
        target=app.run,
        kwargs={"port": 5021, "use_reloader": False},
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.5)  # give the dev server a moment to bind before hitting it

    with urllib.request.urlopen("http://127.0.0.1:5021/ping") as response:
        print("Ping check:", response.status, response.read().decode())
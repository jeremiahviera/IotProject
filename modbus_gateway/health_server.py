from flask import Flask
from simulators import base_machine
from simulators.hipot_tester import HiPotTester
import threading
import time
import urllib.request



def create_health_app(machine, lock, latest_test_result_ref=None):
    app = Flask(__name__)
    if latest_test_result_ref is None:
        latest_test_result_ref = {"value": None}
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

    @app.route("/test_result")
    def test_result():
        """Traceability data for the last completed test (unit_serial,
        job_order_id, operator_id, fail_reason) -- out-of-band from
        Modbus for the same reason machine health is, see the register
        map's design notes."""
        with lock:
            result = latest_test_result_ref.get("value")
        if result is None:
            return ({"error": "no test has completed yet"}, 404)
        return result

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
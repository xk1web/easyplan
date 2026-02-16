from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from scheduler import generate_schedule


class RequestHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/generate":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)

            employees = data.get("employees", [])
            days = data.get("days", [])
            raw_unavailable = data.get("unavailable", [])
            unavailable = []

            for emp_name, day_name in raw_unavailable:
                if emp_name in employees and day_name in days:
                    emp_index = employees.index(emp_name)
                    day_index = days.index(day_name)
                    unavailable.append((emp_index, day_index))


            schedule = generate_schedule(employees, days, unavailable)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(schedule).encode())
        else:
            self.send_response(404)
            self.end_headers()


def run():
    server_address = ("", 5000)
    httpd = HTTPServer(server_address, RequestHandler)
    print("Server running on port 5000...")
    httpd.serve_forever()


if __name__ == "__main__":
    run()

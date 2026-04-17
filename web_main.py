"""Entry point for the kindle2notion web interface."""

import os
import socket

from web.app import create_app

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000


def _get_candidate_ipv4_addresses() -> list[str]:
    addresses = []

    try:
        hostname_addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        addresses.extend(hostname_addresses)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            addresses.insert(0, probe.getsockname()[0])
    except OSError:
        pass

    seen = set()
    candidates = []
    for address in addresses:
        if address.startswith("127."):
            continue
        if address in seen:
            continue
        seen.add(address)
        candidates.append(address)
    return candidates


def _print_access_urls(host: str, port: int) -> None:
    print("")
    print("kindle2notion Web UI is starting.")
    print(f"Local access:   http://127.0.0.1:{port}")
    print(f"Local access:   http://localhost:{port}")

    if host == "0.0.0.0":
        lan_addresses = _get_candidate_ipv4_addresses()
        for address in lan_addresses:
            print(f"Wi-Fi access:   http://{address}:{port}")

        if not lan_addresses:
            print("Wi-Fi access:   Check this PC's IPv4 address with ipconfig.")

        print("")
        print("Open one of the Wi-Fi access URLs above from a phone on the same network.")
    else:
        print(f"Configured host: http://{host}:{port}")

    print("")


app = create_app()


if __name__ == "__main__":
    host = os.getenv("WEB_HOST", DEFAULT_HOST)
    port = int(os.getenv("WEB_PORT", str(DEFAULT_PORT)))
    _print_access_urls(host, port)
    app.run(host=host, port=port, threaded=True)

import os

# System SOCKS4 proxy (127.0.0.1:10808) is not supported by httpx (only SOCKS5).
# Setting NO_PROXY=* disables env-based proxy detection in httpx before any
# test client is built — same workaround used for pip on this machine.
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

"""给 UTM 虚拟机用的最小 HTTP/CONNECT 代理。

宿主机流量走 VPN 隧道时，vmnet NAT 出不去；虚拟机把 apt/pip/npm 代理指到
指定的宿主机虚拟网桥地址与端口，由宿主机网络栈代发。绑定地址须显式指定。
用法：python3 tools/vm_proxy.py --host <宿主机虚拟网桥地址> [--port 3128]
"""
import argparse
import asyncio
from urllib.parse import urlsplit


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle(client_r, client_w):
    try:
        head = await client_r.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        client_w.close()
        return
    line, _, rest = head.partition(b"\r\n")
    method, target, version = line.decode("latin-1").split(" ", 2)
    try:
        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            up_r, up_w = await asyncio.open_connection(host, int(port))
            client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_w.drain()
        else:
            u = urlsplit(target)
            up_r, up_w = await asyncio.open_connection(u.hostname, u.port or 80)
            path = (u.path or "/") + (f"?{u.query}" if u.query else "")
            up_w.write(f"{method} {path} {version}\r\n".encode("latin-1") + rest)
    except OSError:
        client_w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        client_w.close()
        return
    await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True, help="显式指定宿主机虚拟网桥地址")
    p.add_argument("--port", type=int, default=3128)
    a = p.parse_args()
    server = await asyncio.start_server(handle, a.host, a.port)
    print(f"proxy listening on {a.host}:{a.port}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

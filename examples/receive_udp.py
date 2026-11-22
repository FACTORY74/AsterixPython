"""Receive ASTERIX UDP datagrams and print normalised track updates."""

from __future__ import annotations

import argparse
import asyncio
import socket
from collections.abc import AsyncIterator

from asterix import DecodeContext, Decoder, SchemaRegistry
from asterix.normalize import TrackUpdate, normalise

EDITIONS = {21: "2.7", 48: "1.32", 62: "1.21"}


async def datagrams(group: str, port: int) -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        socket.inet_aton(group) + socket.inet_aton("0.0.0.0"),
    )
    sock.setblocking(False)
    try:
        while True:
            payload, _source = await loop.sock_recvfrom(sock, 65_535)
            yield payload
    finally:
        sock.close()


async def run(group: str, port: int) -> None:
    decoder = Decoder(
        registry=SchemaRegistry.builtin(),
        context=DecodeContext(editions=EDITIONS, validation="compatible"),
    )
    async for payload in datagrams(group, port):
        # A datagram may contain more than one ASTERIX message.
        for message in decoder.decode_datagram(payload):
            for event in normalise(message):
                if isinstance(event, TrackUpdate):
                    print(event)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    asyncio.run(run(args.group, args.port))


if __name__ == "__main__":
    main()

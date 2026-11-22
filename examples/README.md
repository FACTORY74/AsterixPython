# Intended usage examples

These are runnable examples for the library described in `architecture.md`.

The three editions used in examples are an initial vertical slice only. The
library's coverage target is every publicly specified ASTERIX category and
published edition; examples are deliberately small enough to teach one workflow
without listing the complete support matrix.

## Examples

- `decode_file.py` incrementally decodes concatenated ASTERIX messages from a
  binary capture with explicit category editions.
- `encode_record.py` creates a CAT062 record by item identifier; the encoder
  derives FSPEC, item lengths, and outer LEN.
- `receive_udp.py` receives UDP datagrams, decodes them, and yields normalised
  track updates without coupling the receiver to a map product.
- `kody_tracks_service.py` turns the same pipeline into an independent Kody v1
  GeoJSON data-layer service.

The examples intentionally select editions explicitly. Real deployments should
put this mapping, receiver limits, endpoints, retention, and timing policy in a
reviewed configuration file or service configuration API.

## Commands

```powershell
uv run --python 3.15 python examples/decode_file.py capture.ast
uv run --python 3.15 python examples/encode_record.py output.ast
uv run --python 3.15 python examples/receive_udp.py --group 239.1.2.3 --port 8600
uv run --python 3.15 --with fastapi --with uvicorn uvicorn examples.kody_tracks_service:app --port 8018
```


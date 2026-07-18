# System tests

Tests in this layer use real Aegis services across process boundaries. They
must not silently skip when selected; use `make up && make bootstrap` before
running `make test-system`.

from evergrowth.core.runtime_singleton import RuntimeSingleton


def test_persistent_runtime_singleton_blocks_duplicate_and_releases(tmp_path):
    first = RuntimeSingleton.acquire(tmp_path)
    assert first is not None

    try:
        assert RuntimeSingleton.acquire(tmp_path) is None
    finally:
        first.release()

    second = RuntimeSingleton.acquire(tmp_path)
    assert second is not None
    second.release()

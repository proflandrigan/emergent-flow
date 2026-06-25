def test_package_imports():
    import emergentflow
    from emergentflow import ir  # noqa: F401

    assert emergentflow.__version__ == "0.2.0"

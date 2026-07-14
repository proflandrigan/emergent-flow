def test_package_imports():
    import emergentflow
    from emergentflow import ir  # noqa: F401

    assert emergentflow.__version__

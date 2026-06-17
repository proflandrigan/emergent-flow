def test_package_imports():
    import colonymind
    from colonymind import ir  # noqa: F401

    assert colonymind.__version__ == "0.2.0"

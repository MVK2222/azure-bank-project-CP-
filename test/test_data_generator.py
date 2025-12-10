"""
Unit tests for the data generation utilities in data/data_generator.py.

These tests validate deterministic behavior when seeding the random generator and
that KYC document generation writes expected artifacts (kyc_docs directory and zip file).

Note: tests use pytest fixtures `tmp_path` and `monkeypatch` to isolate filesystem side-effects.
"""

import random
import pandas as pd
from data import data_generator as dg


def test_generate_customer_deterministic(tmp_path):
    """
    Ensure that when the global random seed is set the customer generator produces
    a deterministic number of rows and predictable CustomerID format.

    Steps:
        1. Seed random with a fixed value.
        2. Generate N customers.
        3. Assert DataFrame shape and basic column presence/format.
    """
    # Make generator deterministic
    random.seed(42)

    df, coords = dg.generate_customer_data(5)
    # Basic schema checks
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] == 5
    assert "CustomerID" in df.columns
    # CustomerID uses prefix CUST
    assert all(c.startswith("CUST") for c in df["CustomerID"])
    assert isinstance(coords, dict)
    assert len(coords) == 5


def test_generate_kyc_docs_writes_files(tmp_path, monkeypatch):
    """
    Validate that generate_kyc_docs writes document files into a local directory and
    produces a zip archive when executed. Uses a temporary working directory to avoid
    polluting the repository.

    Steps:
        1. Seed random for repeatability.
        2. Generate a small customer and account set.
        3. chdir into tmp path and call generate_kyc_docs.
        4. Assert kyc_docs directory and kyc_documents.zip exist and returned DataFrame shape.
    """
    # Create small customers and accounts in temp dir by monkeypatching os.makedirs and zip
    random.seed(123)
    df_cust, _ = dg.generate_customer_data(3)
    df_acct = dg.generate_account_data(df_cust)

    # Ensure generator writes the files into a tempdir by chdir
    monkeypatch.chdir(tmp_path)
    docs = dg.generate_kyc_docs(df_cust, df_acct)

    # After generation, kyc_docs and zip should exist
    assert (tmp_path / "kyc_docs").exists()
    assert (tmp_path / "kyc_documents.zip").exists()
    assert isinstance(docs, pd.DataFrame)
    assert docs.shape[0] >= 1

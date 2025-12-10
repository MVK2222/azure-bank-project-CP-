"""
Synthetic data generator for testing the ingestion pipeline.

Generates customer, account, KYC, ATM and UPI CSVs and sample KYC document files.
This module is intended to create small datasets for local testing and demos.

Primary functions exposed:
- build_address(city, state) -> (address_str, postal_code, lat, lon)
- generate_customer_data(n) -> (DataFrame, dict(CustomerID -> (lat, lon)))
- generate_account_data(customers_df) -> DataFrame
- generate_kyc_docs(customers_df, accounts_df=None) -> DataFrame
- generate_atm_transactions(accounts_df, n=1000) -> DataFrame
- generate_upi_events(accounts_df, n=1000, customers_coords=None) -> DataFrame

This file is intentionally standalone and has minimal external dependencies
(other than pandas) so it can be used in CI, demos, or locally without cloud.

Design notes and intended use-cases:
- Produce small, realistic-looking datasets for ETL development and unit tests.
- Maintain internal consistency where feasible (balances change when withdrawals succeed,
  KYC tiers reflect documents generated, UPI P2P credits may move money between accounts).
- Outputs are non-sensitive placeholder data; DO NOT use for production purposes.

The code below favors readability and clarity over micro-optimizations since it is
targeted at demos and educational scenarios.
"""

import pandas as pd
import random
import datetime
import os
import zipfile
from typing import Optional, Tuple, Dict

# --- Configuration ---
NUM_CUSTOMERS = 50
MAX_ACCOUNTS_PER_CUST = 1
NUM_ATM_TXNS = 100
NUM_UPI_TXNS = 100

# Banks List
BANKS = ["Azure Bank", "HDFC Bank", "SBI", "ICICI Bank", "HSBC", "Axis Bank"]
BANK_DOMAINS = {
    "Azure Bank": "azure",
    "HDFC Bank": "hdfc",
    "SBI": "sbi",
    "ICICI Bank": "icici",
    "HSBC": "hsbc",
    "Axis Bank": "axis",
}
BRANCHES = ["M G Road", "Indiranagar", "Hitech City", "Bandra West", "Connaught Place", "Salt Lake"]

# Cities & States (used to choose realistic addresses and coordinates)
LOCATIONS = [
    ("Hyderabad", "Telangana"),
    ("Bangalore", "Karnataka"),
    ("Mumbai", "Maharashtra"),
    ("Delhi", "Delhi"),
    ("Chennai", "Tamil Nadu"),
    ("Kolkata", "West Bengal"),
    ("Pune", "Maharashtra"),
    ("Ahmedabad", "Gujarat"),
]

# Email Providers
EMAILS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com"]

# Devices used in UPI events (helps exercise device-based alerting rules)
DEVICES = ["iPhone 13", "Samsung S22", "OnePlus 9", "Pixel 6", "Xiaomi 12", "Realme 11X"]


# Helper: build a full, Nominatim-friendly address and return (address_str, postal_code, lat, lon)
def build_address(city: str, state: str) -> Tuple[str, str, float, float]:
    """
    Return a realistic-looking address string and postal code for the given city/state.

    This helper tries to return a curated, real landmark address (with coordinates)
    for better geocoding and more stable coordinates used by geo-velocity testing.

    If a curated address for the requested city is not available the function synthesizes
    a plausible address (house number, street, locality) and randomly picks a latitude/longitude
    inside a simple bounding box for the city.

    Important: The function uses the global `random` module: set a seed in tests if you
    require deterministic output.
    """

    # Curated real/landmark addresses (improve geocoding hit rate) with coordinates
    REAL_ADDRESSES = {
        "Hyderabad": [
            ("Banjara Hills Rd, Banjara Hills, Hyderabad 500034, Telangana, India", "500034", 17.4240, 78.4284),
            ("Hitech City Rd, Hitech City, Hyderabad 500081, Telangana, India", "500081", 17.4435, 78.3767),
            ("Gachibowli Main Rd, Gachibowli, Hyderabad 500032, Telangana, India", "500032", 17.4444, 78.3800),
        ],
        "Bangalore": [
            ("MG Road, Bengaluru 560001, Karnataka, India", "560001", 12.9716, 77.5946),
            ("Indiranagar, Bengaluru 560038, Karnataka, India", "560038", 12.9718, 77.6413),
            ("Whitefield Main Rd, Whitefield, Bengaluru 560066, Karnataka, India", "560066", 12.9697, 77.7499),
        ],
        "Mumbai": [
            ("Marine Drive, Mumbai 400020, Maharashtra, India", "400020", 18.9436, 72.8238),
            ("Bandra West, Mumbai 400050, Maharashtra, India", "400050", 19.0553, 72.8307),
            ("Andheri West, Mumbai 400058, Maharashtra, India", "400058", 19.1190, 72.8465),
        ],
        "Delhi": [
            ("Connaught Place, New Delhi 110001, Delhi, India", "110001", 28.6304, 77.2177),
            ("Saket, New Delhi 110017, Delhi, India", "110017", 28.5245, 77.2104),
            ("Dwarka, New Delhi 110075, Delhi, India", "110075", 28.5800, 77.0500),
        ],
        "Chennai": [
            ("Anna Salai, Chennai 600002, Tamil Nadu, India", "600002", 13.0627, 80.2707),
            ("T Nagar, Chennai 600017, Tamil Nadu, India", "600017", 13.0422, 80.2397),
            ("Adyar, Chennai 600020, Tamil Nadu, India", "600020", 13.0114, 80.2499),
        ],
        "Kolkata": [
            ("Park Street, Kolkata 700016, West Bengal, India", "700016", 22.5485, 88.3523),
            ("Salt Lake, Kolkata 700091, West Bengal, India", "700091", 22.5726, 88.4175),
            ("Howrah, Howrah 711101, West Bengal, India", "711101", 22.5900, 88.3100),
        ],
        "Pune": [
            ("Koregaon Park, Pune 411001, Maharashtra, India", "411001", 18.5314, 73.8763),
            ("Shivaji Nagar, Pune 411005, Maharashtra, India", "411005", 18.5204, 73.8567),
            ("Baner, Pune 411045, Maharashtra, India", "411045", 18.5599, 73.7815),
        ],
        "Ahmedabad": [
            ("CG Road, Ahmedabad 380009, Gujarat, India", "380009", 23.0286, 72.5626),
            ("Ashram Road, Ahmedabad 380009, Gujarat, India", "380009", 23.0258, 72.5996),
            ("Navrangpura, Ahmedabad 380009, Gujarat, India", "380009", 23.0378, 72.5635),
        ],
    }

    # If we have curated addresses for the requested city prefer those for stability
    if city in REAL_ADDRESSES and REAL_ADDRESSES[city]:
        addr, pcode, lat, lon = random.choice(REAL_ADDRESSES[city])
        return addr, pcode, lat, lon

    # Fallback synthesized address with approximate city bounding boxes
    city_localities = {
        "Hyderabad": ["Banjara Hills", "Gachibowli", "Hitech City", "Kukatpally", "Secunderabad", "Jubilee Hills"],
        "Bangalore": ["Indiranagar", "Koramangala", "Whitefield", "Jayanagar", "Hebbal"],
        "Mumbai": ["Bandra West", "Andheri", "Powai", "Colaba", "Dadar"],
        "Delhi": ["Connaught Place", "Karol Bagh", "Saket", "Dwarka", "Lajpat Nagar"],
        "Chennai": ["T Nagar", "Adyar", "Anna Nagar", "Velachery", "Besant Nagar"],
        "Kolkata": ["Salt Lake", "Park Street", "Howrah", "New Town", "Alipore"],
        "Pune": ["Koregaon Park", "Shivaji Nagar", "Baner", "Pimpri", "Kothrud"],
        "Ahmedabad": ["Navrangpura", "Satellite", "CG Road", "Paldi", "Maninagar"],
    }
    city_streets = {
        "Hyderabad": ["Banjara Hills Rd", "Hitech City Rd", "Gachibowli Main Rd", "Road No. 1"],
        "Bangalore": ["MG Road", "Brigade Road", "Koramangala 5th Block", "Whitefield Main Rd"],
        "Mumbai": ["Linking Road", "SV Road", "Marine Drive", "Powai Lake Rd"],
        "Delhi": ["Janpath", "Ring Road", "Lodi Road", "Saket Road"],
        "Chennai": ["Anna Salai", "Raja Annamalai Rd", "Adyar Main Rd", "Velachery Rd"],
        "Kolkata": ["Park Street", "BBD Bagh Rd", "Salt Lake Sector V", "Howrah Bridge Road"],
        "Pune": ["FC Road", "Bund Garden Rd", "Koregaon Park Rd", "Baner Rd"],
        "Ahmedabad": ["CG Road", "Ashram Road", "SG Highway", "Navrangpura Main Rd"],
    }
    # city bounding boxes for randomized lat/lon: (min_lat, max_lat, min_lon, max_lon)
    city_bounds = {
        "Hyderabad": (17.35, 17.50, 78.30, 78.55),
        "Bangalore": (12.85, 13.05, 77.50, 77.80),
        "Mumbai": (18.90, 19.20, 72.75, 72.95),
        "Delhi": (28.50, 28.72, 77.00, 77.30),
        "Chennai": (12.95, 13.13, 80.20, 80.30),
        "Kolkata": (22.45, 22.65, 88.25, 88.45),
        "Pune": (18.45, 18.65, 73.70, 73.95),
        "Ahmedabad": (23.00, 23.10, 72.50, 72.65),
    }
    city_postal_codes = {
        "Hyderabad": [500001, 500034, 500081, 500072],
        "Bangalore": [560001, 560025, 560047, 560071],
        "Mumbai": [400001, 400020, 400050, 400076],
        "Delhi": [110001, 110003, 110017, 110049],
        "Chennai": [600001, 600018, 600028, 600033],
        "Kolkata": [700001, 700091, 700156, 700135],
        "Pune": [411001, 411004, 411045, 411057],
        "Ahmedabad": [380001, 380009, 380015, 380059],
    }

    locality = random.choice(city_localities.get(city, [random.choice(BRANCHES)]))
    street = random.choice(city_streets.get(city, ["Main Road", "Station Road", "Market Road"]))
    house_no = f"{random.randint(1, 999)}{('/' + str(random.randint(1, 99))) if random.random() < 0.25 else ''}"
    postal_code = str(random.choice(city_postal_codes.get(city, [random.randint(110000, 999999)])))

    # generate a random lat/lon inside the city bounding box if available
    if city in city_bounds:
        min_lat, max_lat, min_lon, max_lon = city_bounds[city]
        lat = round(random.uniform(min_lat, max_lat), 6)
        lon = round(random.uniform(min_lon, max_lon), 6)
    else:
        # global fallback: pick some lat/lon in the India-ish box
        lat = round(random.uniform(12.0, 28.0), 6)
        lon = round(random.uniform(72.0, 88.0), 6)

    address = f"{house_no}, {street}, {locality}, {city} {postal_code}, {state}, India"
    return address, postal_code, lat, lon


# --- Data Generators ---

def generate_customer_data(n: int) -> Tuple[pd.DataFrame, Dict[str, Tuple[float, float]]]:
    """
    Generate `n` synthetic customers as a pandas DataFrame and return a mapping of
    CustomerID -> (lat, lon) for internal geolocation use.

    The generated DataFrame contains demographic and KYC status fields used by the
    ingestion pipeline and ETL notebooks. This function synthesizes realistic but
    non-sensitive personal attributes (names, DOB, occupation, income) suitable for
    demo and testing only.

    Returns:
        tuple: (customers_df, customers_coords)
            - customers_df (pd.DataFrame): customer metadata (CustomerID, Name, DOB, Address, KYC_Status, AnnualIncome, ...)
            - customers_coords (dict): mapping CustomerID -> (lat, lon) used for geo-enrichment

    Contract / expected shape:
      - Input: integer n > 0
      - Output: pandas DataFrame with column `CustomerID` and a dict mapping same IDs to (lat, lon)

    Edge cases considered:
      - n == 0 -> returns empty DataFrame and empty dict
      - Randomness -> not deterministic unless seed set externally
    """
    customers = []
    customers_coords: Dict[str, Tuple[float, float]] = {}

    # Name pools (created once)
    first_names = [
        "Aarav",
        "Vivaan",
        "Aditya",
        "Arjun",
        "Sai",
        "Ishaan",
        "Kabir",
        "Riya",
        "Saanvi",
        "Ananya",
        "Diya",
        "Pooja",
        "Sneha",
        "Priya",
        "Kavya",
    ]
    last_names = [
        "Sharma",
        "Reddy",
        "Patel",
        "Singh",
        "Kumar",
        "Mehta",
        "Nair",
        "Gupta",
        "Iyer",
        "Das",
        "Verma",
        "Kapoor",
        "Chopra",
        "Joshi",
        "Bose",
    ]

    # Defensive: if n is zero or negative return empty structures
    if n <= 0:
        return pd.DataFrame(customers), customers_coords

    for i in range(1, n + 1):
        # Choose a random city/state for the customer
        city, state = random.choice(LOCATIONS)
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        gender = random.choice(["Male", "Female"])  # simple gender assignment for demo

        # Create a random DOB between 1970-01-01 and ~2011 (covering broad age ranges)
        cust_dob_date = datetime.date(1970, 1, 1) + datetime.timedelta(days=random.randint(0, 15000))
        age = (datetime.date.today() - cust_dob_date).days // 365

        # Choose occupation based on age to keep the data plausible
        if age <= 25:
            occupation_choices = ["Student", "Engineer", "Artist", "Doctor", "Business"]
        elif age <= 40:
            occupation_choices = ["Engineer", "Doctor", "Artist", "Business"]
        elif age <= 60:
            occupation_choices = ["Engineer", "Doctor", "Business", "Artist"]
        else:
            occupation_choices = ["Retired", "Business", "Engineer"]

        occupation = random.choice(occupation_choices)

        # Annual income sampling based on occupation bucket
        income_ranges = {
            "Student": (0, 200000),
            "Engineer": (300000, 2000000),
            "Doctor": (500000, 5000000),
            "Artist": (200000, 1000000),
            "Business": (300000, 5000000),
            "Retired": (100000, 500000),
        }
        low, high = income_ranges.get(occupation, (300000, 5000000))
        annual_income = random.randint(low, high)

        # Build a full, geocodable address for this customer and also receive coordinates
        addr_str, postal_code, lat, lon = build_address(city, state)

        cust_id = f"CUST{i:03d}"
        cust = {
            "CustomerID": cust_id,
            "FirstName": first_name,
            "LastName": last_name,
            "DOB": cust_dob_date.isoformat(),
            "Gender": gender,
            "Email": f"{first_name.lower()}.{last_name.lower()}@{random.choice(EMAILS)}",
            "Phone": f"+91 {random.randint(6000000000, 9999999999)}",
            "Address": addr_str,
            "City": city,
            "State": state,
            "ZipCode": postal_code,
            "KYC_Status": random.choices(
                ["Verified", "Pending", "Under Review", "Rejected", "Expired"], weights=[70, 15, 8, 5, 2]
            )[0],
            # KYC_Tier will be adjusted later based on the actual docs generated
            "KYC_Tier": "Unknown",
            "Occupation": occupation,
            "AnnualIncome": annual_income,
        }
        customers.append(cust)
        # store coordinates in an external mapping (not written to CSV) so geolocation can be reused
        customers_coords[cust_id] = (lat, lon)

    return pd.DataFrame(customers), customers_coords


def generate_account_data(customers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate account rows for each customer provided.

    Each customer receives between 1 and `MAX_ACCOUNTS_PER_CUST` accounts.

    Returns a DataFrame with fields like AccountNumber, CustomerID, IFSC_Code, Balance, AccountOpenDate.

    Implementation notes:
    - Account numbers are sequential for readability.
    - Balance is randomized to create a variety of account states (low balance, high net-worth, etc.).
    """
    accounts = []
    # Each customer gets 1 to MAX accounts
    acct_counter = 10000

    for _, cust in customers_df.iterrows():
        # number of accounts per customer (can be configured by MAX_ACCOUNTS_PER_CUST)
        num_accounts = random.randint(1, MAX_ACCOUNTS_PER_CUST)
        for _ in range(num_accounts):
            bank = random.choice(BANKS)
            acct_type = random.choice(["Savings", "Current", "Salary"])
            acct_counter += 1

            acct = {
                # 10-digit account numbers
                "AccountNumber": f"{acct_counter:010d}",
                "CustomerID": cust["CustomerID"],
                "AccountHolderName": f"{cust['FirstName']} {cust['LastName']}",
                "BankName": bank,
                "BranchName": random.choice(BRANCHES),
                "IFSC_Code": f"{BANK_DOMAINS[bank].upper()}{random.randint(10000, 99999)}",
                "AccountType": acct_type,
                "AccountStatus": random.choice(["Active", "Active", "Active", "Dormant"]),
                "AccountOpenDate": (
                    datetime.date(2015, 1, 1) + datetime.timedelta(days=random.randint(0, 3000)
                )
                ).isoformat(),
                "Balance": round(random.uniform(1000.0, 500000.0), 2),
                "Currency": random.choice(["INR", "USD", "EUR"]),
            }
            accounts.append(acct)
    return pd.DataFrame(accounts)


def generate_kyc_docs(customers_df: pd.DataFrame, accounts_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Generate KYC document metadata and write sample text files into ./kyc_docs and a zip archive.

    Side effects:
    - Creates/updates files under ./kyc_docs and writes kyc_documents.zip
    - Updates accounts_df in-place with KYC-related columns when provided

    Behavior summary:
    - If accounts_df is provided, create one document per account (account-level KYC).
    - Otherwise fallback to creating one document per customer.

    Note: This writes intentionally simple, non-sensitive placeholder text files for demo purposes.
    """
    docs = []
    os.makedirs("kyc_docs", exist_ok=True)

    # Helper to randomize verification status
    def random_verification_status():
        return random.choices(
            ["Verified", "Pending", "Under Review", "Rejected", "Expired"], weights=[70, 15, 8, 5, 2]
        )[0]

    if accounts_df is not None and not accounts_df.empty:
        # Create one doc per account - useful when KYC is tracked at account level in the pipeline
        for _, acct in accounts_df.iterrows():
            cust_id = acct["CustomerID"]
            acct_num = acct["AccountNumber"]

            doc_type = random.choice(["Aadhaar", "PAN", "Passport"])  # sample document types
            doc_id = f"DOC-{cust_id}-{acct_num}-{random.randint(100,999)}"
            # doc_num format varies by document type (Aadhaar has groups of digits)
            doc_num = (
                f"{random.randint(1000, 9999)} {random.randint(1000, 9999)}"
                if doc_type == "Aadhaar"
                else f"ABC{random.randint(1000, 9999)}D"
            )
            verification_status = random_verification_status()
            filename = f"{cust_id}_{acct_num}_{doc_type}.txt"

            doc = {
                "DocumentID": doc_id,
                "CustomerID": cust_id,
                "AccountNumber": acct_num,
                "DocumentType": doc_type,
                "DocumentNumber": doc_num,
                "IssueDate": (datetime.date(2015, 1, 1) + datetime.timedelta(days=random.randint(0, 2000))).isoformat(),
                "ExpiryDate": (datetime.date(2025, 1, 1) + datetime.timedelta(days=random.randint(0, 2000))).isoformat(),
                "VerificationStatus": verification_status,
                "DocumentFile": filename,
            }
            docs.append(doc)

            # write dummy file with status and account info
            with open(os.path.join("kyc_docs", filename), "w") as f:
                # Placeholder KYC file content is intentionally simple for demos/tests
                f.write(f"KYC DOCUMENT\nType: {doc_type}\nCustomerID: {cust_id}\nAccountNumber: {acct_num}\nID: {doc_num}\nStatus: {verification_status}")

            # update customer's tier: use Aadhaar as Tier 1 for demo purposes
            tier = "Tier 1" if doc_type == "Aadhaar" else "Tier 2"
            customers_df.loc[customers_df["CustomerID"] == cust_id, "KYC_Tier"] = tier

            # ensure account-level columns exist (idempotent creation)
            if "KYC_Done" not in accounts_df.columns:
                accounts_df["KYC_Done"] = False
            if "KYC_DocID" not in accounts_df.columns:
                accounts_df["KYC_DocID"] = ""
            if "KYC_DocumentVerificationStatus" not in accounts_df.columns:
                accounts_df["KYC_DocumentVerificationStatus"] = ""

            # populate account rows with generated doc info
            accounts_df.loc[accounts_df["AccountNumber"] == acct_num, "KYC_DocID"] = doc_id
            accounts_df.loc[accounts_df["AccountNumber"] == acct_num, "KYC_DocumentVerificationStatus"] = verification_status
            accounts_df.loc[accounts_df["AccountNumber"] == acct_num, "KYC_Done"] = (verification_status == "Verified")

    else:
        # Fallback: create one doc per customer (previous behaviour)
        for _, cust in customers_df.iterrows():
            cust_id = cust["CustomerID"]
            doc_type = random.choice(["Aadhaar", "PAN", "Passport"])
            doc_id = f"DOC-{cust_id}-{random.randint(100, 999)}"
            doc_num = (
                f"{random.randint(1000, 9999)} {random.randint(1000, 9999)}"
                if doc_type == "Aadhaar"
                else f"ABC{random.randint(1000, 9999)}D"
            )
            verification_status = random_verification_status()
            filename = f"{cust_id}_{doc_type}.txt"

            doc = {
                "DocumentID": doc_id,
                "CustomerID": cust_id,
                "AccountNumber": None,
                "DocumentType": doc_type,
                "DocumentNumber": doc_num,
                "IssueDate": (datetime.date(2015, 1, 1) + datetime.timedelta(days=random.randint(0, 2000))).isoformat(),
                "ExpiryDate": (datetime.date(2025, 1, 1) + datetime.timedelta(days=random.randint(0, 2000))).isoformat(),
                "VerificationStatus": verification_status,
                "DocumentFile": filename,
            }
            docs.append(doc)

            with open(os.path.join("kyc_docs", filename), "w") as f:
                # writing simple KYC placeholder file for test/demo
                f.write(f"KYC DOCUMENT\nType: {doc_type}\nCustomerID: {cust_id}\nID: {doc_num}\nStatus: {verification_status}")

            tier = "Tier 1" if doc_type == "Aadhaar" else "Tier 2"
            customers_df.loc[customers_df["CustomerID"] == cust_id, "KYC_Tier"] = tier

    # Zip the docs for convenience when loading test datasets
    with zipfile.ZipFile("kyc_documents.zip", "w") as zipf:
        for root, dirs, files in os.walk("kyc_docs"):
            for file in files:
                zipf.write(os.path.join(root, file), file)

    # Post-process accounts to ensure no blanks in kyc fields - this makes downstream joins easier
    if accounts_df is not None:
        # create columns if missing
        if "KYC_Done" not in accounts_df.columns:
            accounts_df["KYC_Done"] = False
        if "KYC_DocID" not in accounts_df.columns:
            accounts_df["KYC_DocID"] = ""
        if "KYC_DocumentVerificationStatus" not in accounts_df.columns:
            accounts_df["KYC_DocumentVerificationStatus"] = ""

        # map customer-level KYC_Status as fallback
        cust_status_map = {}
        if "CustomerID" in customers_df.columns and "KYC_Status" in customers_df.columns:
            cust_status_map = customers_df.set_index("CustomerID")["KYC_Status"].to_dict()

        for idx, row in accounts_df.iterrows():
            # If account-level verification status is blank use customer-level status or Pending
            if (
                not row.get("KYC_DocumentVerificationStatus")
                or pd.isna(row.get("KYC_DocumentVerificationStatus"))
                or str(row.get("KYC_DocumentVerificationStatus")).strip() == ""
            ):
                fill_status = cust_status_map.get(row["CustomerID"], None)
                if not fill_status or pd.isna(fill_status):
                    fill_status = "Pending"
                accounts_df.at[idx, "KYC_DocumentVerificationStatus"] = fill_status

            is_verified = str(accounts_df.at[idx, "KYC_DocumentVerificationStatus"]).strip().lower() == "verified"
            accounts_df.at[idx, "KYC_Done"] = is_verified

            if not accounts_df.at[idx, "KYC_DocID"] or pd.isna(accounts_df.at[idx, "KYC_DocID"]):
                accounts_df.at[idx, "KYC_DocID"] = ""

    return pd.DataFrame(docs)


def generate_atm_transactions(accounts_df: pd.DataFrame, n: int = 1000) -> pd.DataFrame:
    """
    Generate synthetic ATM transactions for the given accounts DataFrame.

    Returns a DataFrame of transactions; this function mutates accounts_df's
    'Balance' column when withdrawals succeed.

    Logic & fraud-relevant rules:
        - Withdrawals can fail for insufficient funds or non-active accounts.
        - A small random failure rate (~2%) models terminal/network failures and introduces noise for alerting logic.
        - Balance updates are applied in-place to accounts_df so downstream UPI/ATM events see realistic balances.
    """
    txns = []
    start_time = datetime.datetime(2024, 1, 1)

    txn_types = ["Withdrawal", "Deposit", "BalanceEnquiry", "MiniStatement"]
    # weights favor withdrawals and deposits
    weights = [60, 25, 10, 5]

    for i in range(1, n + 1):
        # pick a random account by index so we can update it
        idx = accounts_df.sample(1).index[0]
        acct = accounts_df.loc[idx]
        balance_before = float(acct["Balance"])
        txn_time = start_time + datetime.timedelta(minutes=random.randint(1, 500000))

        txn_type = random.choices(txn_types, weights=weights)[0]

        amount = 0.0
        status = "Success"
        balance_after = balance_before

        if txn_type == "Withdrawal":
            amount = random.choice([500, 1000, 2000, 5000, 10000])
            # fail if insufficient funds or account not active
            if acct.get("AccountStatus", "Active") != "Active" or balance_before < amount:
                status = "Failed"
                balance_after = balance_before
            else:
                # small chance of failure even if funds available
                if random.random() < 0.02:
                    status = "Failed"
                    balance_after = balance_before
                else:
                    balance_after = round(balance_before - amount, 2)
        elif txn_type == "Deposit":
            amount = round(random.uniform(100.0, 50000.0), 2)
            # deposits usually succeed
            balance_after = round(balance_before + amount, 2)
        else:  # BalanceEnquiry or MiniStatement
            amount = 0.0
            status = "Success"
            balance_after = balance_before

        # Update the account balance in-place if changed
        if balance_after != balance_before:
            # update DataFrame so subsequent transactions can see new balance
            accounts_df.at[idx, "Balance"] = balance_after

        txn = {
            "TransactionID": f"ATM{i:06d}",
            "TransactionTime": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
            "TransactionType": txn_type,
            "TransactionStatus": status,
            "Amount": amount,
            "AccountNumber": acct["AccountNumber"],
            "BankName": acct["BankName"],
            "ATMID": f"ATM-{random.randint(1, 50):02d}",
            "ATM_Bank": random.choice(BANKS),
            # Replace simple branch location with a full address suitable for Nominatim
            "Location": build_address(random.choice([x[0] for x in LOCATIONS]), random.choice([x[1] for x in LOCATIONS]))[0],
            "BalanceBefore": round(balance_before, 2),
            "BalanceAfter": round(balance_after, 2),
        }
        txns.append(txn)
    return pd.DataFrame(txns)


def generate_upi_events(accounts_df: pd.DataFrame, n: int = 1000, customers_coords: Optional[dict] = None) -> pd.DataFrame:
    """
    Generate synthetic UPI transactions for given accounts.

    If customers_coords is provided (mapping CustomerID -> (lat, lon)) the payer's
    customer coordinates will be used as the GeoLocation for the UPI event. Otherwise
    a random city coordinate will be generated.

    Logic & fraud notes:
        - P2P transactions may credit a random payee account to model money movement between accounts.
        - Transactions may Fail if payer not Active or has insufficient funds; a small random failure rate exists to introduce noise.
        - GeoLocation uses the customer's coordinates when available so downstream geo-velocity alerts can be simulated deterministically.
    """
    txns = []
    start_time = datetime.datetime(2024, 1, 1)

    for i in range(1, n + 1):
        # Select a payer account by index so we can update the DataFrame in-place
        payer_idx = accounts_df.sample(1).index[0]
        payer = accounts_df.loc[payer_idx]
        payer_balance_before = float(payer.get("Balance", 0.0))
        cust_name = payer["AccountHolderName"].split()[0].lower()
        bank_domain = BANK_DOMAINS[payer["BankName"]]

        txn_time = start_time + datetime.timedelta(minutes=random.randint(1, 500000))

        txn_type = random.choice(["P2P", "P2M"])  # Peer to Peer or Merchant
        # Amount should be reasonable and not exceed a large fraction of balance usually
        amount = round(random.uniform(10.0, min(10000.0, max(100.0, payer_balance_before * 0.5 + 1000.0))), 2)

        # Determine if the transaction succeeds. P2P/P2M are debits for the payer.
        # If account not Active or insufficient funds, transaction may fail.
        status = "Success"
        if payer.get("AccountStatus", "Active") != "Active":
            status = "Failed"
        else:
            if payer_balance_before < amount:
                # Insufficient funds -> most likely fail
                status = random.choices(["Failed", "Pending"], weights=[80, 20])[0]
            else:
                # Small chance of failure due to network/processor
                if random.random() < 0.02:
                    status = "Failed"

        # Apply balance changes on success. For P2P, optionally credit a random payee account.
        payer_balance_after = payer_balance_before
        if status == "Success":
            payer_balance_after = round(payer_balance_before - amount, 2)
            accounts_df.at[payer_idx, "Balance"] = payer_balance_after

            if txn_type == "P2P":
                # credit a random different account as payee (best-effort)
                if len(accounts_df) > 1:
                    # try to pick a different account index
                    payee_idx = payer_idx
                    attempts = 0
                    while payee_idx == payer_idx and attempts < 5:
                        payee_idx = accounts_df.sample(1).index[0]
                        attempts += 1
                    if payee_idx != payer_idx:
                        payee_balance_before = float(accounts_df.at[payee_idx, "Balance"]) or 0.0
                        accounts_df.at[payee_idx, "Balance"] = round(payee_balance_before + amount, 2)

        # Determine GeoLocation (lat,lon) using customer mapping when available
        customer_id = payer.get("CustomerID", None)
        if customers_coords and customer_id in customers_coords:
            lat, lon = customers_coords[customer_id]
        else:
            # fallback: random city coordinate
            city = random.choice([x[0] for x in LOCATIONS])
            _, _, lat, lon = build_address(city, dict(LOCATIONS).get(city, ""))

        geo_str = f"{lat:.6f}, {lon:.6f}"

        txn = {
            "TransactionID": f"UPI{i:06d}",
            "TransactionTime": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
            "TransactionType": txn_type,
            "Status": status,
            "Amount": amount,
            "AccountNumber": payer["AccountNumber"],
            "BankName": payer["BankName"],
            "Payer_UPI_ID": f"{cust_name}{random.randint(1, 99)}@{bank_domain}",
            "Payee_UPI_ID": f"merchant{random.randint(1, 500)}@upi" if random.random() > 0.5 else f"friend{random.randint(1, 500)}@okaxis",
            "DeviceID": random.choice(DEVICES),
            "AppUsed": random.choice(["GPay", "PhonePe", "Paytm", "BHIM"]),
            # GeoLocation is now a lat, lon string (keeps column name unchanged)
            "GeoLocation": geo_str,
            "BalanceBefore": round(payer_balance_before, 2),
            "BalanceAfter": round(payer_balance_after, 2),
        }
        txns.append(txn)
    return pd.DataFrame(txns)


# --- Execution ---
if __name__ == "__main__":
    print("Generating Data...")
    df_cust, cust_coords = generate_customer_data(NUM_CUSTOMERS)
    df_acct = generate_account_data(df_cust)
    df_kyc = generate_kyc_docs(df_cust, df_acct)  # Generates CSV and ZIP
    df_atm = generate_atm_transactions(df_acct, NUM_ATM_TXNS)
    df_upi = generate_upi_events(df_acct, NUM_UPI_TXNS, customers_coords=cust_coords)

    # Saving
    df_cust.to_csv("customer.csv", index=False)
    df_acct.to_csv("account.csv", index=False)
    df_kyc.to_csv("kyc_metadata.csv", index=False)
    df_atm.to_csv("atm_transactions.csv", index=False)
    df_upi.to_csv("upi_events.csv", index=False)

    print("Generation Complete.")
    print(f"Customers: {len(df_cust)}")
    print(f"Accounts: {len(df_acct)}")
    print(f"KYC Docs: {len(df_kyc)}")
    print(f"ATM Txns: {len(df_atm)}")
    print(f"UPI Txns: {len(df_upi)}")

    # Preview
    print("\n--- Account Sample (Different Banks) ---")
    print(df_acct[["AccountNumber", "BankName", "IFSC_Code", "Balance"]].head())

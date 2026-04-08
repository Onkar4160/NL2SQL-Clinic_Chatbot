"""
setup_database.py — Clinic Management Database Setup

Creates the SQLite database `clinic.db` with 5 tables and populates it
with realistic dummy data for the NL2SQL chatbot demo.

Tables: patients, doctors, appointments, treatments, invoices
"""

import sqlite3
import random
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = "clinic.db"

SPECIALIZATIONS = ["Dermatology", "Cardiology", "Orthopedics", "General", "Pediatrics"]

DEPARTMENTS = {
    "Dermatology": "Skin & Aesthetics",
    "Cardiology": "Heart & Vascular",
    "Orthopedics": "Bone & Joint",
    "General": "General Medicine",
    "Pediatrics": "Child Health",
}

# Realistic Indian first / last names
FIRST_NAMES_MALE = [
    "Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Rohan", "Ishaan", "Karthik",
    "Mohit", "Rahul", "Vikram", "Nikhil", "Pranav", "Harsh", "Yash", "Amit",
    "Suresh", "Rajesh", "Manish", "Gaurav", "Deepak", "Ashish", "Kunal", "Varun",
    "Sahil", "Tushar", "Akash", "Ankur", "Dev", "Ravi",
]

FIRST_NAMES_FEMALE = [
    "Ananya", "Diya", "Priya", "Isha", "Kavya", "Meera", "Nisha", "Pooja",
    "Riya", "Sanya", "Tara", "Neha", "Shruti", "Aishwarya", "Sneha", "Divya",
    "Pallavi", "Swati", "Komal", "Jaya", "Aditi", "Bhavna", "Charvi", "Gauri",
    "Lakshmi", "Manju", "Nandini", "Rashmi", "Sarika", "Vidya",
]

LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Kumar", "Gupta", "Reddy", "Nair", "Joshi",
    "Mehta", "Desai", "Rao", "Iyer", "Menon", "Chopra", "Verma", "Mishra",
    "Das", "Bose", "Mukherjee", "Banerjee", "Thakur", "Kapoor", "Malhotra",
    "Saxena", "Agarwal",
]

CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
]

DOCTOR_NAMES = [
    # Dermatology
    "Dr. Anita Sharma", "Dr. Ravi Desai", "Dr. Sneha Kapoor",
    # Cardiology
    "Dr. Vikram Mehta", "Dr. Priya Iyer", "Dr. Arjun Reddy",
    # Orthopedics
    "Dr. Suresh Nair", "Dr. Kavya Joshi", "Dr. Rahul Patel",
    # General
    "Dr. Meera Das", "Dr. Aditya Verma", "Dr. Pooja Mishra",
    # Pediatrics
    "Dr. Karthik Rao", "Dr. Divya Bose", "Dr. Nikhil Thakur",
]

APPOINTMENT_STATUSES = ["Scheduled", "Completed", "Cancelled", "No-Show"]
APPOINTMENT_STATUS_WEIGHTS = [0.20, 0.50, 0.18, 0.12]

TREATMENT_NAMES = [
    "General Consultation", "Blood Test", "X-Ray", "ECG",
    "Skin Biopsy", "Physiotherapy", "Vaccination", "Ultrasound",
    "MRI Scan", "CT Scan", "Dental Cleaning", "Eye Exam",
    "Allergy Testing", "Cardiac Stress Test", "Bone Density Scan",
]

INVOICE_STATUSES = ["Paid", "Pending", "Overdue"]
INVOICE_STATUS_WEIGHTS = [0.50, 0.30, 0.20]


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    date_of_birth DATE,
    gender TEXT,
    city TEXT,
    registered_date DATE
);

CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    specialization TEXT,
    department TEXT,
    phone TEXT
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    doctor_id INTEGER,
    appointment_date DATETIME,
    status TEXT,
    notes TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

CREATE TABLE IF NOT EXISTS treatments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER,
    treatment_name TEXT,
    cost REAL,
    duration_minutes INTEGER,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    invoice_date DATE,
    total_amount REAL,
    paid_amount REAL,
    status TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);
"""


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _random_date(start: datetime, end: datetime) -> str:
    """Return a random date string between *start* and *end*."""
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")


def _random_datetime(start: datetime, end: datetime) -> str:
    """Return a random datetime string between *start* and *end*."""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    dt = start + timedelta(seconds=random_seconds)
    # Clamp hours to 8 AM – 8 PM to simulate clinic hours
    dt = dt.replace(hour=random.randint(8, 20), minute=random.choice([0, 15, 30, 45]))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _random_phone() -> str:
    """Generate a realistic Indian mobile number."""
    return f"+91-{random.randint(70000, 99999)}{random.randint(10000, 99999)}"


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def _insert_doctors(cur: sqlite3.Cursor) -> None:
    """Insert 15 doctors — 3 per specialization."""
    for idx, name in enumerate(DOCTOR_NAMES):
        spec = SPECIALIZATIONS[idx // 3]
        cur.execute(
            "INSERT INTO doctors (name, specialization, department, phone) VALUES (?, ?, ?, ?)",
            (name, spec, DEPARTMENTS[spec], _random_phone()),
        )
    logger.info("Inserted %d doctors", len(DOCTOR_NAMES))


def _insert_patients(cur: sqlite3.Cursor, count: int = 200) -> None:
    """Insert *count* patients with realistic Indian names and varied cities."""
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    for _ in range(count):
        gender = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_MALE if gender == "M" else FIRST_NAMES_FEMALE)
        last = random.choice(LAST_NAMES)

        # ~20 % chance of NULL email
        email = f"{first.lower()}.{last.lower()}@{'gmail' if random.random() > 0.5 else 'yahoo'}.com" if random.random() > 0.20 else None
        # ~15 % chance of NULL phone
        phone = _random_phone() if random.random() > 0.15 else None

        dob = _random_date(datetime(1950, 1, 1), datetime(2015, 12, 31))
        city = random.choice(CITIES)
        reg_date = _random_date(one_year_ago, now)

        cur.execute(
            "INSERT INTO patients (first_name, last_name, email, phone, date_of_birth, gender, city, registered_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (first, last, email, phone, dob, gender, city, reg_date),
        )
    logger.info("Inserted %d patients", count)


def _insert_appointments(cur: sqlite3.Cursor, num_patients: int, num_doctors: int, count: int = 500) -> list[tuple[int, str]]:
    """Insert *count* appointments and return list of (id, status) tuples."""
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    # Create a skewed doctor popularity list — some doctors get many more appointments
    popular_doctors = [1, 4, 7, 10, 13]  # one per specialization
    doctor_weights = [3 if d in popular_doctors else 1 for d in range(1, num_doctors + 1)]

    # Some patients are repeat visitors (ids 1-30 get extra appointments)
    repeat_patients = list(range(1, 31))

    appointments: list[tuple[int, str]] = []

    for _ in range(count):
        # 30 % chance of picking a repeat patient
        if random.random() < 0.30 and repeat_patients:
            patient_id = random.choice(repeat_patients)
        else:
            patient_id = random.randint(1, num_patients)

        doctor_id = random.choices(range(1, num_doctors + 1), weights=doctor_weights, k=1)[0]
        appt_date = _random_datetime(one_year_ago, now)
        status = random.choices(APPOINTMENT_STATUSES, weights=APPOINTMENT_STATUS_WEIGHTS, k=1)[0]

        # ~40 % chance of NULL notes
        notes = random.choice([
            "Follow-up required", "Routine check-up", "Patient reported improvement",
            "Referred to specialist", "Lab results pending", "Prescription renewed",
            None, None, None, None,  # weighted toward None
        ])

        cur.execute(
            "INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (patient_id, doctor_id, appt_date, status, notes),
        )
        appointments.append((cur.lastrowid, status))

    logger.info("Inserted %d appointments", count)
    return appointments


def _insert_treatments(cur: sqlite3.Cursor, appointments: list[tuple[int, str]], count: int = 350) -> None:
    """Insert *count* treatments linked ONLY to Completed appointments."""
    completed = [appt_id for appt_id, status in appointments if status == "Completed"]
    if not completed:
        logger.warning("No completed appointments found — skipping treatments")
        return

    for _ in range(count):
        appt_id = random.choice(completed)
        treatment = random.choice(TREATMENT_NAMES)
        cost = round(random.uniform(50.0, 5000.0), 2)
        duration = random.choice([15, 20, 30, 45, 60, 90, 120])

        cur.execute(
            "INSERT INTO treatments (appointment_id, treatment_name, cost, duration_minutes) "
            "VALUES (?, ?, ?, ?)",
            (appt_id, treatment, cost, duration),
        )
    logger.info("Inserted %d treatments", count)


def _insert_invoices(cur: sqlite3.Cursor, num_patients: int, count: int = 300) -> None:
    """Insert *count* invoices with ~50 % Paid, ~30 % Pending, ~20 % Overdue."""
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    for _ in range(count):
        patient_id = random.randint(1, num_patients)
        inv_date = _random_date(one_year_ago, now)
        total = round(random.uniform(100.0, 15000.0), 2)
        status = random.choices(INVOICE_STATUSES, weights=INVOICE_STATUS_WEIGHTS, k=1)[0]

        if status == "Paid":
            paid = total
        elif status == "Pending":
            paid = round(random.uniform(0, total * 0.5), 2)
        else:  # Overdue
            paid = 0.0

        cur.execute(
            "INSERT INTO invoices (patient_id, invoice_date, total_amount, paid_amount, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (patient_id, inv_date, total, paid, status),
        )
    logger.info("Inserted %d invoices", count)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Create the clinic database and populate it with dummy data."""
    random.seed(42)  # Reproducible data

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON")

    # Drop existing tables for idempotent re-runs
    for table in ("invoices", "treatments", "appointments", "doctors", "patients"):
        cur.execute(f"DROP TABLE IF EXISTS {table}")

    # Create schema
    cur.executescript(SCHEMA_DDL)
    logger.info("Schema created in %s", DB_PATH)

    # Insert data
    _insert_doctors(cur)
    _insert_patients(cur, count=200)
    appointments = _insert_appointments(cur, num_patients=200, num_doctors=15, count=500)
    _insert_treatments(cur, appointments, count=350)
    _insert_invoices(cur, num_patients=200, count=300)

    conn.commit()

    # Print summary
    summary_queries = {
        "patients": "SELECT COUNT(*) FROM patients",
        "doctors": "SELECT COUNT(*) FROM doctors",
        "appointments": "SELECT COUNT(*) FROM appointments",
        "treatments": "SELECT COUNT(*) FROM treatments",
        "invoices": "SELECT COUNT(*) FROM invoices",
    }
    counts = {name: cur.execute(q).fetchone()[0] for name, q in summary_queries.items()}
    conn.close()

    print(
        f"\n✅ Database setup complete!\n"
        f"Created {counts['patients']} patients, {counts['doctors']} doctors, "
        f"{counts['appointments']} appointments, {counts['treatments']} treatments, "
        f"{counts['invoices']} invoices\n"
    )


if __name__ == "__main__":
    main()

import sqlite3
from datetime import date, timedelta
import random
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import math

DB_PATH = "library.db"
DEFAULT_ID_TARGET = 100

# --------------------------
# LOGIC - LibraryDB (SQLite)
# --------------------------
class LibraryDB:
    def __init__(self, db_path=DB_PATH, id_target=DEFAULT_ID_TARGET):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        # Migrations
        self._migrate_persons_table()
        self._migrate_loans_table()
        # Seed initial data if needed
        self._seed_data()
        # Ensure id ranges for persons and books
        self._ensure_ids_range_for_persons(id_target)
        self._ensure_ids_range_for_books(id_target)
        # Ensure books >= persons
        self._ensure_min_books_equal_persons()
        # Seed some active loans
        self._seed_loans(min_loans=20, max_loans=50)
        # Ensure loan ids growth
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM loans WHERE returned_on IS NULL")
        active_loans = cur.fetchone()["cnt"] or 0
        if active_loans > 0:
            self._ensure_ids_range_for_loans(active_loans)
        # Fill missing or zero progress/time with random values so UI always shows stored percents or times
        self._fill_missing_progress_with_random()
        self._fill_missing_time_with_random()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            isbn TEXT UNIQUE,
            total_copies INTEGER NOT NULL DEFAULT 1
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT
            -- additional columns may be added by migration
        )""")
        # loans table includes progress and time_spent_minutes by default for new DBs
        cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            borrowed_on DATE NOT NULL,
            due_on DATE NOT NULL,
            returned_on DATE,
            progress INTEGER NOT NULL DEFAULT 0,
            time_spent_minutes INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(book_id) REFERENCES books(id),
            FOREIGN KEY(person_id) REFERENCES persons(id)
        )""")
        self.conn.commit()

    def _migrate_persons_table(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(persons)")
        existing_cols = {row["name"] for row in cur.fetchall()}

        migrations = {
            "phone": "TEXT",
            "address": "TEXT",
            "membership_id": "TEXT",
            "date_of_birth": "DATE",
            "notes": "TEXT",
            "preferred_contact": "TEXT"
        }
        for col, coltype in migrations.items():
            if col not in existing_cols:
                try:
                    cur.execute(f"ALTER TABLE persons ADD COLUMN {col} {coltype}")
                except Exception:
                    pass
        self.conn.commit()

    def _migrate_loans_table(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(loans)")
        existing = {row["name"] for row in cur.fetchall()}
        if "progress" not in existing:
            try:
                cur.execute("ALTER TABLE loans ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")
            except Exception:
                pass
        if "time_spent_minutes" not in existing:
            try:
                cur.execute("ALTER TABLE loans ADD COLUMN time_spent_minutes INTEGER NOT NULL DEFAULT 0")
            except Exception:
                pass
        self.conn.commit()

    def _seed_data(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM books")
        if cur.fetchone()["cnt"] == 0:
            books = [
                ("Clean Code", "Robert C. Martin", "9780132350884", 2),
                ("The Pragmatic Programmer", "Andrew Hunt", "9780201616224", 1),
                ("Introduction to Algorithms", "Thomas H. Cormen", "9780262033848", 1),
                ("Design Patterns", "Erich Gamma", "9780201633610", 1)
            ]
            cur.executemany("INSERT INTO books (title, author, isbn, total_copies) VALUES (?,?,?,?)", books)

        cur.execute("SELECT COUNT(*) AS cnt FROM persons")
        if cur.fetchone()["cnt"] == 0:
            example_persons = [
                ("Ana Popescu", "ana@example.com", "0712345678", "Str. Primăverii 10, București", "M-001", "1988-05-12", "email", "Studenta, preferă contact prin email"),
                ("Ion Ionescu", "ion@example.com", "0723456789", "Bd. Unirii 20, Cluj", "M-002", "1975-11-02", "phone", "Profesor universitar"),
                ("Maria Georgescu", "maria@example.com", "0734567890", "Str. Libertății 3, Iași", "M-003", "1992-07-23", "email", "Membru activ")
            ]
            cur.executemany("""
                INSERT INTO persons (name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes)
                VALUES (?,?,?,?,?,?,?,?)
            """, example_persons)
            self.conn.commit()

        # Ensure we have at least DEFAULT_ID_TARGET persons
        self._ensure_min_persons(DEFAULT_ID_TARGET)

    def _ensure_min_persons(self, target):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM persons")
        cnt = cur.fetchone()["cnt"] or 0
        if cnt >= target:
            return

        first_names = ["Ana", "Ioana", "Maria", "Elena", "Andrei", "Ion", "Mihai", "Alexandru", "Gabriel", "Cristian",
                       "Radu", "Paul", "Adriana", "Dan", "Daniela", "Lucian", "Vlad", "Laura", "Oana", "Catalin"]
        last_names = ["Popescu", "Ionescu", "Georgescu", "Dumitrescu", "Stan", "Marin", "Florescu", "Petrescu", "Nae",
                      "Rusu", "Matei", "Constantinescu", "Enache", "Iancu", "Vasilescu", "Barbu", "Nicolae", "Iorga"]
        streets = ["Str. Libertății", "Str. Primăverii", "Bd. Unirii", "Str. Mihai Eminescu", "Str. Independenței",
                   "Str. 1 Mai", "Str. Victoriei", "Str. Ion Creangă", "Str. Tudor Vladimirescu", "Str. Ștefan cel Mare"]
        cities = ["București", "Cluj", "Iași", "Timișoara", "Brașov", "Constanța", "Craiova", "Galați", "Ploiești", "Oradea"]
        notes_samples = [
            "Membru activ", "Studenta", "Profesor universitar", "Preferă contact telefonic",
            "Lucrează la IT", "Iubește cărțile", "Este din străinătate", "Voluntar la bibliotecă", ""
        ]

        to_create = target - cnt
        persons = []
        start_index = cnt + 1
        for i in range(start_index, start_index + to_create):
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            name = f"{fn} {ln}"
            email_local = f"{fn.lower()}.{ln.lower()}{random.randint(1,9999)}"
            email = f"{email_local}@example.com"
            phone = f"07{random.randint(10000000, 99999999)}"
            street = random.choice(streets)
            city = random.choice(cities)
            address = f"{street} {random.randint(1, 200)}, {city}"
            membership_id = f"M-{i:04d}"
            year = random.randint(1950, 2005)
            month = random.randint(1, 12)
            if month == 2:
                day = random.randint(1, 28)
            elif month in (4, 6, 9, 11):
                day = random.randint(1, 30)
            else:
                day = random.randint(1, 31)
            date_of_birth = date(year, month, day).isoformat()
            preferred_contact = random.choice(["email", "phone", "sms"])
            notes = random.choice(notes_samples)
            persons.append((name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes))

        cur.executemany("""
            INSERT INTO persons (name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, persons)
        self.conn.commit()

    def _ensure_min_books_equal_persons(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM persons")
        persons = cur.fetchone()["cnt"] or 0
        cur.execute("SELECT COUNT(*) AS cnt FROM books")
        books = cur.fetchone()["cnt"] or 0
        if books >= persons:
            return

        to_create = persons - books

        sample_titles = [
            "Algorithms Unlocked", "Practical Python", "Modern Databases", "Deep Learning Intro",
            "Data Science Essentials", "Effective Testing", "Refactoring Explained", "Concurrency in Practice",
            "Network Programming", "UX Design Basics", "Cloud Fundamentals", "Secure Coding", "Linux System Admin",
            "Microservices Patterns", "Applied Cryptography", "Numerical Methods", "Graph Theory", "AI for Everyone"
        ]
        sample_authors = [
            "A. Author", "B. Writer", "C. Researcher", "D. Engineer", "E. Specialist",
            "F. Developer", "G. Analyst", "H. Designer", "I. Scientist", "J. Teacher"
        ]

        inserted = 0
        attempts = 0
        books_to_insert = []
        while inserted < to_create and attempts < to_create * 5:
            attempts += 1
            title = f"{random.choice(sample_titles)} {random.randint(1,9999)}"
            author = random.choice(sample_authors)
            isbn_candidate = f"978{random.randint(1000000000, 9999999999)}"
            cur.execute("SELECT 1 FROM books WHERE isbn=?", (isbn_candidate,))
            if cur.fetchone():
                continue
            total_copies = random.randint(1, 3)
            books_to_insert.append((title, author, isbn_candidate, total_copies))
            inserted += 1

        if books_to_insert:
            try:
                cur.executemany("INSERT INTO books (title, author, isbn, total_copies) VALUES (?,?,?,?)", books_to_insert)
                self.conn.commit()
            except sqlite3.IntegrityError:
                for b in books_to_insert:
                    try:
                        cur.execute("INSERT INTO books (title, author, isbn, total_copies) VALUES (?,?,?,?)", b)
                    except sqlite3.IntegrityError:
                        continue
                self.conn.commit()

    def _seed_loans(self, min_loans=20, max_loans=50):
        """
        Seed active loans; when inserting, assign a random percent (0..100) to progress
        and a random time_spent_minutes to simulate reading time.
        """
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM loans WHERE returned_on IS NULL")
        current_active = cur.fetchone()["cnt"] or 0
        target = random.randint(min_loans, max_loans)
        if current_active >= target:
            return

        to_create = target - current_active

        cur.execute("SELECT id FROM persons")
        persons = [r["id"] for r in cur.fetchall()]
        if not persons:
            return

        cur.execute("SELECT id FROM books")
        books = [r["id"] for r in cur.fetchall()]
        if not books:
            return

        created = 0
        attempts = 0
        max_attempts = to_create * 10
        while created < to_create and attempts < max_attempts:
            attempts += 1
            book_id = random.choice(books)
            if self.available_copies(book_id) <= 0:
                continue
            person_id = random.choice(persons)
            days_ago = random.randint(0, 60)
            borrowed_on = date.today() - timedelta(days=days_ago)
            due_in = random.randint(7, 30)
            due_on = borrowed_on + timedelta(days=due_in)
            prog = random.randint(0, 100)
            time_minutes = random.randint(5, 600)  # between 5 minutes and 10 hours
            try:
                cur.execute(
                    "INSERT INTO loans (book_id, person_id, borrowed_on, due_on, progress, time_spent_minutes) VALUES (?,?,?,?,?,?)",
                    (book_id, person_id, borrowed_on.isoformat(), due_on.isoformat(), prog, time_minutes)
                )
                created += 1
            except sqlite3.IntegrityError:
                continue

        self.conn.commit()

    def _ensure_ids_range_for_persons(self, target):
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM persons")
        existing = {row["id"] for row in cur.fetchall()}
        missing = [i for i in range(1, target + 1) if i not in existing]
        if not missing:
            cur.execute("SELECT MAX(id) AS m FROM persons")
            m = cur.fetchone()["m"] or 0
            self._set_sqlite_sequence('persons', m)
            return

        first_names = ["Ana", "Ioana", "Maria", "Elena", "Andrei", "Ion", "Mihai", "Alexandru", "Gabriel", "Cristian",
                       "Radu", "Paul", "Adriana", "Dan", "Daniela", "Lucian", "Vlad", "Laura", "Oana", "Catalin"]
        last_names = ["Popescu", "Ionescu", "Georgescu", "Dumitrescu", "Stan", "Marin", "Florescu", "Petrescu", "Nae",
                      "Rusu", "Matei", "Constantinescu", "Enache", "Iancu", "Vasilescu", "Barbu", "Nicolae", "Iorga"]
        streets = ["Str. Libertății", "Str. Primăverii", "Bd. Unirii", "Str. Mihai Eminescu", "Str. Independenței",
                   "Str. 1 Mai", "Str. Victoriei", "Str. Ion Creangă", "Str. Tudor Vladimirescu", "Str. Ștefan cel Mare"]
        cities = ["București", "Cluj", "Iași", "Timișoara", "Brașov", "Constanța", "Craiova", "Galați", "Ploiești", "Oradea"]
        notes_samples = ["Membru activ", "Studenta", "Profesor universitar", "Preferă contact telefonic",
                         "Lucrează la IT", "Iubește cărțile", "Este din străinătate", "Voluntar la bibliotecă", ""]

        to_insert = []
        for i in missing:
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            name = f"{fn} {ln}"
            email = f"{fn.lower()}.{ln.lower()}{random.randint(1,9999)}@example.com"
            phone = f"07{random.randint(10000000, 99999999)}"
            street = random.choice(streets)
            city = random.choice(cities)
            address = f"{street} {random.randint(1,200)}, {city}"
            membership_id = f"M-{i:04d}"
            year = random.randint(1950, 2005)
            month = random.randint(1, 12)
            if month == 2:
                day = random.randint(1, 28)
            elif month in (4, 6, 9, 11):
                day = random.randint(1, 30)
            else:
                day = random.randint(1, 31)
            date_of_birth = date(year, month, day).isoformat()
            preferred_contact = random.choice(["email", "phone", "sms"])
            notes = random.choice(notes_samples)
            to_insert.append((i, name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes))

        cur.executemany("""
            INSERT INTO persons (id, name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, to_insert)
        self.conn.commit()

        cur.execute("SELECT MAX(id) AS m FROM persons")
        m = cur.fetchone()["m"] or 0
        self._set_sqlite_sequence('persons', m)

    def _ensure_ids_range_for_books(self, target):
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM books")
        existing = {row["id"] for row in cur.fetchall()}
        missing = [i for i in range(1, target + 1) if i not in existing]
        if not missing:
            cur.execute("SELECT MAX(id) AS m FROM books")
            m = cur.fetchone()["m"] or 0
            self._set_sqlite_sequence('books', m)
            return

        sample_titles = [
            "Algorithms Unlocked", "Practical Python", "Modern Databases", "Deep Learning Intro",
            "Data Science Essentials", "Effective Testing", "Refactoring Explained", "Concurrency in Practice",
            "Network Programming", "UX Design Basics", "Cloud Fundamentals", "Secure Coding", "Linux System Admin",
            "Microservices Patterns", "Applied Cryptography", "Numerical Methods", "Graph Theory", "AI for Everyone"
        ]
        sample_authors = [
            "A. Author", "B. Writer", "C. Researcher", "D. Engineer", "E. Specialist",
            "F. Developer", "G. Analyst", "H. Designer", "I. Scientist", "J. Teacher"
        ]

        to_insert = []
        used_isbns = set()
        cur.execute("SELECT isbn FROM books WHERE isbn IS NOT NULL")
        for r in cur.fetchall():
            used_isbns.add(r["isbn"])

        for i in missing:
            title = f"{random.choice(sample_titles)} {random.randint(1,9999)}"
            author = random.choice(sample_authors)
            isbn = None
            for _ in range(10):
                isbn_candidate = f"978{random.randint(1000000000, 9999999999)}"
                if isbn_candidate not in used_isbns:
                    isbn = isbn_candidate
                    used_isbns.add(isbn)
                    break
            total_copies = random.randint(1, 3)
            to_insert.append((i, title, author, isbn, total_copies))

        cur.executemany("""
            INSERT INTO books (id, title, author, isbn, total_copies)
            VALUES (?,?,?,?,?)
        """, to_insert)
        self.conn.commit()

        cur.execute("SELECT MAX(id) AS m FROM books")
        m = cur.fetchone()["m"] or 0
        self._set_sqlite_sequence('books', m)

    def _ensure_ids_range_for_loans(self, target):
        if target <= 0:
            return

        cur = self.conn.cursor()
        cur.execute("SELECT id FROM loans WHERE returned_on IS NULL")
        existing = {row["id"] for row in cur.fetchall()}
        missing = [i for i in range(1, target + 1) if i not in existing]
        if not missing:
            cur.execute("SELECT MAX(id) AS m FROM loans")
            m = cur.fetchone()["m"] or 0
            self._set_sqlite_sequence('loans', m)
            return

        cur.execute("SELECT id FROM persons")
        persons = [r["id"] for r in cur.fetchall()]
        cur.execute("SELECT id FROM books")
        books = [r["id"] for r in cur.fetchall()]
        if not persons or not books:
            return

        to_insert = []
        for missing_id in missing:
            found = False
            for _ in range(10):
                book_id = random.choice(books)
                if self.available_copies(book_id) <= 0:
                    continue
                person_id = random.choice(persons)
                days_ago = random.randint(0, 60)
                borrowed_on = date.today() - timedelta(days=days_ago)
                due_in = random.randint(7, 30)
                due_on = borrowed_on + timedelta(days=due_in)
                prog = random.randint(0, 100)
                time_minutes = random.randint(5, 600)
                to_insert.append((missing_id, book_id, person_id, borrowed_on.isoformat(), due_on.isoformat(), prog, time_minutes))
                found = True
                break
            if not found:
                continue

        if to_insert:
            try:
                cur.executemany("""
                    INSERT INTO loans (id, book_id, person_id, borrowed_on, due_on, progress, time_spent_minutes)
                    VALUES (?,?,?,?,?,?,?)
                """, to_insert)
                self.conn.commit()
            except sqlite3.IntegrityError:
                for row in to_insert:
                    try:
                        cur.execute("""
                            INSERT INTO loans (id, book_id, person_id, borrowed_on, due_on, progress, time_spent_minutes)
                            VALUES (?,?,?,?,?,?,?)
                        """, row)
                    except sqlite3.IntegrityError:
                        continue
                self.conn.commit()

        cur.execute("SELECT MAX(id) AS m FROM loans")
        m = cur.fetchone()["m"] or 0
        self._set_sqlite_sequence('loans', m)

    def _set_sqlite_sequence(self, table_name, seq_value):
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            if not cur.fetchone():
                return
            cur.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table_name,))
            if cur.fetchone():
                cur.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (seq_value, table_name))
            else:
                cur.execute("INSERT INTO sqlite_sequence(name, seq) VALUES (?,?)", (table_name, seq_value))
            self.conn.commit()
        except Exception:
            pass

    # Books
    def list_books(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM books ORDER BY id")
        return cur.fetchall()

    def add_book(self, title, author, isbn, total_copies):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO books (title, author, isbn, total_copies) VALUES (?,?,?,?)",
                    (title, author, isbn, total_copies))
        self.conn.commit()
        return cur.lastrowid

    def edit_book(self, book_id, title, author, isbn, total_copies):
        cur = self.conn.cursor()
        cur.execute("UPDATE books SET title=?, author=?, isbn=?, total_copies=? WHERE id=?",
                    (title, author, isbn, total_copies, book_id))
        self.conn.commit()

    def delete_book(self, book_id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM books WHERE id=?", (book_id,))
        self.conn.commit()

    # Persons
    def list_persons(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes
            FROM persons
            ORDER BY id
        """)
        return cur.fetchall()

    def list_subscribers(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes
            FROM persons
            WHERE membership_id IS NOT NULL AND TRIM(membership_id) <> ''
            ORDER BY id
        """)
        return cur.fetchall()

    def get_person(self, person_id):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes
            FROM persons
            WHERE id=?
        """, (person_id,))
        return cur.fetchone()

    def add_person(self, name, email=None, phone=None, address=None, membership_id=None,
                   date_of_birth=None, preferred_contact=None, notes=None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO persons (name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes))
        self.conn.commit()
        return cur.lastrowid

    def edit_person(self, person_id, name, email=None, phone=None, address=None, membership_id=None,
                    date_of_birth=None, preferred_contact=None, notes=None):
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE persons
            SET name=?, email=?, phone=?, address=?, membership_id=?, date_of_birth=?, preferred_contact=?, notes=?
            WHERE id=?
        """, (name, email, phone, address, membership_id, date_of_birth, preferred_contact, notes, person_id))
        self.conn.commit()

    def delete_person(self, person_id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM persons WHERE id=?", (person_id,))
        self.conn.commit()

    # Loans
    def available_copies(self, book_id):
        cur = self.conn.cursor()
        cur.execute("SELECT total_copies FROM books WHERE id=?", (book_id,))
        r = cur.fetchone()
        if not r:
            return 0
        total = r["total_copies"] or 0
        cur.execute("SELECT COUNT(*) AS cnt FROM loans WHERE book_id=? AND returned_on IS NULL", (book_id,))
        borrowed = cur.fetchone()["cnt"] or 0
        return total - borrowed

    def borrow_book(self, book_id, person_id, days=14):
        if self.available_copies(book_id) <= 0:
            raise Exception("No copies available")
        borrowed_on = date.today()
        due_on = borrowed_on + timedelta(days=days)
        cur = self.conn.cursor()
        # initial progress is a random percent; initial time spent is a small random minutes
        prog = random.randint(0, 100)
        time_minutes = random.randint(0, 120)  # initial time between 0 and 2 hours
        cur.execute("INSERT INTO loans (book_id, person_id, borrowed_on, due_on, progress, time_spent_minutes) VALUES (?,?,?,?,?,?)",
                    (book_id, person_id, borrowed_on.isoformat(), due_on.isoformat(), prog, time_minutes))
        self.conn.commit()
        return cur.lastrowid

    def return_book(self, loan_id):
        cur = self.conn.cursor()
        cur.execute("UPDATE loans SET returned_on=? WHERE id=?", (date.today().isoformat(), loan_id))
        self.conn.commit()

    def set_loan_progress(self, loan_id, percent):
        try:
            p = int(percent)
        except Exception:
            raise Exception("Percent must be an integer")
        if p < 0 or p > 100:
            raise Exception("Percent must be between 0 and 100")
        cur = self.conn.cursor()
        cur.execute("UPDATE loans SET progress=? WHERE id=?", (p, loan_id))
        self.conn.commit()

    def set_loan_time(self, loan_id, minutes):
        try:
            m = int(minutes)
        except Exception:
            raise Exception("Minutes must be an integer")
        if m < 0:
            raise Exception("Minutes must be >= 0")
        cur = self.conn.cursor()
        cur.execute("UPDATE loans SET time_spent_minutes=? WHERE id=?", (m, loan_id))
        self.conn.commit()

    def randomize_progress_for_active_loans(self, force=False):
        """
        Set a new random progress (0..100) for all active (not returned) loans.
        If force==False only fill loans with progress IS NULL or =0.
        If force==True overwrite all active loan progress to new random values.
        Returns number of updated rows.
        """
        cur = self.conn.cursor()
        if force:
            cur.execute("SELECT id FROM loans WHERE returned_on IS NULL")
        else:
            cur.execute("SELECT id FROM loans WHERE returned_on IS NULL AND (progress IS NULL OR progress=0)")
        ids = [r["id"] for r in cur.fetchall()]
        for loan_id in ids:
            newp = random.randint(0, 100)
            cur.execute("UPDATE loans SET progress=? WHERE id=?", (newp, loan_id))
        self.conn.commit()
        return len(ids)

    def randomize_time_for_active_loans(self, force=False):
        """
        Set a new random time_spent_minutes for all active (not returned) loans.
        If force==False only fill loans with time_spent_minutes IS NULL or =0.
        If force==True overwrite all active loan time to new random values.
        Returns number of updated rows.
        """
        cur = self.conn.cursor()
        if force:
            cur.execute("SELECT id FROM loans WHERE returned_on IS NULL")
        else:
            cur.execute("SELECT id FROM loans WHERE returned_on IS NULL AND (time_spent_minutes IS NULL OR time_spent_minutes=0)")
        ids = [r["id"] for r in cur.fetchall()]
        for loan_id in ids:
            new_minutes = random.randint(5, 600)
            cur.execute("UPDATE loans SET time_spent_minutes=? WHERE id=?", (new_minutes, loan_id))
        self.conn.commit()
        return len(ids)

    def _fill_missing_progress_with_random(self):
        self.randomize_progress_for_active_loans(force=False)

    def _fill_missing_time_with_random(self):
        self.randomize_time_for_active_loans(force=False)

    def get_currently_borrowed(self):
        cur = self.conn.cursor()
        cur.execute("""
        SELECT l.id AS loan_id, b.id AS book_id, b.title, p.id AS person_id, p.name, l.borrowed_on, l.due_on, l.progress, l.time_spent_minutes
        FROM loans l
        JOIN books b ON l.book_id=b.id
        JOIN persons p ON l.person_id=p.id
        WHERE l.returned_on IS NULL
        ORDER BY l.id ASC
        """)
        return cur.fetchall()

    def get_overdue_report(self):
        cur = self.conn.cursor()
        today = date.today().isoformat()
        cur.execute("""
        SELECT l.id AS loan_id, b.title, p.name, l.borrowed_on, l.due_on, l.progress, l.time_spent_minutes
        FROM loans l
        JOIN books b ON l.book_id=b.id
        JOIN persons p ON l.person_id=p.id
        WHERE l.returned_on IS NULL AND l.due_on < ?
        ORDER BY l.due_on ASC
        """, (today,))
        return cur.fetchall()

    def search_books(self, text):
        cur = self.conn.cursor()
        like = f"%{text}%"
        cur.execute("SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? ORDER BY title",
                    (like, like, like))
        return cur.fetchall()

    def get_book_history(self, book_id):
        cur = self.conn.cursor()
        cur.execute("""
        SELECT l.id AS loan_id, p.name AS person, l.borrowed_on, l.due_on, l.returned_on, l.progress, l.time_spent_minutes
        FROM loans l
        JOIN persons p ON l.person_id=p.id
        WHERE l.book_id=?
        ORDER BY l.borrowed_on DESC
        """, (book_id,))
        return cur.fetchall()

    def get_person_history(self, person_id):
        cur = self.conn.cursor()
        cur.execute("""
        SELECT l.id AS loan_id, b.title AS book, l.borrowed_on, l.due_on, l.returned_on, l.progress, l.time_spent_minutes
        FROM loans l
        JOIN books b ON l.book_id=b.id
        WHERE l.person_id=?
        ORDER BY l.borrowed_on DESC
        """, (person_id,))
        return cur.fetchall()

# --------------------------
# BookViewer - Animated Book Detail Window
# --------------------------
class BookViewer:
    """
    Displays an animated book detail view with:
    - 3D book cover visualization
    - Circular and linear progress indicators
    - Page counter estimation
    - Time spent reading
    - Borrowing history
    - Quick action buttons
    """
    def __init__(self, parent, book_id, db):
        self.parent = parent
        self.book_id = book_id
        self.db = db
        self.window = tk.Toplevel(parent)
        self.window.title("Book Details")
        self.window.configure(bg="#FFF8DC")  # Light cream background
        self.window.geometry("800x600")
        
        # Animation variables
        self.animation_step = 0
        self.animation_max_steps = 15
        
        # Fetch book data
        self.book_data = self._fetch_book_data()
        if not self.book_data:
            messagebox.showerror("Error", "Book not found")
            self.window.destroy()
            return
        
        # Fetch active loan data for progress tracking
        self.loan_data = self._fetch_active_loan_data()
        
        # Setup UI
        self._setup_ui()
        
        # Start opening animation
        self.animate_open()
    
    def _fetch_book_data(self):
        """Fetch book information from database"""
        try:
            cur = self.db.conn.cursor()
            cur.execute("SELECT * FROM books WHERE id=?", (self.book_id,))
            return cur.fetchone()
        except Exception as e:
            print(f"Error fetching book: {e}")
            return None
    
    def _fetch_active_loan_data(self):
        """Fetch active loan data for this book (if any)"""
        try:
            cur = self.db.conn.cursor()
            cur.execute("""
                SELECT l.*, p.name as person_name
                FROM loans l
                JOIN persons p ON l.person_id = p.id
                WHERE l.book_id=? AND l.returned_on IS NULL
                ORDER BY l.borrowed_on DESC
                LIMIT 1
            """, (self.book_id,))
            return cur.fetchone()
        except Exception:
            return None
    
    def _setup_ui(self):
        """Setup the main UI layout"""
        # Main container with padding
        main_frame = tk.Frame(self.window, bg="#FFF8DC")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Top section: Book cover and info side by side
        top_frame = tk.Frame(main_frame, bg="#FFF8DC")
        top_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left: Book cover canvas
        self.cover_frame = tk.Frame(top_frame, bg="#FFF8DC")
        self.cover_frame.pack(side=tk.LEFT, padx=10)
        
        self.cover_canvas = tk.Canvas(self.cover_frame, width=250, height=350, bg="#FFF8DC", highlightthickness=0)
        self.cover_canvas.pack()
        
        # Right: Book information and progress
        info_frame = tk.Frame(top_frame, bg="#FFF8DC")
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        # Book title
        title_label = tk.Label(info_frame, text=self.book_data["title"], 
                              font=("Segoe UI", 18, "bold"), bg="#FFF8DC", fg="#2C3E50")
        title_label.pack(anchor="w", pady=(0, 5))
        
        # Author
        author_label = tk.Label(info_frame, text=f"by {self.book_data['author']}", 
                               font=("Segoe UI", 12, "italic"), bg="#FFF8DC", fg="#555")
        author_label.pack(anchor="w", pady=(0, 10))
        
        # ISBN
        isbn_label = tk.Label(info_frame, text=f"ISBN: {self.book_data['isbn'] or 'N/A'}", 
                             font=("Segoe UI", 10), bg="#FFF8DC", fg="#555")
        isbn_label.pack(anchor="w", pady=2)
        
        # Total copies and availability
        available = self.db.available_copies(self.book_id)
        total = self.book_data["total_copies"]
        avail_text = f"Copies: {total} total, {available} available"
        avail_color = "#27AE60" if available > 0 else "#E74C3C"
        avail_label = tk.Label(info_frame, text=avail_text, 
                              font=("Segoe UI", 10, "bold"), bg="#FFF8DC", fg=avail_color)
        avail_label.pack(anchor="w", pady=2)
        
        # Progress section (only if there's an active loan)
        if self.loan_data:
            progress_frame = tk.Frame(info_frame, bg="#FFF8DC")
            progress_frame.pack(fill=tk.BOTH, expand=True, pady=20)
            
            # Reading Progress header
            tk.Label(progress_frame, text="📖 Reading Progress", 
                    font=("Segoe UI", 14, "bold"), bg="#FFF8DC", fg="#2C3E50").pack(anchor="w", pady=(0, 10))
            
            # Progress indicators container
            indicators_frame = tk.Frame(progress_frame, bg="#FFF8DC")
            indicators_frame.pack(fill=tk.BOTH, expand=True)
            
            # Left: Circular progress
            circular_frame = tk.Frame(indicators_frame, bg="#FFF8DC")
            circular_frame.pack(side=tk.LEFT, padx=(0, 20))
            
            self.circular_canvas = tk.Canvas(circular_frame, width=120, height=120, bg="#FFF8DC", highlightthickness=0)
            self.circular_canvas.pack()
            
            # Right: Details (linear bar, page counter, time)
            details_frame = tk.Frame(indicators_frame, bg="#FFF8DC")
            details_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Linear progress bar
            self.linear_frame = tk.Frame(details_frame, bg="#FFF8DC")
            self.linear_frame.pack(fill=tk.X, pady=5)
            
            # Page counter
            self.page_label = tk.Label(details_frame, text="", 
                                       font=("Segoe UI", 11), bg="#FFF8DC", fg="#2C3E50")
            self.page_label.pack(anchor="w", pady=5)
            
            # Time spent
            self.time_label = tk.Label(details_frame, text="", 
                                      font=("Segoe UI", 11), bg="#FFF8DC", fg="#2C3E50")
            self.time_label.pack(anchor="w", pady=5)
            
            # Current reader info
            reader_text = f"Currently reading by: {self.loan_data['person_name']}"
            tk.Label(details_frame, text=reader_text, 
                    font=("Segoe UI", 9, "italic"), bg="#FFF8DC", fg="#7F8C8D").pack(anchor="w", pady=5)
        
        # Bottom section: History and actions
        bottom_frame = tk.Frame(main_frame, bg="#FFF8DC")
        bottom_frame.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        
        # History label
        tk.Label(bottom_frame, text="📚 Borrowing History", 
                font=("Segoe UI", 12, "bold"), bg="#FFF8DC", fg="#2C3E50").pack(anchor="w", pady=(0, 5))
        
        # History treeview
        history_tree = ttk.Treeview(bottom_frame, 
                                    columns=("person", "borrowed", "returned", "progress"), 
                                    show="headings", height=5)
        history_tree.heading("person", text="Reader")
        history_tree.heading("borrowed", text="Borrowed")
        history_tree.heading("returned", text="Returned")
        history_tree.heading("progress", text="Progress")
        history_tree.column("person", width=200)
        history_tree.column("borrowed", width=100)
        history_tree.column("returned", width=100)
        history_tree.column("progress", width=100)
        history_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Populate history
        history = self.db.get_book_history(self.book_id)
        for h in history[:10]:  # Show last 10 entries
            progress_text = f"{h['progress']}%" if h['progress'] else "N/A"
            returned = h['returned_on'] if h['returned_on'] else "Active"
            history_tree.insert("", "end", values=(h["person"], h["borrowed_on"], returned, progress_text))
        
        # Action buttons
        button_frame = tk.Frame(main_frame, bg="#FFF8DC")
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        style = ttk.Style()
        style.configure("Action.TButton", font=("Segoe UI", 10), padding=8)
        
        ttk.Button(button_frame, text="Close", command=self.animate_close, style="Action.TButton").pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="View Full History", command=self._show_full_history, style="Action.TButton").pack(side=tk.RIGHT, padx=5)
    
    def animate_open(self):
        """Smooth opening animation with scaling effect"""
        if self.animation_step < self.animation_max_steps:
            self.animation_step += 1
            progress = self.animation_step / self.animation_max_steps
            
            # Ease-out effect
            eased_progress = 1 - math.pow(1 - progress, 3)
            
            # Scale window
            scale = 0.7 + (0.3 * eased_progress)
            alpha = eased_progress
            
            # Draw book cover with animation
            self.draw_book_cover(scale)
            
            # Draw progress indicators if loan exists
            if self.loan_data:
                self.draw_circular_progress(eased_progress)
                self.draw_linear_progress(eased_progress)
                self.draw_page_counter()
                self.draw_time_display()
            
            # Continue animation
            self.window.after(20, self.animate_open)
        else:
            # Final draw
            self.draw_book_cover(1.0)
            if self.loan_data:
                self.draw_circular_progress(1.0)
                self.draw_linear_progress(1.0)
                self.draw_page_counter()
                self.draw_time_display()
    
    def draw_book_cover(self, scale=1.0):
        """Draw 3D-style book cover with shadows"""
        self.cover_canvas.delete("all")
        
        # Base dimensions
        width = 200 * scale
        height = 280 * scale
        x = (250 - width) / 2
        y = (350 - height) / 2
        
        # Shadow (offset)
        shadow_offset = 5
        self.cover_canvas.create_rectangle(
            x + shadow_offset, y + shadow_offset,
            x + width + shadow_offset, y + height + shadow_offset,
            fill="#999", outline=""
        )
        
        # Book cover (main)
        self.cover_canvas.create_rectangle(
            x, y, x + width, y + height,
            fill="#BC7325", outline="#8B5A2B", width=2
        )
        
        # Spine effect (left side)
        spine_width = 15 * scale
        self.cover_canvas.create_rectangle(
            x, y, x + spine_width, y + height,
            fill="#8B5A2B", outline=""
        )
        
        # Title on cover (scaled)
        title = self.book_data["title"]
        if len(title) > 25:
            title = title[:25] + "..."
        
        font_size = int(14 * scale)
        if font_size < 8:
            font_size = 8
            
        self.cover_canvas.create_text(
            x + width/2, y + height/3,
            text=title,
            fill="white",
            font=("Segoe UI", font_size, "bold"),
            width=width - 30
        )
        
        # Author on cover
        author = self.book_data["author"] or ""
        if len(author) > 20:
            author = author[:20] + "..."
        
        author_font_size = int(10 * scale)
        if author_font_size < 7:
            author_font_size = 7
            
        self.cover_canvas.create_text(
            x + width/2, y + height - 30*scale,
            text=author,
            fill="white",
            font=("Segoe UI", author_font_size, "italic")
        )
        
        # Decorative lines
        line_y = y + height/2
        self.cover_canvas.create_line(
            x + 20*scale, line_y, x + width - 20*scale, line_y,
            fill="#D4A574", width=int(2*scale)
        )
    
    def draw_circular_progress(self, animation_progress=1.0):
        """Draw circular progress indicator with color coding"""
        self.circular_canvas.delete("all")
        
        progress = self.loan_data["progress"] if self.loan_data else 0
        
        # Determine color based on progress
        if progress < 34:
            color = "#E74C3C"  # Red
        elif progress < 67:
            color = "#F39C12"  # Yellow
        else:
            color = "#27AE60"  # Green
        
        # Circle dimensions
        center_x, center_y = 60, 60
        radius = 45
        
        # Background circle
        self.circular_canvas.create_oval(
            center_x - radius, center_y - radius,
            center_x + radius, center_y + radius,
            outline="#E0E0E0", width=8, fill="#FFF8DC"
        )
        
        # Progress arc (animated)
        extent = -(progress * 3.6 * animation_progress)  # Negative for clockwise
        if abs(extent) > 1:
            self.circular_canvas.create_arc(
                center_x - radius, center_y - radius,
                center_x + radius, center_y + radius,
                start=90, extent=extent,
                outline=color, width=8, style=tk.ARC
            )
        
        # Percentage text in center
        self.circular_canvas.create_text(
            center_x, center_y,
            text=f"{int(progress * animation_progress)}%",
            font=("Segoe UI", 20, "bold"),
            fill=color
        )
    
    def draw_linear_progress(self, animation_progress=1.0):
        """Draw linear progress bar"""
        # Clear previous widgets
        for widget in self.linear_frame.winfo_children():
            widget.destroy()
        
        progress = self.loan_data["progress"] if self.loan_data else 0
        
        # Determine color
        if progress < 34:
            color = "#E74C3C"
        elif progress < 67:
            color = "#F39C12"
        else:
            color = "#27AE60"
        
        # Container frame
        bar_bg = tk.Frame(self.linear_frame, bg="#E0E0E0", height=20)
        bar_bg.pack(fill=tk.X)
        
        # Progress fill
        fill_width = progress * animation_progress
        if fill_width > 0:
            bar_fill = tk.Frame(bar_bg, bg=color, height=20)
            bar_fill.place(relwidth=fill_width/100, relheight=1.0)
        
        # Percentage label
        tk.Label(self.linear_frame, text=f"Progress: {int(progress * animation_progress)}%",
                font=("Segoe UI", 9), bg="#FFF8DC", fg="#555").pack(anchor="w", pady=2)
    
    def draw_page_counter(self):
        """Display estimated page counter"""
        if not self.loan_data:
            return
        
        progress = self.loan_data["progress"]
        total_pages = 400  # Average book length
        current_page = int(total_pages * progress / 100)
        
        page_text = f"📄 Page {current_page} of {total_pages}"
        self.page_label.config(text=page_text)
    
    def draw_time_display(self):
        """Display time spent reading"""
        if not self.loan_data:
            return
        
        minutes = self.loan_data["time_spent_minutes"] or 0
        
        if minutes < 60:
            time_text = f"⏱️ Time spent: {minutes}m"
        else:
            hours = minutes // 60
            mins = minutes % 60
            if mins == 0:
                time_text = f"⏱️ Time spent: {hours}h"
            else:
                time_text = f"⏱️ Time spent: {hours}h {mins}m"
        
        self.time_label.config(text=time_text)
    
    def animate_close(self):
        """Smooth closing animation"""
        # Simple fade/scale out
        self.window.destroy()
    
    def _show_full_history(self):
        """Show full borrowing history in a new window"""
        history_window = tk.Toplevel(self.window)
        history_window.title(f"Full History - {self.book_data['title']}")
        history_window.geometry("700x400")
        
        tree = ttk.Treeview(history_window,
                           columns=("person", "borrowed", "due", "returned", "progress", "time"),
                           show="headings")
        tree.heading("person", text="Reader")
        tree.heading("borrowed", text="Borrowed")
        tree.heading("due", text="Due Date")
        tree.heading("returned", text="Returned")
        tree.heading("progress", text="Progress")
        tree.heading("time", text="Time Spent")
        
        tree.column("person", width=150)
        tree.column("borrowed", width=90)
        tree.column("due", width=90)
        tree.column("returned", width=90)
        tree.column("progress", width=80)
        tree.column("time", width=100)
        
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        history = self.db.get_book_history(self.book_id)
        for h in history:
            progress_text = f"{h['progress']}%" if h['progress'] else "N/A"
            returned = h['returned_on'] if h['returned_on'] else "Active"
            
            minutes = h['time_spent_minutes'] or 0
            if minutes < 60:
                time_text = f"{minutes}m"
            else:
                hours = minutes // 60
                mins = minutes % 60
                time_text = f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
            
            tree.insert("", "end", values=(
                h["person"], h["borrowed_on"], h["due_on"], 
                returned, progress_text, time_text
            ))
        
        ttk.Button(history_window, text="Close", command=history_window.destroy).pack(pady=10)

# --------------------------
# GUI - Tkinter
# --------------------------
class LibraryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Library Shelf - Biblioteca Modernă")
        self.root.configure(bg="#BC7325")
        # display mode: 'percent' or 'time'
        self.show_mode_var = tk.StringVar(value="percent")

        self.set_app_icon()
        self.create_menu()

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background="#BC7325")
        style.configure('TLabel', background="#BC7325", foreground="#FFFFFF", font=("Segoe UI", 12))
        style.configure('TButton', font=('Arial', 10), padding=5, background="#FFFFFF")
        style.configure('Treeview', background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#000000")

        self.db = LibraryDB()
        # Force random values on startup: ensures every active loan shows a random stored percent/time
        self.db.randomize_progress_for_active_loans(force=True)
        self.db.randomize_time_for_active_loans(force=True)

        self.status_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.person_search_var = tk.StringVar()
        self.loan_search_var = tk.StringVar()

        self._setup_ui()
        
        # Bind double-click on books to open BookViewer
        self.books_tree.bind('<Double-Button-1>', self.on_book_double_click)
        
        self.refresh_books()
        self.refresh_persons()
        self.refresh_loans()
        self.set_status("Bine ați venit!")

        self.subs_tree = None
        self.subs_window = None

    def set_app_icon(self):
        try:
            self.root.iconbitmap("bookshelf.ico")
        except Exception:
            pass

    def create_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        # display mode radio buttons
        view_menu.add_radiobutton(label="Afișează: Procent", variable=self.show_mode_var, value="percent", command=self.refresh_loans)
        view_menu.add_radiobutton(label="Afișează: Timp petrecut", variable=self.show_mode_var, value="time", command=self.refresh_loans)
        view_menu.add_separator()
        view_menu.add_command(label="Randomizează progres (active)", command=self.randomize_progress_dialog)
        view_menu.add_command(label="Randomizează timp (active)", command=self.randomize_time_dialog)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def show_about(self):
        messagebox.showinfo("About", "Library Shelf\nv1.0\nMade with Tkinter\nCopilot Modern GUI Example")

    def _setup_ui(self):
        # Left / Right panes
        self.frame_left = ttk.Frame(self.root)
        self.frame_left.grid(row=0, column=0, sticky="nsew")
        self.frame_right = ttk.Frame(self.root)
        self.frame_right.grid(row=0, column=1, sticky="nsew")
        self.root.columnconfigure(0, weight=2)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Books area
        ttk.Label(self.frame_left, text="Cărți", style="TLabel").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(self.frame_left, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")
        self.frame_left.columnconfigure(1, weight=1)
        self.search_var.trace_add('write', lambda *_: self.refresh_books(self.db.search_books(self.search_var.get())))

        self.books_tree = ttk.Treeview(self.frame_left, columns=("id","title","author","isbn","copies"), show="headings", height=12)
        for col,txt in [("id","ID"),("title","Titlu"),("author","Autor"),("isbn","ISBN"),("copies","Copii")]:
            self.books_tree.heading(col, text=txt)
            self.books_tree.column(col, width=100 if col=="id" else 180, anchor="w")
        self.books_tree.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=4)
        self.frame_left.rowconfigure(1, weight=1)
        b_scroll = ttk.Scrollbar(self.frame_left, orient="vertical", command=self.books_tree.yview)
        self.books_tree.configure(yscroll=b_scroll.set)
        b_scroll.grid(row=1, column=2, sticky="ns")

        bframe = ttk.Frame(self.frame_left)
        bframe.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(bframe, text="Adaugă carte", command=self.add_book_dialog).grid(row=0, column=0, padx=2)
        ttk.Button(bframe, text="Editează carte", command=self.edit_book_dialog).grid(row=0, column=1, padx=2)
        ttk.Button(bframe, text="Șterge carte", command=self.delete_book_dialog).grid(row=0, column=2, padx=2)
        ttk.Button(bframe, text="Istoric carte", command=self.book_history_dialog).grid(row=0, column=3, padx=2)

        # Persons + Loans area
        ttk.Label(self.frame_right, text="Persoane", style="TLabel").grid(row=0, column=0, sticky="w")
        person_search_entry = ttk.Entry(self.frame_right, textvariable=self.person_search_var)
        person_search_entry.grid(row=0, column=1, sticky="ew")
        self.frame_right.columnconfigure(1, weight=1)
        self.person_search_var.trace_add('write', lambda *_: self.refresh_persons())

        self.persons_tree = ttk.Treeview(self.frame_right, columns=("id","name","email","phone","address"), show="headings", height=12)
        for col,txt in [("id","ID"),("name","Nume"),("email","Email"),("phone","Telefon"),("address","Adresă")]:
            self.persons_tree.heading(col, text=txt)
            self.persons_tree.column(col, width=100 if col=="id" else 160, anchor="w")
        self.persons_tree.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=4)
        self.frame_right.rowconfigure(1, weight=1)
        p_scroll = ttk.Scrollbar(self.frame_right, orient="vertical", command=self.persons_tree.yview)
        self.persons_tree.configure(yscroll=p_scroll.set)
        p_scroll.grid(row=1, column=2, sticky="ns")

        pframe = ttk.Frame(self.frame_right)
        pframe.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(pframe, text="Adaugă persoană", command=self.add_person_dialog).grid(row=0, column=0, padx=2)
        ttk.Button(pframe, text="Editează persoană", command=self.edit_person_dialog).grid(row=0, column=1, padx=2)
        ttk.Button(pframe, text="Șterge persoană", command=self.delete_person_dialog).grid(row=0, column=2, padx=2)
        ttk.Button(pframe, text="Istoric persoană", command=self.person_history_dialog).grid(row=0, column=3, padx=2)
        ttk.Button(pframe, text="Abonamente active", command=self.subscriptions_dialog).grid(row=0, column=4, padx=2)

        ttk.Label(self.frame_right, text="Împrumuturi curente", style="TLabel").grid(row=3, column=0, sticky="w")
        loan_search_entry = ttk.Entry(self.frame_right, textvariable=self.loan_search_var)
        loan_search_entry.grid(row=3, column=1, sticky="ew")
        self.loan_search_var.trace_add('write', lambda *_: self.refresh_loans())

        self.loans_tree = ttk.Treeview(self.frame_right, columns=("loan_id","book","person","due_on","progress_or_time"), show="headings", height=8)
        for col,txt in [("loan_id","ID împrumut"),("book","Carte"),("person","Persoană"),("due_on","Scadent"),("progress_or_time","Progres / Timp")]:
            self.loans_tree.heading(col, text=txt)
            if col == "loan_id":
                self.loans_tree.column(col, width=100, anchor="w")
            elif col == "progress_or_time":
                self.loans_tree.column(col, width=120, anchor="center")
            else:
                self.loans_tree.column(col, width=150, anchor="w")
        self.loans_tree.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=4)
        self.frame_right.rowconfigure(4, weight=1)
        l_scroll = ttk.Scrollbar(self.frame_right, orient="vertical", command=self.loans_tree.yview)
        self.loans_tree.configure(yscroll=l_scroll.set)
        l_scroll.grid(row=4, column=2, sticky="ns")

        loanframe = ttk.Frame(self.frame_right)
        loanframe.grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(loanframe, text="Împrumută", command=self.borrow_dialog).grid(row=0, column=0, padx=2)
        ttk.Button(loanframe, text="Returnează (selectează împrumut)", command=self.return_selected).grid(row=0, column=1, padx=2)
        ttk.Button(loanframe, text="Rapoarte întârziere", command=self.overdue_report_dialog).grid(row=0, column=3, padx=2)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief='sunken', anchor='w', style="TLabel")
        status_bar.grid(row=99, column=0, columnspan=2, sticky='ew')

    def set_status(self, msg):
        self.status_var.set(msg)

    # ------------------
    # Refresh UI
    # ------------------
    def _format_minutes(self, minutes):
        try:
            m = int(minutes) if minutes is not None else 0
        except Exception:
            m = 0
        if m < 60:
            return f"{m}m"
        h = m // 60
        rem = m % 60
        if rem == 0:
            return f"{h}h"
        return f"{h}h {rem}m"

    def refresh_books(self, rows=None):
        for i in self.books_tree.get_children():
            self.books_tree.delete(i)
        if rows is None:
            rows = self.db.list_books()
        for r in rows:
            self.books_tree.insert("", "end", values=(r["id"], r["title"], r["author"], r["isbn"], r["total_copies"]))
        self.set_status(f"{len(rows)} cărți afișate.")

    def refresh_persons(self):
        for i in self.persons_tree.get_children():
            self.persons_tree.delete(i)
        search = self.person_search_var.get().strip().lower()
        persons = self.db.list_persons()
        if search:
            filtered = []
            for p in persons:
                if (search in (p["name"] or "").lower()
                    or search in (p["email"] or "").lower()
                    or search in (p["phone"] or "").lower()
                    or search in (p["address"] or "").lower()
                    or search in (p["membership_id"] or "").lower()
                    or search in (p["notes"] or "").lower()
                    or search in (p["preferred_contact"] or "").lower()):
                    filtered.append(p)
            persons = filtered
        for p in persons:
            self.persons_tree.insert("", "end", values=(p["id"], p["name"], p["email"], p["phone"], p["address"]))
        self.set_status(f"{len(persons)} persoane afișate.")

    def refresh_loans(self):
        for i in self.loans_tree.get_children():
            self.loans_tree.delete(i)
        search = self.loan_search_var.get().strip()
        loans = self.db.get_currently_borrowed()
        if search:
            loans = [l for l in loans
                     if search.lower() in l["title"].lower()
                     or search.lower() in l["name"].lower()
                     or search.lower() in str(l["due_on"])]
        for l in loans:
            prog = l["progress"] if "progress" in l.keys() and l["progress"] is not None else 0
            time_min = l["time_spent_minutes"] if "time_spent_minutes" in l.keys() and l["time_spent_minutes"] is not None else 0
            if self.show_mode_var.get() == "time":
                progress_display = self._format_minutes(time_min)
            else:
                progress_display = f"{prog}%"
            self.loans_tree.insert("", "end", values=(l["loan_id"], l["title"], l["name"], l["due_on"], progress_display))
        self.set_status(f"{len(loans)} împrumuturi curente.")

    # ------------------
    # Dialogs / Actions
    # ------------------
    def add_book_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Adaugă carte")
        ttk.Label(dlg, text="Titlu", style="TLabel").grid(row=0, column=0, sticky="w")
        ent_title = ttk.Entry(dlg, width=50); ent_title.grid(row=0, column=1, pady=2)
        ttk.Label(dlg, text="Autor", style="TLabel").grid(row=1, column=0, sticky="w")
        ent_author = ttk.Entry(dlg, width=50); ent_author.grid(row=1, column=1, pady=2)
        ttk.Label(dlg, text="ISBN", style="TLabel").grid(row=2, column=0, sticky="w")
        ent_isbn = ttk.Entry(dlg, width=30); ent_isbn.grid(row=2, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="Copii", style="TLabel").grid(row=3, column=0, sticky="w")
        ent_copies = ttk.Entry(dlg, width=10); ent_copies.grid(row=3, column=1, pady=2, sticky="w")
        def ok():
            try:
                title = ent_title.get().strip()
                author = ent_author.get().strip()
                isbn = ent_isbn.get().strip() or None
                copies = int(ent_copies.get())
                if not title:
                    messagebox.showerror("Eroare", "Titlu obligatoriu")
                    return
                self.db.add_book(title, author, isbn, copies)
                dlg.destroy()
                self.refresh_books()
            except Exception as e:
                messagebox.showerror("Eroare", str(e))
        ttk.Button(dlg, text="Adaugă", command=ok).grid(row=4, column=0, pady=6)
        ttk.Button(dlg, text="Anulează", command=dlg.destroy).grid(row=4, column=1, pady=6)

    def edit_book_dialog(self):
        sel = self.books_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o carte pentru editare")
            return
        values = self.books_tree.item(sel[0])["values"]
        book_id, title, author, isbn, copies = values
        dlg = tk.Toplevel(self.root)
        dlg.title("Editează carte")
        ttk.Label(dlg, text="Titlu", style="TLabel").grid(row=0, column=0, sticky="w")
        ent_title = ttk.Entry(dlg, width=50); ent_title.insert(0, title); ent_title.grid(row=0, column=1, pady=2)
        ttk.Label(dlg, text="Autor", style="TLabel").grid(row=1, column=0, sticky="w")
        ent_author = ttk.Entry(dlg, width=50); ent_author.insert(0, author); ent_author.grid(row=1, column=1, pady=2)
        ttk.Label(dlg, text="ISBN", style="TLabel").grid(row=2, column=0, sticky="w")
        ent_isbn = ttk.Entry(dlg, width=30); ent_isbn.insert(0, isbn); ent_isbn.grid(row=2, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="Copii", style="TLabel").grid(row=3, column=0, sticky="w")
        ent_copies = ttk.Entry(dlg, width=10); ent_copies.insert(0, copies); ent_copies.grid(row=3, column=1, pady=2, sticky="w")
        def ok():
            try:
                self.db.edit_book(book_id,
                    ent_title.get().strip(),
                    ent_author.get().strip(),
                    ent_isbn.get().strip(),
                    int(ent_copies.get())
                )
                dlg.destroy()
                self.refresh_books()
            except Exception as e:
                messagebox.showerror("Eroare", str(e))
        ttk.Button(dlg, text="Salvează", command=ok).grid(row=4, column=0, pady=6)
        ttk.Button(dlg, text="Anulează", command=dlg.destroy).grid(row=4, column=1, pady=6)

    def delete_book_dialog(self):
        sel = self.books_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o carte pentru ștergere")
            return
        book_id = self.books_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirmare", "Sigur doriți să ștergeți cartea?"):
            try:
                self.db.delete_book(book_id)
                self.refresh_books()
            except Exception as e:
                messagebox.showerror("Eroare", str(e))

    def book_history_dialog(self):
        sel = self.books_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o carte pentru istoric")
            return
        book_id = self.books_tree.item(sel[0])["values"][0]
        rows = self.db.get_book_history(book_id)
        dlg = tk.Toplevel(self.root)
        dlg.title("Istoric carte")
        tree = ttk.Treeview(dlg, columns=("loan_id","person","borrowed_on","due_on","returned_on","progress_or_time"), show="headings")
        for col,txt in [("loan_id","ID"),("person","Persoană"),("borrowed_on","Împrumutat"),("due_on","Scadent"),("returned_on","Returnat"),("progress_or_time","Progres / Timp")]:
            tree.heading(col, text=txt); tree.column(col, anchor="w", width=120 if col=="loan_id" else 150)
        for r in rows:
            prog = r["progress"] if "progress" in r.keys() and r["progress"] is not None else 0
            time_min = r["time_spent_minutes"] if "time_spent_minutes" in r.keys() and r["time_spent_minutes"] is not None else 0
            display = f"{prog}%" if self.show_mode_var.get()=="percent" else self._format_minutes(time_min)
            tree.insert("", "end", values=(r["loan_id"], r["person"], r["borrowed_on"], r["due_on"], r["returned_on"], display))
        tree.pack(fill="both", expand=True)
        ttk.Button(dlg, text="Închide", command=dlg.destroy).pack(pady=4)

    def add_person_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Adaugă persoană")
        ttk.Label(dlg, text="Nume", style="TLabel").grid(row=0, column=0, sticky="w")
        ent_name = ttk.Entry(dlg, width=40); ent_name.grid(row=0, column=1, pady=2)
        ttk.Label(dlg, text="Email", style="TLabel").grid(row=1, column=0, sticky="w")
        ent_email = ttk.Entry(dlg, width=40); ent_email.grid(row=1, column=1, pady=2)
        ttk.Label(dlg, text="Telefon", style="TLabel").grid(row=2, column=0, sticky="w")
        ent_phone = ttk.Entry(dlg, width=30); ent_phone.grid(row=2, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="Adresă", style="TLabel").grid(row=3, column=0, sticky="w")
        ent_address = ttk.Entry(dlg, width=50); ent_address.grid(row=3, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="ID membru", style="TLabel").grid(row=4, column=0, sticky="w")
        ent_membership = ttk.Entry(dlg, width=30); ent_membership.grid(row=4, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="Data nașterii (YYYY-MM-DD)", style="TLabel").grid(row=5, column=0, sticky="w")
        ent_dob = ttk.Entry(dlg, width=20); ent_dob.grid(row=5, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="Preferat contact", style="TLabel").grid(row=6, column=0, sticky="w")
        ent_pref = ttk.Entry(dlg, width=20); ent_pref.grid(row=6, column=1, pady=2, sticky="w")
        ttk.Label(dlg, text="Note", style="TLabel").grid(row=7, column=0, sticky="w")
        ent_notes = ttk.Entry(dlg, width=60); ent_notes.grid(row=7, column=1, pady=2, sticky="w")

        def ok():
            try:
                name = ent_name.get().strip()
                if not name:
                    messagebox.showerror("Eroare", "Nume obligatoriu")
                    return
                email = ent_email.get().strip() or None
                phone = ent_phone.get().strip() or None
                address = ent_address.get().strip() or None
                membership = ent_membership.get().strip() or None
                dob = ent_dob.get().strip() or None
                pref = ent_pref.get().strip() or None
                notes = ent_notes.get().strip() or None
                self.db.add_person(name, email=email, phone=phone, address=address,
                                   membership_id=membership, date_of_birth=dob,
                                   preferred_contact=pref, notes=notes)
                dlg.destroy()
                self.db._ensure_ids_range_for_persons(DEFAULT_ID_TARGET)
                self.db._ensure_min_books_equal_persons()
                self.db._seed_loans(min_loans=20, max_loans=50)
                cur = self.db.conn.cursor()
                cur.execute("SELECT COUNT(*) AS cnt FROM loans WHERE returned_on IS NULL")
                active_loans = cur.fetchone()["cnt"] or 0
                if active_loans > 0:
                    self.db._ensure_ids_range_for_loans(active_loans)
                self.refresh_persons()
                self.refresh_books()
                self.refresh_loans()
            except Exception as e:
                messagebox.showerror("Eroare", str(e))
        ttk.Button(dlg, text="Adaugă", command=ok).grid(row=8, column=0, pady=6)
        ttk.Button(dlg, text="Anulează", command=dlg.destroy).grid(row=8, column=1, pady=6)

    def edit_person_dialog(self):
        sel = self.persons_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o persoană pentru editare")
            return
        values = self.persons_tree.item(sel[0])["values"]
        person_id = values[0]
        persons = self.db.list_persons()
        person = None
        for p in persons:
            if p["id"] == person_id:
                person = p
                break
        if person is None:
            messagebox.showerror("Eroare", "Persoana nu a fost găsită")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Editează persoană")
        ttk.Label(dlg, text="Nume", style="TLabel").grid(row=0, column=0, sticky="w")
        ent_name = ttk.Entry(dlg, width=40); ent_name.grid(row=0, column=1, pady=2); ent_name.insert(0, person["name"] or "")
        ttk.Label(dlg, text="Email", style="TLabel").grid(row=1, column=0, sticky="w")
        ent_email = ttk.Entry(dlg, width=40); ent_email.grid(row=1, column=1, pady=2); ent_email.insert(0, person["email"] or "")
        ttk.Label(dlg, text="Telefon", style="TLabel").grid(row=2, column=0, sticky="w")
        ent_phone = ttk.Entry(dlg, width=30); ent_phone.grid(row=2, column=1, pady=2, sticky="w"); ent_phone.insert(0, person["phone"] or "")
        ttk.Label(dlg, text="Adresă", style="TLabel").grid(row=3, column=0, sticky="w")
        ent_address = ttk.Entry(dlg, width=50); ent_address.grid(row=3, column=1, pady=2, sticky="w"); ent_address.insert(0, person["address"] or "")
        ttk.Label(dlg, text="ID membru", style="TLabel").grid(row=4, column=0, sticky="w")
        ent_membership = ttk.Entry(dlg, width=30); ent_membership.grid(row=4, column=1, pady=2, sticky="w"); ent_membership.insert(0, person["membership_id"] or "")
        ttk.Label(dlg, text="Data nașterii (YYYY-MM-DD)", style="TLabel").grid(row=5, column=0, sticky="w")
        ent_dob = ttk.Entry(dlg, width=20); ent_dob.grid(row=5, column=1, pady=2, sticky="w"); ent_dob.insert(0, person["date_of_birth"] or "")
        ttk.Label(dlg, text="Preferat contact", style="TLabel").grid(row=6, column=0, sticky="w")
        ent_pref = ttk.Entry(dlg, width=20); ent_pref.grid(row=6, column=1, pady=2, sticky="w"); ent_pref.insert(0, person["preferred_contact"] or "")
        ttk.Label(dlg, text="Note", style="TLabel").grid(row=7, column=0, sticky="w")
        ent_notes = ttk.Entry(dlg, width=60); ent_notes.grid(row=7, column=1, pady=2, sticky="w"); ent_notes.insert(0, person["notes"] or "")

        def ok():
            try:
                name = ent_name.get().strip()
                if not name:
                    messagebox.showerror("Eroare", "Nume obligatoriu")
                    return
                email = ent_email.get().strip() or None
                phone = ent_phone.get().strip() or None
                address = ent_address.get().strip() or None
                membership = ent_membership.get().strip() or None
                dob = ent_dob.get().strip() or None
                pref = ent_pref.get().strip() or None
                notes = ent_notes.get().strip() or None
                self.db.edit_person(person_id, name, email=email, phone=phone, address=address,
                                    membership_id=membership, date_of_birth=dob,
                                    preferred_contact=pref, notes=notes)
                dlg.destroy()
                self.refresh_persons()
            except Exception as e:
                messagebox.showerror("Eroare", str(e))
        ttk.Button(dlg, text="Salvează", command=ok).grid(row=8, column=0, pady=6)
        ttk.Button(dlg, text="Anulează", command=dlg.destroy).grid(row=8, column=1, pady=6)

    def delete_person_dialog(self):
        sel = self.persons_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o persoană pentru ștergere")
            return
        person_id = self.persons_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirmare", "Sigur doriți să ștergeți persoana?"):
            try:
                self.db.delete_person(person_id)
                self.refresh_persons()
            except Exception as e:
                messagebox.showerror("Eroare", str(e))

    def subscriptions_dialog(self):
        if hasattr(self, "subs_window") and self.subs_window and tk.Toplevel.winfo_exists(self.subs_window):
            self.subs_window.lift()
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Abonamente active")
        tree = ttk.Treeview(dlg, columns=("id", "name", "membership_id", "email", "phone"), show="headings", height=15)
        tree.heading("id", text="ID"); tree.column("id", width=60, anchor="w")
        tree.heading("name", text="Nume"); tree.column("name", width=200, anchor="w")
        tree.heading("membership_id", text="ID membru"); tree.column("membership_id", width=120, anchor="w")
        tree.heading("email", text="Email"); tree.column("email", width=200, anchor="w")
        tree.heading("phone", text="Telefon"); tree.column("phone", width=120, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        rows = self.db.list_subscribers()
        for p in rows:
            tree.insert("", "end", values=(p["id"], p["name"], p["membership_id"], p["email"], p["phone"]))
        ttk.Button(dlg, text="Închide", command=dlg.destroy).grid(row=1, column=0, pady=6)

    def borrow_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Împrumută carte")
        books = self.db.list_books()
        persons = self.db.list_persons()
        ttk.Label(dlg, text="Carte:", style="TLabel").grid(row=0, column=0)
        book_var = tk.StringVar()
        book_combo = ttk.Combobox(dlg, textvariable=book_var, width=40)
        book_combo['values'] = [f'{b["id"]}: {b["title"]} ({self.db.available_copies(b["id"])} disponibile)' for b in books]
        book_combo.grid(row=0, column=1)
        ttk.Label(dlg, text="Persoană:", style="TLabel").grid(row=1, column=0)
        person_var = tk.StringVar()
        person_combo = ttk.Combobox(dlg, textvariable=person_var, width=60)
        person_combo['values'] = [f'{p["id"]}: {p["name"]} ({p["phone"] or "—"}, {p["membership_id"] or "—"})' for p in persons]
        person_combo.grid(row=1, column=1)
        ttk.Label(dlg, text="Durata (zile):", style="TLabel").grid(row=2, column=0)
        days_var = tk.IntVar(value=14)
        ttk.Entry(dlg, textvariable=days_var, width=10).grid(row=2, column=1, sticky="w")
        def ok():
            try:
                if not book_var.get() or not person_var.get():
                    messagebox.showerror("Eroare", "Selectați carte și persoană")
                    return
                book_id = int(book_var.get().split(":")[0])
                person_id = int(person_var.get().split(":")[0])
                days = days_var.get()
                self.db.borrow_book(book_id, person_id, days)
                messagebox.showinfo("OK", "Împrumut înregistrat")
                self.refresh_loans()
                self.refresh_books()
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Eroare la împrumut", str(e))
        ttk.Button(dlg, text="Împrumută", command=ok).grid(row=3, column=0, columnspan=2)
        ttk.Button(dlg, text="Anulează", command=dlg.destroy).grid(row=4, column=0, columnspan=2)

    def return_selected(self):
        sel = self.loans_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează mai întâi un împrumut")
            return
        loan_id = self.loans_tree.item(sel[0])["values"][0]
        try:
            self.db.return_book(loan_id)
            messagebox.showinfo("OK", "Cartea a fost returnată")
            self.refresh_loans()
            self.refresh_books()
        except Exception as e:
            messagebox.showerror("Eroare", str(e))

    def update_progress_dialog(self):
        sel = self.loans_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează mai întâi un împrumut")
            return
        loan_id = self.loans_tree.item(sel[0])["values"][0]
        cur_val = None
        try:
            cur = self.db.conn.cursor()
            cur.execute("SELECT progress FROM loans WHERE id=?", (loan_id,))
            row = cur.fetchone()
            if row:
                cur_val = row["progress"]
        except Exception:
            cur_val = None
        answer = simpledialog.askinteger("Actualizează progres", "Introduceți progres (%) (0-100):", initialvalue=(cur_val if cur_val is not None else 0), minvalue=0, maxvalue=100, parent=self.root)
        if answer is None:
            return
        try:
            self.db.set_loan_progress(loan_id, answer)
            messagebox.showinfo("OK", "Progres actualizat")
            self.refresh_loans()
        except Exception as e:
            messagebox.showerror("Eroare", str(e))

    def update_time_dialog(self):
        sel = self.loans_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează mai întâi un împrumut")
            return
        loan_id = self.loans_tree.item(sel[0])["values"][0]
        cur_val = None
        try:
            cur = self.db.conn.cursor()
            cur.execute("SELECT time_spent_minutes FROM loans WHERE id=?", (loan_id,))
            row = cur.fetchone()
            if row:
                cur_val = row["time_spent_minutes"]
        except Exception:
            cur_val = None
        answer = simpledialog.askinteger("Actualizează timp (minute)", "Introduceți timpul petrecut în minute:", initialvalue=(cur_val if cur_val is not None else 0), minvalue=0, parent=self.root)
        if answer is None:
            return
        try:
            self.db.set_loan_time(loan_id, answer)
            messagebox.showinfo("OK", "Timp actualizat")
            self.refresh_loans()
        except Exception as e:
            messagebox.showerror("Eroare", str(e))

    def update_progress_or_time_dialog(self):
        # Call appropriate dialog depending on current display mode; user can still edit both separately if desired.
        if self.show_mode_var.get() == "time":
            self.update_time_dialog()
        else:
            self.update_progress_dialog()

    def randomize_progress_dialog(self):
        """
        Ask for confirmation and randomize progress for active loans.
        Called from View -> Randomizează progres (active).
        """
        try:
            if not messagebox.askyesno("Confirmare", "Doriți să atribuiți aleator un nou procent pentru toate împrumuturile active?"):
                return
            updated = self.db.randomize_progress_for_active_loans(force=True)
            messagebox.showinfo("OK", f"Actualizat progresul pentru {updated} împrumuturi active.")
            self.refresh_loans()
        except Exception as e:
            messagebox.showerror("Eroare", f"A apărut o eroare la randomizare: {e}")

    def randomize_time_dialog(self):
        """
        Ask for confirmation and randomize time_spent_minutes for active loans.
        """
        try:
            if not messagebox.askyesno("Confirmare", "Doriți să atribuiți aleator un nou timp (minute) pentru toate împrumuturile active?"):
                return
            updated = self.db.randomize_time_for_active_loans(force=True)
            messagebox.showinfo("OK", f"Actualizat timpul pentru {updated} împrumuturi active.")
            self.refresh_loans()
        except Exception as e:
            messagebox.showerror("Eroare", f"A apărut o eroare la randomizare timp: {e}")

    def overdue_report_dialog(self):
        rows = self.db.get_overdue_report()
        if not rows:
            messagebox.showinfo("Rapoarte întârziere", "Nicio întârziere")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Rapoarte întârziere")
        tree = ttk.Treeview(dlg, columns=("loan_id","title","person","due_on","progress_or_time"), show="headings")
        for col,txt in [("loan_id","ID"),("title","Carte"),("person","Persoană"),("due_on","Scadent"),("progress_or_time","Progres / Timp")]:
            tree.heading(col, text=txt); tree.column(col, anchor="w", width=120 if col=="loan_id" else 200)
        for r in rows:
            prog = r["progress"] if "progress" in r.keys() and r["progress"] is not None else 0
            time_min = r["time_spent_minutes"] if "time_spent_minutes" in r.keys() and r["time_spent_minutes"] is not None else 0
            display = f"{prog}%" if self.show_mode_var.get()=="percent" else self._format_minutes(time_min)
            tree.insert("", "end", values=(r["loan_id"], r["title"], r["name"], r["due_on"], display))
        tree.pack(fill="both", expand=True)
        ttk.Button(dlg, text="Închide", command=dlg.destroy).pack(pady=4)

    def book_history_dialog(self):
        sel = self.books_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o carte pentru istoric")
            return
        book_id = self.books_tree.item(sel[0])["values"][0]
        rows = self.db.get_book_history(book_id)
        dlg = tk.Toplevel(self.root)
        dlg.title("Istoric carte")
        tree = ttk.Treeview(dlg, columns=("loan_id","person","borrowed_on","due_on","returned_on","progress_or_time"), show="headings")
        for col,txt in [("loan_id","ID"),("person","Persoană"),("borrowed_on","Împrumutat"),("due_on","Scadent"),("returned_on","Returnat"),("progress_or_time","Progres / Timp")]:
            tree.heading(col, text=txt); tree.column(col, anchor="w", width=120 if col=="loan_id" else 150)
        for r in rows:
            prog = r["progress"] if "progress" in r.keys() and r["progress"] is not None else 0
            time_min = r["time_spent_minutes"] if "time_spent_minutes" in r.keys() and r["time_spent_minutes"] is not None else 0
            display = f"{prog}%" if self.show_mode_var.get()=="percent" else self._format_minutes(time_min)
            tree.insert("", "end", values=(r["loan_id"], r["person"], r["borrowed_on"], r["due_on"], r["returned_on"], display))
        tree.pack(fill="both", expand=True)
        ttk.Button(dlg, text="Închide", command=dlg.destroy).pack(pady=4)

    def person_history_dialog(self):
        sel = self.persons_tree.selection()
        if not sel:
            messagebox.showwarning("Atenție", "Selectează o persoană pentru istoric")
            return
        person_id = self.persons_tree.item(sel[0])["values"][0]
        rows = self.db.get_person_history(person_id)
        dlg = tk.Toplevel(self.root)
        dlg.title("Istoric persoană")
        tree = ttk.Treeview(dlg, columns=("loan_id","book","borrowed_on","due_on","returned_on","progress_or_time"), show="headings")
        for col,txt in [("loan_id","ID"),("book","Carte"),("borrowed_on","Împrumutat"),("due_on","Scadent"),("returned_on","Returnat"),("progress_or_time","Progres / Timp")]:
            tree.heading(col, text=txt); tree.column(col, anchor="w", width=120 if col=="loan_id" else 150)
        for r in rows:
            prog = r["progress"] if "progress" in r.keys() and r["progress"] is not None else 0
            time_min = r["time_spent_minutes"] if "time_spent_minutes" in r.keys() and r["time_spent_minutes"] is not None else 0
            display = f"{prog}%" if self.show_mode_var.get()=="percent" else self._format_minutes(time_min)
            tree.insert("", "end", values=(r["loan_id"], r["book"], r["borrowed_on"], r["due_on"], r["returned_on"], display))
        tree.pack(fill="both", expand=True)
        ttk.Button(dlg, text="Închide", command=dlg.destroy).pack(pady=4)
    
    def on_book_double_click(self, event):
        """Handle double-click on a book in the treeview to open BookViewer"""
        selection = self.books_tree.selection()
        if selection:
            book_id = self.books_tree.item(selection[0])["values"][0]
            BookViewer(self.root, book_id, self.db)

# --------------------------
# Run app
# --------------------------
def main():
    root = tk.Tk()
    app = LibraryGUI(root)
    root.geometry("1100x750")
    root.mainloop()

if __name__ == "__main__":
    main()
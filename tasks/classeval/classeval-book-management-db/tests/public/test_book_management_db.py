import unittest
import sqlite3
from book_management_db import BookManagementDB


class BookManagementDBTestCreateTable(unittest.TestCase):
    def setUp(self):
        self.db_name = "test.db"
        self.db = BookManagementDB(self.db_name)
        self.connection = sqlite3.connect(self.db_name)
        self.cursor = self.connection.cursor()

    def test_create_table_1(self):
        # Check if the table exists
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books'")
        result = self.cursor.fetchone()
        self.assertIsNotNone(result)

    def test_create_table_2(self):
        self.db.create_table()
        # Check if the table has the correct columns
        self.cursor.execute("PRAGMA table_info(books)")
        columns = self.cursor.fetchall()
        column_names = [column[1] for column in columns]
        expected_column_names = ['id', 'title', 'author', 'available']
        self.assertEqual(column_names, expected_column_names)

    def tearDown(self):
        self.db.connection.close()
        self.connection.close()
        # remove the test database file
        os.remove(self.db_name)

class BookManagementDBTestAddBook(unittest.TestCase):
    def setUp(self):
        self.db_name = "test.db"
        self.db = BookManagementDB(self.db_name)
        self.connection = sqlite3.connect(self.db_name)
        self.cursor = self.connection.cursor()

    def test_add_book(self):
        title = "Introduction to Python"
        author = "John Smith"
        self.db.add_book(title, author)

        # Check if the book was added correctly
        self.cursor.execute("SELECT title, author, available FROM books WHERE id=1")
        result = self.cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], title)
        self.assertEqual(result[1], author)
        self.assertEqual(result[2], 1)

    def tearDown(self):
        self.db.connection.close()
        self.connection.close()
        # remove the test database file
        os.remove(self.db_name)

class BookManagementDBTestRemoveBook(unittest.TestCase):
    def setUp(self):
        self.db_name = "test.db"
        self.db = BookManagementDB(self.db_name)
        self.connection = sqlite3.connect(self.db_name)
        self.cursor = self.connection.cursor()
        # Add a book for testing removal
        self.db.add_book("Book to Remove", "John Doe")

    def test_remove_book(self):
        self.db.remove_book(1)

        # Check if the book was removed correctly
        self.cursor.execute("SELECT * FROM books WHERE id=1")
        result = self.cursor.fetchone()
        self.assertIsNone(result)

    def tearDown(self):
        self.db.connection.close()
        self.connection.close()
        # remove the test database file
        os.remove(self.db_name)

class BookManagementDBTestBorrowBook(unittest.TestCase):
    def setUp(self):
        self.db_name = "test.db"
        self.db = BookManagementDB(self.db_name)
        self.connection = sqlite3.connect(self.db_name)
        self.cursor = self.connection.cursor()
        # Add a book for testing borrowing
        self.db.add_book("Book to Borrow", "Jane Smith")

    def test_borrow_book(self):
        self.db.borrow_book(1)

        # Check if the book was marked as unavailable
        self.cursor.execute("SELECT available FROM books WHERE id=1")
        result = self.cursor.fetchone()
        self.assertEqual(result[0], 0)

    def tearDown(self):
        self.db.connection.close()
        self.connection.close()
        # remove the test database file
        os.remove(self.db_name)

class BookManagementDBTestReturnBook(unittest.TestCase):
    def setUp(self):
        self.db_name = "test.db"
        self.db = BookManagementDB(self.db_name)
        self.connection = sqlite3.connect(self.db_name)
        self.cursor = self.connection.cursor()
        # Add a book for testing returning
        self.db.add_book("Book to Return", "James Smith")
        self.db.borrow_book(1)  # Mark the book as borrowed

    def test_return_book(self):
        self.db.return_book(1)

        # Check if the book was marked as available again
        self.cursor.execute("SELECT available FROM books WHERE id=1")
        result = self.cursor.fetchone()
        self.assertEqual(result[0], 1)

    def tearDown(self):
        self.db.connection.close()
        self.connection.close()
        # remove the test database file
        os.remove(self.db_name)

# test_app.py
import unittest
from unittest.mock import patch, MagicMock
import app


class TestApp(unittest.TestCase):

    @patch('app.get_db_connection')
    def test_get_db_connection_success(self, mock_conn):
        mock_conn.return_value = 'mock_connection'
        result = app.get_db_connection()
        self.assertEqual(result, 'mock_connection')

    @patch('app.psycopg2.connect', side_effect=Exception('Connection error'))
    def test_get_db_connection_failure(self, mock_connect):
        with self.assertRaises(SystemExit) as cm:
            app.get_db_connection()
        self.assertEqual(cm.exception.code, 1)

    @patch('app.get_db_connection')
    @patch('app.app.psycopg2.sql.SQL')
    def test_check_database_extension_exists(self, mock_sql, mock_conn):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = (1,)
        app.check_database_extension(conn)
        cursor.close.assert_called_once()

    @patch('app.get_db_connection')
    @patch('app.app.psycopg2.sql.SQL')
    def test_check_database_extension_not_exists(self, mock_sql, mock_conn):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = None
        with self.assertRaises(SystemExit) as cm:
            app.check_database_extension(conn)
        self.assertEqual(cm.exception.code, 1)
        cursor.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()
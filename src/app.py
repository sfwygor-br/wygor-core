# app.py
import sys
import requests
import psycopg2
from psycopg2 import sql


def get_db_connection():
    try:
        conn = psycopg2.connect(
            host='127.0.0.1',
            database='postgres',
            user='postgres',
            password='root'
        )
        return conn
    except Exception as e:
        print(f'Erro ao conectar ao banco de dados: {e}')
        sys.exit(1)

def check_database_extension(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'pgvector';")
        extension_exists = cur.fetchone()
        if not extension_exists:
            print('Extenso pgvector no est disponvel.')
            sys.exit(1)
    finally:
        cur.close()

def main():
    conn = get_db_connection()
    check_database_extension(conn)
    # Adicionar lgica de auto-healing e ingesto aqui
    conn.close()
    print('Anlise concluda com sucesso.')

if __name__ == '__main__':
    main()
from flask import Flask, jsonify
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv() # Load environment variables from a .env file (if you use one)

app = Flask(__name__)

# Database connection details from environment variables
DB_NAME = os.getenv('POSTGRES_DB', 'your_database_name')
DB_USER = os.getenv('POSTGRES_USER', 'your_username')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'your_password')
DB_HOST = os.getenv('DB_HOST', 'postgis_db') # 'postgis_db' is the service name in docker-compose
DB_PORT = os.getenv('DB_PORT', '5432')

@app.route('/')
def hello_world():
    return 'Hello from the Mapwork AI Backend!'

@app.route('/test-db')
def test_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({"message": "Successfully connected to database!", "version": db_version[0]})
    except Exception as e:
        return jsonify({"message": "Database connection failed", "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)